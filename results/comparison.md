# MEDIC cross-platform benchmark

This report separates computational efficiency (wall time and peak RSS) from corrected-image agreement (correlation). Correlation alone does not establish numerical equivalence.

## macbook-air machine

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

## linux1 machine

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

Hostnames are retained only in the raw JSON files.

## Software

### macbook-air

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

### linux1

| software | version / path |
| --- | --- |
| Python | 3.12.3 (/usr/bin/python3.12) |
| warpkit | 1.4.1 |
| wk-medic | /ZPOOL/data/projects/medic_bench/.benchmark-tools/warpkit-1.4.1/bin/wk-medic |
| wk-apply-warp | /ZPOOL/data/projects/medic_bench/.benchmark-tools/warpkit-1.4.1/bin/wk-apply-warp |
| niimath | v1.0.20260726 OpenMP GCC13.3.0 BSD (64-bit Linux) (/ZPOOL/data/projects/medic_bench/.benchmark-tools/niimath-9dda863702e6/bin/niimath) |
| niimath source | 9dda863702e64078ab11061df65e6824251c293f |
| niimath compiler | cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0<br>Copyright (C) 2023 Free Software Foundation, Inc.<br>This is free software; see the source for copying conditions.  There is NO<br>warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. |
| OpenMP | compiler default (normally libgomp for GCC or libomp for Clang) discover from linked_libraries |
| medic_bench | 5036d63cefa92d17b80325693a646865a9e7700b |

## Per-machine measurements

### macbook-air

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

### linux1

### echo2 — 2 echoes, 170 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 216.34 s | 56.65 s | **3.82x** | 2.48 GB | 1.23 GB |
| estimate | 16 | 98.48 s | 15.72 s | **6.26x** | 2.73 GB | 1.32 GB |
| apply | 1 | 2614.95 s | 40.45 s | **64.64x** | 1.13 GB | 0.51 GB |
| apply | 16 | 973.22 s | 5.44 s | **178.76x** | 1.13 GB | 0.50 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2831.28 s | 97.10 s | **29.16x** | 0.996167 |
| 16 | 1071.70 s | 21.17 s | **50.63x** | 0.996167 |

### echo3 — 3 echoes, 138 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 173.82 s | 46.41 s | **3.75x** | 2.19 GB | 1.27 GB |
| estimate | 16 | 80.12 s | 13.29 s | **6.03x** | 2.78 GB | 1.36 GB |
| apply | 1 | 3323.19 s | 48.94 s | **67.91x** | 0.94 GB | 0.41 GB |
| apply | 16 | 1229.21 s | 7.07 s | **173.80x** | 0.94 GB | 0.41 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3497.01 s | 95.35 s | **36.68x** | 0.996278 |
| 16 | 1309.33 s | 20.36 s | **64.31x** | 0.996278 |

### openneuro-ds005123 — 4 echoes, 240 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| estimate | 1 | 399.96 s | 130.64 s | **3.06x** | 5.13 GB | 3.29 GB |
| estimate | 16 | 213.65 s | 40.10 s | **5.33x** | 4.95 GB | 3.41 GB |
| apply | 1 | 11033.54 s | 148.10 s | **74.50x** | 1.88 GB | 0.88 GB |
| apply | 16 | 4817.74 s | 19.17 s | **251.36x** | 1.87 GB | 0.87 GB |

| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 11433.50 s | 278.74 s | **41.02x** | 0.998199 |
| 16 | 5031.39 s | 59.27 s | **84.89x** | 0.998199 |


## Notes and incomplete work

- No external mask exists for the OpenNeuro run; both tools used internal masks.

## Direct cross-system wall-time comparison

A ratio above 1 means the second machine took longer. Native rows compare each platform's recorded default multithreaded count, which can differ.

| dataset | setting | tool | stage | macbook-air | linux1 | linux1 / macbook-air |
| --- | --- | --- | --- | ---: | ---: | ---: |
| echo2 | 1 thread | warpkit | estimate | 79.41 s | 216.34 s | 2.72x |
| echo2 | 1 thread | warpkit | apply | 977.58 s | 2614.95 s | 2.67x |
| echo2 | 1 thread | warpkit | end to end | 1056.99 s | 2831.28 s | 2.68x |
| echo2 | 1 thread | niimath | estimate | 15.95 s | 56.65 s | 3.55x |
| echo2 | 1 thread | niimath | apply | 11.85 s | 40.45 s | 3.41x |
| echo2 | 1 thread | niimath | end to end | 27.80 s | 97.10 s | 3.49x |
| echo2 | native (4 vs 16 threads) | warpkit | estimate | 47.37 s | 98.48 s | 2.08x |
| echo2 | native (4 vs 16 threads) | warpkit | apply | 372.04 s | 973.22 s | 2.62x |
| echo2 | native (4 vs 16 threads) | warpkit | end to end | 419.41 s | 1071.70 s | 2.56x |
| echo2 | native (4 vs 16 threads) | niimath | estimate | 8.90 s | 15.72 s | 1.77x |
| echo2 | native (4 vs 16 threads) | niimath | apply | 5.50 s | 5.44 s | 0.99x |
| echo2 | native (4 vs 16 threads) | niimath | end to end | 14.39 s | 21.17 s | 1.47x |
| echo3 | 1 thread | warpkit | estimate | 70.03 s | 173.82 s | 2.48x |
| echo3 | 1 thread | warpkit | apply | 1199.70 s | 3323.19 s | 2.77x |
| echo3 | 1 thread | warpkit | end to end | 1269.73 s | 3497.01 s | 2.75x |
| echo3 | 1 thread | niimath | estimate | 13.58 s | 46.41 s | 3.42x |
| echo3 | 1 thread | niimath | apply | 14.41 s | 48.94 s | 3.40x |
| echo3 | 1 thread | niimath | end to end | 28.00 s | 95.35 s | 3.41x |
| echo3 | native (4 vs 16 threads) | warpkit | estimate | 37.68 s | 80.12 s | 2.13x |
| echo3 | native (4 vs 16 threads) | warpkit | apply | 487.44 s | 1229.21 s | 2.52x |
| echo3 | native (4 vs 16 threads) | warpkit | end to end | 525.12 s | 1309.33 s | 2.49x |
| echo3 | native (4 vs 16 threads) | niimath | estimate | 9.96 s | 13.29 s | 1.33x |
| echo3 | native (4 vs 16 threads) | niimath | apply | 8.90 s | 7.07 s | 0.80x |
| echo3 | native (4 vs 16 threads) | niimath | end to end | 18.86 s | 20.36 s | 1.08x |
| openneuro-ds005123 | 1 thread | warpkit | estimate | 172.62 s | 399.96 s | 2.32x |
| openneuro-ds005123 | 1 thread | warpkit | apply | 3853.34 s | 11033.54 s | 2.86x |
| openneuro-ds005123 | 1 thread | warpkit | end to end | 4025.96 s | 11433.50 s | 2.84x |
| openneuro-ds005123 | 1 thread | niimath | estimate | 38.96 s | 130.64 s | 3.35x |
| openneuro-ds005123 | 1 thread | niimath | apply | 43.14 s | 148.10 s | 3.43x |
| openneuro-ds005123 | 1 thread | niimath | end to end | 82.10 s | 278.74 s | 3.40x |
| openneuro-ds005123 | native (4 vs 16 threads) | warpkit | estimate | 89.53 s | 213.65 s | 2.39x |
| openneuro-ds005123 | native (4 vs 16 threads) | warpkit | apply | 2025.47 s | 4817.74 s | 2.38x |
| openneuro-ds005123 | native (4 vs 16 threads) | warpkit | end to end | 2115.00 s | 5031.39 s | 2.38x |
| openneuro-ds005123 | native (4 vs 16 threads) | niimath | estimate | 41.73 s | 40.10 s | 0.96x |
| openneuro-ds005123 | native (4 vs 16 threads) | niimath | apply | 40.55 s | 19.17 s | 0.47x |
| openneuro-ds005123 | native (4 vs 16 threads) | niimath | end to end | 82.28 s | 59.27 s | 0.72x |

## Direct cross-system peak-RSS comparison

Peak RSS uses platform-correct units: bytes from macOS `getrusage`, KiB from Linux.

| dataset | setting | tool | stage | macbook-air peak | linux1 peak | linux1 / macbook-air |
| --- | --- | --- | --- | ---: | ---: | ---: |
| echo2 | 1 thread | warpkit | estimate | 2.23 GB | 2.48 GB | 1.11x |
| echo2 | 1 thread | warpkit | apply | 1.00 GB | 1.13 GB | 1.13x |
| echo2 | 1 thread | niimath | estimate | 1.27 GB | 1.23 GB | 0.96x |
| echo2 | 1 thread | niimath | apply | 0.59 GB | 0.51 GB | 0.86x |
| echo2 | native (4 vs 16 threads) | warpkit | estimate | 2.34 GB | 2.73 GB | 1.17x |
| echo2 | native (4 vs 16 threads) | warpkit | apply | 1.13 GB | 1.13 GB | 1.00x |
| echo2 | native (4 vs 16 threads) | niimath | estimate | 1.51 GB | 1.32 GB | 0.88x |
| echo2 | native (4 vs 16 threads) | niimath | apply | 0.59 GB | 0.50 GB | 0.85x |
| echo3 | 1 thread | warpkit | estimate | 2.34 GB | 2.19 GB | 0.94x |
| echo3 | 1 thread | warpkit | apply | 0.85 GB | 0.94 GB | 1.10x |
| echo3 | 1 thread | niimath | estimate | 1.22 GB | 1.27 GB | 1.04x |
| echo3 | 1 thread | niimath | apply | 0.48 GB | 0.41 GB | 0.86x |
| echo3 | native (4 vs 16 threads) | warpkit | estimate | 2.30 GB | 2.78 GB | 1.21x |
| echo3 | native (4 vs 16 threads) | warpkit | apply | 0.88 GB | 0.94 GB | 1.07x |
| echo3 | native (4 vs 16 threads) | niimath | estimate | 1.54 GB | 1.36 GB | 0.88x |
| echo3 | native (4 vs 16 threads) | niimath | apply | 0.48 GB | 0.41 GB | 0.85x |
| openneuro-ds005123 | 1 thread | warpkit | estimate | 2.71 GB | 5.13 GB | 1.89x |
| openneuro-ds005123 | 1 thread | warpkit | apply | 1.62 GB | 1.88 GB | 1.16x |
| openneuro-ds005123 | 1 thread | niimath | estimate | 3.34 GB | 3.29 GB | 0.99x |
| openneuro-ds005123 | 1 thread | niimath | apply | 1.02 GB | 0.88 GB | 0.86x |
| openneuro-ds005123 | native (4 vs 16 threads) | warpkit | estimate | 3.83 GB | 4.95 GB | 1.29x |
| openneuro-ds005123 | native (4 vs 16 threads) | warpkit | apply | 1.63 GB | 1.87 GB | 1.15x |
| openneuro-ds005123 | native (4 vs 16 threads) | niimath | estimate | 3.37 GB | 3.41 GB | 1.01x |
| openneuro-ds005123 | native (4 vs 16 threads) | niimath | apply | 1.02 GB | 0.87 GB | 0.85x |

## Dataset identity checks

- `echo2`: metadata match across the two raw results.
- `echo3`: metadata match across the two raw results.
- `openneuro-ds005123`: metadata match across the two raw results.

## Failures, warnings, and run notes

- macbook-air: MacBook Air was on AC power at start (94% charging).
- macbook-air: Pre-run system-wide memory free was 38%; cumulative swap counters were already nonzero.
- macbook-air: macOS pmset thermal/performance warning levels were unavailable (IOKit 0xe00002bc).
- macbook-air: No external mask exists for the OpenNeuro run; both tools used internal masks.
- linux1: No external mask exists for the OpenNeuro run; both tools used internal masks.

Thermal state and memory pressure are reported only when explicitly recorded in the raw result notes; neither is inferred from timing alone.
