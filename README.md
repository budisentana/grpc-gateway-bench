# qsbg-bench — PQC authentication at a REST-to-gRPC gateway

Experiment code for the paper *PQC Authentication at a REST-to-gRPC Edge Gateway*.
It measures what post-quantum authentication costs when a gateway translates
public REST/JSON calls into internal gRPC calls.

Everything builds with **only the Go standard library** (Go 1.24+). No module
downloads are needed, so it also works on lab machines without internet.

## What is inside

| Component | Path | Role |
| --- | --- | --- |
| Gateway | `cmd/gateway` | REST/JSON over TLS 1.3 (HTTP/1.1) in, gRPC over HTTP/2 + mTLS out; configurations C0–C3 |
| Backend | `cmd/backend` | gRPC service `qsbg.eval.Echo/Submit`; verifies signatures (C2) and batch proofs (C3); enforces the 8 KB metadata limit |
| Load generator | `cmd/loadgen` | Closed-loop (N clients) and open-loop (fixed rate, no coordinated omission); writes one JSON file per run |
| Micro-benchmark | `cmd/microbench` | Key generation / sign / verify per operation (Table 6) |
| ML-DSA-65 | `internal/mldsa` | Pure-Go FIPS 204 implementation, cross-checked against OpenSSL |
| Scripts | `scripts/` | `run_one.sh`, `run_matrix.sh`, `netem.sh`, `headroom.sh`, `capture.sh`, `run_pilot.sh` |
| Analysis | `analysis/` | `summarize.py` (tables, tests, figures), `crosscheck_mldsa.py`, `microbench_openssl.py` |

### Configurations (paper Table 3)

| ID | Internal channel | Message authentication |
| --- | --- | --- |
| C0 | mTLS, X25519 + ECDSA P-256 certificates | none |
| C1 | mTLS, **X25519MLKEM768** key exchange + ECDSA certificates | none |
| C2 | as C0 | ML-DSA-65 signature per request, in `x-qsbg-sig-bin` metadata |
| C3 | as C0 | ML-DSA-65 signature over a Merkle root per batch (window `T`, size `B`) |

The public link always uses TLS 1.3 with X25519MLKEM768 (`-public-kex hybrid`).

## Requirements

- Go 1.24 or newer
- Python 3.10+ with `numpy pandas scipy matplotlib` (analysis)
- `cryptography` with ML-DSA support (only for the OpenSSL cross-check and reference benchmark)
- For WAN emulation: Linux, root, `iproute2` (`ip`, `tc`), `sch_netem` module
- Optional: `tcpdump` + `tshark` for segment counts, `taskset` for CPU pinning

## Quick start (one machine, no emulation)

```bash
go build -o bin/ ./cmd/...
./bin/certgen -out certs
scripts/run_one.sh C2 results/test/C2.json -mode closed -c 50 -warmup 5s -duration 20s
python3 analysis/summarize.py results/test
```

Or run the whole pilot (about 25 minutes):

```bash
GW_CPUS=0 GW_PROCS=1 BE_CPUS=1 LG_CPUS=1 scripts/run_pilot.sh results/pilot
```

## Lab procedure for the paper

1. **Check correctness:** `python3 analysis/crosscheck_mldsa.py ./bin/mldsatool 200`
2. **Fix the hardware:** disable CPU frequency scaling, record CPU model, cores, RAM, kernel, Go version.
   Pin components so they do not share cores, e.g. on 8 cores: `GW_CPUS=0-1 GW_PROCS=2 BE_CPUS=2-3 LG_CPUS=4-7`.
3. **Micro-benchmark (Table 6):** `GOMAXPROCS=2 taskset -c 0-1 ./bin/microbench -out results/microbench_go.json`
   and `python3 analysis/microbench_openssl.py > results/microbench_openssl.json`.
4. **Network emulation:** `./bin/certgen -out certs -hosts localhost,127.0.0.1,10.77.0.1`, then
   `sudo scripts/netem.sh up constrained` (or `fast`). Check with `sudo scripts/netem.sh show`.
5. **Full matrix:** (as root, because the load generator runs inside the network namespace)
   ```bash
   sudo -E env PROFILE=constrained NETNS=1 GW_CPUS=0-1 GW_PROCS=2 BE_CPUS=2-3 LG_CPUS=4-7 \
     RATES="250 500 1000 2000 4000" \
     C3_GRID="1ms:16 1ms:64 1ms:256 5ms:16 5ms:64 5ms:256 10ms:16 10ms:64 10ms:256" \
     scripts/run_matrix.sh results/constrained
   ```
   **Use at least 6 repetitions (`REPS=6`).** With the exact Mann–Whitney test, n = 3 per group
   cannot give p below 0.1, and n = 5 only just survives Holm correction across the six
   configuration pairs (smallest adjusted p ≈ 0.048). n = 6 gives a minimum p of 0.002.
   Repeat with `PROFILE=fast` after `sudo scripts/netem.sh up fast`. Defaults give the paper's design:
   4 configurations × 4 payloads × 4 concurrency levels × 5 repetitions (set `REPS=6`, see above), 60 s warm-up, 300 s
   measurement, in random order. That is long (~2 days per profile); the script skips finished
   runs, so it can be stopped and resumed.
6. **Metadata headroom (Section V-C):** `scripts/headroom.sh results/headroom`
7. **Segments per request (Table 8):** `sudo scripts/capture.sh C2 128 results/capture` for each configuration.
8. **Summarise:** `python3 analysis/summarize.py results/constrained --microbench results/microbench_*.json`

`summarize.py` writes `table7_translation.csv`, `table8_bytes.csv`, `table9_throughput.csv`,
`table10_batch.csv`, `headroom.csv`, `stats_tests.csv` (Kruskal–Wallis + Holm-corrected
Mann–Whitney U with rank-biserial effect sizes), the p99-vs-load and throughput figures, and
`results.json`.

## Things to state honestly in the paper

- **ML-DSA implementation.** The default backend is the pure-Go implementation in
  `internal/mldsa`. It passes byte-exact key-generation and two-way signature cross-checks against
  OpenSSL, but it is *not* optimised and *not* constant-time. Compare its Table 6 numbers with
  `microbench_openssl.json`. For headline numbers, either report this implementation explicitly or
  build with an optimised library: `go get github.com/cloudflare/circl@latest && go build -tags circl -o bin/ ./cmd/...`
  (the `circl` adapter in `internal/sig/circl.go` was written against CIRCL's documented API but
  could not be compiled where this suite was written; check it builds).
- **C1 is post-quantum key exchange only.** Go's TLS stack does not support ML-DSA certificates,
  so C1 uses X25519MLKEM768 with ECDSA certificates. Either describe C1 that way in Section III, or
  add OpenSSL 3.5+ TLS proxies with ML-DSA certificates for a true PQ-authenticated channel.
- **gRPC framing.** gRPC is implemented on Go's `net/http` HTTP/2 stack following the
  "gRPC over HTTP2" specification, rather than with the grpc-go library.
- **Loss** in the `constrained` profile is applied 0.2% in each direction.
- **Metadata size.** The gateway's `metadata_bytes_*` figures are computed before Go's HTTP/2
  client adds `user-agent` and `accept-encoding` (about 111 bytes). The backend's
  `metadata_bytes_*_received` figures are what arrives and what the 8 KB limit is checked against;
  `summarize.py` uses them when present.
- **One host vs three.** With a single host, components share memory bandwidth and caches even
  when pinned to separate cores. Three hosts match the paper's description more closely.

## Result file format

Each run writes one JSON file: load-generator settings, throughput, latency summary
(p50/p90/p95/p99/p99.9 in µs), errors, client bytes, and the gateway and backend `/stats`
snapshots over the same measurement window (stage timings, CPU seconds, RSS, metadata size,
bytes on each link, signatures made, verification time, metadata-limit rejections).
