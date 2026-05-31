#!/usr/bin/env bash
set -euo pipefail

out="${1:?usage: sample-metrics.sh OUT.csv [INTERVAL_SECONDS]}"
interval="${2:-1}"
sample_connections="${SAMPLE_CONNECTIONS:-0}"

mkdir -p "$(dirname "$out")"
app_pattern='/opt/tako-performance/.*/benchapp|/opt/tako-performance/bin/benchapp|/opt/tako-performance/tako-data/.*/bun'
proxy_pattern='tako-server|nginx: worker|nginx: master|caddy run'
loadgen_pattern='(^| )(\./)?\.bin/loadgen|/opt/tako-performance/source/.bin/loadgen|/opt/tako-performance/.*/loadgen'

printf 'timestamp,cpu_pct,mem_used_bytes,mem_available_bytes,load1,load5,load15,bench_rss_bytes,proxy_rss_bytes,conn_established,app_cpu_pct,proxy_cpu_pct,loadgen_cpu_pct,loadgen_rss_bytes\n' > "$out"

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
  local sum_kib=0
  local cmdline_file pid_dir pid cmdline rss_kib
  for cmdline_file in /proc/[0-9]*/cmdline; do
    pid_dir="${cmdline_file%/cmdline}"
    pid="${pid_dir##*/}"
    [[ -r "$cmdline_file" && -r "/proc/$pid/status" ]] || continue
    cmdline="$(tr '\0' ' ' < "$cmdline_file" 2>/dev/null || true)"
    [[ -n "$cmdline" ]] || continue
    [[ "$cmdline" =~ $pattern ]] || continue
    rss_kib="$(awk '/^VmRSS:/ { print $2 }' "/proc/$pid/status" 2>/dev/null || true)"
    [[ -n "$rss_kib" ]] || rss_kib=0
    sum_kib=$((sum_kib + rss_kib))
  done
  echo $((sum_kib * 1024))
}

sum_jiffies() {
  local pattern="$1"
  local sum=0
  local cmdline_file pid_dir pid cmdline stat rest
  local fields
  for cmdline_file in /proc/[0-9]*/cmdline; do
    pid_dir="${cmdline_file%/cmdline}"
    pid="${pid_dir##*/}"
    [[ -r "$cmdline_file" && -r "/proc/$pid/stat" ]] || continue
    cmdline="$(tr '\0' ' ' < "$cmdline_file" 2>/dev/null || true)"
    [[ -n "$cmdline" ]] || continue
    [[ "$cmdline" =~ $pattern ]] || continue
    stat="$(< "/proc/$pid/stat")"
    rest="${stat##*) }"
    fields=($rest)
    if [[ "${#fields[@]}" -gt 12 ]]; then
      sum=$((sum + fields[11] + fields[12]))
    fi
  done
  echo "$sum"
}

proc_cpu_pct() {
  local delta="$1"
  if [[ "$total_delta" -le 0 ]]; then
    echo "0"
    return
  fi
  awk -v delta="$delta" -v total="$total_delta" 'BEGIN { printf "%.2f", delta * 100 / total }'
}

read prev_total prev_idle < <(read_cpu)
prev_app_jiffies="$(sum_jiffies "$app_pattern")"
prev_proxy_jiffies="$(sum_jiffies "$proxy_pattern")"
prev_loadgen_jiffies="$(sum_jiffies "$loadgen_pattern")"
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

  app_jiffies="$(sum_jiffies "$app_pattern")"
  proxy_jiffies="$(sum_jiffies "$proxy_pattern")"
  loadgen_jiffies="$(sum_jiffies "$loadgen_pattern")"
  app_cpu_pct="$(proc_cpu_pct "$((app_jiffies - prev_app_jiffies))")"
  proxy_cpu_pct="$(proc_cpu_pct "$((proxy_jiffies - prev_proxy_jiffies))")"
  loadgen_cpu_pct="$(proc_cpu_pct "$((loadgen_jiffies - prev_loadgen_jiffies))")"
  prev_app_jiffies="$app_jiffies"
  prev_proxy_jiffies="$proxy_jiffies"
  prev_loadgen_jiffies="$loadgen_jiffies"

  read mem_used mem_available < <(read_mem)
  read load1 load5 load15 _ < /proc/loadavg
  bench_rss="$(sum_rss "$app_pattern")"
  proxy_rss="$(sum_rss "$proxy_pattern")"
  loadgen_rss="$(sum_rss "$loadgen_pattern")"
  conn_established="0"
  if [[ "$sample_connections" == "1" ]]; then
    conn_established="$(ss -tan state established '( sport = :18443 )' 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')"
  fi

  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$cpu_pct" \
    "$mem_used" \
    "$mem_available" \
    "$load1" \
    "$load5" \
    "$load15" \
    "$bench_rss" \
    "$proxy_rss" \
    "$conn_established" \
    "$app_cpu_pct" \
    "$proxy_cpu_pct" \
    "$loadgen_cpu_pct" \
    "$loadgen_rss" >> "$out"
done
