#!/usr/bin/env bash
set -euo pipefail

dir="${1:?usage: render-metrics-graphs.sh RESULTS_DIR}"
mkdir -p "$dir/graphs"
mkdir -p .bin
go build -o .bin/metricsplot ./cmd/metricsplot

for csv in "$dir"/*-metrics.csv; do
  [[ -e "$csv" ]] || continue
  base="$(basename "$csv" -metrics.csv)"
  ./.bin/metricsplot \
    -in "$csv" \
    -out "$dir/graphs/$base.svg" \
    -title "$base"
done

echo "$dir/graphs"
