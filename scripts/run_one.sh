#!/usr/bin/env bash
# Run one measurement: start backend + gateway for a configuration, drive load,
# write one result JSON, stop everything.
#
# Usage: scripts/run_one.sh CONFIG OUTFILE [loadgen flags...]
#   CONFIG   C0|C1|C2|C3
#   OUTFILE  result JSON path
# Environment (all optional):
#   BIN=./bin  CERTS=./certs  GW_CPUS=0  BE_CPUS=1  LG_CPUS=2-3   (taskset CPU lists)
#   GW_PROCS=1               (GOMAXPROCS for the gateway)
#   BATCH_WINDOW=5ms BATCH_MAX=64 BATCH_SIG=first   (C3 only)
#   PAD_BYTES=0  MAX_METADATA=8192  SIG_BACKEND=  GATEWAY_URL=  PUBLIC_KEX=hybrid
#   GATEWAY_LISTEN=127.0.0.1:8443   (use 0.0.0.0:8443 when the client runs in a netns)
#   ADMIN_BIND=127.0.0.1   (0.0.0.0 when the load generator runs in a netns)
#   LG_PREFIX="ip netns exec qsbg-client"   (run the load generator inside the shaped netns)
set -euo pipefail
CONFIG=$1; OUTFILE=$2; shift 2
ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn)" 2>/dev/null || true  # open-loop overload opens many sockets
BIN=${BIN:-./bin}; CERTS=${CERTS:-./certs}
PUBKEY=$(mktemp -u /tmp/qsbg_pub_XXXX)
# exec so that $! is the real process, not a wrapper subshell
pin() { local cpus=$1; shift; if [[ -n "$cpus" ]]; then exec taskset -c "$cpus" "$@"; else exec "$@"; fi; }

wait_free() {  # wait until nothing listens on the given port
  for _ in $(seq 50); do
    if ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then return 0; fi
    sleep 0.2
  done
  echo "port $1 still in use; is an old gateway/backend running?" >&2; exit 1
}
wait_ready() {  # wait until an admin endpoint answers and reports the expected config
  local url=$1 want=$2
  for _ in $(seq 100); do
    if out=$(curl -sf "$url/stats" 2>/dev/null) && grep -q "$want" <<<"$out"; then return 0; fi
    sleep 0.1
  done
  echo "component at $url did not become ready with $want" >&2; exit 1
}

case $CONFIG in
  C0) AUTH=none;  KEX=classical ;;
  C1) AUTH=none;  KEX=hybrid ;;
  C2) AUTH=msg;   KEX=classical ;;
  C3) AUTH=batch; KEX=classical ;;
  *) echo "unknown config $CONFIG" >&2; exit 2 ;;
esac

wait_free 8443; wait_free 9443; wait_free 8901; wait_free 9901

LOGDIR=$(dirname "$OUTFILE")/logs; mkdir -p "$LOGDIR"
BASE=$(basename "$OUTFILE" .json)

( [[ -n "${GW_PROCS:-}" ]] && export GOMAXPROCS=$GW_PROCS; pin "${GW_CPUS:-}" "$BIN/gateway" -config "$CONFIG" -certs "$CERTS" -admin "${ADMIN_BIND:-127.0.0.1}:8901" \
  -listen "${GATEWAY_LISTEN:-127.0.0.1:8443}" -public-kex "${PUBLIC_KEX:-hybrid}" \
  -pubkey-out "$PUBKEY" -batch-window "${BATCH_WINDOW:-5ms}" -batch-max "${BATCH_MAX:-64}" \
  -batch-sig "${BATCH_SIG:-first}" -pad-bytes "${PAD_BYTES:-0}" ${SIG_BACKEND:+-sig-backend "$SIG_BACKEND"} \
  >"$LOGDIR/$BASE.gateway.log" 2>&1 ) &
GW=$!
cleanup() {
  kill "$GW" ${BE:-} 2>/dev/null || true
  for _ in $(seq 50); do kill -0 "$GW" 2>/dev/null || kill -0 ${BE:-$GW} 2>/dev/null || break; sleep 0.1; done
  kill -9 "$GW" ${BE:-} 2>/dev/null || true
  wait 2>/dev/null || true
  rm -f "$PUBKEY"
}
trap cleanup EXIT
wait_ready http://127.0.0.1:8901 "\"config\":\"$CONFIG\""

if [[ $AUTH != none ]]; then
  for _ in $(seq 100); do [[ -s $PUBKEY ]] && break; sleep 0.1; done
fi
pin "${BE_CPUS:-}" "$BIN/backend" -certs "$CERTS" -admin "${ADMIN_BIND:-127.0.0.1}:9901" -kex "$KEX" -auth "$AUTH" -gateway-pubkey "$PUBKEY" \
  -max-metadata "${MAX_METADATA:-8192}" ${SIG_BACKEND:+-sig-backend "$SIG_BACKEND"} \
  >"$LOGDIR/$BASE.backend.log" 2>&1 &
BE=$!
wait_ready http://127.0.0.1:9901 "\"auth\":\"$AUTH\""

( pin "${LG_CPUS:-}" ${LG_PREFIX:-} "$BIN/loadgen" -certs "$CERTS" ${GATEWAY_URL:+-url "$GATEWAY_URL"} -kex "${PUBLIC_KEX:-hybrid}" \
  -out "$OUTFILE" "$@" 2>>"$LOGDIR/$BASE.loadgen.log" )
tail -1 "$LOGDIR/$BASE.loadgen.log"
