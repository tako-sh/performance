#!/usr/bin/env bash
set -euo pipefail

dir="${1:?usage: render-metrics-graphs.sh RESULTS_DIR}"
mkdir -p "$dir/graphs"
mkdir -p .bin
go build -o .bin/metricsplot ./cmd/metricsplot
go build -o .bin/resultplot ./cmd/resultplot

index="$dir/graphs/README.md"
{
  echo "# Benchmark Graphs"
  echo
  echo "Generated from result JSON and per-test metrics CSV files in \`$(basename "$dir")\`."
  echo
} > "$index"

if compgen -G "$dir/*.json" >/dev/null; then
  ./.bin/resultplot \
    -dir "$dir" \
    -out "$dir/graphs/throughput-200-rps.svg" \
    -metric rps200 \
    -title "HTTP 200 RPS by concurrency"
  ./.bin/resultplot \
    -dir "$dir" \
    -out "$dir/graphs/p99-latency-ms.svg" \
    -metric p99 \
    -title "p99 latency by concurrency"
  ./.bin/resultplot \
    -dir "$dir" \
    -out "$dir/graphs/non-200-rate.svg" \
    -metric non200pct \
    -title "Non-200 response rate by concurrency"
  ./.bin/resultplot \
    -dir "$dir" \
    -out "$dir/graphs/client-error-rate.svg" \
    -metric errorspct \
    -title "Client error rate by concurrency"
  {
    echo "## Summary"
    echo
    echo "![HTTP 200 RPS by concurrency](throughput-200-rps.svg)"
    echo
    echo "![p99 latency by concurrency](p99-latency-ms.svg)"
    echo
    echo "![Non-200 response rate by concurrency](non-200-rate.svg)"
    echo
    echo "![Client error rate by concurrency](client-error-rate.svg)"
    echo
  } >> "$index"
fi

for csv in "$dir"/*-metrics.csv; do
  [[ -e "$csv" ]] || continue
  base="$(basename "$csv" -metrics.csv)"
  summary=""
  json="${csv%-metrics.csv}.json"
  if [[ -f "$json" ]]; then
    summary="$(jq -r '
      def n($v): (($v | tonumber) * 100 | round / 100 | tostring);
      "200 rps " + n(.requests_per_sec * ((.status_counts["200"] // 0) / .requests)) +
      " | total rps " + n(.requests_per_sec) +
      " | p99 " + n(.latency_ms.p99) + " ms" +
      " | non-200 " + n(((.requests - (.status_counts["200"] // 0)) / .requests) * 100) + "%" +
      " | errors " + (.errors | tostring)
    ' "$json")"
  fi
  ./.bin/metricsplot \
    -in "$csv" \
    -out "$dir/graphs/$base.svg" \
    -title "$base" \
    -summary "$summary"
  {
    echo "## $base"
    echo
    if [[ -n "$summary" ]]; then
      echo "$summary"
      echo
    fi
    echo "![CPU and memory for $base]($base.svg)"
    echo
  } >> "$index"
done

echo "$dir/graphs"
