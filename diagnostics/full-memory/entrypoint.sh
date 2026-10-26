#!/usr/bin/env bash
set -euo pipefail
test "$(cat /proc/1/cgroup)" = '0::/'
mkdir /sys/fs/cgroup/control
echo $$ > /sys/fs/cgroup/control/cgroup.procs
echo '+cpu +memory +pids' > /sys/fs/cgroup/cgroup.subtree_control
ulimit -n 131072
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
