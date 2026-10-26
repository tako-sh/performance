# Full Tako memory comparison

Run the complete Tako server with a deployed Go app, production app provisioning,
and TLS HTTP/1.1 traffic. Compare its 64 KiB default accepted-socket read buffer
against 32 KiB and 16 KiB, and a pinned Caddy build with its per-IP rate-limit
plugin. The patch is for measurement only and does not change production defaults.

The [memory workflow](../../.github/workflows/memory.yml) lives in this performance
repository. It uses the free standard runner for public repositories, then limits
the disposable test container to 2 CPUs, 8 GiB, and no swap. Both proxies, their
upstream app, and the client share that limit. Cgroups and app identities are set
up by Tako's original installer. The container has a private cgroup namespace;
never mount the host cgroup tree into it.

The private network namespace uses ephemeral ports 10240–65535 and 65535-entry
listen/SYN backlogs for both proxies and their apps. The initial untuned 20k run
exhausted the default 28,232 upstream source ports during connection churn and
hit upstream health-check timeouts. These kernel settings are recorded in each
result and do not modify the host or Tako's connection/health-check policies.
The public listener ports are reserved from ephemeral allocation, and Caddy uses
a fresh upstream port per case, as Tako's deployed app already does.

The workflow pins the Tako revision, Rust and Go versions, Caddy and plugin
dependencies, and Ubuntu image digest. It uploads raw samples, request results,
binary hashes, resource limits, and source revisions as an artifact. Runtime logs
stay in the local output directory; they can contain build-machine source paths.

## Workload and interpretation

- 5,000 concurrent workers; 16 loopback client IPs avoid Tako's
  per-IP active-request limit. Each case starts fresh proxy processes.
- 5 seconds of warmup and 20 seconds measured load, twice with reversed variant
  order. Small responses, TLS HTTP/1.1, one upstream instance, same certificate.
- PSS, RSS, and private pages sampled every 250 ms for the proxy process. Peaks
  include warmup and connection churn; the existing load generator closes idle
  connections between warmup and timing. Client and upstream memory are excluded.
- Any transport error or non-200 response marks a case unsuccessful. Examine
  throughput and latency alongside memory. Established TCP connections on the
  TLS listener are also counted approximately every 5 seconds. Worker count is
  not proof that exactly that many TLS sessions remained active throughout.
- These are short shared-host experiments, not capacity guarantees. HTTP/2,
  uploads, downloads, long-duration retention, and PROXY protocol require separate
  checks before changing Tako's defaults. The temporary patch does not affect the
  custom PROXY-protocol listener, upstream sockets, or HTTP body buffers.

The second mode (`--mode held --concurrency 20000`) opens exactly 20,000 TLS
connections, performs 21 verified requests per connection with at most 64 requests
in flight, then holds every connection open for ten seconds. It reports median
PSS during that holding phase and verifies the established-connection count.
This measures retained connection memory without saturating the upstream. It
does not measure maximum throughput. Both modes run twice in reverse order in CI.

The optional workflow-dispatch `stress` input runs 20,000 continuously active
workers as well. Local runs overloaded the upstream and triggered health checks;
those failing cases remain explicitly unsuccessful and are not capacity wins.

## Requirement for changing the production default

Memory savings must preserve performance. A candidate must satisfy both of these
comparisons under the same workload and resource limits:

- No repeatable regression against unchanged Tako (64 KiB) in throughput,
  p95/p99 latency, or CPU per request/transferred byte.
- Remain faster than Caddy on the compared workloads, with successful responses.
  Staying ahead of Caddy does not justify a slowdown relative to current Tako.

Check small requests, large uploads and downloads, HTTP/1.1 and HTTP/2, and steady
connections and connection churn. Compare tail latency at matched offered load;
verify that the client is not the throughput bottleneck. Use enough paired trials
to establish measurement uncertainty. An inconclusive difference requires more
measurement; it does not establish absence of a regression. There is no approved
percentage of slowdown to exchange for lower memory use.

The current two short active repetitions and held-connection tests establish
memory savings and basic correctness. A successful memory workflow does **not**
certify this performance requirement. Neither smaller buffer is approved as the
production default by these results alone.

## Local run

Use Linux with Docker and cgroup v2. Follow the workflow's build commands to
produce `build/{tako-server,benchapp,loadgen,hold-connections,caddy}`. Then run its Docker commands.
The runner accepts `--concurrency 5000 --duration 20 --repetitions 2`; use
`--concurrency 20 --duration 2 --warmup 1 --repetitions 1` for a smoke test.

Results belong in a new output directory on every invocation. Keep published
performance tables unchanged until complete comparable runs support an update.
