#!/usr/bin/env bash
set -euo pipefail

out="${1:?usage: start-metrics.sh OUT.csv [INTERVAL_SECONDS]}"
interval="${2:-1}"
pidfile="${3:-/tmp/tako-performance-metrics.pid}"
sample_connections="${SAMPLE_CONNECTIONS:-0}"

mkdir -p "$(dirname "$out")"
if [[ -f "$pidfile" ]]; then
  old_pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]]; then
    kill -- "-$old_pid" 2>/dev/null || kill "$old_pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
fi
SAMPLE_CONNECTIONS="$sample_connections" setsid ./scripts/remote/sample-metrics.sh "$out" "$interval" </dev/null >/dev/null 2>&1 &
echo $! > "$pidfile"
