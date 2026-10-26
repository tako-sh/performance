#!/usr/bin/env bash
set -euo pipefail
group="${1:?group}"
repetition="${2:?repetition}"
chmod 755 build/{tako-server,benchapp,loadgen,caddy,bun}
zstd -dc build/runtime-image.tar.zst | docker load
test "$(docker image inspect tako-full-suite --format '{{.Id}}')" = "$(cat build/runtime-image.txt)"
mkdir -p results/full-suite
cp build/{build.txt,runtime-image.txt} results/full-suite/
cpus="$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[:2])))')"
args=(--group "$group" --repetition "$repetition")
if [[ "$group" == smoke ]]; then
  args+=(--warmup 1 --duration 2 --cooldown 1)
fi
docker run --rm --privileged --cgroupns=private --cpus=2 --cpuset-cpus="$cpus" --memory=8g --memory-swap=8g \
  --mount "type=bind,src=$PWD/build,dst=/build,readonly" \
  --mount "type=bind,src=$PWD/tako-source,dst=/source,readonly" \
  --mount "type=bind,src=$PWD,dst=/perf,readonly" \
  --mount "type=bind,src=$PWD/results/full-suite,dst=/results" \
  tako-full-suite "${args[@]}"
