// gateway terminates public REST/JSON over TLS 1.3 (HTTP/1.1), translates the
// request to Protobuf, applies the internal authentication of the selected
// configuration, and forwards it as a gRPC call over HTTP/2 + mutual TLS.
//
// Configurations (paper Table 3):
//
//	C0  classical mTLS (X25519 + ECDSA certs), no message signature
//	C1  hybrid PQ key exchange mTLS (X25519MLKEM768), no message signature
//	C2  as C0 + ML-DSA-65 signature per request in metadata
//	C3  as C0 + one ML-DSA-65 signature per Merkle batch
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/json"
	"errors"
	"flag"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"qsbg/internal/sig"
	"qsbg/internal/stats"
	"qsbg/internal/tlsutil"
	"qsbg/internal/wire"
)

var (
	listen      = flag.String("listen", "127.0.0.1:8443", "public REST listen address (TLS 1.3, HTTP/1.1)")
	admin       = flag.String("admin", "127.0.0.1:8901", "admin/stats listen address (plain HTTP)")
	backendAddr = flag.String("backend", "127.0.0.1:9443", "backend gRPC address")
	backendName = flag.String("backend-name", "localhost", "TLS server name of the backend")
	certDir     = flag.String("certs", "certs", "test PKI directory")
	config      = flag.String("config", "C0", "C0|C1|C2|C3")
	publicKex   = flag.String("public-kex", "hybrid", "public TLS key exchange: hybrid|classical")
	sigBackend  = flag.String("sig-backend", "", "ML-DSA backend (default: best compiled in)")
	pubKeyOut   = flag.String("pubkey-out", "gateway_mldsa65.pub", "where to write the gateway ML-DSA public key")
	batchWindow = flag.Duration("batch-window", 5*time.Millisecond, "C3: max time to collect a batch (T)")
	batchMax    = flag.Int("batch-max", 64, "C3: max requests per batch (B)")
	batchSig    = flag.String("batch-sig", "first", "C3: send root signature with 'first' request of each batch or with 'all'")
	padBytes    = flag.Int("pad-bytes", 0, "extra metadata bytes to simulate tracing/auth headers")
	signWorkers = flag.Int("sign-workers", 0, "C3: concurrent batch-signing goroutines (0 = GOMAXPROCS)")
)

// ---- statistics ----

type gwStats struct {
	parse, mapping, auth, forward, total *stats.Histogram
	metaBytesSum, metaBytesMax, metaN    atomic.Int64
	signatures, batches, batchedReqs     atomic.Int64
	requests, ok                         atomic.Int64
	errMu                                sync.Mutex
	errors                               map[string]int64
	public, internal                     stats.Counter
	cpuAtReset                           atomic.Value
}

func newStats() *gwStats {
	s := &gwStats{
		parse: stats.NewHistogram(), mapping: stats.NewHistogram(), auth: stats.NewHistogram(),
		forward: stats.NewHistogram(), total: stats.NewHistogram(), errors: map[string]int64{},
	}
	s.cpuAtReset.Store(stats.CPUSeconds())
	return s
}

func (s *gwStats) fail(kind string) {
	s.errMu.Lock()
	s.errors[kind]++
	s.errMu.Unlock()
}

func (s *gwStats) reset() {
	for _, h := range []*stats.Histogram{s.parse, s.mapping, s.auth, s.forward, s.total} {
		h.Reset()
	}
	for _, c := range []*atomic.Int64{&s.metaBytesSum, &s.metaBytesMax, &s.metaN, &s.signatures, &s.batches, &s.batchedReqs, &s.requests, &s.ok} {
		c.Store(0)
	}
	s.errMu.Lock()
	s.errors = map[string]int64{}
	s.errMu.Unlock()
	s.public.Reset()
	s.internal.Reset()
	s.cpuAtReset.Store(stats.CPUSeconds())
}

func (s *gwStats) recordMeta(n int) {
	s.metaBytesSum.Add(int64(n))
	s.metaN.Add(1)
	for {
		cur := s.metaBytesMax.Load()
		if int64(n) <= cur || s.metaBytesMax.CompareAndSwap(cur, int64(n)) {
			return
		}
	}
}

// ---- C3 batch signer ----

type batchItem struct {
	leaf  [32]byte
	reply chan batchProof
}

type batchProof struct {
	root [32]byte
	path [][32]byte
	idx  int
	n    int
	sig  []byte // nil unless this request carries the root signature
	err  error
}

type batcher struct {
	in     chan batchItem
	signer sig.Signer
	st     *gwStats
	sem    chan struct{}
}

func (b *batcher) run() {
	for {
		first := <-b.in
		items := []batchItem{first}
		timer := time.NewTimer(*batchWindow)
	collect:
		for len(items) < *batchMax {
			select {
			case it := <-b.in:
				items = append(items, it)
			case <-timer.C:
				break collect
			}
		}
		timer.Stop()
		b.sem <- struct{}{}
		go func(items []batchItem) {
			defer func() { <-b.sem }()
			leaves := make([][32]byte, len(items))
			for i, it := range items {
				leaves[i] = it.leaf
			}
			root, paths := wire.BuildTree(leaves)
			signature, err := b.signer.Sign(root[:], []byte(wire.CtxBatch))
			b.st.signatures.Add(1)
			b.st.batches.Add(1)
			b.st.batchedReqs.Add(int64(len(items)))
			for i, it := range items {
				p := batchProof{root: root, path: paths[i], idx: i, n: len(items), err: err}
				if i == 0 || *batchSig == "all" {
					p.sig = signature
				}
				it.reply <- p
			}
		}(items)
	}
}

// ---- gateway ----

type gateway struct {
	client  *http.Client
	signer  sig.Signer
	batch   *batcher
	st      *gwStats
	pad     string
	backend string
}

type apiError struct {
	Error      string `json:"error"`
	GrpcStatus int    `json:"grpc_status,omitempty"`
}

func writeErr(w http.ResponseWriter, code int, e apiError) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(e)
}

func (g *gateway) handle(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost || r.URL.Path != "/v1/submit" {
		http.NotFound(w, r)
		return
	}
	g.st.requests.Add(1)
	t0 := time.Now()

	// 1. parse JSON
	raw, err := io.ReadAll(io.LimitReader(r.Body, 4<<20))
	if err != nil {
		g.st.fail("read_body")
		writeErr(w, http.StatusBadRequest, apiError{Error: "read body"})
		return
	}
	var p wire.Payload
	if err := json.Unmarshal(raw, &p); err != nil {
		g.st.fail("bad_json")
		writeErr(w, http.StatusBadRequest, apiError{Error: "bad json"})
		return
	}
	t1 := time.Now()

	// 2. map to Protobuf
	body := p.Marshal()
	t2 := time.Now()

	// 3. internal authentication
	req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, "https://"+g.backend+wire.Method, nil)
	if err != nil {
		g.st.fail("build_request")
		writeErr(w, http.StatusInternalServerError, apiError{Error: "build request"})
		return
	}
	req.Header.Set("Content-Type", "application/grpc")
	req.Header.Set("Te", "trailers")
	if g.pad != "" {
		req.Header.Set(wire.HdrPad, g.pad)
	}
	if err := g.authenticate(req, body); err != nil {
		g.st.fail("auth")
		writeErr(w, http.StatusInternalServerError, apiError{Error: err.Error()})
		return
	}
	t3 := time.Now()
	g.st.recordMeta(wire.RequestHeaderListSize(req))

	// 4. forward over HTTP/2
	framed := wire.Frame(body)
	req.Body = io.NopCloser(bytes.NewReader(framed))
	req.ContentLength = int64(len(framed))
	resp, err := g.client.Do(req)
	if err != nil {
		g.st.fail("forward")
		writeErr(w, http.StatusBadGateway, apiError{Error: "backend unreachable"})
		return
	}
	msg, rerr := wire.ReadFrame(resp.Body, 4<<20)
	io.Copy(io.Discard, resp.Body)
	resp.Body.Close()
	status := resp.Header.Get("Grpc-Status")
	if status == "" {
		status = resp.Trailer.Get("Grpc-Status")
	}
	t4 := time.Now()
	if status != "0" || rerr != nil {
		code, _ := strconv.Atoi(status)
		g.st.fail("grpc_status_" + status)
		writeErr(w, http.StatusBadGateway, apiError{Error: "backend error: " + resp.Header.Get("Grpc-Message"), GrpcStatus: code})
		return
	}
	var out wire.Payload
	if err := out.Unmarshal(msg); err != nil {
		g.st.fail("bad_response")
		writeErr(w, http.StatusBadGateway, apiError{Error: "bad backend response"})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(&out)

	g.st.parse.Record(t1.Sub(t0))
	g.st.mapping.Record(t2.Sub(t1))
	g.st.auth.Record(t3.Sub(t2))
	g.st.forward.Record(t4.Sub(t3))
	g.st.total.Record(time.Since(t0))
	g.st.ok.Add(1)
}

func (g *gateway) authenticate(req *http.Request, body []byte) error {
	if *config == "C0" || *config == "C1" {
		return nil
	}
	ts := time.Now().UnixMilli()
	rid := make([]byte, 16)
	rand.Read(rid)
	req.Header.Set(wire.HdrTS, strconv.FormatInt(ts, 10))
	req.Header.Set(wire.HdrRID, wire.B64.EncodeToString(rid))
	canon := wire.Canonical(wire.Method, body, ts, rid)

	switch *config {
	case "C2":
		s, err := g.signer.Sign(canon, []byte(wire.CtxMsg))
		if err != nil {
			return err
		}
		g.st.signatures.Add(1)
		req.Header.Set(wire.HdrSig, wire.B64.EncodeToString(s))
		return nil
	case "C3":
		reply := make(chan batchProof, 1)
		g.batch.in <- batchItem{leaf: wire.LeafHash(canon), reply: reply}
		pr := <-reply
		if pr.err != nil {
			return pr.err
		}
		req.Header.Set(wire.HdrRoot, wire.B64.EncodeToString(pr.root[:]))
		req.Header.Set(wire.HdrPath, wire.B64.EncodeToString(wire.PackPath(pr.path)))
		req.Header.Set(wire.HdrIdx, strconv.Itoa(pr.idx))
		req.Header.Set(wire.HdrN, strconv.Itoa(pr.n))
		if pr.sig != nil {
			req.Header.Set(wire.HdrSig, wire.B64.EncodeToString(pr.sig))
		}
		return nil
	}
	return errors.New("unknown config")
}

func (g *gateway) statsHandler(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/reset" {
		g.st.reset()
		w.Write([]byte("ok\n"))
		return
	}
	s := g.st
	metaAvg := 0.0
	if n := s.metaN.Load(); n > 0 {
		metaAvg = float64(s.metaBytesSum.Load()) / float64(n)
	}
	s.errMu.Lock()
	errs := map[string]int64{}
	for k, v := range s.errors {
		errs[k] = v
	}
	s.errMu.Unlock()
	sigName := ""
	if g.signer != nil {
		sigName = g.signer.Name()
	}
	out := map[string]any{
		"component":          "gateway",
		"config":             *config,
		"public_kex":         *publicKex,
		"sig_backend":        sigName,
		"gomaxprocs":         runtime.GOMAXPROCS(0),
		"batch_window_ms":    float64(*batchWindow) / float64(time.Millisecond),
		"batch_max":          *batchMax,
		"batch_sig":          *batchSig,
		"pad_bytes":          *padBytes,
		"stage_parse":        s.parse.Summary(),
		"stage_map":          s.mapping.Summary(),
		"stage_auth":         s.auth.Summary(),
		"stage_forward":      s.forward.Summary(),
		"stage_total":        s.total.Summary(),
		"metadata_bytes_avg": metaAvg,
		"metadata_bytes_max": s.metaBytesMax.Load(),
		"signatures":         s.signatures.Load(),
		"batches":            s.batches.Load(),
		"batched_requests":   s.batchedReqs.Load(),
		"requests":           s.requests.Load(),
		"ok":                 s.ok.Load(),
		"errors":             errs,
		"public_bytes_in":    s.public.Read.Load(),
		"public_bytes_out":   s.public.Written.Load(),
		"internal_bytes_out": s.internal.Written.Load(),
		"internal_bytes_in":  s.internal.Read.Load(),
		"cpu_seconds":        stats.CPUSeconds() - s.cpuAtReset.Load().(float64),
		"rss_mb":             stats.RSSMB(),
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(out)
}

func main() {
	flag.Parse()
	st := newStats()
	g := &gateway{st: st, backend: *backendAddr}
	if *padBytes > 0 {
		g.pad = strings.Repeat("p", *padBytes)
	}

	internalKex := "classical"
	switch *config {
	case "C0", "C2", "C3":
	case "C1":
		internalKex = "hybrid"
	default:
		log.Fatalf("unknown config %q", *config)
	}

	if *config == "C2" || *config == "C3" {
		scheme, err := sig.LoadMLDSA(*sigBackend)
		if err != nil {
			log.Fatal(err)
		}
		signer, _, err := scheme.GenerateKey()
		if err != nil {
			log.Fatal(err)
		}
		g.signer = signer
		// write atomically so the backend never reads a partial key
		tmp := *pubKeyOut + ".tmp"
		if err := os.WriteFile(tmp, signer.PublicKey(), 0o644); err != nil {
			log.Fatal(err)
		}
		if err := os.Rename(tmp, *pubKeyOut); err != nil {
			log.Fatal(err)
		}
		log.Printf("ML-DSA-65 key generated (%s); public key written to %s", signer.Name(), *pubKeyOut)
	}
	if *config == "C3" {
		workers := *signWorkers
		if workers <= 0 {
			workers = runtime.GOMAXPROCS(0)
		}
		g.batch = &batcher{in: make(chan batchItem, 4096), signer: g.signer, st: st, sem: make(chan struct{}, workers)}
		go g.batch.run()
	}

	clientTLS, err := tlsutil.ClientConfig(*certDir, internalKex, *backendName, true, []string{"h2"})
	if err != nil {
		log.Fatal(err)
	}
	dialer := &net.Dialer{Timeout: 5 * time.Second}
	tr := &http.Transport{
		TLSClientConfig:     clientTLS,
		ForceAttemptHTTP2:   true,
		MaxIdleConnsPerHost: 16,
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			c, err := dialer.DialContext(ctx, network, addr)
			if err != nil {
				return nil, err
			}
			return stats.WrapConn(c, &st.internal), nil
		},
	}
	g.client = &http.Client{Transport: tr, Timeout: 30 * time.Second}

	pubTLS, err := tlsutil.ServerConfig(*certDir, *publicKex, false, []string{"http/1.1"})
	if err != nil {
		log.Fatal(err)
	}
	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		log.Fatal(err)
	}
	srv := &http.Server{
		Handler:      http.HandlerFunc(g.handle),
		TLSConfig:    pubTLS,
		TLSNextProto: map[string]func(*http.Server, *tls.Conn, http.Handler){}, // HTTP/1.1 only
	}
	go func() {
		log.Printf("admin on http://%s/stats", *admin)
		log.Fatal(http.ListenAndServe(*admin, http.HandlerFunc(g.statsHandler)))
	}()
	log.Printf("gateway %s: REST on https://%s/v1/submit (public kex=%s) -> gRPC %s (internal kex=%s)",
		*config, *listen, *publicKex, *backendAddr, internalKex)
	log.Fatal(srv.Serve(tls.NewListener(stats.WrapListener(ln, &st.public), pubTLS)))
}
