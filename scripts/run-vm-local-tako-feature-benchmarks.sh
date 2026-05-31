#!/usr/bin/env bash
set -euo pipefail

bench_vm="${BENCH_VM:?set BENCH_VM to the benchmark VM SSH host}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="results/$timestamp/tako-features-vm-local"
remote_root=/opt/tako-performance/source

mkdir -p "$out_dir"

ssh "$bench_vm" "cd $remote_root && ./scripts/remote/setup.sh >/dev/null"
ssh "$bench_vm" "cd $remote_root && mkdir -p .bin '$out_dir' && go build -o .bin/loadgen ./cmd/loadgen"

concurrency_list="${CONCURRENCY_LIST:-500 1000 2000 4000}"
warmup="${WARMUP:-10s}"
duration="${DURATION:-30s}"
metrics_interval="${METRICS_INTERVAL:-1}"
metrics_connections="${METRICS_CONNECTIONS:-0}"
source_ips="${SOURCE_IPS:-}"
bench_host="${BENCH_HOST:-bench.test}"
tako_server_bin="${TAKO_SERVER_BIN:-/usr/local/bin/tako-server}"

stop_metrics() {
  ssh "$bench_vm" "if [[ -f /tmp/tako-performance-metrics.pid ]]; then kill \$(cat /tmp/tako-performance-metrics.pid) 2>/dev/null || true; rm -f /tmp/tako-performance-metrics.pid; fi" >/dev/null 2>&1 || true
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
    -method POST \
    -body ok \
    -content-type application/json \
    -url \"https://$bench_host:18443/$endpoint\" \
    -host \"$bench_host\" \
    -sni \"$bench_host\" \
    -resolve \"$bench_host:18443:127.0.0.1\" \
    -source-ips \"$source_ips\" \
    -insecure \
    -warmup \"$warmup\" \
    -duration \"$duration\" \
    -concurrency \"$concurrency\"' \
    > '$out_dir/$name.json'"
}

run_case() {
  local endpoint="$1"
  local concurrency="$2"
  local name="tako-feature-$endpoint-c$concurrency"

  ssh "$bench_vm" "cd $remote_root && TAKO_SERVER_BIN='$tako_server_bin' BENCH_IP=127.0.0.1 ./scripts/remote/control.sh tako-features"
  sleep 2
  ssh "$bench_vm" "cd $remote_root && SAMPLE_CONNECTIONS='$metrics_connections' ./scripts/remote/start-metrics.sh '$out_dir/$name-metrics.csv' '$metrics_interval'"
  remote_loadgen "$name" "$endpoint" "$concurrency"
  stop_metrics
  rsync -az "$bench_vm:$remote_root/$out_dir/$name.json" "$bench_vm:$remote_root/$out_dir/$name-metrics.csv" "$out_dir/"
}

for concurrency in $concurrency_list; do
  run_case channel-publish "$concurrency"
  run_case workflow-enqueue "$concurrency"
done

stop_remote
trap - EXIT
./scripts/render-metrics-graphs.sh "$out_dir" >/dev/null
echo "$out_dir"
