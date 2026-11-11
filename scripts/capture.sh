#!/usr/bin/env bash
# Count TCP segments and bytes per request on each link (paper Table 8),
# using tcpdump + tshark during a short, low-rate run.
#
# Usage: sudo scripts/capture.sh CONFIG PAYLOAD OUTDIR
# Without netns the public link is loopback port 8443; internal is port 9443.
set -euo pipefail
CFG=${1:?config}; PL=${2:-128}; OUTDIR=${3:-results/capture}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUTDIR"
PCAP="$OUTDIR/${CFG}_p${PL}.pcap"
tcpdump -i any -s 200 -w "$PCAP" 'tcp port 8443 or tcp port 9443' >/dev/null 2>&1 &
TD=$!; sleep 1
"$HERE/run_one.sh" "$CFG" "$OUTDIR/${CFG}_p${PL}.json" -mode open -rate 50 -payload "$PL" -warmup 2s -duration 10s -label capture
sleep 1; kill $TD; wait $TD 2>/dev/null || true
REQS=$(python3 -c "import json;print(json.load(open('$OUTDIR/${CFG}_p${PL}.json'))['gateway']['requests'])")
for port in 8443 9443; do
  segs=$(tshark -r "$PCAP" -Y "tcp.port==$port && tcp.len>0" 2>/dev/null | wc -l)
  bytes=$(tshark -r "$PCAP" -Y "tcp.port==$port" -T fields -e tcp.len 2>/dev/null | awk '{s+=$1} END{print s+0}')
  frags=$(tshark -r "$PCAP" -Y "tcp.port==$port && ip.flags.mf==1" 2>/dev/null | wc -l)
  echo "$CFG payload=$PL port=$port data_segments=$segs payload_bytes=$bytes ip_fragments=$frags requests~$REQS"
done | tee "$OUTDIR/${CFG}_p${PL}.txt"
echo "note: counts include warm-up and handshakes; divide by requests for an estimate, or filter by time in Wireshark."
