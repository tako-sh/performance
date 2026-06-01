#!/usr/bin/env bash
set -euo pipefail

bench_vm="${BENCH_VM:?set BENCH_VM to the benchmark VM SSH host}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="results/$timestamp/http-vm-local"
remote_root=/opt/tako-performance/source

mkdir -p "$out_dir"

ssh "$bench_vm" "cd $remote_root && ./scripts/remote/setup.sh >/dev/null"
ssh "$bench_vm" "cd $remote_root && mkdir -p .bin '$out_dir' && go build -o .bin/loadgen ./cmd/loadgen"

concurrency_list="${CONCURRENCY_LIST:-1000 2500 5000 10000}"
warmup="${WARMUP:-5s}"
duration="${DURATION:-20s}"
request_timeout="${REQUEST_TIMEOUT:-60s}"
metrics_interval="${METRICS_INTERVAL:-1}"
metrics_connections="${METRICS_CONNECTIONS:-0}"
source_ips="${SOURCE_IPS:-}"
bench_host="${BENCH_HOST:-bench.test}"
endpoints="${ENDPOINTS:-plaintext}"
modes="${MODES:-single}"
proxies="${PROXIES:-nginx caddy tako}"

stop_metrics() {
  ssh "$bench_vm" 'if [[ -f /tmp/tako-performance-metrics.pid ]]; then pid="$(cat /tmp/tako-performance-metrics.pid 2>/dev/null || true)"; if [[ -n "$pid" ]]; then kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; fi; rm -f /tmp/tako-performance-metrics.pid; fi' >/dev/null 2>&1 || true
}

stop_remote() {
  stop_metrics
  ssh "$bench_vm" "cd $remote_root && ./scripts/remote/control.sh stop" >/dev/null 2>&1 || true
}

trap stop_remote EXIT

remote_loadgen() {
  local name="$1"
  local endpoint="$2"
  local concurrency="$3"

  ssh "$bench_vm" "cd $remote_root && sudo -n sh -c 'ulimit -n 65535; exec ./.bin/loadgen \
    -name \"$name\" \
    -url \"https://$bench_host:18443/$endpoint\" \
    -host \"$bench_host\" \
    -sni \"$bench_host\" \
    -resolve \"$bench_host:18443:127.0.0.1\" \
    -source-ips \"$source_ips\" \
    -insecure \
    -warmup \"$warmup\" \
    -duration \"$duration\" \
    -request-timeout \"$request_timeout\" \
    -concurrency \"$concurrency\"' \
    > '$out_dir/$name.json'"
}

run_case() {
  local proxy="$1"
  local mode="$2"
  local endpoint="$3"
  local concurrency="$4"
  local remote_case="$proxy-$mode"
  local name="$proxy-$mode-$endpoint-c$concurrency"

  ssh "$bench_vm" "cd $remote_root && BENCH_IP=127.0.0.1 ./scripts/remote/control.sh $remote_case"
  sleep 2
  ssh "$bench_vm" "cd $remote_root && SAMPLE_CONNECTIONS='$metrics_connections' ./scripts/remote/start-metrics.sh '$out_dir/$name-metrics.csv' '$metrics_interval'"
  remote_loadgen "$name" "$endpoint" "$concurrency"
  stop_metrics
  rsync -az "$bench_vm:$remote_root/$out_dir/$name.json" "$bench_vm:$remote_root/$out_dir/$name-metrics.csv" "$out_dir/"
}

for concurrency in $concurrency_list; do
  for mode in $modes; do
    for proxy in $proxies; do
      for endpoint in $endpoints; do
        run_case "$proxy" "$mode" "$endpoint" "$concurrency"
      done
    done
  done
done

stop_remote
trap - EXIT
./scripts/render-metrics-graphs.sh "$out_dir" >/dev/null
echo "$out_dir"
