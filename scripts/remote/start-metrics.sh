#!/usr/bin/env bash
set -euo pipefail

out="${1:?usage: start-metrics.sh OUT.csv [INTERVAL_SECONDS]}"
interval="${2:-1}"
pidfile="${3:-/tmp/tako-performance-metrics.pid}"
sample_connections="${SAMPLE_CONNECTIONS:-0}"

mkdir -p "$(dirname "$out")"
SAMPLE_CONNECTIONS="$sample_connections" setsid ./scripts/remote/sample-metrics.sh "$out" "$interval" </dev/null >/dev/null 2>&1 &
echo $! > "$pidfile"
