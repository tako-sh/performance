# Tako Performance

Repeatable benchmarks for Tako, Caddy, and nginx.

See [RESULTS.md](RESULTS.md) for the baseline, high-load follow-up, raw result
links, findings, and profiling targets.

This repo contains:

- A small Go HTTP application used by every proxy candidate.
- Proxy configs for single-upstream runs, with load-balanced mode available for
  larger testbeds.
- Remote setup and restore scripts for benchmark hosts.
- A VM-local high-load harness with CPU/RAM/RPS/failure graph rendering.
- Raw benchmark output and Markdown reports.

The first baseline target was an Ubuntu 24.04 VM. The public report
intentionally omits exact hostnames, IP addresses, and private network details.

## Run

```bash
BENCH_VM=<ssh-host> ./scripts/sync-to-vm.sh
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> CONCURRENCY_LIST="100 500" ./scripts/run-http-benchmarks.sh
BENCH_VM=<ssh-host> \
TAKO_SERVER_BIN=/opt/tako-performance/bin/<tako-server-release> \
SOURCE_IPS="127.0.0.2,127.0.0.3" \
PROXIES="nginx tako caddy" \
CONCURRENCY_LIST="1000 2500 5000" \
REQUEST_TIMEOUT=60s \
COOLDOWN_SECONDS=10 \
./scripts/run-vm-local-http-benchmarks.sh
./scripts/render-metrics-graphs.sh results/<timestamp>/http-vm-local
BENCH_VM=<ssh-host> \
TAKO_SERVER_BIN=/opt/tako-performance/bin/<tako-server-release> \
COOLDOWN_SECONDS=10 \
./scripts/run-vm-local-tako-feature-benchmarks.sh
```

HTTP scripts default to `MODES=single`. Use `MODES="single lb"` only on a
larger testbed where four upstream app processes have enough CPU capacity.
HTTP scripts also default to `REQUEST_TIMEOUT=60s` so high-concurrency rows
measure overload latency instead of a short client timeout.
