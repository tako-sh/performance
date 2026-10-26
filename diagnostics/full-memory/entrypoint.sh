#!/usr/bin/env bash
set -euo pipefail
test "$(cat /proc/1/cgroup)" = '0::/'
mkdir /sys/fs/cgroup/control
echo $$ > /sys/fs/cgroup/control/cgroup.procs
echo '+cpu +memory +pids' > /sys/fs/cgroup/cgroup.subtree_control
ulimit -n 131072
# This container has its own network namespace. Warmup-to-measurement churn at
# 20k workers can exhaust the default 28k upstream source ports and 4096 backlog.
sysctl -w 'net.ipv4.ip_local_port_range=10240 65535' \
  net.core.somaxconn=65535 net.ipv4.tcp_max_syn_backlog=65535 > /results/network.txt
# Local builds may need a supplied native library directory. CI builds use the
# distribution's libraries. The helper intentionally clears its environment.
if [[ -d /native ]]; then
  echo /native > /etc/ld.so.conf.d/benchmark-native.conf
  ldconfig
fi
# The unmodified installer creates the production users and provisioning policy.
tar -cf - -C /build tako-server | zstd -q -o /tmp/tako-server.tar.zst
sha256sum /tmp/tako-server.tar.zst | awk '{print $1}' > /tmp/tako-server.tar.zst.sha256
TAKO_SERVER_URL=file:///tmp/tako-server.tar.zst TAKO_RESTART_SERVICE=0 \
  TAKO_SERVER_NAME=benchmark bash /source/scripts/install-tako-server.sh > /results/install.log 2>&1
exec python3 /perf/diagnostics/full-memory/run.py "$@"
