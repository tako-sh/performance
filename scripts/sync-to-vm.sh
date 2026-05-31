#!/usr/bin/env bash
set -euo pipefail

VM="${1:-${BENCH_VM:-}}"
REMOTE_ROOT=/opt/tako-performance

if [[ -z "$VM" ]]; then
  echo "usage: BENCH_VM=<ssh-host> $0" >&2
  echo "   or: $0 <ssh-host>" >&2
  exit 2
fi

ssh "$VM" "sudo mkdir -p $REMOTE_ROOT/source && sudo chown -R \$USER:\$USER $REMOTE_ROOT"
rsync -az --delete \
  --exclude .git \
  --exclude .bin \
  --exclude results \
  ./ "$VM:$REMOTE_ROOT/source/"
ssh "$VM" "cd $REMOTE_ROOT/source && chmod +x scripts/*.sh scripts/remote/*.sh scripts/remote/*.py && ./scripts/remote/setup.sh"
