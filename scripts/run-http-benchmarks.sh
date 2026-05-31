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
request_timeout="${REQUEST_TIMEOUT:-60s}"
metrics_interval="${METRICS_INTERVAL:-1}"
metrics_connections="${METRICS_CONNECTIONS:-0}"
source_ips="${SOURCE_IPS:-}"
modes="${MODES:-single}"
proxies="${PROXIES:-nginx caddy tako}"

stop_metrics() {
  ssh "$bench_vm" 'if [[ -f /tmp/tako-performance-metrics.pid ]]; then pid="$(cat /tmp/tako-performance-metrics.pid 2>/dev/null || true)"; if [[ -n "$pid" ]]; then kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; fi; rm -f /tmp/tako-performance-metrics.pid; fi' >/dev/null 2>&1 || true
}

stop_remote() {
  stop_metrics
  ssh "$bench_vm" "cd /opt/tako-performance/source && ./scripts/remote/control.sh stop" >/dev/null 2>&1 || true
}

trap stop_remote EXIT

run_case() {
  local proxy="$1"
  local mode="$2"
  local endpoint="$3"
  local concurrency="$4"
  local remote_case="$proxy-$mode"
  local name="$proxy-$mode-$endpoint-c$concurrency"

  ssh "$bench_vm" "cd /opt/tako-performance/source && ./scripts/remote/control.sh $remote_case"
  sleep 2
  ssh "$bench_vm" "cd /opt/tako-performance/source && SAMPLE_CONNECTIONS='$metrics_connections' ./scripts/remote/start-metrics.sh '$out_dir/$name-metrics.csv' '$metrics_interval'"
  ./.bin/loadgen \
    -name "$name" \
    -url "https://$bench_host:18443/$endpoint" \
    -host "$bench_host" \
    -sni "$bench_host" \
    -resolve "$bench_host:18443:$bench_ip" \
    -source-ips "$source_ips" \
    -insecure \
    -warmup "$warmup" \
    -duration "$duration" \
    -request-timeout "$request_timeout" \
    -concurrency "$concurrency" \
    > "$out_dir/$name.json"
  stop_metrics
  rsync -az "$bench_vm:/opt/tako-performance/source/$out_dir/$name-metrics.csv" "$out_dir/"
}

for concurrency in $concurrency_list; do
  for mode in $modes; do
    for proxy in $proxies; do
      for endpoint in plaintext json; do
        run_case "$proxy" "$mode" "$endpoint" "$concurrency"
      done
    done
  done
done

stop_remote
trap - EXIT
echo "$out_dir"
