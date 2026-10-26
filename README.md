# Tako Performance

The [26 October production validation](results/20261026-buffer-release/README.md)
measures the buffer reclamation merged into Tako master: **55.2% less retained
memory with 20,000 held TLS connections**, and **42.0% less for uploads followed
by streaming responses**, preserving 64 KiB transfer reads. All 188 complete
correctness cases passed. The report includes longer paired and matched-rate
checks, their uncertainty, and existing Caddy bulk-transfer advantages.
Reproduce the pinned [production workflow](.github/workflows/buffer-release.yml)
using the [validation guide](diagnostics/release-validation/README.md).

The [full-server memory comparison](diagnostics/full-memory/README.md) runs Tako's
64/32/16 KiB socket-buffer experiment and a Caddy control in the dedicated
[GitHub Actions workflow](.github/workflows/memory.yml).

The [buffer lifetime experiments](diagnostics/buffer-lifetime/README.md) test idle
socket-buffer release and completed request-body release against unchanged Tako
and Caddy, including HTTP/2, bulk transfers, and streaming responses.
The [26 October investigation](results/20261026-buffer-lifetime/README.md) records
the memory savings, performance limitations and socket-count correction.

The [TLS offload investigation](results/20261026-tls-offload/README.md) compares
established-request latency, completed handshake throughput and memory after
profiling found handshake interference.

Repeatable benchmarks for Tako, nginx, Caddy, HAProxy, and Envoy.

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
PROXIES="nginx haproxy envoy tako caddy" \
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

HAProxy and Envoy cases require the matching system binaries on the benchmark
VM. All proxy cases use the same local app, HTTPS route, certificate, and
high-water request/connection protection where the proxy exposes a comparable
knob.
