| TLS arrivals/s | Variant | Runs / failed | Foreground p95 / p99 ms | Completed RPS (foreground / background) | PSS MiB | Threads | CPU µs/total request |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | baseline | 4 / 0 | 1.41 / 1.50 | 1000.00 / — | 64.52 | 10.75 | 256.50 |
| 0 | caddy | 4 / 0 | 1.45 / 1.51 | 1000.01 / — | 110.04 | 8.00 | 321.83 |
| 0 | offload1 | 4 / 0 | 1.40 / 1.48 | 1000.00 / — | 66.72 | 11.50 | 252.83 |
| 0 | offload2 | 4 / 0 | 1.41 / 1.50 | 1000.00 / — | 67.30 | 12.75 | 257.00 |
| 1500 | baseline | 4 / 0 | 93.87 / 145.07 | 996.35 / 694.91 | 90.52 | 13.00 | 1078.93 |
| 1500 | caddy | 4 / 0 | 145.25 / 192.60 | 993.81 / 623.53 | 133.16 | 8.00 | 1306.33 |
| 1500 | offload1 | 4 / 0 | 28.16 / 33.82 | 1000.00 / 675.66 | 79.81 | 14.00 | 1073.00 |
| 1500 | offload2 | 4 / 0 | 56.33 / 69.21 | 998.69 / 669.01 | 93.18 | 14.25 | 1156.53 |
| 2500 | baseline | 4 / 0 | 91.69 / 128.66 | 995.64 / 729.79 | 90.46 | 13.75 | 1235.62 |
| 2500 | caddy | 4 / 0 | 144.25 / 184.35 | 994.20 / 662.10 | 134.52 | 8.00 | 1478.43 |
| 2500 | offload1 | 4 / 0 | 28.33 / 33.84 | 999.65 / 715.71 | 79.25 | 16.75 | 1223.86 |
| 2500 | offload2 | 4 / 0 | 55.67 / 67.79 | 997.43 / 702.85 | 90.61 | 13.75 | 1327.62 |

Foreground arrivals are fixed at 1,000 requests/s. Inspect background completion time and errors before claiming latency wins.
CPU includes both streams; throughput and memory costs still matter. Profiling is performed separately from acceptance measurements.
