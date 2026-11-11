#!/usr/bin/env bash
# Network emulation for the public (client <-> gateway) link, paper Table 4.
# Puts the load generator in its own network namespace joined to the host by a
# veth pair, and shapes BOTH directions. Gateway and backend stay on the host,
# so the internal link (loopback) is unshaped.
#
#   sudo scripts/netem.sh up constrained   # 10 Mbit/s, 25 ms each way (RTT 50 ms), 0.2% loss
#   sudo scripts/netem.sh up fast          # 100 Mbit/s, 25 ms each way, 0% loss
#   sudo scripts/netem.sh show
#   sudo scripts/netem.sh down
#
# Afterwards: gateway reachable from the client at https://10.77.0.1:8443.
# Requires: iproute2 (ip, tc) and the sch_netem kernel module.
set -euo pipefail
NS=qsbg-client; HOST_IF=qsbg-h; NS_IF=qsbg-c
HOST_IP=10.77.0.1; NS_IP=10.77.0.2

profile_args() {
  case $1 in
    constrained) echo "delay 25ms loss 0.2% rate 10mbit limit 10000" ;;
    fast)        echo "delay 25ms rate 100mbit limit 10000" ;;
    *) echo "unknown profile $1 (constrained|fast)" >&2; exit 2 ;;
  esac
}

case ${1:-} in
  up)
    PROFILE=${2:?profile}
    ARGS=$(profile_args "$PROFILE")
    ip netns add $NS 2>/dev/null || true
    ip link add $HOST_IF type veth peer name $NS_IF 2>/dev/null || true
    ip link set $NS_IF netns $NS 2>/dev/null || true
    ip addr replace $HOST_IP/24 dev $HOST_IF
    ip link set $HOST_IF up mtu 1500
    ip netns exec $NS ip addr replace $NS_IP/24 dev $NS_IF
    ip netns exec $NS ip link set $NS_IF up mtu 1500
    ip netns exec $NS ip link set lo up
    # disable offloads so packet sizes on the wire match the MTU
    ethtool -K $HOST_IF tso off gso off gro off 2>/dev/null || true
    ip netns exec $NS ethtool -K $NS_IF tso off gso off gro off 2>/dev/null || true
    tc qdisc replace dev $HOST_IF root netem $ARGS
    ip netns exec $NS tc qdisc replace dev $NS_IF root netem $ARGS
    echo "netem profile '$PROFILE' applied: $ARGS (each direction)"
    ;;
  show)
    tc qdisc show dev $HOST_IF; ip netns exec $NS tc qdisc show dev $NS_IF
    ip netns exec $NS ping -c 3 $HOST_IP
    ;;
  down)
    ip link del $HOST_IF 2>/dev/null || true
    ip netns del $NS 2>/dev/null || true
    echo "netem removed"
    ;;
  *) echo "usage: $0 up constrained|fast | show | down" >&2; exit 2 ;;
esac
