#!/usr/bin/env bash
set -euo pipefail
sed 's@exec python3 /perf/diagnostics/full-memory/run.py@exec python3 /perf/diagnostics/rate-validation/run.py@' \
  /perf/diagnostics/full-memory/entrypoint.sh > /tmp/release-entrypoint.sh
exec bash /tmp/release-entrypoint.sh "$@"
