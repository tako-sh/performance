# Tako Performance

Repeatable benchmarks for Tako, Caddy, and nginx.

See [PERFORMANCE.md](PERFORMANCE.md) for the first baseline, raw result links,
findings, and follow-up profiling targets.

This repo contains:

- A small Go HTTP application used by every proxy candidate.
- Proxy configs for single-upstream and load-balanced runs.
- Remote setup and restore scripts for benchmark hosts.
- A VM-local high-load harness with CPU/RAM graph rendering.
- Raw benchmark output and Markdown reports.

The first baseline target was an Ubuntu 24.04 VM reachable over Tailscale. The
public report intentionally omits exact hostnames and IP addresses.

## Run

```bash
BENCH_VM=<ssh-host> ./scripts/sync-to-vm.sh
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> CONCURRENCY_LIST="100 500" ./scripts/run-http-benchmarks.sh
BENCH_VM=<ssh-host> SOURCE_IPS="127.0.0.2,127.0.0.3" CONCURRENCY_LIST="1000 2500 5000" ./scripts/run-vm-local-http-benchmarks.sh
./scripts/render-metrics-graphs.sh results/<timestamp>/http-vm-local
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> TAKO_SERVER_BIN=/opt/tako-performance/bin/tako-server-patched ./scripts/run-tako-feature-benchmarks.sh
```
