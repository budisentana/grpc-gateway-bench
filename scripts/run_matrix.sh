#!/usr/bin/env bash
# Run the full experiment matrix in randomised order (paper Section IV).
# Each run writes one JSON file; existing files are skipped, so the script can
# be stopped and resumed.
#
# Usage: scripts/run_matrix.sh OUTDIR
# Environment (defaults are the paper's full design):
#   PROFILE=fast            label stored in results; constrained|fast|none
#   NETNS=1                 1 = load generator runs in the netem namespace (needs scripts/netem.sh up)
#   (set a list to "" to skip it, e.g. CLIENTS="" for an open-loop-only sweep)
#   CONFIGS="C0 C1 C2 C3"   PAYLOADS="128 512 1024 4096"   CLIENTS="10 50 100 500"
#   REPS=5  WARMUP=60s  DURATION=300s
#   RATES=""                open-loop rates to add, e.g. "500 1000 2000 4000"
#   C3_GRID=""              extra C3 runs, e.g. "1ms:16 1ms:64 5ms:16 5ms:64 5ms:256 10ms:256" (window:max)
#   C3_GRID_CLIENTS=100     concurrency for the C3 grid
#   Plus anything run_one.sh accepts (GW_CPUS, GW_PROCS, BE_CPUS, LG_CPUS, ...).
set -euo pipefail
OUTDIR=${1:?outdir}
HERE=$(cd "$(dirname "$0")" && pwd)
PROFILE=${PROFILE:-fast}
CONFIGS=${CONFIGS-"C0 C1 C2 C3"}
PAYLOADS=${PAYLOADS-"128 512 1024 4096"}
CLIENTS=${CLIENTS-"10 50 100 500"}
REPS=${REPS:-5}; WARMUP=${WARMUP:-60s}; DURATION=${DURATION:-300s}
RATES=${RATES-}; C3_GRID=${C3_GRID-}; C3_GRID_CLIENTS=${C3_GRID_CLIENTS:-100}
mkdir -p "$OUTDIR"

if [[ ${NETNS:-0} == 1 ]]; then
  export ADMIN_BIND=0.0.0.0 GATEWAY_LISTEN=0.0.0.0:8443 GATEWAY_URL=https://10.77.0.1:8443/v1/submit
  export LG_PREFIX="ip netns exec qsbg-client"
  ADMIN_FLAGS="-gateway-admin http://10.77.0.1:8901 -backend-admin http://10.77.0.1:9901"
else
  ADMIN_FLAGS=""
fi

# Build the job list: id|env|loadgen-args
JOBS=$(mktemp)
for rep in $(seq "$REPS"); do
  for cfg in $CONFIGS; do
    for pl in $PAYLOADS; do
      for c in $CLIENTS; do
        echo "${PROFILE}_${cfg}_closed_c${c}_p${pl}_r${rep}|CONFIG=$cfg|-mode closed -c $c -payload $pl -rep $rep" >>"$JOBS"
      done
      for rt in $RATES; do
        echo "${PROFILE}_${cfg}_open_r${rt}_p${pl}_r${rep}|CONFIG=$cfg|-mode open -rate $rt -payload $pl -rep $rep" >>"$JOBS"
      done
    done
  done
  for g in $C3_GRID; do
    T=${g%%:*}; B=${g##*:}
    echo "${PROFILE}_C3grid_T${T}_B${B}_c${C3_GRID_CLIENTS}_p128_r${rep}|CONFIG=C3 BATCH_WINDOW=$T BATCH_MAX=$B|-mode closed -c $C3_GRID_CLIENTS -payload 128 -rep $rep" >>"$JOBS"
  done
done

TOTAL=$(wc -l <"$JOBS"); N=0
echo "$TOTAL runs planned -> $OUTDIR"
shuf "$JOBS" | while IFS='|' read -r id envs args; do
  N=$((N+1))
  out="$OUTDIR/$id.json"
  if [[ -s $out ]]; then echo "[$N/$TOTAL] skip $id (exists)"; continue; fi
  echo "[$N/$TOTAL] $id"
  # shellcheck disable=SC2086
  env $envs bash -c "\"$HERE/run_one.sh\" \"\$CONFIG\" \"$out\" $args -warmup $WARMUP -duration $DURATION -label $PROFILE $ADMIN_FLAGS" \
    || echo "  run failed: $id" | tee -a "$OUTDIR/failures.log"
done
rm -f "$JOBS"
echo "done; summarise with: python3 analysis/summarize.py $OUTDIR"
