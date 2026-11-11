// backend is the gRPC service behind the gateway. It implements
// qsbg.eval.Echo/Submit over HTTP/2 + mutual TLS and verifies the gateway's
// message signatures (C2) or batch proofs (C3).
package main

import (
	"crypto/tls"
	"encoding/json"
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"qsbg/internal/sig"
	"qsbg/internal/stats"
	"qsbg/internal/tlsutil"
	"qsbg/internal/wire"
)

var (
	addr        = flag.String("addr", "127.0.0.1:9443", "gRPC listen address (TLS, HTTP/2)")
	admin       = flag.String("admin", "127.0.0.1:9901", "admin/stats listen address (plain HTTP)")
	certDir     = flag.String("certs", "certs", "test PKI directory")
	kex         = flag.String("kex", "classical", "internal TLS key exchange: classical|hybrid")
	authMode    = flag.String("auth", "none", "required gateway authentication: none|msg|batch")
	pubKeyFile  = flag.String("gateway-pubkey", "gateway_mldsa65.pub", "gateway ML-DSA-65 public key")
	backendName = flag.String("sig-backend", "", "ML-DSA backend (default: best compiled in)")
	maxMeta     = flag.Int("max-metadata", 8192, "max request header list size in bytes, like gRPC's default (0 = off)")
	skewMs      = flag.Int64("max-skew-ms", 30000, "accepted timestamp skew for replay protection")
)

type server struct {
	verifier  sig.Verifier
	verifyH   *stats.Histogram
	handleH   *stats.Histogram
	counters  map[string]*atomic.Int64
	bytes     stats.Counter
	cpuAtRst  atomic.Value // float64
	seen      sync.Map     // request id -> expiry (unix ms)
	roots     sync.Map     // [32]byte -> *rootEntry
	rootWaits atomic.Int64
	metaSum   atomic.Int64
	metaN     atomic.Int64
	metaMax   atomic.Int64
}

type rootEntry struct {
	done    chan struct{}
	ok      bool
	created time.Time
	once    sync.Once
}

func (s *server) inc(name string) { s.counters[name].Add(1) }

func newServer() *server {
	s := &server{verifyH: stats.NewHistogram(), handleH: stats.NewHistogram(), counters: map[string]*atomic.Int64{}}
	for _, c := range []string{"requests", "ok", "metadata_too_large", "bad_signature", "replay", "stale", "bad_request", "batch_sig_verified", "batch_root_cache_hit", "batch_root_wait_timeout"} {
		s.counters[c] = &atomic.Int64{}
	}
	s.cpuAtRst.Store(stats.CPUSeconds())
	return s
}

func grpcError(w http.ResponseWriter, code int, msg string) {
	// Trailers-only response (gRPC over HTTP/2 spec).
	w.Header().Set("Content-Type", "application/grpc")
	w.Header().Set("Grpc-Status", strconv.Itoa(code))
	w.Header().Set("Grpc-Message", msg)
	w.WriteHeader(http.StatusOK)
}

func (s *server) handle(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	s.inc("requests")
	if r.Method != http.MethodPost || r.URL.Path != wire.Method || r.ProtoMajor != 2 {
		s.inc("bad_request")
		http.Error(w, "unsupported", http.StatusNotFound)
		return
	}
	metaSize := wire.RequestHeaderListSize(r)
	s.metaSum.Add(int64(metaSize))
	s.metaN.Add(1)
	for cur := s.metaMax.Load(); int64(metaSize) > cur && !s.metaMax.CompareAndSwap(cur, int64(metaSize)); cur = s.metaMax.Load() {
	}
	if *maxMeta > 0 && metaSize > *maxMeta {
		s.inc("metadata_too_large")
		grpcError(w, wire.StatusResourceExhausted, "metadata size exceeds limit")
		return
	}
	body, err := wire.ReadFrame(r.Body, 4<<20)
	if err != nil {
		s.inc("bad_request")
		grpcError(w, wire.StatusInvalidArgument, err.Error())
		return
	}
	if code, msg := s.authenticate(r, body); code != wire.StatusOK {
		grpcError(w, code, msg)
		return
	}
	var p wire.Payload
	if err := p.Unmarshal(body); err != nil {
		s.inc("bad_request")
		grpcError(w, wire.StatusInvalidArgument, err.Error())
		return
	}
	// Echo the message back.
	w.Header().Set("Content-Type", "application/grpc")
	w.Header().Set("Trailer", "Grpc-Status")
	w.WriteHeader(http.StatusOK)
	w.Write(wire.Frame(p.Marshal()))
	w.Header().Set("Grpc-Status", "0")
	s.inc("ok")
	s.handleH.Record(time.Since(start))
}

func (s *server) authenticate(r *http.Request, body []byte) (int, string) {
	if *authMode == "none" {
		return wire.StatusOK, ""
	}
	ts, err := strconv.ParseInt(r.Header.Get(wire.HdrTS), 10, 64)
	if err != nil {
		s.inc("bad_request")
		return wire.StatusUnauthenticated, "missing timestamp"
	}
	now := time.Now().UnixMilli()
	if ts < now-*skewMs || ts > now+*skewMs {
		s.inc("stale")
		return wire.StatusUnauthenticated, "stale timestamp"
	}
	rid, err := wire.B64.DecodeString(r.Header.Get(wire.HdrRID))
	if err != nil || len(rid) != 16 {
		s.inc("bad_request")
		return wire.StatusUnauthenticated, "bad request id"
	}
	if _, dup := s.seen.LoadOrStore(string(rid), ts+*skewMs); dup {
		s.inc("replay")
		return wire.StatusUnauthenticated, "replayed request"
	}
	canon := wire.Canonical(wire.Method, body, ts, rid)

	switch *authMode {
	case "msg":
		sigBytes, err := wire.B64.DecodeString(r.Header.Get(wire.HdrSig))
		if err != nil {
			s.inc("bad_signature")
			return wire.StatusUnauthenticated, "bad signature encoding"
		}
		t0 := time.Now()
		ok := s.verifier.Verify(canon, sigBytes, []byte(wire.CtxMsg))
		s.verifyH.Record(time.Since(t0))
		if !ok {
			s.inc("bad_signature")
			return wire.StatusUnauthenticated, "signature verification failed"
		}
		return wire.StatusOK, ""

	case "batch":
		root, err1 := wire.B64.DecodeString(r.Header.Get(wire.HdrRoot))
		pathB, err2 := wire.B64.DecodeString(r.Header.Get(wire.HdrPath))
		idx, err3 := strconv.Atoi(r.Header.Get(wire.HdrIdx))
		nLeaves, err4 := strconv.Atoi(r.Header.Get(wire.HdrN))
		path, err5 := wire.UnpackPath(pathB)
		if err1 != nil || err2 != nil || err3 != nil || err4 != nil || err5 != nil || len(root) != 32 || idx < 0 || idx >= nLeaves {
			s.inc("bad_request")
			return wire.StatusUnauthenticated, "bad batch proof"
		}
		var rootArr [32]byte
		copy(rootArr[:], root)
		if wire.VerifyPath(wire.LeafHash(canon), idx, nLeaves, path) != rootArr {
			s.inc("bad_signature")
			return wire.StatusUnauthenticated, "leaf not in batch"
		}
		e, loaded := s.roots.LoadOrStore(rootArr, &rootEntry{done: make(chan struct{}), created: time.Now()})
		entry := e.(*rootEntry)
		if sigHdr := r.Header.Get(wire.HdrSig); sigHdr != "" {
			sigBytes, err := wire.B64.DecodeString(sigHdr)
			if err == nil {
				entry.once.Do(func() {
					t0 := time.Now()
					entry.ok = s.verifier.Verify(root, sigBytes, []byte(wire.CtxBatch))
					s.verifyH.Record(time.Since(t0))
					s.inc("batch_sig_verified")
					close(entry.done)
				})
			}
		} else if loaded {
			s.inc("batch_root_cache_hit")
		}
		// Wait for the signature-carrying request of this batch, which may be
		// in flight on another HTTP/2 stream.
		select {
		case <-entry.done:
		case <-time.After(200 * time.Millisecond):
			s.rootWaits.Add(1)
			s.inc("batch_root_wait_timeout")
			return wire.StatusUnauthenticated, "batch root not verified"
		}
		if !entry.ok {
			s.inc("bad_signature")
			return wire.StatusUnauthenticated, "batch signature invalid"
		}
		return wire.StatusOK, ""
	}
	return wire.StatusInternal, "unknown auth mode"
}

// sweep removes expired replay entries and old batch roots.
func (s *server) sweep() {
	for range time.Tick(5 * time.Second) {
		now := time.Now().UnixMilli()
		s.seen.Range(func(k, v any) bool {
			if v.(int64) < now {
				s.seen.Delete(k)
			}
			return true
		})
		s.roots.Range(func(k, v any) bool {
			if time.Since(v.(*rootEntry).created) > 30*time.Second {
				s.roots.Delete(k)
			}
			return true
		})
	}
}

func (s *server) statsHandler(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/reset" {
		s.verifyH.Reset()
		s.handleH.Reset()
		for _, c := range s.counters {
			c.Store(0)
		}
		s.bytes.Reset()
		s.metaSum.Store(0)
		s.metaN.Store(0)
		s.metaMax.Store(0)
		s.cpuAtRst.Store(stats.CPUSeconds())
		w.Write([]byte("ok\n"))
		return
	}
	out := map[string]any{
		"component":    "backend",
		"auth":         *authMode,
		"kex":          *kex,
		"verify":       s.verifyH.Summary(),
		"handle":       s.handleH.Summary(),
		"cpu_seconds":  stats.CPUSeconds() - s.cpuAtRst.Load().(float64),
		"rss_mb":       stats.RSSMB(),
		"bytes_in":     s.bytes.Read.Load(),
		"bytes_out":    s.bytes.Written.Load(),
		"max_metadata": *maxMeta,
	}
	// header list size as received, including headers the HTTP/2 client adds
	if n := s.metaN.Load(); n > 0 {
		out["metadata_bytes_avg_received"] = float64(s.metaSum.Load()) / float64(n)
	}
	out["metadata_bytes_max_received"] = s.metaMax.Load()
	cs := map[string]int64{}
	for k, v := range s.counters {
		cs[k] = v.Load()
	}
	out["counters"] = cs
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(out)
}

func main() {
	flag.Parse()
	s := newServer()
	if *authMode != "none" {
		pk, err := os.ReadFile(*pubKeyFile)
		if err != nil {
			log.Fatalf("read gateway public key: %v (start the gateway first, it writes this file)", err)
		}
		v, err := sig.NewMLDSAVerifier(*backendName, pk) // raw binary key: never trim
		if err != nil {
			log.Fatal(err)
		}
		s.verifier = v
	}
	go s.sweep()

	tlsCfg, err := tlsutil.ServerConfig(*certDir, *kex, true, []string{"h2"})
	if err != nil {
		log.Fatal(err)
	}
	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		log.Fatal(err)
	}
	srv := &http.Server{
		Handler:        http.HandlerFunc(s.handle),
		MaxHeaderBytes: 1 << 20, // enforce the gRPC-style limit in the handler instead
		TLSConfig:      tlsCfg,
	}
	go func() {
		log.Printf("admin on http://%s/stats", *admin)
		log.Fatal(http.ListenAndServe(*admin, http.HandlerFunc(s.statsHandler)))
	}()
	log.Printf("backend: gRPC on %s (kex=%s, auth=%s, max-metadata=%d)", *addr, *kex, *authMode, *maxMeta)
	log.Fatal(srv.Serve(tls.NewListener(stats.WrapListener(ln, &s.bytes), tlsCfg)))
}
