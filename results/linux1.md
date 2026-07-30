# MEDIC benchmark — linux1

Status: **complete**. Started `2026-07-29T14:17:51.521140-04:00`.

## Machine

| field | value |
| --- | --- |
| Label | linux1 |
| Operating system | Linux Ubuntu 24.04.4 LTS |
| Kernel | 6.17.0-23-generic |
| Architecture | x86_64 |
| CPU | GenuineIntel Intel(R) Xeon(R) Silver 4116 CPU @ 2.10GHz |
| Physical cores | 24 |
| Logical CPUs | 48 |
| Performance cores | unavailable |
| Efficiency cores | unavailable |
| Installed RAM | 125.6 GiB |

The hostname is intentionally retained only in raw JSON.

## Software

| software | version / path |
| --- | --- |
| Python | 3.12.3 (/usr/bin/python3.12) |
| warpkit | 1.4.1 |
| wk-medic | /ZPOOL/data/projects/medic_bench/.benchmark-tools/warpkit-1.4.1/bin/wk-medic |
| wk-apply-warp | /ZPOOL/data/projects/medic_bench/.benchmark-tools/warpkit-1.4.1/bin/wk-apply-warp |
| niimath | v1.0.20260726 OpenMP GCC13.3.0 BSD (64-bit Linux) (/ZPOOL/data/projects/medic_bench/.benchmark-tools/niimath-9dda863702e6/bin/niimath) |
| niimath source | 9dda863702e64078ab11061df65e6824251c293f |
| niimath compiler | cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
Copyright (C) 2023 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. |
| OpenMP | compiler default (normally libgomp for GCC or libomp for Clang) discover from linked_libraries |
| medic_bench | 5036d63cefa92d17b80325693a646865a9e7700b |

## Datasets

| dataset | accession | snapshot / commit | subject | task | run | echoes | frames | dimensions | voxel (mm) | TE (ms) | readout (s) | PE |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- |
| echo2 | bundled | medic_bench repository content / 5036d63cefa92d17b80325693a646865a9e7700b | sub-crlab | rest | 02 | 2 | 170 | 76 × 76 × 46 | 2.803, 2.803, 2.8 | 16.8, 38.56 | 0.02025 | j |
| echo3 | bundled | medic_bench repository content / 5036d63cefa92d17b80325693a646865a9e7700b | sub-crlab | rest | 03 | 3 | 138 | 76 × 76 × 46 | 2.803, 2.803, 2.8 | 14.8, 34.38, 53.94 | 0.02025 | j |
| openneuro-ds005123 | ds005123 | 1.1.3 / a3213b56b7bd27d7e3ac10577558eb26bb7c2a61 | sub-10317 | ugr | 1 | 4 | 240 | 80 × 80 × 51 | 2.7, 2.7, 2.97 | 13.8, 31.54, 49.28, 67.02 | 0.0193552 | j- |

## Measurements

### echo2 — 2 echoes, 170 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 216.34 s | 56.65 s | **3.82x** | 2.48 GB | 1.23 GB |
| estimate | 16 | 98.48 s | 15.72 s | **6.26x** | 2.73 GB | 1.32 GB |
| apply | 1 | 2614.95 s | 40.45 s | **64.64x** | 1.13 GB | 0.51 GB |
| apply | 16 | 973.22 s | 5.44 s | **178.76x** | 1.13 GB | 0.50 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2831.28 s | 97.10 s | **29.16x** | 1.00 |
| 16 | 1071.70 s | 21.17 s | **50.63x** | 1.00 |

### echo3 — 3 echoes, 138 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 173.82 s | 46.41 s | **3.75x** | 2.19 GB | 1.27 GB |
| estimate | 16 | 80.12 s | 13.29 s | **6.03x** | 2.78 GB | 1.36 GB |
| apply | 1 | 3323.19 s | 48.94 s | **67.91x** | 0.94 GB | 0.41 GB |
| apply | 16 | 1229.21 s | 7.07 s | **173.80x** | 0.94 GB | 0.41 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3497.01 s | 95.35 s | **36.68x** | 1.00 |
| 16 | 1309.33 s | 20.36 s | **64.31x** | 1.00 |

### openneuro-ds005123 — 4 echoes, 240 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 399.96 s | 130.64 s | **3.06x** | 5.13 GB | 3.29 GB |
| estimate | 16 | 213.65 s | 40.10 s | **5.33x** | 4.95 GB | 3.41 GB |
| apply | 1 | 11033.54 s | 148.10 s | **74.50x** | 1.88 GB | 0.88 GB |
| apply | 16 | 4817.74 s | 19.17 s | **251.36x** | 1.87 GB | 0.87 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 11433.50 s | 278.74 s | **41.02x** | 1.00 |
| 16 | 5031.39 s | 59.27 s | **84.89x** | 1.00 |


## Notes and incomplete work

- No external mask exists for the OpenNeuro run; both tools used internal masks.
