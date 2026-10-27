#!/usr/bin/env bash
set -euo pipefail
# Reuse the production installer and isolated cgroup/network setup.
sed 's@exec python3 /perf/diagnostics/full-memory/run.py@exec python3 /perf/diagnostics/full-suite/run.py@' \
  /perf/diagnostics/full-memory/entrypoint.sh > /tmp/full-suite-entrypoint.sh
exec bash /tmp/full-suite-entrypoint.sh "$@"
