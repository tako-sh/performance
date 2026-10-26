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

The workflow pins the Tako revision, Rust and Go versions, Caddy and plugin
dependencies, and Ubuntu image digest. It uploads raw samples, request results,
binary hashes, resource limits, and source revisions as an artifact. Runtime logs
stay in the local output directory; they can contain build-machine source paths.

## Workload and interpretation

- 5,000 and 20,000 concurrent workers; 16 loopback client IPs avoid Tako's
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

## Local run

Use Linux with Docker and cgroup v2. Follow the workflow's build commands to
produce `build/{tako-server,benchapp,loadgen,caddy}`. Then run its Docker commands.
The runner accepts `--concurrency 5000 --duration 20 --repetitions 2`; use
`--concurrency 20 --duration 2 --warmup 1 --repetitions 1` for a smoke test.

Results belong in a new output directory on every invocation. Keep published
performance tables unchanged until complete comparable runs support an update.
