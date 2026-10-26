| Workload | Variant | Runs / failed | Median-phase PSS MiB (mean) | Successful RPS (mean) | p99 ms (mean) | CPU µs/success (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| held | baseline | 3 / 0 | 2,269.86 | — | — | — |
| held | body | 3 / 0 | 2,266.81 | — | — | — |
| held | caddy | 3 / 0 | 1,049.98 | — | — | — |
| held | combined | 3 / 0 | 1,015.79 | — | — | — |
| held | idle | 3 / 1 | 1,015.15 | — | — | — |
| stream | baseline | 3 / 0 | 568.69 | — | — | — |
| stream | body | 3 / 0 | 454.32 | — | — | — |
| stream | caddy | 3 / 0 | 473.48 | — | — | — |
| stream | combined | 3 / 0 | 329.38 | — | — | — |
| stream | idle | 3 / 0 | 445.16 | — | — | — |

These are diagnostic paired experiments on shared CPU quota. Failed or incomplete cases are not performance wins.
Memory is median process PSS during measurement/holding; inspect peak PSS and every repetition in raw JSON.
CPU covers acknowledged measurement start through request drain. Compare latency at matched offered load, not only saturation.
