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

Runtime depends strongly on the host and dataset. The pinned three-dataset
matrix took **2 h 41 min** on the Apple M3 MacBook Air and **7 h 9 min** on
the Xeon Silver 4116 Linux host. Most of that time was `wk-apply-warp`; the
full timing and machine provenance are in
[`results/comparison.md`](results/comparison.md).

Three choices make the comparison like-for-like:

- **Uncompressed NIfTI throughout.** gzip is a large, single-threaded share of niimath's wall time, and warpkit writes `.nii` by default. Compressing one side and not the other measures zlib, not MEDIC.
- **Each tool applies its own displacement maps**, so each is timed on the workflow a user would actually run rather than on a hybrid.
- **Thread counts are requested ceilings, not measured utilization.**
  `wk-medic` receives `-n`, niimath receives `--n-cpus` / `-p`, and the
  standard OpenMP, ITK, and BLAS environment limits are set. However,
  `wk-apply-warp` has no thread-count option and its Python driver traverses
  echoes and frames serially. Its native code may use several threads within
  a resampling call, but a “16-thread” row must not be read as sustained use
  of 16 processors.

Peak RSS comes from `getrusage(RUSAGE_CHILDREN)` inside a one-shot wrapper process, so every figure belongs to exactly one command.

## Field-map QA and visualization

[`notebooks/fieldmap_qa.ipynb`](notebooks/fieldmap_qa.ipynb) discovers the
generated `fmap_fieldmaps.nii`, `fmap_fieldmaps_native.nii`, and
`fmap_displacementmaps.nii` files beneath `bench_out/`. It provides:

- interactive multiplanar and 4D frame inspection with
  [ipyniivue](https://github.com/niivue/ipyniivue);
- sampled finite-value, zero-fraction, robust-range, orientation, affine, and
  qform/sform checks; and
- geometry, correlation, and difference summaries for matched Warpkit and
  niimath maps.

Create a separate QA environment and open the notebook from the repository
root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-qa.txt
.venv/bin/python -m jupyter lab notebooks/fieldmap_qa.ipynb
```

By default the notebook searches `bench_out/` in the checkout. If the outputs
are elsewhere, set `MEDIC_BENCH_OUTPUT_ROOT=/path/to/bench_out` before
launching Jupyter.

The same sampled checks are available without Jupyter:

```bash
.venv/bin/python scripts/fieldmap_qa.py \
  --root bench_out \
  --dataset openneuro-ds005123 \
  --kind fieldmaps \
  --json results/fieldmap-qa.json
```

The automated checks screen for common output failures; they do not impose a
universal physiologic field-map range. Visual review of the complete time
series remains the important final step.

## The datasets

The two repository datasets are single-subject resting-state runs. The pinned
cross-platform benchmark adds one complete, uncropped public OpenNeuro run
selected by [`manifests/openneuro-ds005123-1.1.3.json`](manifests/openneuro-ds005123-1.1.3.json).

| dataset | geometry | echoes | frames | echo times (ms) | readout / PE |
| --- | --- | ---: | ---: | --- | --- |
| `echo2` | 76 × 76 × 46, 2.8 mm | 2 | 170 | 16.80, 38.56 | 0.02025 s / `j` |
| `echo3` | 76 × 76 × 46, 2.8 mm | 3 | 138 | 14.80, 34.38, 53.94 | 0.02025 s / `j` |
| `openneuro-ds005123` | 80 × 80 × 51, 2.7 × 2.7 × 2.97 mm | 4 | 240 | 13.80, 31.54, 49.28, 67.02 | 0.0193552 s / `j-` |

`estimate` is one `wk-medic` / `niimath --medic` call producing the field
and displacement maps. `apply` is the total across all echoes: two
`wk-apply-warp` / `niimath -unwarp` calls for `echo2`, three for `echo3`,
and four for the OpenNeuro run.

## Cross-platform benchmark (2026-07-29)

The pinned matrix completed without failures on an Apple M3 MacBook Air
(4 performance cores, 16 GiB) and an Intel Xeon Silver 4116 Linux host
(24 physical cores, 125.6 GiB). Both used warpkit 1.4.1, niimath commit
`9dda863702e64078ab11061df65e6824251c293f`, and benchmark harness commit
`5036d63cefa92d17b80325693a646865a9e7700b`.

The table uses each platform's recorded native setting: 4 threads on the Mac
and a 16-thread cap on Linux.

| host | dataset | threads | warpkit end to end | niimath end to end | speed-up |
| --- | --- | ---: | ---: | ---: | ---: |
| M3 MacBook Air | `echo2` | 4 | 419.41 s | 14.39 s | **29.14×** |
| M3 MacBook Air | `echo3` | 4 | 525.12 s | 18.86 s | **27.85×** |
| M3 MacBook Air | `openneuro-ds005123` | 4 | 2115.00 s | 82.28 s | **25.71×** |
| Xeon Linux | `echo2` | 16 | 1071.70 s | 21.17 s | **50.63×** |
| Xeon Linux | `echo3` | 16 | 1309.33 s | 20.36 s | **64.31×** |
| Xeon Linux | `openneuro-ds005123` | 16 | 5031.39 s | 59.27 s | **84.89×** |

### What the completed run shows

- **niimath was 25.71–84.89× faster end to end at the native settings.**
  Looking only at field/displacement-map estimation, it was 2.15–6.26×
  faster; the much larger 49.95–251.36× apply-stage difference dominates
  the workflow result.
- **The result reproduced across OS, architecture, compiler, and OpenMP
  runtime.** Tool-to-tool corrected-image correlation was exactly
  `0.9961670301619666` for `echo2`, `0.9962783108102466` for `echo3`, and
  `0.9981994018239215` for the OpenNeuro run in both raw result files.
  Correlation is an agreement check, not proof of numerical equivalence; the
  remaining interpretation is discussed below.
- **The M3 had substantially higher single-thread performance.** Across
  like-for-like one-thread stages, Linux took 2.32–3.55× as long. Sixteen
  Linux threads brought niimath close to or ahead of the four-core Mac result,
  but did not close the Warpkit gap: native-setting Warpkit remained
  2.38–2.56× slower on Linux.
- **Apply-stage memory was lower for niimath in every recorded cell:**
  0.41–1.02 GB versus 0.85–1.88 GB for Warpkit. Estimate-stage memory was
  more data- and platform-dependent, so the results do not support a blanket
  “half the memory” claim for the complete workflow.
- **The full matrix took 2 h 41 min on the Mac and 7 h 9 min on Linux.**
  The raw timestamps include tool checks, measurement, and agreement
  calculation, but exclude environment creation and public-data retrieval.

The native rows measure actual end-to-end behavior under a thread ceiling,
not ideal parallel scaling. In particular, `wk-apply-warp` exposes no CPU-count
argument and traverses the time series serially in its Python driver; only its
native resampling call can use the thread-limited libraries. The apply numbers
also use each implementation's own displacement map, so they measure the
workflow a user runs rather than resampling a shared map.

See the [complete comparison](results/comparison.md) for stage-level timing,
peak RSS, machine/software provenance, and dataset identity checks. The
authoritative inputs are
[`results/macbook-air.json`](results/macbook-air.json) and
[`results/linux1.json`](results/linux1.json); reproduction instructions are
in [`docs/reproducing-benchmarks.md`](docs/reproducing-benchmarks.md).

<!-- BENCH_TABLES -->

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
| `scripts/fieldmap_qa.py` | discovers generated maps, samples structural/value QA metrics, and compares matched Warpkit and niimath outputs |
| `notebooks/fieldmap_qa.ipynb` | interactive ipyniivue field-map and displacement-map inspection |
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
