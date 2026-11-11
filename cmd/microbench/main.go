// microbench measures key generation, signing and verification per operation
// for each signature scheme compiled in (paper Table 6), plus multi-core
// signing throughput.
package main

import (
	"crypto/rand"
	"encoding/json"
	"flag"
	"log"
	"os"
	"runtime"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"qsbg/internal/sig"
)

var (
	iters   = flag.Int("n", 2000, "operations per measurement")
	keygens = flag.Int("keygen-n", 200, "key generations to time")
	msgLen  = flag.Int("msg", 200, "message length in bytes (about one canonical 128-byte request)")
	tputDur = flag.Duration("throughput-dur", 3*time.Second, "parallel signing throughput window")
	out     = flag.String("out", "", "write JSON here (default stdout)")
)

type opStats struct {
	N      int     `json:"n"`
	MedUs  float64 `json:"median_us"`
	P95Us  float64 `json:"p95_us"`
	MeanUs float64 `json:"mean_us"`
}

type schemeResult struct {
	Scheme           string  `json:"scheme"`
	SigBytes         int     `json:"signature_bytes"`
	PubKeyBytes      int     `json:"public_key_bytes"`
	KeyGen           opStats `json:"keygen"`
	Sign             opStats `json:"sign"`
	Verify           opStats `json:"verify"`
	SignOpsPerCore   float64 `json:"sign_ops_per_s_one_core"`
	SignOpsAllCores  float64 `json:"sign_ops_per_s_all_cores"`
	VerifyOpsPerCore float64 `json:"verify_ops_per_s_one_core"`
	ParallelWorkers  int     `json:"parallel_workers"`
}

func summarize(ds []time.Duration) opStats {
	sort.Slice(ds, func(i, j int) bool { return ds[i] < ds[j] })
	var sum time.Duration
	for _, d := range ds {
		sum += d
	}
	us := func(d time.Duration) float64 { return float64(d.Nanoseconds()) / 1000 }
	return opStats{N: len(ds), MedUs: us(ds[len(ds)/2]), P95Us: us(ds[len(ds)*95/100]), MeanUs: us(sum) / float64(len(ds))}
}

func main() {
	flag.Parse()
	names := make([]string, 0, len(sig.Schemes))
	for n := range sig.Schemes {
		names = append(names, n)
	}
	sort.Strings(names)
	msg := make([]byte, *msgLen)
	rand.Read(msg)
	ctx := []byte("qsbg-msg-v1")

	var results []schemeResult
	for _, name := range names {
		sc := sig.Schemes[name]
		var kg []time.Duration
		var signer sig.Signer
		var verifier sig.Verifier
		for i := 0; i < *keygens; i++ {
			t := time.Now()
			s, v, err := sc.GenerateKey()
			kg = append(kg, time.Since(t))
			if err != nil {
				log.Fatal(err)
			}
			signer, verifier = s, v
		}
		var sg, vf []time.Duration
		var lastSig []byte
		for i := 0; i < *iters; i++ {
			t := time.Now()
			s, err := signer.Sign(msg, ctx)
			sg = append(sg, time.Since(t))
			if err != nil {
				log.Fatal(err)
			}
			lastSig = s
			t = time.Now()
			ok := verifier.Verify(msg, s, ctx)
			vf = append(vf, time.Since(t))
			if !ok {
				log.Fatalf("%s: verification failed", name)
			}
		}
		res := schemeResult{
			Scheme: name, SigBytes: len(lastSig), PubKeyBytes: len(signer.PublicKey()),
			KeyGen: summarize(kg), Sign: summarize(sg), Verify: summarize(vf),
			ParallelWorkers: runtime.GOMAXPROCS(0),
		}
		res.SignOpsPerCore = 1e6 / res.Sign.MeanUs
		res.VerifyOpsPerCore = 1e6 / res.Verify.MeanUs

		var count atomic.Int64
		var wg sync.WaitGroup
		deadline := time.Now().Add(*tputDur)
		for w := 0; w < res.ParallelWorkers; w++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for time.Now().Before(deadline) {
					signer.Sign(msg, ctx)
					count.Add(1)
				}
			}()
		}
		wg.Wait()
		res.SignOpsAllCores = float64(count.Load()) / tputDur.Seconds()
		log.Printf("%-16s sign median %8.1f us  verify median %8.1f us  sig %d B", name, res.Sign.MedUs, res.Verify.MedUs, res.SigBytes)
		results = append(results, res)
	}
	doc := map[string]any{
		"host":    map[string]any{"num_cpu": runtime.NumCPU(), "gomaxprocs": runtime.GOMAXPROCS(0), "go": runtime.Version(), "arch": runtime.GOARCH},
		"msg_len": *msgLen,
		"results": results,
	}
	enc, _ := json.MarshalIndent(doc, "", "  ")
	if *out == "" {
		os.Stdout.Write(append(enc, '\n'))
	} else {
		os.WriteFile(*out, append(enc, '\n'), 0o644)
	}
}
