# Complete production buffer comparisons

Each row is the mean of the listed repetitions. Memory is median holding/measuring-phase proxy PSS. Latency and CPU use the same measurement boundaries as the raw data; saturated latency is not a matched-load comparison.

| Group | Workload | Variant | Valid cases | PSS MiB | RPS | p95 ms | p99 ms | CPU µs/success |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| memory | held | baseline | 3/3 | 2,273.68 | — | — | — | — |
| memory | held | combined | 3/3 | 1,019.02 | — | — | — | — |
| memory | held | caddy | 3/3 | 1,054.17 | — | — | — | — |
| memory | stream | baseline | 3/3 | 577.97 | — | — | — | — |
| memory | stream | combined | 3/3 | 335.30 | — | — | — | — |
| memory | stream | caddy | 3/3 | 486.44 | — | — | — | — |
| h1 | small | baseline | 3/3 | 81.65 | 15,543.59 | 5.718 | 47.805 | 67.22 |
| h1 | small | combined | 3/3 | 77.28 | 15,605.43 | 5.708 | 47.718 | 66.35 |
| h1 | small | caddy | 3/3 | 124.12 | 12,616.19 | 32.082 | 44.251 | 90.73 |
| h1 | rate | baseline | 3/3 | 65.13 | 1,000.02 | 1.283 | 1.342 | 162.67 |
| h1 | rate | combined | 3/3 | 64.35 | 1,000.03 | 1.280 | 1.341 | 162.67 |
| h1 | rate | caddy | 3/3 | 99.65 | 1,000.03 | 1.302 | 1.374 | 223.56 |
| h1 | upload | baseline | 3/3 | 78.82 | 913.14 | 72.533 | 79.189 | 997.69 |
| h1 | upload | combined | 3/3 | 79.39 | 913.74 | 72.140 | 78.157 | 997.28 |
| h1 | upload | caddy | 3/3 | 118.15 | 1,047.39 | 71.323 | 79.342 | 930.14 |
| h1 | chunked | baseline | 3/3 | 82.93 | 919.83 | 71.861 | 77.961 | 1,021.22 |
| h1 | chunked | combined | 3/3 | 81.72 | 892.55 | 72.672 | 78.548 | 1,056.59 |
| h1 | chunked | caddy | 3/3 | 115.36 | 1,069.00 | 70.536 | 79.028 | 927.28 |
| h1 | download | baseline | 3/3 | 106.65 | 1,034.66 | 68.961 | 74.046 | 1,008.32 |
| h1 | download | combined | 3/3 | 107.17 | 1,052.53 | 68.476 | 73.510 | 993.55 |
| h1 | download | caddy | 3/3 | 113.11 | 1,190.43 | 68.630 | 75.726 | 852.23 |
| h1 | churn | baseline | 3/3 | 72.89 | 1,488.47 | 53.425 | 56.773 | 842.16 |
| h1 | churn | combined | 3/3 | 69.55 | 1,526.39 | 52.902 | 56.402 | 820.18 |
| h1 | churn | caddy | 3/3 | 114.95 | 1,141.42 | 55.003 | 63.408 | 1,286.00 |
| h2 | h2-small | baseline | 3/3 | 78.85 | 14,616.18 | 6.237 | 45.873 | 69.60 |
| h2 | h2-small | combined | 3/3 | 79.26 | 14,728.20 | 6.049 | 45.876 | 68.61 |
| h2 | h2-small | caddy | 3/3 | 73.94 | 9,449.77 | 37.213 | 42.226 | 122.96 |
| h2 | h2-rate | baseline | 3/3 | 66.87 | 1,000.00 | 1.328 | 1.366 | 202.67 |
| h2 | h2-rate | combined | 3/3 | 67.04 | 1,000.01 | 1.338 | 1.372 | 204.89 |
| h2 | h2-rate | caddy | 3/3 | 62.14 | 1,000.02 | 1.367 | 1.422 | 298.67 |
| h2 | h2-upload | baseline | 3/3 | 77.39 | 252.50 | 169.397 | 183.155 | 3,292.74 |
| h2 | h2-upload | combined | 3/3 | 77.97 | 254.00 | 168.618 | 181.330 | 3,279.24 |
| h2 | h2-upload | caddy | 3/3 | 74.30 | 563.14 | 140.118 | 196.579 | 1,682.39 |
| h2 | h2-download | baseline | 3/3 | 100.83 | 550.74 | 86.338 | 214.824 | 1,607.63 |
| h2 | h2-download | combined | 3/3 | 99.80 | 538.46 | 137.224 | 266.258 | 1,597.48 |
| h2 | h2-download | caddy | 3/3 | 68.38 | 415.94 | 87.929 | 90.805 | 2,587.97 |
| small-repeat | small | baseline | 8/8 | 76.01 | 6,032.20 | 51.980 | 55.806 | 173.76 |
| small-repeat | small | combined | 8/8 | 72.24 | 6,024.16 | 51.977 | 55.760 | 173.91 |
| h2-download-repeat | h2-download | baseline | 8/8 | 97.53 | 552.28 | 102.862 | 135.446 | 1,665.76 |
| h2-download-repeat | h2-download | combined | 8/8 | 97.90 | 563.02 | 83.710 | 92.537 | 1,673.89 |
| h2-rate-repeat | h2-rate | baseline | 8/8 | 67.27 | 1,000.00 | 1.311 | 1.411 | 228.31 |
| h2-rate-repeat | h2-rate | combined | 8/8 | 66.81 | 1,000.00 | 1.312 | 1.412 | 228.23 |
| chunked-repeat | chunked | baseline | 8/8 | 80.43 | 912.31 | 74.923 | 83.160 | 926.39 |
| chunked-repeat | chunked | combined | 8/8 | 80.66 | 900.81 | 75.361 | 83.594 | 942.19 |
| chunked-rate-repeat | chunked | baseline | 8/8 | 70.54 | 249.85 | 3.875 | 4.079 | 3,130.83 |
| chunked-rate-repeat | chunked | combined | 8/8 | 70.38 | 250.00 | 3.885 | 4.102 | 3,134.00 |
