| Workload | Variant | Runs / failed | Median-phase PSS MiB (mean) | Successful RPS (mean) | p99 ms (mean) | CPU µs/success (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| chunked | baseline | 3 / 0 | 81.06 | 626.57 | 96.68 | 1,468.52 |
| chunked | body | 3 / 0 | 80.37 | 630.84 | 95.04 | 1,463.68 |
| chunked | caddy | 3 / 0 | 113.89 | 709.28 | 138.27 | 1,462.46 |
| chunked | combined | 3 / 0 | 79.50 | 651.27 | 93.69 | 1,407.69 |
| chunked | idle | 3 / 0 | 81.38 | 627.33 | 94.80 | 1,481.81 |
| churn | baseline | 3 / 0 | 72.28 | 1,256.36 | 61.87 | 942.04 |
| churn | body | 3 / 0 | 72.55 | 1,279.41 | 61.19 | 931.27 |
| churn | caddy | 3 / 0 | 114.12 | 880.05 | 74.57 | 1,646.78 |
| churn | combined | 3 / 0 | 69.22 | 1,278.39 | 61.48 | 927.94 |
| churn | idle | 3 / 0 | 70.42 | 1,267.38 | 61.42 | 936.38 |
| download | baseline | 3 / 0 | 138.78 | 592.97 | 87.35 | 1,980.78 |
| download | body | 3 / 0 | 148.32 | 607.64 | 85.66 | 1,936.13 |
| download | caddy | 3 / 0 | 112.59 | 880.65 | 88.17 | 1,272.58 |
| download | combined | 3 / 0 | 143.07 | 609.83 | 85.41 | 1,923.71 |
| download | idle | 3 / 0 | 144.46 | 601.56 | 86.42 | 1,946.78 |
| rate | baseline | 3 / 0 | 65.45 | 1,000.00 | 1.35 | 186.22 |
| rate | body | 3 / 0 | 64.80 | 1,000.01 | 1.36 | 185.78 |
| rate | caddy | 3 / 0 | 93.40 | 1,000.01 | 1.37 | 252.22 |
| rate | combined | 3 / 0 | 65.12 | 1,000.01 | 1.36 | 186.44 |
| rate | idle | 3 / 0 | 64.42 | 1,000.02 | 1.36 | 187.33 |
| small | baseline | 3 / 0 | 78.00 | 9,944.66 | 51.44 | 105.92 |
| small | body | 3 / 0 | 77.78 | 9,658.99 | 51.53 | 109.07 |
| small | caddy | 3 / 0 | 122.66 | 9,571.34 | 49.45 | 112.62 |
| small | combined | 3 / 0 | 74.38 | 9,856.35 | 51.73 | 106.58 |
| small | idle | 3 / 0 | 73.12 | 9,863.50 | 51.43 | 107.72 |
| upload | baseline | 3 / 0 | 82.19 | 627.63 | 93.90 | 1,437.67 |
| upload | body | 3 / 0 | 79.26 | 660.00 | 92.10 | 1,360.59 |
| upload | caddy | 3 / 0 | 117.12 | 760.77 | 92.35 | 1,318.69 |
| upload | combined | 3 / 0 | 81.92 | 649.05 | 91.29 | 1,379.13 |
| upload | idle | 3 / 0 | 81.44 | 646.79 | 92.83 | 1,388.17 |

These are diagnostic paired experiments on shared CPU quota. Failed or incomplete cases are not performance wins.
Memory is median process PSS during measurement/holding; inspect peak PSS and every repetition in raw JSON.
CPU covers acknowledged measurement start through request drain. Compare latency at matched offered load, not only saturation.
