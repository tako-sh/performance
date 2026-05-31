#!/usr/bin/env bash
set -euo pipefail

out="${1:?usage: sample-metrics.sh OUT.csv [INTERVAL_SECONDS]}"
interval="${2:-1}"
sample_connections="${SAMPLE_CONNECTIONS:-0}"

mkdir -p "$(dirname "$out")"
printf 'timestamp,cpu_pct,mem_used_bytes,mem_available_bytes,load1,load5,load15,bench_rss_bytes,proxy_rss_bytes,conn_established\n' > "$out"

read_cpu() {
  awk '/^cpu / {
    idle=$5+$6
    total=0
    for (i=2; i<=NF; i++) total += $i
    print total, idle
  }' /proc/stat
}

read_mem() {
  awk '
    /^MemTotal:/ { total=$2 * 1024 }
    /^MemAvailable:/ { available=$2 * 1024 }
    END { print total - available, available }
  ' /proc/meminfo
}

sum_rss() {
  local pattern="$1"
  ps -eo rss=,args= | awk -v pattern="$pattern" '$0 ~ pattern { sum += $1 } END { print sum * 1024 }'
}

read prev_total prev_idle < <(read_cpu)
while true; do
  sleep "$interval"
  read total idle < <(read_cpu)
  total_delta=$((total - prev_total))
  idle_delta=$((idle - prev_idle))
  cpu_pct="0"
  if [[ "$total_delta" -gt 0 ]]; then
    cpu_pct="$(awk -v total="$total_delta" -v idle="$idle_delta" 'BEGIN { printf "%.2f", (total - idle) * 100 / total }')"
  fi
  prev_total="$total"
  prev_idle="$idle"

  read mem_used mem_available < <(read_mem)
  read load1 load5 load15 _ < /proc/loadavg
  bench_rss="$(sum_rss '/opt/tako-performance/.*/benchapp|/opt/tako-performance/bin/benchapp|/opt/tako-performance/tako-data/.*/bun')"
  proxy_rss="$(sum_rss 'tako-server|nginx: worker|nginx: master|caddy run')"
  conn_established="0"
  if [[ "$sample_connections" == "1" ]]; then
    conn_established="$(ss -tan state established '( sport = :18443 )' 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')"
  fi

  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$cpu_pct" \
    "$mem_used" \
    "$mem_available" \
    "$load1" \
    "$load5" \
    "$load15" \
    "$bench_rss" \
    "$proxy_rss" \
    "$conn_established" >> "$out"
done
