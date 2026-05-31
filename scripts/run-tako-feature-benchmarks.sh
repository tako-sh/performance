#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="results/$timestamp/tako-features"
mkdir -p "$out_dir"
mkdir -p .bin

go build -o .bin/loadgen ./cmd/loadgen

bench_vm="${BENCH_VM:?set BENCH_VM to the benchmark VM SSH host}"
bench_ip="${BENCH_IP:?set BENCH_IP to the benchmark target IP}"
bench_host="${BENCH_HOST:-bench.test}"
concurrency="${CONCURRENCY:-50}"
warmup="${WARMUP:-5s}"
duration="${DURATION:-30s}"
tako_server_bin="${TAKO_SERVER_BIN:-/opt/tako-performance/bin/tako-server-patched}"

ssh "$bench_vm" "cd /opt/tako-performance/source && TAKO_SERVER_BIN='$tako_server_bin' ./scripts/remote/control.sh tako-features"
sleep 2

run_case() {
  local endpoint="$1"
  local name="tako-feature-$endpoint-c$concurrency"
  ./.bin/loadgen \
    -name "$name" \
    -method POST \
    -body '{"ok":true}' \
    -content-type application/json \
    -url "https://$bench_host:18443/$endpoint" \
    -host "$bench_host" \
    -sni "$bench_host" \
    -resolve "$bench_host:18443:$bench_ip" \
    -insecure \
    -warmup "$warmup" \
    -duration "$duration" \
    -concurrency "$concurrency" \
    > "$out_dir/$name.json"
}

run_case channel-publish
run_case workflow-enqueue

ssh "$bench_vm" "cd /opt/tako-performance/source && ./scripts/remote/control.sh stop"
echo "$out_dir"
