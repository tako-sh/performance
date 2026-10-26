#!/usr/bin/env bash
set -euo pipefail
sed 's@exec python3 /perf/diagnostics/full-memory/run.py@exec python3 /perf/diagnostics/tls-offload/run.py@' \
  /perf/diagnostics/full-memory/entrypoint.sh > /tmp/tls-entrypoint.sh
exec bash /tmp/tls-entrypoint.sh "$@"
