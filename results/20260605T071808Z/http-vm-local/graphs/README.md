# Benchmark Graphs

Generated from result JSON and per-test metrics CSV files in `http-vm-local`.

## Summary

![HTTP 200 RPS by concurrency](throughput-200-rps.svg)

![p99 latency by concurrency](p99-latency-ms.svg)

![Non-200 response rate by concurrency](non-200-rate.svg)

![Client error rate by concurrency](client-error-rate.svg)

## caddy-single-plaintext-c10000

200 rps 1822.24 | total rps 1822.24 | p99 19732.38 ms | non-200 0% | errors 0

![CPU and memory for caddy-single-plaintext-c10000](caddy-single-plaintext-c10000.svg)

## caddy-single-plaintext-c20000

200 rps 1610.26 | total rps 1610.26 | p99 29700.99 ms | non-200 0% | errors 4418

![CPU and memory for caddy-single-plaintext-c20000](caddy-single-plaintext-c20000.svg)

## caddy-single-plaintext-c5000

200 rps 5258.34 | total rps 5260.56 | p99 5649.76 ms | non-200 0.04% | errors 0

![CPU and memory for caddy-single-plaintext-c5000](caddy-single-plaintext-c5000.svg)

## envoy-single-plaintext-c10000

200 rps 8565.68 | total rps 9387.5 | p99 6859.72 ms | non-200 8.75% | errors 0

![CPU and memory for envoy-single-plaintext-c10000](envoy-single-plaintext-c10000.svg)

## envoy-single-plaintext-c20000

200 rps 623.5 | total rps 1204.69 | p99 20396.77 ms | non-200 48.24% | errors 488

![CPU and memory for envoy-single-plaintext-c20000](envoy-single-plaintext-c20000.svg)

## envoy-single-plaintext-c5000

200 rps 4760.97 | total rps 4760.97 | p99 2749.27 ms | non-200 0% | errors 800

![CPU and memory for envoy-single-plaintext-c5000](envoy-single-plaintext-c5000.svg)

## haproxy-single-plaintext-c10000

200 rps 15737.8 | total rps 15737.8 | p99 6517.55 ms | non-200 0% | errors 0

![CPU and memory for haproxy-single-plaintext-c10000](haproxy-single-plaintext-c10000.svg)

## haproxy-single-plaintext-c20000

200 rps 11904.47 | total rps 11904.47 | p99 14387.71 ms | non-200 0% | errors 0

![CPU and memory for haproxy-single-plaintext-c20000](haproxy-single-plaintext-c20000.svg)

## haproxy-single-plaintext-c5000

200 rps 17901.23 | total rps 17901.23 | p99 1479.45 ms | non-200 0% | errors 0

![CPU and memory for haproxy-single-plaintext-c5000](haproxy-single-plaintext-c5000.svg)

## nginx-single-plaintext-c10000

200 rps 17140.68 | total rps 17140.68 | p99 1501.7 ms | non-200 0% | errors 0

![CPU and memory for nginx-single-plaintext-c10000](nginx-single-plaintext-c10000.svg)

## nginx-single-plaintext-c20000

200 rps 10286.54 | total rps 10345.08 | p99 6697.91 ms | non-200 0.57% | errors 3

![CPU and memory for nginx-single-plaintext-c20000](nginx-single-plaintext-c20000.svg)

## nginx-single-plaintext-c5000

200 rps 17974.57 | total rps 17974.57 | p99 1032.95 ms | non-200 0% | errors 0

![CPU and memory for nginx-single-plaintext-c5000](nginx-single-plaintext-c5000.svg)

## tako-single-plaintext-c10000

200 rps 10979.11 | total rps 10979.11 | p99 6435.42 ms | non-200 0% | errors 0

![CPU and memory for tako-single-plaintext-c10000](tako-single-plaintext-c10000.svg)

## tako-single-plaintext-c20000

200 rps 7818.41 | total rps 7818.41 | p99 15449.07 ms | non-200 0% | errors 0

![CPU and memory for tako-single-plaintext-c20000](tako-single-plaintext-c20000.svg)

## tako-single-plaintext-c5000

200 rps 12895.07 | total rps 12895.07 | p99 2844.62 ms | non-200 0% | errors 0

![CPU and memory for tako-single-plaintext-c5000](tako-single-plaintext-c5000.svg)

