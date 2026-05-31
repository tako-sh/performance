# Environment Summary

Date: 2026-05-31 UTC

Hostnames, public IPs, private Tailscale IPs, MagicDNS suffixes, peer names, and
user identifiers are intentionally omitted from this public artifact.

## Load Generator

- OS: macOS Darwin 25.5.0 arm64
- CPU count: 10
- Memory: 16 GiB
- Load condition: normal desktop/Codex background load; no runaway CPU or memory
  process observed before the timed feature benchmark.

## Server

- OS: Ubuntu 24.04.4 LTS, Linux 6.12.90, x86_64
- VM: KVM
- CPU: 2 vCPU, AMD EPYC 9554P 64-Core Processor
- Memory: 7.8 GiB, no swap
- Disk: 25 GiB root filesystem
- Region observed from the VM direct public address: Tokyo, Japan
- Public access endpoint observed through the external hostname: US anycast

## Network

| target | min ms | avg ms | max ms | stddev ms | loss |
|---|---:|---:|---:|---:|---:|
| private Tailscale route | 28.087 | 32.591 | 64.541 | 7.489 | 0% |
| public access hostname | 69.118 | 70.684 | 73.740 | 1.205 | 0% |

## Software

- Tako release used for HTTP proxy comparison: `tako-server 0.0.0-ea3eb66`
- Patched Tako binary used for channel/workflow validation: `tako-server 0.0.0`
- nginx: `nginx/1.24.0 (Ubuntu)`
- Caddy: `2.6.2`
- Go on VM: `go1.26.3 linux/amd64`
- Tailscale on VM: `1.98.4-t9e69045b2-ged3a62f14`
