# Reproducing the cross-platform MEDIC benchmarks

This workflow uses only public repositories and one complete public OpenNeuro
run. It does not require an OpenNeuro account, API key, or private data.

## Linux1 quick start

Clone the benchmark branch, then detach at the exact harness commit used for
the Mac measurements:

```bash
git clone --branch benchmark-macos-linux-openneuro --single-branch \
  https://github.com/DVSneuro/medic_bench.git
cd medic_bench
git checkout --detach 5036d63cefa92d17b80325693a646865a9e7700b
```

The later commits on the branch contain the recorded Mac result and reporting
improvements only. Using the commit above keeps the measured Python harness
identical on both hosts. The raw JSON records the OS, CPU, memory, compiler,
tool versions, thread counts, and source commits for auditability.

After satisfying the prerequisites below, create the Python 3.12 environment,
build pinned niimath, and fetch the public OpenNeuro subset:

```bash
python3.12 -m venv .benchmark-tools/warpkit-1.4.1
.benchmark-tools/warpkit-1.4.1/bin/python -m pip install \
  -r requirements-benchmark-lock.txt
python3 scripts/build_niimath.py

export PATH="$PWD/.benchmark-tools/warpkit-1.4.1/bin:$PATH"
export NIIMATH="$PWD/.benchmark-tools/niimath-9dda863702e6/bin/niimath"

python3 scripts/fetch_openneuro_sample.py
python3 scripts/fetch_openneuro_sample.py --verify-only
```

Run the validation and benchmark with the pinned Python interpreter:

```bash
.benchmark-tools/warpkit-1.4.1/bin/python bench.py \
  --dry-run \
  --datasets echo2 echo3 openneuro-ds005123 \
  --niimath "$NIIMATH"

.benchmark-tools/warpkit-1.4.1/bin/python bench.py \
  --datasets echo2 echo3 openneuro-ds005123 \
  --machine-label linux1 \
  --niimath "$NIIMATH" \
  --out-dir bench_out/linux1 \
  --json results/linux1.json \
  --markdown results/linux1.md
```

The run measures one thread and the platform default (logical CPU count,
capped at 16). It takes several hours. Keep `results/linux1.json` and
`results/linux1.md`; do not copy or commit `bench_out/`, the OpenNeuro cache,
the environment, or compiled binaries.

To combine the Linux result with the committed Mac result, return to the
branch tip and render the comparison:

```bash
git switch benchmark-macos-linux-openneuro
python3 scripts/render_results.py \
  results/macbook-air.json results/linux1.json \
  --output results/comparison.md
```

## Immutable inputs

The authoritative pins are in
[`config/benchmark-versions.json`](../config/benchmark-versions.json):

- warpkit `1.4.1`;
- niimath commit `9dda863702e64078ab11061df65e6824251c293f`;
- OpenNeuro `ds005123` snapshot `1.1.3`, resolved to commit
  `a3213b56b7bd27d7e3ac10577558eb26bb7c2a61`.

Do not compare a result produced with a different niimath commit as though it
were the same build. The raw result records the source commit, compiler, and
OpenMP build metadata.

## Prerequisites

- Python 3.9 or newer;
- Git;
- DataLad and git-annex;
- a C compiler, Make, zlib development files, and an OpenMP runtime.

On macOS, niimath needs LLVM `libomp`. Homebrew provides it with
`brew install libomp`. An existing FSL installation can also provide
`include/omp.h` and `lib/libomp.dylib`; set `LIBOMP_ROOT=$FSLDIR` if the build
script cannot discover it.

On Linux, GCC normally supplies `libgomp` with `-fopenmp`. Use a user-owned
Conda environment when shared system packages cannot be changed. Do not use
`sudo` for this workflow.

## Prepare the pinned tools

From the medic_bench checkout:

```bash
python3 -m venv .benchmark-tools/warpkit-1.4.1
.benchmark-tools/warpkit-1.4.1/bin/python -m pip install --upgrade pip
.benchmark-tools/warpkit-1.4.1/bin/python -m pip install -r requirements-benchmark-lock.txt

python3 scripts/build_niimath.py

export PATH="$PWD/.benchmark-tools/warpkit-1.4.1/bin:$PATH"
export NIIMATH="$PWD/.benchmark-tools/niimath-9dda863702e6/bin/niimath"
```

The niimath builder retains `build-provenance.json` beside the binary. The
directory is ignored by Git. Run the same commands and use the same source
commit on both hosts; compiler and OpenMP runtime differences are recorded
rather than guessed.

Confirm the environment before running:

```bash
python3 --version
wk-medic --version
wk-apply-warp --version
"$NIIMATH" --version
cc --version
```

## Retrieve only the selected OpenNeuro run

The default cache is
`~/.cache/medic_bench/openneuro/ds005123/1.1.3`. Override its parent with
`--cache-root` or `MEDIC_BENCH_CACHE`.

```bash
python3 scripts/fetch_openneuro_sample.py
```

The script checks out the immutable snapshot commit and calls `datalad get`
only for:

```text
sub-10317/func/sub-10317_task-ugr_run-1_echo-<1-4>_part-<mag|phase>_bold.nii.gz
sub-10317/func/sub-10317_task-ugr_run-1_echo-<1-4>_part-<mag|phase>_bold.json
```

It verifies all 16 files and writes content SHA-256 hashes and git-annex keys
to `openneuro-sample-provenance.json` in the cache. Re-running is resumable and
checks retained hashes:

```bash
python3 scripts/fetch_openneuro_sample.py
python3 scripts/fetch_openneuro_sample.py --verify-only
```

To test from an empty disposable cache:

```bash
python3 scripts/fetch_openneuro_sample.py --cache-root /tmp/medic-bench-fetch-test
python3 scripts/fetch_openneuro_sample.py --cache-root /tmp/medic-bench-fetch-test --verify-only
```

## Validate command construction

The built-in datasets remain the default:

```bash
python3 bench.py --dry-run --datasets echo2
python3 bench.py --dry-run --datasets echo3
```

After retrieval, validate the manifest-backed run:

```bash
python3 bench.py --dry-run --datasets openneuro-ds005123
```

Discovery is shared with `medic.py`. The driver rejects unmatched magnitude
and phase echo sets, duplicate image variants, missing exact sidecars,
inconsistent acquisition metadata, and geometry differences.

## Run a host

Omit `--threads` to use one thread and the platform default. On Apple Silicon
the default is the performance-core count; elsewhere it is the logical CPU
count capped at 16. Both tool arguments and all recorded thread-limiting
environment variables receive the same count.

Mac example:

```bash
python3 bench.py \
  --datasets echo2 echo3 openneuro-ds005123 \
  --machine-label macbook-air \
  --niimath "$NIIMATH" \
  --out-dir bench_out/macbook-air \
  --json results/macbook-air.json \
  --markdown results/macbook-air.md
```

Linux example:

```bash
python3 bench.py \
  --datasets echo2 echo3 openneuro-ds005123 \
  --machine-label linux1 \
  --niimath "$NIIMATH" \
  --out-dir bench_out/linux1 \
  --json results/linux1.json \
  --markdown results/linux1.md
```

One full-length measurement is the default. `--repetitions N` adds independent
measurement records without changing the JSON schema. The OpenNeuro run is
never cropped. A genuine memory or runtime failure is retained as an
incomplete cell, and the process exits nonzero after writing the partial raw
result.

The supplied masks continue to be passed only to niimath for `echo2` and
`echo3`, because warpkit has no mask option. No corresponding mask is supplied
for the OpenNeuro run, so both implementations use their internal masks there.

## Linux transfer and comparison

Use the configured SSH name rather than embedding an address. Check out the
same medic_bench commit on the Linux host, retrieve the OpenNeuro subset
independently, and copy back only JSON and Markdown result files. Never copy
`bench_out/`, the OpenNeuro cache, environments, or binaries into Git.

Regenerate an individual report from its raw JSON:

```bash
python3 scripts/render_results.py results/macbook-air.json \
  --output results/macbook-air.md
```

Generate the cross-platform report:

```bash
python3 scripts/render_results.py \
  results/macbook-air.json results/linux1.json \
  --output results/comparison.md
```

If a host is unreachable, produce an explicit partial comparison instead of
inventing a placeholder benchmark:

```bash
python3 scripts/render_results.py results/macbook-air.json \
  --unavailable-machine linux1 \
  --unavailable-reason "The configured SSH alias did not resolve." \
  --output results/comparison.md
```

The report presents estimate, apply, and end-to-end cost separately. Timing
and peak RSS describe computational efficiency; corrected-image correlation
describes agreement and is not, by itself, evidence of numerical equivalence.

## Validation checklist

```bash
PYTHONPYCACHEPREFIX=/tmp/medic-bench-pyc \
  python3 -m py_compile bench.py medic.py scripts/*.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test.test_bench
git diff --check
git status --short
git diff --cached --name-only -z | xargs -0 stat
```

The unit tests exercise missing sidecars, echo-set mismatch, ambiguous
duplicates, and the macOS-versus-Linux peak-RSS conversion. The result renderer
is also tested. Before committing, confirm that no generated NIfTI, downloaded
OpenNeuro content, environment, binary, or multi-gigabyte directory is staged.
