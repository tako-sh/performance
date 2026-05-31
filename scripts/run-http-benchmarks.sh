#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="results/$timestamp/http"
mkdir -p "$out_dir"
mkdir -p .bin

go build -o .bin/loadgen ./cmd/loadgen

bench_vm="${BENCH_VM:?set BENCH_VM to the benchmark VM SSH host}"
bench_ip="${BENCH_IP:?set BENCH_IP to the benchmark target IP}"
bench_host="${BENCH_HOST:-bench.test}"
concurrency_list="${CONCURRENCY_LIST:-100}"
warmup="${WARMUP:-10s}"
duration="${DURATION:-30s}"

run_case() {
  local proxy="$1"
  local mode="$2"
  local endpoint="$3"
  local concurrency="$4"
  local remote_case="$proxy-$mode"
  local name="$proxy-$mode-$endpoint-c$concurrency"

  ssh "$bench_vm" "cd /opt/tako-performance/source && ./scripts/remote/control.sh $remote_case"
  sleep 2
  ./.bin/loadgen \
    -name "$name" \
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

for concurrency in $concurrency_list; do
  for mode in single lb; do
    for proxy in nginx caddy tako; do
      for endpoint in plaintext json; do
        run_case "$proxy" "$mode" "$endpoint" "$concurrency"
      done
    done
  done
done

ssh "$bench_vm" "cd /opt/tako-performance/source && ./scripts/remote/control.sh stop"
echo "$out_dir"
