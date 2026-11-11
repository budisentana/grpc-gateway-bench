#!/usr/bin/env bash
# Short pilot of the whole pipeline on ONE machine, no network emulation.
# Its numbers check that the setup works; they are NOT the paper's data.
#
# Usage: scripts/run_pilot.sh [OUTDIR]     (default results/pilot)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-results/pilot}
mkdir -p "$OUT"
[[ -d certs ]] || ./bin/certgen -out certs

echo "== 1. ML-DSA cross-check against OpenSSL"
python3 analysis/crosscheck_mldsa.py ./bin/mldsatool 50 | tail -1 | tee "$OUT/crosscheck.txt"

echo "== 2. micro-benchmarks (Table 6)"
GOMAXPROCS=${GW_PROCS:-1} ./bin/microbench -n 1000 -keygen-n 100 -out "$OUT/microbench_go.json"
python3 analysis/microbench_openssl.py 1000 > "$OUT/microbench_openssl.json"

echo "== 3. closed-loop matrix"
PROFILE=none NETNS=0 CONFIGS="C0 C1 C2 C3" PAYLOADS="${PAYLOADS:-128 1024}" CLIENTS="${CLIENTS:-10 50}" \
  REPS=${REPS:-3} WARMUP=${WARMUP:-3s} DURATION=${DURATION:-10s} \
  RATES="${RATES:-}" C3_GRID="${C3_GRID:-1ms:16 1ms:64 5ms:16 5ms:64 5ms:256 10ms:64 10ms:256}" C3_GRID_CLIENTS=50 \
  scripts/run_matrix.sh "$OUT/runs"

echo "== 3b. open-loop sweep (payload 128 B, one repetition)"
PROFILE=none NETNS=0 CONFIGS="C0 C1 C2 C3" PAYLOADS=128 CLIENTS="" REPS=1 WARMUP=3s DURATION=8s \
  RATES="${OPEN_RATES:-250 500 1000 1500 2500}" scripts/run_matrix.sh "$OUT/open"

echo "== 4. metadata headroom"
scripts/headroom.sh "$OUT/headroom"

echo "== 5. summary"
python3 analysis/summarize.py "$OUT" --out "$OUT/summary" --microbench "$OUT/microbench_go.json" "$OUT/microbench_openssl.json"
