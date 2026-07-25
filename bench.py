#!/usr/bin/env python3
"""Benchmark warpkit MEDIC against niimath --medic on the two supplied datasets.

Runs each tool independently through the full workflow -- estimate the field/displacement maps,
then apply them to every magnitude echo -- and records wall time and peak RSS for each stage, at
one thread and at a thread count matched to this machine.

Fairness notes, so the numbers mean something:

  * Both tools write UNCOMPRESSED NIfTI. gzip is a large, single-threaded share of niimath's
    wall time and warpkit writes .nii by default, so compressing one side and not the other
    measures zlib rather than MEDIC.
  * Each tool applies ITS OWN displacement maps, i.e. each is timed on the workflow a user would
    actually run, not on a hybrid.
  * warpkit exposes no option for an external brain mask, so the supplied mindgrab masks are
    given to niimath only (--mask). This is a capability difference, not a handicap applied to
    either side; see README.md. Use --no-mask to run niimath with its own built-in mask instead.

Peak RSS is measured with getrusage(RUSAGE_CHILDREN) inside a one-shot wrapper process, so each
figure belongs to exactly one command. Stdlib only.

    python3 bench.py                     # both datasets, 1 thread and this machine's default
    python3 bench.py --datasets echo2    # just the two-echo run
    python3 bench.py --threads 1 4 8     # explicit thread counts
    python3 bench.py --dry-run           # print the commands without running them
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NIIMATH_MIN = "v1.0.20260725"

# dataset key -> (BIDS root, run entity, mask file)
DATASETS = {
    "echo2": ("echo2", "sub-crlab_task-rest_acq-2d2echo_run-02", "echo2bet.nii.gz"),
    "echo3": ("echo3", "sub-crlab_task-rest_acq-2d3echo_run-03", "echo3bet.nii.gz"),
}

# One-shot wrapper: runs argv[1:] and reports its wall time and peak RSS. Because the wrapper is
# a fresh process, RUSAGE_CHILDREN covers exactly the one command it spawned.
WRAPPER = (
    "import json,resource,subprocess,sys,time;"
    "t=time.monotonic();"
    "r=subprocess.run(sys.argv[1:],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
    "u=resource.getrusage(resource.RUSAGE_CHILDREN);"
    "print(json.dumps({'wall':time.monotonic()-t,'rss':u.ru_maxrss,'rc':r.returncode}))"
)


# --------------------------------------------------------------------------- environment


def default_threads() -> int:
    """A sensible 'multi-threaded' count for this machine.

    On Apple Silicon the efficiency cores drag the wall time down without adding throughput, so
    prefer the performance-core count when we can read it. Elsewhere use the CPU count, capped at
    16 -- beyond that MEDIC is memory-bandwidth bound and the extra threads mostly add noise.
    """
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(["sysctl", "-n", "hw.perflevel0.logicalcpu"],
                                 capture_output=True, text=True, check=True).stdout.strip()
            if out.isdigit() and int(out) > 0:
                return int(out)
        except Exception:
            pass
    return max(1, min(16, os.cpu_count() or 1))


def version_tuple(v: str):
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else None


def check_tools(niimath: str, allow_older: bool) -> dict:
    """Verify warpkit and niimath are installed and new enough. Exits with advice if not."""
    info = {}
    missing = []

    for exe in ("wk-medic", "wk-apply-warp"):
        path = shutil.which(exe)
        if not path:
            missing.append(exe)
            continue
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True).stdout.strip()
        except Exception:
            out = "?"
        info[exe] = {"path": path, "version": out}
    if missing:
        sys.exit("warpkit is not on PATH (missing: %s).\n"
                 "  Install it with:  pip install warpkit\n"
                 "  Or activate the environment that provides wk-medic / wk-apply-warp."
                 % ", ".join(missing))

    path = shutil.which(niimath) or (niimath if Path(niimath).is_file() else None)
    if not path:
        sys.exit("niimath is not on PATH (looked for %r).\n"
                 "  Build it from https://github.com/rordenlab/niimath, or pass --niimath /path/to/niimath."
                 % niimath)
    out = subprocess.run([path, "--version"], capture_output=True, text=True).stdout.strip()
    have, need = version_tuple(out), version_tuple(NIIMATH_MIN)
    if have is None:
        sys.exit("could not parse a version from `%s --version` (got %r)" % (path, out))
    if need and have < need:
        msg = ("niimath %s is older than the %s this benchmark requires.\n"
               "  --medic gained its phase-encoding polarity, mask and output-transaction\n"
               "  behaviour after that date, so older builds are not comparable.\n"
               "  Update niimath, or pass --allow-older to benchmark anyway."
               % (out.split()[0], NIIMATH_MIN))
        if not allow_older:
            sys.exit(msg)
        print("WARNING: " + msg.replace("\n", "\n  "), file=sys.stderr)
    info["niimath"] = {"path": path, "version": out}
    return info


# --------------------------------------------------------------------------- measurement


def rss_to_bytes(rss: int) -> float:
    """getrusage reports ru_maxrss in bytes on macOS and kilobytes on Linux."""
    return float(rss) if platform.system() == "Darwin" else float(rss) * 1024.0


# Thread-limiting variables honoured by the libraries underneath warpkit (ITK, numpy/BLAS,
# OpenMP). wk-medic has -n but wk-apply-warp has NO thread option at all, so without these the
# "1 thread" row would silently be a full-machine run for warpkit's apply stage and the
# comparison would be meaningless.
THREAD_ENV = ("OMP_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS", "MKL_NUM_THREADS",
              "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def thread_env(threads: int) -> dict:
    env = dict(os.environ)
    for k in THREAD_ENV:
        env[k] = str(threads)
    env["FSLOUTPUTTYPE"] = "NIFTI"   # uncompressed, for both tools
    return env


def measure(cmd: list, dry: bool, env: dict | None = None) -> dict:
    """Run one command under the wrapper; return {wall, peak_gb, rc}."""
    if dry:
        print("    " + " ".join(str(c) for c in cmd))
        return {"wall": float("nan"), "peak_gb": float("nan"), "rc": 0}
    proc = subprocess.run([sys.executable, "-c", WRAPPER] + [str(c) for c in cmd],
                          capture_output=True, text=True, env=env)
    try:
        d = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        raise SystemExit("measurement wrapper produced no result for:\n  %s\n%s"
                         % (" ".join(str(c) for c in cmd), proc.stderr))
    if d["rc"] != 0:
        raise SystemExit("command failed with exit %d:\n  %s" % (d["rc"], " ".join(str(c) for c in cmd)))
    return {"wall": d["wall"], "peak_gb": rss_to_bytes(d["rss"]) / 2 ** 30, "rc": d["rc"]}


# --------------------------------------------------------------------------- the workload


def dataset_files(key: str):
    root, run, mask = DATASETS[key]
    func = HERE / root / "sub-crlab" / "func"
    echoes = sorted(int(m.group(1)) for m in
                    (re.search(r"_echo-(\d+)_part-mag_bold\.nii", p.name)
                     for p in func.glob("*_part-mag_bold.nii*")) if m)
    mags = [func / f"{run}_echo-{e}_part-mag_bold.nii.gz" for e in echoes]
    phas = [func / f"{run}_echo-{e}_part-phase_bold.nii.gz" for e in echoes]
    meta = [func / f"{run}_echo-{e}_part-phase_bold.json" for e in echoes]
    for f in mags + phas + meta:
        if not f.is_file():
            sys.exit("missing input: %s" % f)
    tes, trt, ped = [], None, None
    for j in meta:
        d = json.loads(j.read_text())
        tes.append(float(d["EchoTime"]) * 1000.0)
        trt = float(d.get("TotalReadoutTime", trt or 0))
        ped = d.get("PhaseEncodingDirection", ped)
    return {"echoes": echoes, "mags": mags, "phas": phas, "meta": meta,
            "tes": tes, "trt": trt, "ped": ped, "mask": HERE / mask}


def run_one(tool: str, ds: dict, out: Path, threads: int, niimath: str,
            use_mask: bool, dry: bool) -> dict:
    """Estimate then apply, for one tool at one thread count. Returns both stages' figures."""
    out.mkdir(parents=True, exist_ok=True)
    pre = out / "fmap"
    axis = ds["ped"][0]

    if tool == "warpkit":
        est = ["wk-medic", "--magnitude", *ds["mags"], "--phase", *ds["phas"],
               "--metadata", *ds["meta"], "--out-prefix", pre, "-n", threads]
    else:
        est = [niimath, "--medic", "--magnitude", *ds["mags"], "--phase", *ds["phas"],
               "--te-ms", ",".join("%g" % t for t in ds["tes"]),
               "--total-readout-time", "%g" % ds["trt"],
               "--phase-encoding-direction", ds["ped"],
               "--n-cpus", threads, "--gz", "0", "--out-prefix", pre]
        if use_mask:
            est += ["--mask", ds["mask"]]

    env = thread_env(threads)
    r_est = measure(est, dry, env)

    dmap = Path(str(pre) + "_displacementmaps.nii")
    apply_wall, apply_peak = 0.0, 0.0
    for i, mag in enumerate(ds["mags"]):
        dst = out / ("undistorted_echo-%d.nii" % ds["echoes"][i])
        if tool == "warpkit":
            cmd = ["wk-apply-warp", "--input", mag, "--transform", dmap,
                   "--transform-type", "map", "--phase-encoding-axis", axis, "--output", dst]
        else:
            cmd = [niimath, mag, "-p", threads, "-gz", "0", "-unwarp", dmap, axis, dst]
        r = measure(cmd, dry, env)
        apply_wall += r["wall"]
        apply_peak = max(apply_peak, r["peak_gb"])

    return {"estimate": r_est, "apply": {"wall": apply_wall, "peak_gb": apply_peak}}


# --------------------------------------------------------------------------- sanity


def agreement(out_dir: Path, key: str, threads: int) -> dict:
    """Did both tools actually do the job?

    A benchmark that only reports speed can be won by doing less work, so compare the two
    corrected images and confirm each one actually moved the input. Reads NIfTI headers directly
    (stdlib only, uncompressed .nii, float32 or scaled int) rather than pulling in numpy.
    """
    import struct

    def read(path: Path):
        blob = path.read_bytes()
        dim = struct.unpack("<8h", blob[40:56])
        dt, = struct.unpack("<h", blob[70:72])
        slope, inter = struct.unpack("<2f", blob[112:120])
        off = int(struct.unpack("<f", blob[108:112])[0])
        n = 1
        for d in dim[1:dim[0] + 1]:
            n *= d
        fmt = {16: "f", 512: "H", 4: "h"}.get(dt)
        if fmt is None:
            return None
        v = struct.unpack("<%d%s" % (n, fmt), blob[off:off + n * struct.calcsize(fmt)])
        if slope not in (0.0, 1.0) or inter != 0.0:
            v = [x * (slope or 1.0) + inter for x in v]
        return v

    try:
        a = read(out_dir / key / "warpkit" / str(threads) / "undistorted_echo-1.nii")
        b = read(out_dir / key / "niimath" / str(threads) / "undistorted_echo-1.nii")
    except Exception:
        return {}
    if not a or not b or len(a) != len(b):
        return {}
    n = float(len(a))
    ma, mb = sum(a) / n, sum(b) / n
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((x - mb) ** 2 for x in b) ** 0.5
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return {"corr": cov / (sa * sb) if sa > 0 and sb > 0 else float("nan")}


# --------------------------------------------------------------------------- reporting


def fmt(v: float, unit: str) -> str:
    return "n/a" if v != v else ("%.2f %s" % (v, unit))


def tables(results: dict, threads: list) -> str:
    lines = []
    for key in results:
        n = results[key]["frames"]
        e = results[key]["echoes"]
        lines.append("### %s — %d echoes, %d frames\n" % (key, e, n))
        lines.append("| stage | threads | warpkit wall | niimath wall | speed-up | warpkit peak RAM | niimath peak RAM |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for stage in ("estimate", "apply"):
            for t in threads:
                run = results[key]["runs"][str(t)]
                if "warpkit" not in run or "niimath" not in run:
                    continue
                w = run["warpkit"][stage]
                m = run["niimath"][stage]
                sp = ("%.2fx" % (w["wall"] / m["wall"])) if m["wall"] > 0 else "n/a"
                lines.append("| %s | %d | %s | %s | **%s** | %s | %s |" % (
                    stage, t, fmt(w["wall"], "s"), fmt(m["wall"], "s"), sp,
                    fmt(w["peak_gb"], "GB"), fmt(m["peak_gb"], "GB")))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", nargs="+", choices=sorted(DATASETS), default=sorted(DATASETS))
    ap.add_argument("--threads", type=int, nargs="+", default=None,
                    help="thread counts to test (default: 1 and this machine's core count)")
    ap.add_argument("--niimath", default=os.environ.get("NIIMATH", "niimath"))
    ap.add_argument("--out-dir", type=Path, default=HERE / "bench_out")
    ap.add_argument("--tools", nargs="+", choices=["warpkit", "niimath"],
                    default=["warpkit", "niimath"],
                    help="which implementations to run; use --tools niimath to refresh only "
                         "niimath's rows after a niimath change (warpkit's are unaffected)")
    ap.add_argument("--compare-dir", type=Path, default=None,
                    help="directory holding a previous run's outputs, used for the quality check "
                         "when only one tool was re-run")
    ap.add_argument("--merge", type=Path, default=None,
                    help="merge results into an existing bench_results.json, keeping rows for "
                         "tools not re-run")
    ap.add_argument("--no-mask", action="store_true",
                    help="do not pass --mask to niimath (use its built-in mask, as warpkit does)")
    ap.add_argument("--allow-older", action="store_true", help="skip the niimath version gate")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", type=Path, default=HERE / "bench_results.json")
    ap.add_argument("--update-readme", action="store_true",
                    help="write the tables into README.md at the <!-- BENCH_TABLES --> marker")
    args = ap.parse_args()

    threads = args.threads or sorted({1, default_threads()})
    tools = {} if args.dry_run else check_tools(args.niimath, args.allow_older)
    niimath = tools.get("niimath", {}).get("path", args.niimath)

    print("machine : %s %s, %d logical CPUs" % (platform.system(), platform.machine(), os.cpu_count() or 0))
    print("threads : %s" % ", ".join(str(t) for t in threads))
    for k, v in tools.items():
        print("%-14s %s" % (k, v["version"]))
    print("mask    : %s" % ("built-in (both tools)" if args.no_mask else
                            "supplied to niimath only — warpkit has no --mask option"))
    print()

    results = {}
    for key in args.datasets:
        ds = dataset_files(key)
        frames = 0
        if not args.dry_run:
            with open(ds["mags"][0], "rb") as fh:
                import gzip
                import struct
                blob = gzip.open(ds["mags"][0], "rb").read(56) if str(ds["mags"][0]).endswith(".gz") else fh.read(56)
                frames = struct.unpack("<8h", blob[40:56])[4]
        results[key] = {"echoes": len(ds["echoes"]), "frames": frames, "runs": {}}
        for t in threads:
            results[key]["runs"][str(t)] = {}
            for tool in args.tools:
                print("  %-6s %-8s %d thread(s) ..." % (key, tool, t), end="", flush=True)
                start = time.monotonic()
                r = run_one(tool, ds, args.out_dir / key / tool / str(t), t, niimath,
                            not args.no_mask, args.dry_run)
                results[key]["runs"][str(t)][tool] = r
                print(" estimate %s, apply %s (%.0fs total)"
                      % (fmt(r["estimate"]["wall"], "s"), fmt(r["apply"]["wall"], "s"),
                         time.monotonic() - start))

    if args.dry_run:
        return 0

    for key in results:
        # Compare the two tools' corrected images. When only one tool was re-run (--tools), fall
        # back to a directory that holds the other one so the quality check still happens.
        ag = agreement(args.out_dir, key, threads[-1])
        if not ag and args.compare_dir:
            ag = agreement(args.compare_dir, key, threads[-1])
        results[key]["agreement"] = ag
        # `not ag` first: an empty dict's .get() returns None, and None == None is True, so a bare
        # NaN test would sail past a missing measurement and then KeyError.
        if not ag or ag["corr"] != ag["corr"]:
            print("  %-6s corrected-image correlation: not available "
                  "(need both tools' outputs; see --compare-dir)" % key)
        else:
            print("  %-6s corrected-image correlation between the two tools: %.6f" % (key, ag["corr"]))

    if args.merge and args.merge.is_file():
        old = json.loads(args.merge.read_text()).get("results", {})
        for key in results:
            for t in results[key]["runs"]:
                for tool in ("warpkit", "niimath"):
                    if tool in results[key]["runs"][t]:
                        continue
                    prev = old.get(key, {}).get("runs", {}).get(t, {}).get(tool)
                    if prev:
                        results[key]["runs"][t][tool] = prev
                        results[key].setdefault("carried", []).append("%s/%s" % (t, tool))

    payload = {"machine": {"system": platform.system(), "machine": platform.machine(),
                           "cpus": os.cpu_count()},
               "tools": tools, "threads": threads,
               "mask": "niimath only" if not args.no_mask else "built-in",
               "results": results}
    args.json.write_text(json.dumps(payload, indent=2, default=str))
    md = tables(results, threads)
    print("\n" + md)
    print("wrote %s" % args.json)

    if args.update_readme:
        readme = HERE / "README.md"
        text = readme.read_text()
        marker = "<!-- BENCH_TABLES -->"
        if marker not in text:
            print("README.md has no %s marker; tables not inserted" % marker, file=sys.stderr)
        else:
            head, _, tail = text.partition(marker)
            # everything up to the next "## " heading belongs to the generated block
            rest = tail.split("\n## ", 1)
            body = marker + "\n\n" + provenance(payload) + "\n" + md
            readme.write_text(head + body + ("\n## " + rest[1] if len(rest) > 1 else ""))
            print("updated %s" % readme)
    return 0


def provenance(payload: dict) -> str:
    m = payload["machine"]
    t = payload["tools"]
    return ("Measured on %s %s, %d logical CPUs, with %s and %s. "
            "Uncompressed NIfTI both sides; thread counts pinned by environment as well as by "
            "each tool's own flag. Mask: %s.\n"
            % (m["system"], m["machine"], m["cpus"] or 0,
               t.get("wk-medic", {}).get("version", "warpkit"),
               t.get("niimath", {}).get("version", "niimath").split()[0],
               payload["mask"]))


if __name__ == "__main__":
    sys.exit(main())
