#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:-results/env}"
vm="${BENCH_VM:?set BENCH_VM to the benchmark VM SSH host}"
bench_ip="${BENCH_IP:?set BENCH_IP to the benchmark target IP}"
mkdir -p "$out_dir"

{
  date -u
  uname -srmo
  uptime
  sysctl -n hw.ncpu 2>/dev/null || true
  sysctl -n hw.memsize 2>/dev/null || true
} > "$out_dir/client.txt"

ping -c 20 "$bench_ip" | sed "s/$bench_ip/<bench-ip>/g" > "$out_dir/ping-target.txt"

ssh "$vm" '{
  date -u
  uname -srmo
  cat /etc/os-release
  echo "nproc=$(nproc)"
  lscpu
  free -h
  df -h /
  nginx -v 2>&1 || true
  caddy version 2>&1 || true
  /usr/local/bin/tako-server --version 2>&1 || true
  go version 2>&1 || true
}' > "$out_dir/vm.txt"
