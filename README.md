## About

MEDIC (Multi-Echo DIstortion Correction) uses the phase images that come for free with a multi-echo EPI acquisition to estimate and remove susceptibility distortion. Because the field is re-estimated at every frame, the correction tracks head motion through a run — an advantage over methods such as FSL FUGUE and FSL TOPUP, which require a separate acquisition and are sensitive to movement between that acquisition and the data being corrected.

[warpkit](https://github.com/vanandrew/warpkit) is the reference implementation of MEDIC, from the group that developed and published the method. It is distributed under an institutional licence permitting non-commercial use. That is a reasonable choice for the authors, but it does constrain reuse: it is not an OSI-approved open-source licence, and developers who intend to write an independently licensed implementation generally avoid reading such source at all, so that their work is demonstrably their own.

This repository benchmarks [niimath](https://github.com/rordenlab/niimath)'s `--medic` as a complementary implementation, with four aims:

- **Fewer dependencies** — a single cross-platform C program rather than a Python stack.
- **A permissive licence** — BSD-2-Clause, so the method can be embedded freely.
- **Lower time and memory cost.**
- **Equivalent results.**

The benchmark below shows clear progress on the first three. On the fourth the two implementations agree closely at some stages and not yet at others; see [Agreement](#agreement).

niimath's `--medic` was developed clean-room, from the published paper and from black-box measurement of the released `wk-medic` / `wk-apply-warp` executables. No warpkit source was read. The measurement record — every convention, the experiment that established it, and the questions that remain open — is kept in the niimath repository as `test/medic_reference_manifest.md`.

## Requirements

- **warpkit**, providing `wk-medic` and `wk-apply-warp` on your `PATH` (`pip install warpkit`).
- **niimath** ≥ `v1.0.20260725`, built with OpenMP. `--medic` acquired its phase-encoding polarity handling, `--mask` option and output transaction after that date, so earlier builds are not comparable.

`bench.py` checks both and explains what to do if either is missing or too old.

## Running the benchmarks

```bash
python3 bench.py                          # both datasets, 1 thread and this machine's core count
python3 bench.py --datasets echo2         # just the two-echo run
python3 bench.py --threads 1 4 8          # explicit thread counts
python3 bench.py --dry-run                # print the commands without running anything
python3 bench.py --niimath /path/to/niimath
```

Results are written to `bench_results.json` and printed as the tables below; `--update-readme` writes them straight into this file. Intermediate and output images go to `bench_out/` (several GB — delete it when you are done).

For a pinned cross-platform run, including the manifest-backed four-echo
OpenNeuro `ds005123` sample, selective DataLad/git-annex retrieval, rich machine
provenance, repeat-ready JSON, and comparison reports, see
[`docs/reproducing-benchmarks.md`](docs/reproducing-benchmarks.md). The built-in
`echo2` and `echo3` datasets remain the default, so existing commands continue
to work.

**Budget about 75 minutes for the full matrix on a modern workstation, and note that almost all of it is one arm.** `wk-apply-warp` has no thread option, so pinning it to a single thread (required for a single-threaded row) takes it to roughly 15 minutes per echo. The other seven arms together finish in a few minutes. If you only want the multi-threaded comparison, `python3 bench.py --threads 8` runs in well under ten minutes.

Three choices make the comparison like-for-like:

- **Uncompressed NIfTI throughout.** gzip is a large, single-threaded share of niimath's wall time, and warpkit writes `.nii` by default. Compressing one side and not the other measures zlib, not MEDIC.
- **Each tool applies its own displacement maps**, so each is timed on the workflow a user would actually run rather than on a hybrid.
- **Thread counts are pinned by environment** (`OMP_NUM_THREADS`, `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS` and the BLAS equivalents) as well as by each tool's own flag. `wk-apply-warp` has no thread option, so without this its single-thread row would quietly be a full-machine run.

Peak RSS comes from `getrusage(RUSAGE_CHILDREN)` inside a one-shot wrapper process, so every figure belongs to exactly one command.

## The datasets

Both are single-subject resting-state runs at 76 × 76 × 46, 2.8 mm, `TotalReadoutTime` 0.02025 s, phase-encoding `j`.

| dataset | echoes | frames | echo times (ms) |
| --- | --- | --- | --- |
| `echo2` | 2 | 170 | 16.80, 38.56 |
| `echo3` | 3 | 138 | 14.80, 34.38, 53.94 |

`estimate` is one `wk-medic` / `niimath --medic` call producing the field and displacement maps. `apply` is the total across all echoes — two `wk-apply-warp` / `niimath -unwarp` calls for `echo2`, three for `echo3`.

## Benchmarks

<!-- BENCH_TABLES -->

Measured on Apple silicon (macOS, arm64; 10 performance + 4 efficiency cores, 48 GB), with warpkit 1.4.1 and niimath built from the current `--medic` sources against zlib-ng with OpenMP. Uncompressed NIfTI on both sides; thread counts pinned by environment as well as by each tool's own flag; the mindgrab mask supplied to niimath only. Regenerate with `python3 bench.py --update-readme`, or refresh one side with `python3 bench.py --tools niimath --merge bench_results.json --compare-dir bench_out`.

`estimate` is a single call producing the field and displacement maps. `apply` is the total across all echoes — two calls for `echo2`, three for `echo3`.

### echo2 — 2 echoes, 170 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | --- | --- | --- | --- | --- | --- |
| estimate | 1 | 51.54 s | 12.36 s | **4.2x** | 3.49 GB | 1.70 GB |
| estimate | 10 | 14.39 s | 3.15 s | **4.6x** | 4.36 GB | 1.90 GB |
| apply | 1 | 770.44 s | 8.09 s | **95x** | 1.25 GB | 0.59 GB |
| apply | 10 | 129.47 s | 1.41 s | **92x** | 1.25 GB | 0.59 GB |

### echo3 — 3 echoes, 138 frames

| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |
| --- | --- | --- | --- | --- | --- | --- |
| estimate | 1 | 46.10 s | 9.96 s | **4.6x** | 3.20 GB | 1.66 GB |
| estimate | 10 | 12.82 s | 2.88 s | **4.4x** | 3.83 GB | 1.83 GB |
| apply | 1 | 957.98 s | 9.57 s | **100x** | 1.11 GB | 0.48 GB |
| apply | 10 | 159.33 s | 1.86 s | **86x** | 1.13 GB | 0.48 GB |

### End to end

| dataset | threads | warpkit | niimath | speed-up |
| --- | --- | --- | --- | --- |
| `echo2` | 1 | 822 s (13.7 min) | 20.5 s | **40x** |
| `echo2` | 10 | 144 s | 4.6 s | **32x** |
| `echo3` | 1 | 1004 s (16.7 min) | 19.5 s | **51x** |
| `echo3` | 10 | 172 s | 4.7 s | **36x** |

### Reading these numbers

- **The estimate stage is the fair fight**, and niimath is 4.2–4.6x faster at roughly half the memory. Both implement the same algorithm; the difference is C against a Python/ITK stack.
- **The apply stage difference is much larger — 86x to 100x — and deserves a caveat.** `wk-apply-warp` has no thread option, so its single-threaded figures come from pinning it by environment; that is the honest way to obtain a single-threaded number, but it is not a configuration its authors optimised for. The multi-threaded rows (92x, 86x) are the more meaningful comparison, and are still a large difference: warpkit spends roughly 470 s of CPU per echo where niimath spends a few seconds.
- **`-unwarp` timing is data-dependent**, so quote the map alongside the number. Its resampler has an exact fast path where the displacement is precisely zero (the sinc kernel vanishes at nonzero integers), and niimath's own maps are ~75 % exact zeros outside the brain mask, where a uint16-quantised reference map has none. The same 170-frame apply takes about 3x longer against a quantised map than against niimath's own.
- **Memory is consistently lower**, and niimath's peak barely moves with thread count, whereas warpkit's estimate peak rises by 0.6–0.9 GB from 1 to 10 threads.
- **Neither tool is fast because it skipped work.** The two corrected images correlate **0.9962** (`echo2`) and **0.9963** (`echo3`), unchanged across niimath revisions, and both move the input substantially (p95 absolute change 679–1047 intensity units against a signal ranging to ~2.3 x 10⁴). `bench.py` reports this correlation automatically and refuses to publish a timing from a command that failed.

## A note on brain masks

Both implementations derive a brain mask internally, and by visual inspection both are fairly crude. Supplying a good mask is worthwhile for either, so masks made with [MindGrab](https://pubmed.ncbi.nlm.nih.gov/42331200/) are included here (`echo2bet.nii.gz`, `echo3bet.nii.gz`).

At the time of writing, **`wk-medic` exposes no option to supply an external mask**, so the benchmark passes the mask to niimath only (`--mask`). This is a capability difference rather than a thumb on the scale — masking is not a hot path, so it barely moves the timings — but it does mean the two runs are not masked identically, which matters when comparing *results* rather than *cost*. Run `python3 bench.py --no-mask` if you would prefer both sides to use their own internal masks.

niimath's in-mask test is `>= 1`, so threshold a probability map first: `niimath prob.nii -thr 0.5 -bin mask.nii`.

## Agreement

Cost is the easy half of this comparison; agreement is the interesting half. The current state, stated plainly:

- **Applying a displacement map matches the reference closely.** Given warpkit's own displacement maps, `niimath -unwarp` reproduces warpkit's corrected magnitude at nrmse 3.5 × 10⁻⁵, correlation 0.999999999, with no non-finite mismatches. The resampling convention — a Lanczos-windowed sinc of radius 5, unnormalised, with zero fill and no Jacobian modulation — was recovered by measurement and matches exactly.
- **Field-map estimation agrees very well once the masks are the same.** Supplying warpkit's own mask to niimath, the native field maps agree to 0.0027 Hz at the 99th percentile — which says the phase rescaling, MCPC-3D-S offset estimation, ROMEO unwrapping and magnitude-weighted regression are all doing the same thing.
- **End to end, the two do not yet match.** With each tool using its own mask the field maps diverge substantially, because a different mask changes which voxels ROMEO's region growing can reach. Even with a shared mask, roughly 0.2 % of voxels settle on a different 2π branch, and the displacement inversion amplifies those along the phase-encoding direction.
- **Two conventions remain unresolved**, and have deliberately not been guessed at: how warpkit constructs its three-level mask, and the origin of a broadband residual that survives its rank-10 low-rank filter on real data. niimath's low-rank stage is labelled experimental in its help text for that reason, and `--rank 0` disables it.

So: use this repository for a fair comparison of time and memory, and treat numerical agreement as work in progress rather than settled.

## Files

| file | purpose |
| --- | --- |
| `bench.py` | the benchmark driver — checks the tools, runs both implementations, writes the tables |
| `medic.py` | a small stdlib-only BIDS front end for `niimath --medic`: discovers echo/part pairs, reads the sidecars, and calls niimath once per run to estimate and once per echo to apply. Useful on its own, and it documents the intended workflow |
| `echo2/`, `echo3/` | the two BIDS datasets |
| `echo2bet.nii.gz`, `echo3bet.nii.gz` | MindGrab brain masks |

`medic.py` is also distributed with niimath; this copy is the one the benchmark documents.

## Links

- [warpkit](https://github.com/vanandrew/warpkit) — reference MEDIC implementation.
- [ROMEO.jl](https://github.com/korbinian90/ROMEO.jl) — reference ROMEO implementation.
- [niimath](https://github.com/rordenlab/niimath) — the implementation benchmarked here.

## Citations

- [MEDIC (Multi-Echo DIstortion Correction)](https://pubmed.ncbi.nlm.nih.gov/42232073/)
- [MindGrab](https://pubmed.ncbi.nlm.nih.gov/42331200/) — brain extraction
- [MCPC-3D](https://pubmed.ncbi.nlm.nih.gov/21254207/) — phase offset combination
- [MCPC-3D-S](https://pubmed.ncbi.nlm.nih.gov/27717080/) — short-echo-time-difference variant
- [ROMEO](https://pubmed.ncbi.nlm.nih.gov/33104278/) — Rapid Opensource Minimum spanning treE algOrithm
