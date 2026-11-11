#!/usr/bin/env bash
# Metadata headroom experiment (paper Section V-C): add filler headers that
# stand in for tracing/authorisation metadata and find where requests start
# failing against the backend's 8 KB gRPC-style metadata limit.
#
# Usage: scripts/headroom.sh OUTDIR [CONFIGS]
set -euo pipefail
OUTDIR=${1:?outdir}; CONFIGS=${2:-"C0 C2 C3"}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUTDIR"
for cfg in $CONFIGS; do
  for pad in 0 1000 2000 3000 3200 3400 3600 4000 5000 6000 7000 7500; do
    out="$OUTDIR/headroom_${cfg}_pad${pad}.json"
    [[ -s $out ]] && continue
    PAD_BYTES=$pad "$HERE/run_one.sh" "$cfg" "$out" -mode closed -c 4 -warmup 1s -duration 3s -label "headroom" || true
  done
done
