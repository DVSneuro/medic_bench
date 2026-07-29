# MEDIC benchmark — macbook-air

Status: **complete**. Started `2026-07-29T11:16:33.038361-04:00`.

## Machine

| field | value |
| --- | --- |
| Label | macbook-air |
| Operating system | Darwin 26.5.2 |
| Kernel | 25.5.0 |
| Architecture | arm64 |
| CPU | Apple M3 |
| Physical cores | 8 |
| Logical CPUs | 8 |
| Performance cores | 4 |
| Efficiency cores | 4 |
| Installed RAM | 16.0 GiB |

The hostname is intentionally retained only in raw JSON.

## Software

| software | version / path |
| --- | --- |
| Python | 3.12.12 (/Users/tug87422/fsl/bin/python3.12) |
| warpkit | 1.4.1 |
| wk-medic | /Users/tug87422/github/medic_bench/.benchmark-tools/warpkit-1.4.1/bin/wk-medic |
| wk-apply-warp | /Users/tug87422/github/medic_bench/.benchmark-tools/warpkit-1.4.1/bin/wk-apply-warp |
| niimath | v1.0.20260726 OpenMP Clang21.0.0 BSD (64-bit MacOS) (/Users/tug87422/github/medic_bench/.benchmark-tools/niimath-9dda863702e6/bin/niimath) |
| niimath source | 9dda863702e64078ab11061df65e6824251c293f |
| niimath compiler | Apple clang version 21.0.0 (clang-2100.1.1.101)<br>Target: arm64-apple-darwin25.5.0<br>Thread model: posix<br>InstalledDir: /Library/Developer/CommandLineTools/usr/bin |
| OpenMP | LLVM libomp 21.1.5 |
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
| estimate | 1 | 79.41 s | 15.95 s | **4.98x** | 2.23 GB | 1.27 GB |
| estimate | 4 | 47.37 s | 8.90 s | **5.33x** | 2.34 GB | 1.51 GB |
| apply | 1 | 977.58 s | 11.85 s | **82.50x** | 1.00 GB | 0.59 GB |
| apply | 4 | 372.04 s | 5.50 s | **67.69x** | 1.13 GB | 0.59 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1056.99 s | 27.80 s | **38.02x** | 0.996167 |
| 4 | 419.41 s | 14.39 s | **29.14x** | 0.996167 |

### echo3 — 3 echoes, 138 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 70.03 s | 13.58 s | **5.16x** | 2.34 GB | 1.22 GB |
| estimate | 4 | 37.68 s | 9.96 s | **3.78x** | 2.30 GB | 1.54 GB |
| apply | 1 | 1199.70 s | 14.41 s | **83.24x** | 0.85 GB | 0.48 GB |
| apply | 4 | 487.44 s | 8.90 s | **54.80x** | 0.88 GB | 0.48 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1269.73 s | 28.00 s | **45.35x** | 0.996278 |
| 4 | 525.12 s | 18.86 s | **27.85x** | 0.996278 |

### openneuro-ds005123 — 4 echoes, 240 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 172.62 s | 38.96 s | **4.43x** | 2.71 GB | 3.34 GB |
| estimate | 4 | 89.53 s | 41.73 s | **2.15x** | 3.83 GB | 3.37 GB |
| apply | 1 | 3853.34 s | 43.14 s | **89.33x** | 1.62 GB | 1.02 GB |
| apply | 4 | 2025.47 s | 40.55 s | **49.95x** | 1.63 GB | 1.02 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 4025.96 s | 82.10 s | **49.04x** | 0.998199 |
| 4 | 2115.00 s | 82.28 s | **25.71x** | 0.998199 |


## Notes and incomplete work

- MacBook Air was on AC power at start (94% charging).
- Pre-run system-wide memory free was 38%; cumulative swap counters were already nonzero.
- macOS pmset thermal/performance warning levels were unavailable (IOKit 0xe00002bc).
- No external mask exists for the OpenNeuro run; both tools used internal masks.
