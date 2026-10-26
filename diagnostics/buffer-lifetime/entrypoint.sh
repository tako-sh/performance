#!/usr/bin/env bash
set -euo pipefail
# Reuse the exact installer, resource, and network setup of the existing harness.
# Only substitute the final runner, keeping the shared file unchanged.
sed 's@exec python3 /perf/diagnostics/full-memory/run.py@exec python3 /perf/diagnostics/buffer-lifetime/run.py@' \
  /perf/diagnostics/full-memory/entrypoint.sh > /tmp/buffer-entrypoint.sh
exec bash /tmp/buffer-entrypoint.sh "$@"
