# Tako Proxy Performance Baseline

Date: 2026-05-31 UTC

This is the first repeatable baseline for Tako against nginx and Caddy on the
benchmark VM. The benchmark was driven from a laptop over Tailscale, using the
same TLS route, certificate, application payloads, and load generator for each
proxy. Exact hostnames, public IPs, private Tailscale IPs, MagicDNS suffixes,
peer names, and user identifiers are intentionally omitted from this public
report.

## Executive Summary

At 500 concurrent HTTP/1.1 clients over TLS, nginx was the fastest HTTP proxy in
this run. Tako single-instance was close to nginx single-instance, trailing by
about 7.4% on both plaintext and JSON responses. Tako was much faster than
Caddy in this environment: about 112% higher throughput than Caddy on the
single plaintext case.

Load-balanced Tako is the main performance gap: Tako with four upstream
instances was about 19-20% behind nginx with four upstream instances, and also
slower than Tako's single-instance case. That makes the load-balanced path the
first area to profile.

The channel and workflow benchmark initially failed on the released
`tako-server 0.0.0-ea3eb66` because app processes could not use the internal
workflow/channel Unix socket. A source fix was implemented and validated with a
patched VM-native `tako-server` build. With the patched binary, channel publish
and workflow enqueue both completed with only HTTP 200 responses.

## Test Host And Network

### Load Generator

- OS: macOS Darwin 25.5.0 arm64
- CPU count: 10
- Memory: 16 GiB
- Load snapshot before the feature benchmark: normal desktop/Codex background
  load; no process near 200% CPU or high memory.

### Server

- OS: Ubuntu 24.04.4 LTS, Linux 6.12.90, x86_64
- VM: KVM
- CPU: 2 vCPU, AMD EPYC 9554P 64-Core Processor
- Memory: 7.8 GiB, no swap
- Disk: 25 GiB root filesystem
- Tailscale relay: `tok`
- Direct public address geolocation: Tokyo, Japan, AS396356 Latitude.sh
- Public access hostname geolocation: Berkeley, CA, AS402146 Bold Software Inc,
  anycast

The public access URL was not used for the timed proxy comparison because it
redirected to an `exe.dev` login gate. Benchmarking that URL would measure the
public access layer rather than Tako, nginx, or Caddy directly. The controlled
route was:

```text
https://bench.test:18443/
Host/SNI: bench.test
Resolved to: private Tailscale address
TLS: same self-signed certificate for every proxy
```

Ping from the laptop:

| target | min ms | avg ms | max ms | stddev ms | loss |
|---|---:|---:|---:|---:|---:|
| private Tailscale route | 28.087 | 32.591 | 64.541 | 7.489 | 0% |
| public access hostname | 69.118 | 70.684 | 73.740 | 1.205 | 0% |

## Software Versions

- Tako release used for HTTP proxy comparison: `tako-server 0.0.0-ea3eb66`
- Patched Tako binary used for valid channel/workflow benchmark:
  `tako-server 0.0.0`, built on the VM from local source
- nginx: `nginx/1.24.0 (Ubuntu)`
- Caddy: `2.6.2`
- Go on VM: `go1.26.3 linux/amd64`
- Tailscale on VM: `1.98.4-t9e69045b2-ged3a62f14`

## Applications

### HTTP App

The HTTP comparison uses `cmd/benchapp`, a small Go application with identical
payloads behind all three proxies:

- `/plaintext`: `hello, world\n`, fixed `Content-Length: 13`
- `/json`: `{"message":"hello","ok":true}\n`
- `/status`: internal Tako health check endpoint when `Host: bench-http.tako`
- `/pid`: instance metadata for manual checks

Manual nginx and Caddy runs start the same Go binary on loopback ports. Tako
runs the same binary as a deployed app from:

```text
/opt/tako-performance/tako-data/apps/bench-http/production/releases/baseline-001
```

### Channels And Workflows App

The feature benchmark uses `apps/channels-workflows`, a small Bun/Tako SDK app:

- `/channel-publish`: `feed.publish({ type: "tick", data: ... })`
- `/workflow-enqueue`: `noop.enqueue({ seq, at })`
- `/status`: JSON health response

The workflow handler performs one persisted `ctx.run("ack", ...)` step and
returns immediately.

## Methodology

- One route and TLS certificate were used for all HTTP proxy comparisons:
  `bench.test:18443`.
- The load generator resolves `bench.test:18443` to the Tailscale IP and sets
  both Host and SNI to `bench.test`.
- TLS verification is disabled because the certificate is self-signed, but TLS
  is still active for every proxy.
- HTTP/2 is disabled in the load generator, so the comparison is HTTP/1.1 over
  TLS.
- Each timed case has a 5 second warmup followed by a 30 second measurement
  window.
- Single mode uses one upstream instance.
- Load-balanced mode uses four upstream instances:
  - nginx: upstream ports `9101` through `9104`
  - Caddy: upstream ports `9101` through `9104`
  - Tako: app scaled to four instances

Because the load generator is the laptop and the VM is in Tokyo, the `c=100`
run is mostly RTT/concurrency limited. The `c=500` run is more useful for proxy
comparison, but still includes real Tailscale and cross-network overhead.

## HTTP Results: 100 Concurrent Clients

Raw data: `results/20260531T043913Z/http`

| case | rps | mean ms | p95 ms | p99 ms | errors | status |
|---|---:|---:|---:|---:|---:|---|
| caddy-lb-json-c100 | 2742.56 | 36.42 | 48.27 | 57.61 | 0 | 200:82368 |
| caddy-lb-plaintext-c100 | 2721.32 | 36.71 | 48.52 | 58.28 | 0 | 200:81700 |
| caddy-single-json-c100 | 2653.42 | 37.65 | 49.29 | 60.02 | 0 | 200:79703 |
| caddy-single-plaintext-c100 | 2698.53 | 37.01 | 49.36 | 57.27 | 0 | 200:81036 |
| nginx-lb-json-c100 | 2755.39 | 36.25 | 44.95 | 51.23 | 0 | 200:82752 |
| nginx-lb-plaintext-c100 | 2743.73 | 36.4 | 45.78 | 51.24 | 0 | 200:82410 |
| nginx-single-json-c100 | 2720.52 | 36.72 | 45.17 | 51.83 | 0 | 200:81734 |
| nginx-single-plaintext-c100 | 2740.66 | 36.43 | 44.62 | 50.88 | 0 | 200:82324 |
| tako-lb-json-c100 | 2736.23 | 36.5 | 46.14 | 51.15 | 0 | 200:82185 |
| tako-lb-plaintext-c100 | 2649.75 | 37.71 | 49.87 | 59.33 | 0 | 200:79575 |
| tako-single-json-c100 | 2768.7 | 36.08 | 44.97 | 50.53 | 0 | 200:83138 |
| tako-single-plaintext-c100 | 2731.22 | 36.56 | 45.06 | 51.8 | 0 | 200:82072 |

At this concurrency, all three proxies cluster around 2.6-2.8k requests/sec.
That matches the RTT limit: `100 / ~36ms` is roughly 2.8k requests/sec.

## HTTP Results: 500 Concurrent Clients

Raw data: `results/20260531T045015Z/http`

| case | rps | mean ms | p95 ms | p99 ms | errors | status |
|---|---:|---:|---:|---:|---:|---|
| caddy-lb-json-c500 | 5408.8 | 92.3 | 139.02 | 166.91 | 0 | 200:162588 |
| caddy-lb-plaintext-c500 | 5361.73 | 93.1 | 140.98 | 164.14 | 0 | 200:161333 |
| caddy-single-json-c500 | 5733.18 | 87.05 | 129.26 | 151.82 | 0 | 200:172383 |
| caddy-single-plaintext-c500 | 5980.57 | 83.49 | 129.68 | 206.95 | 0 | 200:179811 |
| nginx-lb-json-c500 | 12586.27 | 39.64 | 54.31 | 73.55 | 0 | 200:378012 |
| nginx-lb-plaintext-c500 | 12804.48 | 38.97 | 52.7 | 76.03 | 0 | 200:384651 |
| nginx-single-json-c500 | 13567.68 | 36.78 | 45.44 | 63.53 | 0 | 200:407489 |
| nginx-single-plaintext-c500 | 13691.31 | 36.45 | 45.04 | 64.56 | 0 | 200:411206 |
| tako-lb-json-c500 | 10159.38 | 49.15 | 72.15 | 84.32 | 0 | 200:305170 |
| tako-lb-plaintext-c500 | 10229.89 | 48.82 | 70.15 | 82.3 | 0 | 200:307214 |
| tako-single-json-c500 | 12571.87 | 39.7 | 52.05 | 60.87 | 0 | 200:377592 |
| tako-single-plaintext-c500 | 12675.96 | 39.37 | 50.51 | 59.79 | 0 | 200:380687 |

Key comparisons from the 500-concurrency run:

- Tako single plaintext: 12,675.96 rps, 7.4% below nginx single plaintext.
- Tako single JSON: 12,571.87 rps, 7.3% below nginx single JSON.
- Tako load-balanced plaintext: 10,229.89 rps, 20.1% below nginx
  load-balanced plaintext.
- Tako load-balanced JSON: 10,159.38 rps, 19.3% below nginx load-balanced
  JSON.
- Tako single plaintext was about 112% faster than Caddy single plaintext.
- Tako load-balanced plaintext was about 91% faster than Caddy load-balanced
  plaintext.

## Channel And Workflow Results

Raw valid data: `results/20260531T053951Z/tako-features`

These were run with the patched VM-native `tako-server` build because the
released server failed the first feature attempt. The client sent 50 concurrent
POST requests, with the same TLS route and network path as the HTTP proxy tests.

| case | rps | mean ms | p95 ms | p99 ms | errors | status |
|---|---:|---:|---:|---:|---:|---|
| tako-feature-channel-publish-c50 | 1310.81 | 38.11 | 52.59 | 63.57 | 0 | 200:39380 |
| tako-feature-workflow-enqueue-c50 | 1100.17 | 45.41 | 65.29 | 72.81 | 0 | 200:33054 |

The invalid first attempt is preserved in
`results/20260531T050527Z/tako-features`. It returned only 502/503 responses
and is excluded from the performance result. That run exposed the internal
socket problem fixed in the source tree.

## Findings

1. Tako's normal single-instance proxy path is reasonably close to nginx in
   this cross-network TLS run. The measured gap was about 7.4% at 500
   concurrency.
2. Tako's load-balanced path underperformed its single-instance path. That is
   the clearest performance issue from this baseline.
3. Caddy 2.6.2 was much slower than both nginx and Tako in this setup.
4. The channel/workflow feature path was blocked in the released server by the
   internal socket issue. The patched source build fixed the failure and
   produced clean 200-only results.
5. The benchmark is not a pure local proxy ceiling test. It includes a real
   28-33ms Tailscale path from the laptop to Tokyo. For an additional ceiling
   benchmark, run the same harness from a same-region load generator or from a
   second VM near the benchmark VM.

## Follow-up Profiling Targets

- Profile Tako load-balanced HTTP at `c=500` and higher:
  - upstream selection path
  - per-request locking in the route/load-balancer path
  - connection reuse and keep-alive behavior to app instances
  - health/state checks on hot request paths
- Add an in-region or VM-local load generator pass to separate proxy overhead
  from Tailscale RTT.
- Add higher-concurrency runs once the load generator path is closer to the VM.
- Add repeated runs and confidence intervals after the first load-balanced Tako
  optimization pass.
- Keep channel/workflow benchmarks in CI or release validation so internal
  socket regressions fail before release.

## Reproducing

Prepare the VM from this repo:

```bash
BENCH_VM=<ssh-host> ./scripts/sync-to-vm.sh
```

Run HTTP proxy comparisons:

```bash
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> CONCURRENCY_LIST="100 500" ./scripts/run-http-benchmarks.sh
```

Run Tako channel/workflow feature benchmarks with a patched server binary on
the VM:

```bash
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> TAKO_SERVER_BIN=/opt/tako-performance/bin/tako-server-patched ./scripts/run-tako-feature-benchmarks.sh
```

Stop benchmark services:

```bash
ssh <ssh-host> 'cd /opt/tako-performance/source && ./scripts/remote/control.sh stop'
```

The sanitized environment summary is in `results/baseline-001/env/summary.md`.
