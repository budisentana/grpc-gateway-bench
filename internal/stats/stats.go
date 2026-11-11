// Package stats provides latency histograms, byte-counting connections and
// process CPU/memory readings.
package stats

import (
	"math"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Histogram records durations in log-spaced buckets (~0.5% relative error),
// covering 100 ns to ~1000 s. Safe for concurrent use.
type Histogram struct {
	mu     sync.Mutex
	counts []uint64
	n      uint64
	sum    float64 // ns
	min    float64
	max    float64
}

const (
	hMin    = 100.0 // ns
	hGrowth = 1.01
	hBins   = 2400
)

func NewHistogram() *Histogram {
	return &Histogram{counts: make([]uint64, hBins), min: math.Inf(1)}
}

func bucketOf(ns float64) int {
	if ns <= hMin {
		return 0
	}
	b := int(math.Log(ns/hMin) / math.Log(hGrowth))
	if b >= hBins {
		b = hBins - 1
	}
	return b
}

func bucketValue(b int) float64 { return hMin * math.Pow(hGrowth, float64(b)+0.5) }

func (h *Histogram) Record(d time.Duration) {
	ns := float64(d.Nanoseconds())
	b := bucketOf(ns)
	h.mu.Lock()
	h.counts[b]++
	h.n++
	h.sum += ns
	if ns < h.min {
		h.min = ns
	}
	if ns > h.max {
		h.max = ns
	}
	h.mu.Unlock()
}

func (h *Histogram) Reset() {
	h.mu.Lock()
	for i := range h.counts {
		h.counts[i] = 0
	}
	h.n, h.sum, h.min, h.max = 0, 0, math.Inf(1), 0
	h.mu.Unlock()
}

// Merge adds the contents of o into h.
func (h *Histogram) Merge(o *Histogram) {
	o.mu.Lock()
	defer o.mu.Unlock()
	h.mu.Lock()
	defer h.mu.Unlock()
	for i, c := range o.counts {
		h.counts[i] += c
	}
	h.n += o.n
	h.sum += o.sum
	if o.min < h.min {
		h.min = o.min
	}
	if o.max > h.max {
		h.max = o.max
	}
}

// Summary is a JSON-friendly snapshot in microseconds.
type Summary struct {
	Count  uint64  `json:"count"`
	MeanUs float64 `json:"mean_us"`
	MinUs  float64 `json:"min_us"`
	P50Us  float64 `json:"p50_us"`
	P90Us  float64 `json:"p90_us"`
	P95Us  float64 `json:"p95_us"`
	P99Us  float64 `json:"p99_us"`
	P999Us float64 `json:"p999_us"`
	MaxUs  float64 `json:"max_us"`
}

func (h *Histogram) Summary() Summary {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.n == 0 {
		return Summary{}
	}
	q := func(p float64) float64 {
		target := uint64(math.Ceil(p * float64(h.n)))
		if target == 0 {
			target = 1
		}
		var cum uint64
		for i, c := range h.counts {
			cum += c
			if cum >= target {
				v := bucketValue(i)
				if v > h.max {
					v = h.max
				}
				if v < h.min {
					v = h.min
				}
				return v / 1000
			}
		}
		return h.max / 1000
	}
	return Summary{
		Count: h.n, MeanUs: h.sum / float64(h.n) / 1000, MinUs: h.min / 1000,
		P50Us: q(0.50), P90Us: q(0.90), P95Us: q(0.95), P99Us: q(0.99), P999Us: q(0.999),
		MaxUs: h.max / 1000,
	}
}

// ---- byte counting ----

// Counter accumulates bytes read and written on wrapped connections.
type Counter struct {
	Read, Written atomic.Int64
}

func (c *Counter) Reset() { c.Read.Store(0); c.Written.Store(0) }

type countConn struct {
	net.Conn
	c *Counter
}

func (cc countConn) Read(b []byte) (int, error) {
	n, err := cc.Conn.Read(b)
	cc.c.Read.Add(int64(n))
	return n, err
}

func (cc countConn) Write(b []byte) (int, error) {
	n, err := cc.Conn.Write(b)
	cc.c.Written.Add(int64(n))
	return n, err
}

// WrapConn counts the raw (TLS-encrypted) bytes on a connection.
func WrapConn(conn net.Conn, c *Counter) net.Conn { return countConn{conn, c} }

type countListener struct {
	net.Listener
	c *Counter
}

func (l countListener) Accept() (net.Conn, error) {
	conn, err := l.Listener.Accept()
	if err != nil {
		return nil, err
	}
	return WrapConn(conn, l.c), nil
}

// WrapListener counts bytes on every accepted connection.
func WrapListener(l net.Listener, c *Counter) net.Listener { return countListener{l, c} }

// ---- process metrics (Linux /proc) ----

// CPUSeconds returns user+system CPU time consumed by this process.
func CPUSeconds() float64 {
	b, err := os.ReadFile("/proc/self/stat")
	if err != nil {
		return 0
	}
	s := string(b)
	// fields after the ")" of the comm field; utime=14, stime=15 (1-based)
	i := strings.LastIndexByte(s, ')')
	f := strings.Fields(s[i+2:])
	if len(f) < 13 {
		return 0
	}
	ut, _ := strconv.ParseFloat(f[11], 64)
	st, _ := strconv.ParseFloat(f[12], 64)
	return (ut + st) / 100 // USER_HZ is 100 on Linux
}

// RSSMB returns resident set size in MiB.
func RSSMB() float64 {
	b, err := os.ReadFile("/proc/self/status")
	if err != nil {
		return 0
	}
	for _, line := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(line, "VmRSS:") {
			f := strings.Fields(line)
			kb, _ := strconv.ParseFloat(f[1], 64)
			return kb / 1024
		}
	}
	return 0
}
