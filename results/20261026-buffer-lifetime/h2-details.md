| Workload | Variant | Runs / failed | Median-phase PSS MiB (mean) | Successful RPS (mean) | p99 ms (mean) | CPU µs/success (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| h2-download | baseline | 3 / 0 | 139.09 | 841.73 | 78.40 | 1,243.43 |
| h2-download | body | 3 / 0 | 145.42 | 821.31 | 79.43 | 1,286.80 |
| h2-download | caddy | 3 / 0 | 68.49 | 264.88 | 151.86 | 4,032.21 |
| h2-download | combined | 3 / 0 | 144.79 | 846.75 | 78.33 | 1,233.34 |
| h2-download | idle | 3 / 0 | 138.69 | 840.35 | 78.63 | 1,248.77 |
| h2-rate | baseline | 3 / 0 | 66.14 | 1,000.02 | 1.51 | 273.11 |
| h2-rate | body | 3 / 0 | 66.42 | 1,000.01 | 1.50 | 272.44 |
| h2-rate | caddy | 3 / 0 | 63.00 | 1,000.03 | 1.59 | 440.00 |
| h2-rate | combined | 3 / 0 | 67.28 | 1,000.00 | 1.53 | 276.44 |
| h2-rate | idle | 3 / 0 | 65.78 | 999.99 | 1.52 | 276.44 |
| h2-small | baseline | 3 / 0 | 76.85 | 8,767.93 | 50.83 | 116.25 |
| h2-small | body | 3 / 0 | 77.08 | 8,804.39 | 50.71 | 115.74 |
| h2-small | caddy | 3 / 0 | 74.10 | 6,287.44 | 47.48 | 180.03 |
| h2-small | combined | 3 / 0 | 80.34 | 8,869.32 | 50.88 | 114.06 |
| h2-small | idle | 3 / 0 | 78.83 | 8,835.95 | 50.92 | 115.75 |
| h2-upload | baseline | 3 / 0 | 77.03 | 145.77 | 308.15 | 5,841.54 |
| h2-upload | body | 3 / 0 | 78.10 | 146.78 | 306.86 | 5,800.08 |
| h2-upload | caddy | 3 / 0 | 74.79 | 381.65 | 286.07 | 2,452.82 |
| h2-upload | combined | 3 / 0 | 75.51 | 146.76 | 305.62 | 5,789.75 |
| h2-upload | idle | 3 / 0 | 76.15 | 145.83 | 307.81 | 5,837.97 |

These are diagnostic paired experiments on shared CPU quota. Failed or incomplete cases are not performance wins.
Memory is median process PSS during measurement/holding; inspect peak PSS and every repetition in raw JSON.
CPU covers acknowledged measurement start through request drain. Compare latency at matched offered load, not only saturation.
