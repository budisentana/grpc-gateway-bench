// loadgen drives the gateway's public REST endpoint over TLS 1.3 / HTTP/1.1
// and writes one JSON result file per run, including the gateway and backend
// statistics collected over the same measurement window.
//
// Closed loop: -mode closed -c N  (N clients, each waits for its response).
// Open loop:   -mode open -rate R (requests scheduled at a fixed rate; latency
// is measured from the scheduled send time, which avoids coordinated omission).
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"runtime"
	"sync"
	"sync/atomic"
	"time"

	"qsbg/internal/stats"
	"qsbg/internal/tlsutil"
	"qsbg/internal/wire"
)

var (
	target     = flag.String("url", "https://127.0.0.1:8443/v1/submit", "gateway REST endpoint")
	serverName = flag.String("server-name", "localhost", "TLS server name")
	certDir    = flag.String("certs", "certs", "test PKI directory (for the CA)")
	kex        = flag.String("kex", "hybrid", "public TLS key exchange offered: hybrid|classical")
	mode       = flag.String("mode", "closed", "closed|open")
	conc       = flag.Int("c", 10, "closed loop: concurrent clients")
	rate       = flag.Float64("rate", 100, "open loop: requests per second")
	maxInFl    = flag.Int("max-inflight", 5000, "open loop: cap on outstanding requests (excess counted as dropped)")
	warmup     = flag.Duration("warmup", 10*time.Second, "warm-up period (not measured)")
	duration   = flag.Duration("duration", 60*time.Second, "measurement window")
	payloadSz  = flag.Int("payload", 128, "payload_vector size in bytes")
	gwAdmin    = flag.String("gateway-admin", "http://127.0.0.1:8901", "gateway admin URL ('' to skip)")
	beAdmin    = flag.String("backend-admin", "http://127.0.0.1:9901", "backend admin URL ('' to skip)")
	out        = flag.String("out", "", "write result JSON here (default stdout)")
	label      = flag.String("label", "", "free-text label stored in the result (e.g. network profile)")
	rep        = flag.Int("rep", 1, "repetition number stored in the result")
)

type result struct {
	Label          string           `json:"label"`
	Rep            int              `json:"rep"`
	Mode           string           `json:"mode"`
	Concurrency    int              `json:"concurrency,omitempty"`
	OfferedRate    float64          `json:"offered_rate,omitempty"`
	PayloadBytes   int              `json:"payload_bytes"`
	PublicKex      string           `json:"public_kex"`
	WarmupS        float64          `json:"warmup_s"`
	DurationS      float64          `json:"duration_s"`
	Started        string           `json:"started"`
	Completed      int64            `json:"completed_ok"`
	Errors         map[string]int64 `json:"errors"`
	Dropped        int64            `json:"dropped"`
	ThroughputRPS  float64          `json:"throughput_rps"`
	Latency        stats.Summary    `json:"latency"`
	ClientBytesOut int64            `json:"client_bytes_out"`
	ClientBytesIn  int64            `json:"client_bytes_in"`
	NewConnections int64            `json:"new_connections"`
	Host           map[string]any   `json:"host"`
	Gateway        map[string]any   `json:"gateway,omitempty"`
	Backend        map[string]any   `json:"backend,omitempty"`
}

var letters = []byte("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

func randomVector(n int) string {
	b := make([]byte, n)
	rand.Read(b)
	for i := range b {
		b[i] = letters[int(b[i])%len(letters)]
	}
	return string(b)
}

type runner struct {
	client    *http.Client
	vector    string
	txID      atomic.Int64
	measuring atomic.Bool
	hist      *stats.Histogram
	okCount   atomic.Int64
	dropped   atomic.Int64
	errMu     sync.Mutex
	errs      map[string]int64
}

func (r *runner) fail(kind string) {
	if !r.measuring.Load() {
		return
	}
	r.errMu.Lock()
	r.errs[kind]++
	r.errMu.Unlock()
}

// one sends a single request. `from` is when the request should have started.
func (r *runner) one(from time.Time) {
	p := wire.Payload{TransactionID: r.txID.Add(1), PayloadVector: r.vector, IngressEpochMs: time.Now().UnixMilli()}
	body, _ := json.Marshal(&p)
	resp, err := r.client.Post(*target, "application/json", bytes.NewReader(body))
	if err != nil {
		r.fail("transport")
		return
	}
	data, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	elapsed := time.Since(from)
	if err != nil {
		r.fail("read")
		return
	}
	if resp.StatusCode != http.StatusOK {
		var e struct {
			GrpcStatus int `json:"grpc_status"`
		}
		json.Unmarshal(data, &e)
		if e.GrpcStatus != 0 {
			r.fail("grpc_status_" + itoa(e.GrpcStatus))
		} else {
			r.fail("http_" + itoa(resp.StatusCode))
		}
		return
	}
	var echo wire.Payload
	if json.Unmarshal(data, &echo) != nil || echo.TransactionID != p.TransactionID || len(echo.PayloadVector) != len(p.PayloadVector) {
		r.fail("bad_echo")
		return
	}
	if r.measuring.Load() {
		r.hist.Record(elapsed)
		r.okCount.Add(1)
	}
}

func itoa(i int) string { return string(appendInt(nil, i)) }
func appendInt(b []byte, i int) []byte {
	if i < 0 {
		b = append(b, '-')
		i = -i
	}
	if i >= 10 {
		b = appendInt(b, i/10)
	}
	return append(b, byte('0'+i%10))
}

func adminCall(base, path string, into *map[string]any) {
	if base == "" {
		return
	}
	resp, err := http.Get(base + path)
	if err != nil {
		log.Printf("admin %s%s: %v", base, path, err)
		return
	}
	defer resp.Body.Close()
	if into != nil {
		json.NewDecoder(resp.Body).Decode(into)
	} else {
		io.Copy(io.Discard, resp.Body)
	}
}

func main() {
	flag.Parse()
	tlsCfg, err := tlsutil.ClientConfig(*certDir, *kex, *serverName, false, []string{"http/1.1"})
	if err != nil {
		log.Fatal(err)
	}
	var bytesCtr stats.Counter
	var newConns atomic.Int64
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	tr := &http.Transport{
		TLSClientConfig:     tlsCfg,
		TLSNextProto:        map[string]func(string, *tls.Conn) http.RoundTripper{}, // force HTTP/1.1
		MaxIdleConnsPerHost: 100000,
		IdleConnTimeout:     5 * time.Minute,
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			c, err := dialer.DialContext(ctx, network, addr)
			if err != nil {
				return nil, err
			}
			newConns.Add(1)
			return stats.WrapConn(c, &bytesCtr), nil
		},
	}
	r := &runner{
		client: &http.Client{Transport: tr, Timeout: 30 * time.Second},
		vector: randomVector(*payloadSz),
		hist:   stats.NewHistogram(),
		errs:   map[string]int64{},
	}

	stop := make(chan struct{})
	var wg sync.WaitGroup
	switch *mode {
	case "closed":
		for i := 0; i < *conc; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for {
					select {
					case <-stop:
						return
					default:
					}
					r.one(time.Now())
				}
			}()
		}
	case "open":
		sem := make(chan struct{}, *maxInFl)
		interval := time.Duration(float64(time.Second) / *rate)
		wg.Add(1)
		go func() {
			defer wg.Done()
			next := time.Now()
			for {
				select {
				case <-stop:
					return
				default:
				}
				now := time.Now()
				if now.Before(next) {
					time.Sleep(next.Sub(now))
				}
				scheduled := next
				next = next.Add(interval)
				select {
				case sem <- struct{}{}:
					wg.Add(1)
					go func() {
						defer wg.Done()
						r.one(scheduled)
						<-sem
					}()
				default:
					if r.measuring.Load() {
						r.dropped.Add(1)
					}
				}
			}
		}()
	default:
		log.Fatalf("unknown mode %q", *mode)
	}

	time.Sleep(*warmup)
	adminCall(*gwAdmin, "/reset", nil)
	adminCall(*beAdmin, "/reset", nil)
	bytesCtr.Reset()
	newConns.Store(0)
	started := time.Now()
	r.measuring.Store(true)
	time.Sleep(*duration)
	r.measuring.Store(false)
	measured := time.Since(started)

	res := result{
		Label: *label, Rep: *rep, Mode: *mode, PayloadBytes: *payloadSz, PublicKex: *kex,
		WarmupS: warmup.Seconds(), DurationS: measured.Seconds(), Started: started.UTC().Format(time.RFC3339),
		Completed: r.okCount.Load(), Dropped: r.dropped.Load(),
		Latency:        r.hist.Summary(),
		ClientBytesOut: bytesCtr.Written.Load(), ClientBytesIn: bytesCtr.Read.Load(),
		NewConnections: newConns.Load(),
		Host:           map[string]any{"num_cpu": runtime.NumCPU(), "go": runtime.Version(), "os": runtime.GOOS},
	}
	if *mode == "closed" {
		res.Concurrency = *conc
	} else {
		res.OfferedRate = *rate
	}
	res.ThroughputRPS = float64(res.Completed) / measured.Seconds()
	r.errMu.Lock()
	res.Errors = r.errs
	r.errMu.Unlock()
	adminCall(*gwAdmin, "/stats", &res.Gateway)
	adminCall(*beAdmin, "/stats", &res.Backend)

	close(stop)
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
	}

	enc, _ := json.MarshalIndent(res, "", "  ")
	if *out == "" {
		os.Stdout.Write(append(enc, '\n'))
	} else if err := os.WriteFile(*out, append(enc, '\n'), 0o644); err != nil {
		log.Fatal(err)
	}
	log.Printf("%s c=%d rate=%.0f payload=%d: %d ok, %.1f RPS, p50=%.2fms p99=%.2fms, errors=%v",
		*mode, *conc, *rate, *payloadSz, res.Completed, res.ThroughputRPS,
		res.Latency.P50Us/1000, res.Latency.P99Us/1000, res.Errors)
}
