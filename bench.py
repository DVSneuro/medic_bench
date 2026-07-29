#!/usr/bin/env python3
"""Benchmark warpkit MEDIC against niimath --medic.

The two bundled datasets remain the default workload.  A committed manifest
adds the pinned OpenNeuro run without embedding machine-specific paths:

    python3 bench.py
    python3 bench.py --datasets echo2
    python3 bench.py --threads 1 4 8
    python3 bench.py --dry-run
    python3 bench.py --datasets openneuro-ds005123 --machine-label macbook-air

Both implementations write uncompressed NIfTI, apply their own displacement
maps, and are pinned through tool arguments and thread-limiting environment
variables.  Estimate and apply stages are measured independently.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from medic import find_runs, read_meta, sidecar

HERE = Path(__file__).resolve().parent
NIIMATH_MIN = "v1.0.20260725"
PROVENANCE_NAME = "openneuro-sample-provenance.json"

# Preserve the original built-in names and default behavior. External datasets
# live in manifests/ and are resolved via --cache-root or --bids-root.
DATASETS = {
    "echo2": ("echo2", "sub-crlab_task-rest_acq-2d2echo_run-02", "echo2bet.nii.gz"),
    "echo3": ("echo3", "sub-crlab_task-rest_acq-2d3echo_run-03", "echo3bet.nii.gz"),
}

THREAD_ENV = (
    "OMP_NUM_THREADS",
    "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)

# A fresh wrapper makes RUSAGE_CHILDREN specific to one command. Capturing only
# output tails keeps a failed cell diagnosable without bloating result JSON.
WRAPPER = (
    "import json,resource,subprocess,sys,time;"
    "t=time.monotonic();"
    "r=subprocess.run(sys.argv[1:],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);"
    "u=resource.getrusage(resource.RUSAGE_CHILDREN);"
    "print(json.dumps({'wall':time.monotonic()-t,'rss':u.ru_maxrss,'rc':r.returncode,"
    "'stdout_tail':r.stdout[-4000:],'stderr_tail':r.stderr[-4000:]}))"
)


class BenchmarkError(RuntimeError):
    pass


class CommandFailed(BenchmarkError):
    def __init__(self, measurement: Dict):
        self.measurement = measurement
        detail = measurement.get("stderr_tail") or measurement.get("stdout_tail") or ""
        message = "command failed with exit %s:\n  %s" % (
            measurement.get("rc"),
            " ".join(measurement.get("command", [])),
        )
        if detail:
            message += "\n" + detail.strip()
        super().__init__(message)


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def default_cache_root() -> Path:
    configured = os.environ.get("MEDIC_BENCH_CACHE")
    return Path(configured).expanduser() if configured else Path.home() / ".cache" / "medic_bench" / "openneuro"


def run_text(argv: List[str], cwd: Optional[Path] = None) -> Optional[str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    text = (proc.stdout or proc.stderr).strip()
    return text if proc.returncode == 0 and text else None


def default_threads() -> int:
    """Prefer Apple performance cores; cap other machines at 16."""
    if platform.system() == "Darwin":
        out = run_text(["sysctl", "-n", "hw.perflevel0.logicalcpu"])
        if out and out.isdigit() and int(out) > 0:
            return int(out)
        hardware = run_text(["system_profiler", "SPHardwareDataType"]) or ""
        match = re.search(r"(\d+)\s+Performance", hardware)
        if match:
            return int(match.group(1))
    return max(1, min(16, os.cpu_count() or 1))


def version_tuple(value: str) -> Optional[Tuple[int, int, int]]:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", value)
    return tuple(int(x) for x in match.groups()) if match else None


def executable_version(path: str) -> str:
    for flag in ("--version", "-version"):
        try:
            proc = subprocess.run([path, flag], capture_output=True, text=True)
        except OSError:
            return "unavailable"
        text = (proc.stdout or proc.stderr).strip()
        if text:
            return text.splitlines()[0]
    return "unavailable"


def find_build_provenance(binary: Path) -> Optional[Dict]:
    for parent in [binary.parent] + list(binary.parents)[:4]:
        candidate = parent / "build-provenance.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text())
            except (OSError, json.JSONDecodeError):
                return None
    return None


def warpkit_environment(executable: Path) -> Dict:
    try:
        first = executable.open(errors="ignore").readline().strip()
    except OSError:
        first = ""
    interpreter = first[2:] if first.startswith("#!") else sys.executable
    if " " in interpreter or not Path(interpreter).is_file():
        interpreter = sys.executable
    code = "import importlib.metadata;print(importlib.metadata.version('warpkit'))"
    freeze = run_text([interpreter, "-m", "pip", "freeze"]) or ""
    return {
        "version": run_text([interpreter, "-c", code]) or "unavailable",
        "python_executable": interpreter,
        "python_version": run_text([interpreter, "--version"]) or "unavailable",
        "packages": [line for line in freeze.splitlines() if line],
    }


def check_tools(niimath: str, allow_older: bool) -> Dict:
    missing = [exe for exe in ("wk-medic", "wk-apply-warp") if not shutil.which(exe)]
    if missing:
        raise BenchmarkError(
            "warpkit is not on PATH (missing: %s).\n"
            "Install the pinned environment with:\n"
            "  python3 -m venv .benchmark-tools/warpkit-1.4.1\n"
            "  .benchmark-tools/warpkit-1.4.1/bin/pip install -r requirements-benchmark-lock.txt\n"
            "Then prepend that environment's bin directory to PATH." % ", ".join(missing)
        )

    wk_medic = Path(shutil.which("wk-medic") or "")
    wk_apply = Path(shutil.which("wk-apply-warp") or "")
    environment = warpkit_environment(wk_medic)
    info = {
        "warpkit": {
            "version": environment["version"],
            "executables": {
                "wk-medic": str(wk_medic.resolve()),
                "wk-apply-warp": str(wk_apply.resolve()),
            },
            "reported_versions": {
                "wk-medic": executable_version(str(wk_medic)),
                "wk-apply-warp": executable_version(str(wk_apply)),
            },
            "environment": environment,
        }
    }

    resolved_niimath = shutil.which(niimath) or (niimath if Path(niimath).is_file() else None)
    if not resolved_niimath:
        raise BenchmarkError(
            "niimath is not on PATH (looked for %r).\n"
            "Build the pinned revision with scripts/build_niimath.py, then pass "
            "--niimath /path/to/niimath." % niimath
        )
    niimath_path = Path(resolved_niimath).resolve()
    reported = executable_version(str(niimath_path))
    have, need = version_tuple(reported), version_tuple(NIIMATH_MIN)
    if have is None:
        raise BenchmarkError(
            "could not parse a version from `%s --version` (got %r)" % (niimath_path, reported)
        )
    if need and have < need and not allow_older:
        raise BenchmarkError(
            "niimath %s is older than required %s; update to the pinned revision or "
            "pass --allow-older to label a non-comparable run." % (reported, NIIMATH_MIN)
        )
    build = find_build_provenance(niimath_path)
    info["niimath"] = {
        "version": reported,
        "executable": str(niimath_path),
        "source_commit": (build or {}).get("source_commit", "unavailable"),
        "compiler": (build or {}).get("compiler", "unavailable"),
        "openmp": (build or {}).get("openmp", "unavailable"),
        "build": build or "unavailable",
    }
    return info


def rss_to_bytes(rss: int, system: Optional[str] = None) -> float:
    """getrusage uses bytes on macOS and KiB on Linux."""
    return float(rss) if (system or platform.system()) == "Darwin" else float(rss) * 1024.0


def thread_env(threads: int) -> Dict[str, str]:
    env = dict(os.environ)
    for key in THREAD_ENV:
        env[key] = str(threads)
    env["FSLOUTPUTTYPE"] = "NIFTI"
    return env


def measure(cmd: List, dry: bool, env: Optional[Dict[str, str]] = None) -> Dict:
    command = [str(value) for value in cmd]
    limited_env = {key: (env or {}).get(key) for key in THREAD_ENV + ("FSLOUTPUTTYPE",)}
    if dry:
        print("    " + " ".join(command))
        return {
            "wall": float("nan"),
            "peak_gb": float("nan"),
            "rc": 0,
            "command": command,
            "environment": limited_env,
        }
    proc = subprocess.run(
        [sys.executable, "-c", WRAPPER] + command,
        capture_output=True,
        text=True,
        env=env,
    )
    try:
        raw = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        raise BenchmarkError(
            "measurement wrapper produced no result for:\n  %s\n%s"
            % (" ".join(command), proc.stderr)
        )
    result = {
        "wall": raw["wall"],
        "peak_gb": rss_to_bytes(raw["rss"]) / 2**30,
        "rc": raw["rc"],
        "command": command,
        "environment": limited_env,
    }
    if raw.get("stdout_tail"):
        result["stdout_tail"] = raw["stdout_tail"]
    if raw.get("stderr_tail"):
        result["stderr_tail"] = raw["stderr_tail"]
    if raw["rc"] != 0:
        raise CommandFailed(result)
    return result


def load_manifest(path: Path) -> Dict:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError("cannot read dataset manifest %s: %s" % (path, exc))
    required = (
        "key",
        "accession",
        "snapshot",
        "resolved_commit",
        "cache_relative",
        "func_dir",
        "run_stem",
        "echoes",
    )
    missing = [field for field in required if field not in manifest]
    if missing:
        raise BenchmarkError("%s is missing: %s" % (path, ", ".join(missing)))
    manifest["_manifest_path"] = str(path.resolve())
    return manifest


def available_manifests(extra: Iterable[Path]) -> Dict[str, Dict]:
    manifests = {}
    paths = sorted((HERE / "manifests").glob("*.json")) + list(extra)
    for path in paths:
        manifest = load_manifest(path)
        manifests[manifest["key"]] = manifest
    return manifests


def nifti_header(path: Path) -> Dict:
    opener = gzip.open if path.name.endswith(".gz") else open
    try:
        with opener(path, "rb") as stream:
            blob = stream.read(348)
    except OSError as exc:
        raise BenchmarkError("cannot read NIfTI header %s: %s" % (path, exc))
    if len(blob) < 348:
        raise BenchmarkError("%s is shorter than a NIfTI-1 header" % path)
    if struct.unpack("<I", blob[:4])[0] == 348:
        endian = "<"
    elif struct.unpack(">I", blob[:4])[0] == 348:
        endian = ">"
    else:
        raise BenchmarkError("%s is not a NIfTI-1 file" % path)
    dim = struct.unpack(endian + "8h", blob[40:56])
    pixdim = struct.unpack(endian + "8f", blob[76:108])
    datatype = struct.unpack(endian + "h", blob[70:72])[0]
    vox_offset = int(struct.unpack(endian + "f", blob[108:112])[0])
    slope, intercept = struct.unpack(endian + "2f", blob[112:120])
    ndim = max(0, min(7, dim[0]))
    dimensions = [int(value) for value in dim[1 : ndim + 1]]
    while len(dimensions) < 4:
        dimensions.append(1)
    return {
        "endian": endian,
        "dimensions": dimensions,
        "spatial_dimensions": dimensions[:3],
        "frames": dimensions[3],
        "voxel_size_mm": [abs(float(value)) for value in pixdim[1:4]],
        "datatype": datatype,
        "vox_offset": vox_offset,
        "slope": float(slope) if slope else 1.0,
        "intercept": float(intercept),
    }


def validate_geometry(files: List[Path]) -> Dict:
    headers = [nifti_header(path) for path in files]
    first = headers[0]
    for path, header in zip(files[1:], headers[1:]):
        if header["dimensions"] != first["dimensions"]:
            raise BenchmarkError(
                "%s dimensions %s disagree with %s" % (path, header["dimensions"], first["dimensions"])
            )
        if any(
            abs(a - b) > 1e-5
            for a, b in zip(header["voxel_size_mm"], first["voxel_size_mm"])
        ):
            raise BenchmarkError(
                "%s voxel size %s disagrees with %s"
                % (path, header["voxel_size_mm"], first["voxel_size_mm"])
            )
    return first


def validate_selected_run(
    func_root: Path,
    stem: str,
    expected_echoes: Optional[List[int]] = None,
) -> Dict:
    runs = find_runs(func_root)
    if stem not in runs:
        available = ", ".join(sorted(runs)) or "none"
        raise BenchmarkError("%s: run %s not found (available: %s)" % (func_root, stem, available))
    run = runs[stem]
    if run["dupes"]:
        detail = "\n".join(
            "  echo %s part %s: %s and %s" % (echo, part, first, second)
            for part, echo, first, second in run["dupes"]
        )
        raise BenchmarkError("%s has ambiguous duplicate images:\n%s" % (stem, detail))
    mag_echoes = sorted(run["mag"])
    phase_echoes = sorted(run["phase"])
    if mag_echoes != phase_echoes:
        raise BenchmarkError(
            "%s: magnitude echoes %s != phase echoes %s" % (stem, mag_echoes, phase_echoes)
        )
    if len(mag_echoes) < 2:
        raise BenchmarkError("%s needs at least two echoes, found %d" % (stem, len(mag_echoes)))
    if expected_echoes is not None and mag_echoes != sorted(expected_echoes):
        raise BenchmarkError(
            "%s: discovered echoes %s, manifest requires %s"
            % (stem, mag_echoes, sorted(expected_echoes))
        )

    mags = [run["mag"][echo] for echo in mag_echoes]
    phases = [run["phase"][echo] for echo in mag_echoes]
    sidecars = [sidecar(path) for path in mags + phases]
    missing = [path for path in mags + phases + sidecars if not path.is_file()]
    if missing:
        raise BenchmarkError("missing selected-run input(s):\n  " + "\n  ".join(str(x) for x in missing))

    mag_meta = read_meta(run["mag"])
    phase_meta = read_meta(run["phase"])
    for field in ("tes", "trt", "ped", "echoes"):
        if mag_meta[field] != phase_meta[field]:
            raise BenchmarkError(
                "%s: magnitude and phase sidecars disagree for %s (%s != %s)"
                % (stem, field, mag_meta[field], phase_meta[field])
            )
    header = validate_geometry(mags + phases)
    return {
        "echoes": mag_echoes,
        "mags": mags,
        "phas": phases,
        "meta": [sidecar(path) for path in phases],
        "all_sidecars": sidecars,
        "tes": phase_meta["tes"],
        "trt": phase_meta["trt"],
        "ped": phase_meta["ped"],
        "header": header,
    }


def stem_entities(stem: str) -> Dict:
    entities = {}
    for key in ("sub", "ses", "task", "run"):
        match = re.search(r"(?:^|_)%s-([^_]+)" % key, stem)
        entities[key] = match.group(1) if match else None
    return entities


def verify_external_identity(root: Path, manifest: Dict) -> Tuple[str, List[Dict]]:
    expected = manifest["resolved_commit"]
    record_path = root / PROVENANCE_NAME
    records = []
    resolved = None
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkError("cannot read %s: %s" % (record_path, exc))
        resolved = record.get("resolved_commit")
        records = record.get("files", [])
    git_head = run_text(["git", "rev-parse", "HEAD"], cwd=root) if (root / ".git").exists() else None
    for source, value in (("retrieval provenance", resolved), ("Git checkout", git_head)):
        if value and value != expected:
            raise BenchmarkError("%s is at %s, manifest requires %s" % (source, value, expected))
    if not resolved and not git_head:
        raise BenchmarkError(
            "%s has neither %s nor Git metadata; retrieve it with "
            "scripts/fetch_openneuro_sample.py so its immutable identity can be verified"
            % (root, PROVENANCE_NAME)
        )
    return expected, records


def builtin_dataset(key: str) -> Dict:
    root_name, stem, mask_name = DATASETS[key]
    root = HERE / root_name
    func = root / "sub-crlab" / "func"
    run = validate_selected_run(func, stem)
    entities = stem_entities(stem)
    run.update(
        {
            "key": key,
            "root": root,
            "run_stem": stem,
            "mask": HERE / mask_name,
            "dataset_metadata": {
                "key": key,
                "accession": "bundled",
                "snapshot": "medic_bench repository content",
                "resolved_commit": git_info(HERE).get("commit", "unavailable"),
                "subject": "sub-" + entities["sub"] if entities["sub"] else "unavailable",
                "session": "ses-" + entities["ses"] if entities["ses"] else None,
                "task": entities["task"] or "unavailable",
                "run": entities["run"] or "unavailable",
            },
        }
    )
    return finalize_dataset(run)


def external_dataset(
    manifest: Dict,
    cache_root: Path,
    bids_root: Optional[Path],
) -> Dict:
    root = (
        bids_root.expanduser().resolve()
        if bids_root
        else cache_root.expanduser().resolve() / manifest["cache_relative"]
    )
    commit, file_records = verify_external_identity(root, manifest)
    func = root / manifest["func_dir"]
    run = validate_selected_run(func, manifest["run_stem"], [int(x) for x in manifest["echoes"]])
    run.update(
        {
            "key": manifest["key"],
            "root": root,
            "run_stem": manifest["run_stem"],
            "mask": None,
            "dataset_metadata": {
                "key": manifest["key"],
                "description": manifest.get("description"),
                "accession": manifest["accession"],
                "snapshot": manifest["snapshot"],
                "resolved_commit": commit,
                "immutable_dataset_id": "%s@%s:%s"
                % (manifest["accession"], manifest["snapshot"], commit),
                "subject": manifest.get("subject", "unavailable"),
                "session": manifest.get("session"),
                "task": manifest.get("task", "unavailable"),
                "run": str(manifest.get("run", "unavailable")),
                "manifest": manifest["_manifest_path"],
                "verified_files": file_records,
            },
        }
    )
    return finalize_dataset(run)


def finalize_dataset(dataset: Dict) -> Dict:
    metadata = dataset["dataset_metadata"]
    header = dataset["header"]
    metadata.update(
        {
            "echo_count": len(dataset["echoes"]),
            "echoes": dataset["echoes"],
            "frame_count": header["frames"],
            "image_dimensions": header["spatial_dimensions"],
            "voxel_size_mm": header["voxel_size_mm"],
            "echo_times_ms": dataset["tes"],
            "total_readout_time_seconds": dataset["trt"],
            "phase_encoding_direction": dataset["ped"],
        }
    )
    return dataset


def public_dataset_metadata(dataset: Dict) -> Dict:
    return dataset["dataset_metadata"]


def aggregate_apply(commands: List[Dict], complete: bool) -> Dict:
    successful = [item for item in commands if item.get("rc") == 0]
    return {
        "status": "complete" if complete else "incomplete",
        "wall": sum(item["wall"] for item in successful) if complete else None,
        "peak_gb": max((item["peak_gb"] for item in commands), default=None),
        "completed_echoes": len(successful),
        "commands": commands,
    }


def run_one(
    tool: str,
    dataset: Dict,
    out: Path,
    threads: int,
    software: Dict,
    use_mask: bool,
    dry: bool,
) -> Dict:
    if not dry:
        out.mkdir(parents=True, exist_ok=True)
    prefix = out / "fmap"
    axis = dataset["ped"][0]
    niimath = software.get("niimath", {}).get("executable", "niimath")
    wk_medic = software.get("warpkit", {}).get("executables", {}).get("wk-medic", "wk-medic")
    wk_apply = software.get("warpkit", {}).get("executables", {}).get(
        "wk-apply-warp", "wk-apply-warp"
    )

    if tool == "warpkit":
        estimate_command = [
            wk_medic,
            "--magnitude",
            *dataset["mags"],
            "--phase",
            *dataset["phas"],
            "--metadata",
            *dataset["meta"],
            "--out-prefix",
            prefix,
            "-n",
            threads,
        ]
    else:
        estimate_command = [
            niimath,
            "--medic",
            "--magnitude",
            *dataset["mags"],
            "--phase",
            *dataset["phas"],
            "--te-ms",
            ",".join("%g" % value for value in dataset["tes"]),
            "--total-readout-time",
            "%g" % dataset["trt"],
            "--phase-encoding-direction",
            dataset["ped"],
            "--n-cpus",
            threads,
            "--gz",
            "0",
            "--out-prefix",
            prefix,
        ]
        if use_mask and dataset.get("mask"):
            estimate_command.extend(["--mask", dataset["mask"]])

    result = {"status": "incomplete", "started_at": iso_now()}
    env = thread_env(threads)
    try:
        result["estimate"] = measure(estimate_command, dry, env)
    except CommandFailed as exc:
        result["estimate"] = exc.measurement
        result["error"] = str(exc)
        result["completed_at"] = iso_now()
        return result

    dmap = Path(str(prefix) + "_displacementmaps.nii")
    apply_commands = []
    for echo, magnitude in zip(dataset["echoes"], dataset["mags"]):
        destination = out / ("undistorted_echo-%d.nii" % echo)
        if tool == "warpkit":
            command = [
                wk_apply,
                "--input",
                magnitude,
                "--transform",
                dmap,
                "--transform-type",
                "map",
                "--phase-encoding-axis",
                axis,
                "--output",
                destination,
            ]
        else:
            command = [
                niimath,
                magnitude,
                "-p",
                threads,
                "-gz",
                "0",
                "-unwarp",
                dmap,
                axis,
                destination,
            ]
        try:
            apply_commands.append(measure(command, dry, env))
        except CommandFailed as exc:
            apply_commands.append(exc.measurement)
            result["apply"] = aggregate_apply(apply_commands, complete=False)
            result["error"] = str(exc)
            result["completed_at"] = iso_now()
            return result
    result["apply"] = aggregate_apply(apply_commands, complete=True)
    result["status"] = "complete"
    result["completed_at"] = iso_now()
    return result


def nifti_value_layout(path: Path) -> Tuple[Dict, str, int]:
    header = nifti_header(path)
    formats = {
        2: ("B", 1),
        4: ("h", 2),
        8: ("i", 4),
        16: ("f", 4),
        64: ("d", 8),
        256: ("b", 1),
        512: ("H", 2),
        768: ("I", 4),
        1024: ("q", 8),
        1280: ("Q", 8),
    }
    if header["datatype"] not in formats:
        raise BenchmarkError("%s has unsupported NIfTI datatype %s" % (path, header["datatype"]))
    code, size = formats[header["datatype"]]
    count = math.prod(header["dimensions"])
    return header, code, count


def correlation_numpy(path_a: Path, path_b: Path, header_a: Dict, header_b: Dict, count: int) -> float:
    import numpy as np

    dtypes = {
        2: "u1",
        4: "i2",
        8: "i4",
        16: "f4",
        64: "f8",
        256: "i1",
        512: "u2",
        768: "u4",
        1024: "i8",
        1280: "u8",
    }
    dtype_a = np.dtype(header_a["endian"] + dtypes[header_a["datatype"]])
    dtype_b = np.dtype(header_b["endian"] + dtypes[header_b["datatype"]])
    a = np.memmap(path_a, dtype=dtype_a, mode="r", offset=header_a["vox_offset"], shape=(count,))
    b = np.memmap(path_b, dtype=dtype_b, mode="r", offset=header_b["vox_offset"], shape=(count,))
    sums = [0.0] * 5
    for start in range(0, count, 4_000_000):
        stop = min(count, start + 4_000_000)
        x = np.asarray(a[start:stop], dtype=np.float64)
        y = np.asarray(b[start:stop], dtype=np.float64)
        x = x * header_a["slope"] + header_a["intercept"]
        y = y * header_b["slope"] + header_b["intercept"]
        sums[0] += float(x.sum())
        sums[1] += float(y.sum())
        sums[2] += float(np.dot(x, x))
        sums[3] += float(np.dot(y, y))
        sums[4] += float(np.dot(x, y))
    sx, sy, sxx, syy, sxy = sums
    covariance = sxy - sx * sy / count
    variance_a = sxx - sx * sx / count
    variance_b = syy - sy * sy / count
    return covariance / math.sqrt(variance_a * variance_b)


def correlation_stdlib(
    path_a: Path,
    path_b: Path,
    header_a: Dict,
    header_b: Dict,
    code_a: str,
    code_b: str,
    count: int,
) -> float:
    size_a = struct.calcsize(code_a)
    size_b = struct.calcsize(code_b)
    sums = [0.0] * 5
    remaining = count
    with path_a.open("rb") as stream_a, path_b.open("rb") as stream_b:
        stream_a.seek(header_a["vox_offset"])
        stream_b.seek(header_b["vox_offset"])
        while remaining:
            take = min(remaining, 250_000)
            values_a = struct.iter_unpack(
                header_a["endian"] + code_a, stream_a.read(take * size_a)
            )
            values_b = struct.iter_unpack(
                header_b["endian"] + code_b, stream_b.read(take * size_b)
            )
            for packed_a, packed_b in zip(values_a, values_b):
                x = packed_a[0] * header_a["slope"] + header_a["intercept"]
                y = packed_b[0] * header_b["slope"] + header_b["intercept"]
                sums[0] += x
                sums[1] += y
                sums[2] += x * x
                sums[3] += y * y
                sums[4] += x * y
            remaining -= take
    sx, sy, sxx, syy, sxy = sums
    covariance = sxy - sx * sy / count
    variance_a = sxx - sx * sx / count
    variance_b = syy - sy * sy / count
    return covariance / math.sqrt(variance_a * variance_b)


def agreement(out_dir: Path, key: str, threads: int, repetition: Optional[int] = None) -> Dict:
    base = out_dir / key
    suffix = Path("repeat-%d" % repetition) if repetition is not None else Path()
    path_a = base / "warpkit" / str(threads) / suffix / "undistorted_echo-1.nii"
    path_b = base / "niimath" / str(threads) / suffix / "undistorted_echo-1.nii"
    if not path_a.is_file() or not path_b.is_file():
        return {}
    try:
        header_a, code_a, count_a = nifti_value_layout(path_a)
        header_b, code_b, count_b = nifti_value_layout(path_b)
        if count_a != count_b:
            return {"status": "unavailable", "reason": "corrected images have different sizes"}
        try:
            corr = correlation_numpy(path_a, path_b, header_a, header_b, count_a)
            engine = "numpy-memmap"
        except ImportError:
            corr = correlation_stdlib(
                path_a, path_b, header_a, header_b, code_a, code_b, count_a
            )
            engine = "stdlib-streaming"
        return {"status": "complete", "corr": corr, "voxels": count_a, "engine": engine}
    except (BenchmarkError, OSError, ValueError, ZeroDivisionError) as exc:
        return {"status": "unavailable", "reason": str(exc)}


def sysctl_value(name: str) -> Optional[str]:
    return run_text(["sysctl", "-n", name])


def parse_os_release() -> Dict[str, str]:
    values = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def machine_info(label: str) -> Dict:
    system = platform.system()
    info = {
        "label": label,
        "hostname": socket.gethostname(),
        "operating_system": system,
        "os_version": platform.version(),
        "kernel_version": platform.release(),
        "architecture": platform.machine(),
        "cpu_manufacturer": "unavailable",
        "cpu_model": platform.processor() or "unavailable",
        "physical_cores": "unavailable",
        "logical_cpus": os.cpu_count() or "unavailable",
        "performance_cores": "unavailable",
        "efficiency_cores": "unavailable",
        "total_ram_bytes": "unavailable",
    }
    if system == "Darwin":
        info["os_version"] = run_text(["sw_vers", "-productVersion"]) or info["os_version"]
        info["cpu_manufacturer"] = "Apple"
        brand = sysctl_value("machdep.cpu.brand_string")
        physical = sysctl_value("hw.physicalcpu")
        logical = sysctl_value("hw.logicalcpu")
        memory = sysctl_value("hw.memsize")
        perf = sysctl_value("hw.perflevel0.physicalcpu")
        efficiency = sysctl_value("hw.perflevel1.physicalcpu")
        hardware = run_text(["system_profiler", "SPHardwareDataType"]) or ""
        chip = re.search(r"^\s*Chip:\s*(.+)$", hardware, re.MULTILINE)
        cores = re.search(
            r"Total Number of Cores:\s*(\d+)\s*\((\d+)\s+Performance and\s+(\d+)\s+Efficiency",
            hardware,
        )
        memory_text = re.search(r"^\s*Memory:\s*(\d+)\s+GB", hardware, re.MULTILINE)
        info["cpu_model"] = brand or (chip.group(1) if chip else info["cpu_model"])
        info["physical_cores"] = int(physical) if physical and physical.isdigit() else (
            int(cores.group(1)) if cores else "unavailable"
        )
        info["logical_cpus"] = int(logical) if logical and logical.isdigit() else info["logical_cpus"]
        info["performance_cores"] = int(perf) if perf and perf.isdigit() else (
            int(cores.group(2)) if cores else "unavailable"
        )
        info["efficiency_cores"] = int(efficiency) if efficiency and efficiency.isdigit() else (
            int(cores.group(3)) if cores else "unavailable"
        )
        info["total_ram_bytes"] = int(memory) if memory and memory.isdigit() else (
            int(memory_text.group(1)) * 1024**3 if memory_text else "unavailable"
        )
    elif system == "Linux":
        os_release = parse_os_release()
        info["os_version"] = os_release.get("PRETTY_NAME", info["os_version"])
        lscpu = run_text(["lscpu"]) or ""
        fields = {}
        for line in lscpu.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        info["cpu_manufacturer"] = fields.get("Vendor ID", "unavailable")
        info["cpu_model"] = fields.get("Model name", info["cpu_model"])
        sockets = fields.get("Socket(s)")
        cores_per_socket = fields.get("Core(s) per socket")
        if sockets and cores_per_socket and sockets.isdigit() and cores_per_socket.isdigit():
            info["physical_cores"] = int(sockets) * int(cores_per_socket)
        if fields.get("CPU(s)", "").isdigit():
            info["logical_cpus"] = int(fields["CPU(s)"])
        try:
            mem_kib = next(
                int(line.split()[1])
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemTotal:")
            )
            info["total_ram_bytes"] = mem_kib * 1024
        except (OSError, StopIteration, ValueError):
            pass
    return info


def git_info(root: Path) -> Dict:
    commit = run_text(["git", "rev-parse", "HEAD"], cwd=root) or "unavailable"
    branch = run_text(["git", "branch", "--show-current"], cwd=root) or "detached"
    dirty_text = run_text(["git", "status", "--porcelain"], cwd=root)
    return {"commit": commit, "branch": branch, "dirty": bool(dirty_text)}


def python_info() -> Dict:
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
    }


def fmt(value, unit: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        if math.isnan(float(value)):
            return "n/a"
    except (TypeError, ValueError):
        return str(value)
    return ("%.2f %s" % (float(value), unit)).strip()


def measurement_for(cell: Dict) -> Optional[Dict]:
    if "measurements" in cell:
        completed = [item for item in cell["measurements"] if item.get("status") == "complete"]
        # Never publish a timing from a failed or partial measurement. Its
        # command, elapsed time, and error remain available in raw JSON.
        return completed[-1] if completed else None
    return cell if "estimate" in cell else None


def stage_for(cell: Dict, stage: str) -> Optional[Dict]:
    measurement = measurement_for(cell)
    return measurement.get(stage) if measurement else None


def end_to_end(cell: Dict) -> Optional[float]:
    estimate = stage_for(cell, "estimate")
    apply = stage_for(cell, "apply")
    if not estimate or not apply or estimate.get("wall") is None or apply.get("wall") is None:
        return None
    return float(estimate["wall"]) + float(apply["wall"])


def tables(results: Dict, threads: List[int]) -> str:
    lines = []
    for key, result in results.items():
        dataset = result.get("dataset", {})
        frames = dataset.get("frame_count", result.get("frames", 0))
        echoes = dataset.get("echo_count", result.get("echoes", 0))
        lines.append("### %s — %s echoes, %s frames\n" % (key, echoes, frames))
        lines.append(
            "| stage | threads | warpkit wall | niimath wall | speed-up | "
            "warpkit peak RAM | niimath peak RAM |"
        )
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for stage in ("estimate", "apply"):
            for thread in threads:
                run = result.get("runs", {}).get(str(thread), {})
                if "warpkit" not in run or "niimath" not in run:
                    continue
                warpkit = stage_for(run["warpkit"], stage)
                niimath = stage_for(run["niimath"], stage)
                if not warpkit or not niimath:
                    continue
                w_wall, n_wall = warpkit.get("wall"), niimath.get("wall")
                speed = (
                    "%.2fx" % (w_wall / n_wall)
                    if w_wall is not None and n_wall not in (None, 0)
                    else "n/a"
                )
                lines.append(
                    "| %s | %d | %s | %s | **%s** | %s | %s |"
                    % (
                        stage,
                        thread,
                        fmt(w_wall, "s"),
                        fmt(n_wall, "s"),
                        speed,
                        fmt(warpkit.get("peak_gb"), "GB"),
                        fmt(niimath.get("peak_gb"), "GB"),
                    )
                )
        lines.append("")
        lines.append("| threads | warpkit end to end | niimath end to end | speed-up | agreement (r) |")
        lines.append("| ---: | ---: | ---: | ---: | ---: |")
        for thread in threads:
            run = result.get("runs", {}).get(str(thread), {})
            w_total = end_to_end(run.get("warpkit", {}))
            n_total = end_to_end(run.get("niimath", {}))
            speed = (
                "%.2fx" % (w_total / n_total)
                if w_total is not None and n_total not in (None, 0)
                else "n/a"
            )
            agreement_result = result.get("agreement", {}).get(str(thread), {})
            corr = agreement_result.get("corr")
            corr_text = "n/a" if corr is None else "%.6f" % float(corr)
            lines.append(
                "| %d | %s | %s | **%s** | %s |"
                % (thread, fmt(w_total, "s"), fmt(n_total, "s"), speed, corr_text)
            )
        failures = result.get("failures", [])
        if failures:
            lines.append("")
            lines.append("Incomplete cells: " + "; ".join(failures))
        lines.append("")
    return "\n".join(lines)


def human_bytes(value) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return "%.1f %s" % (amount, unit)
        amount /= 1024
    return str(value)


def machine_markdown(machine: Dict) -> str:
    manufacturer = str(machine.get("cpu_manufacturer", "unavailable"))
    model = str(machine.get("cpu_model", "unavailable"))
    cpu = model if model.lower().startswith(manufacturer.lower()) else manufacturer + " " + model
    rows = [
        ("Label", machine.get("label")),
        ("Operating system", "%s %s" % (machine.get("operating_system"), machine.get("os_version"))),
        ("Kernel", machine.get("kernel_version")),
        ("Architecture", machine.get("architecture")),
        ("CPU", cpu),
        ("Physical cores", machine.get("physical_cores")),
        ("Logical CPUs", machine.get("logical_cpus")),
        ("Performance cores", machine.get("performance_cores")),
        ("Efficiency cores", machine.get("efficiency_cores")),
        ("Installed RAM", human_bytes(machine.get("total_ram_bytes"))),
    ]
    lines = ["| field | value |", "| --- | --- |"]
    lines.extend("| %s | %s |" % (name, value if value is not None else "unavailable") for name, value in rows)
    return "\n".join(lines)


def software_markdown(payload: Dict) -> str:
    software = payload.get("software", payload.get("tools", {}))
    python = software.get("python", {})
    warpkit = software.get("warpkit", {})
    niimath = software.get("niimath", {})
    bench = software.get("medic_bench", {})
    compiler = niimath.get("compiler", {})
    openmp = niimath.get("openmp", {})
    if not isinstance(compiler, dict):
        compiler = {"version": compiler}
    if not isinstance(openmp, dict):
        openmp = {"runtime": openmp}
    rows = [
        ("Python", "%s (%s)" % (python.get("version", "unavailable"), python.get("executable", ""))),
        ("warpkit", warpkit.get("version", "unavailable")),
        ("wk-medic", warpkit.get("executables", {}).get("wk-medic", "unavailable")),
        ("wk-apply-warp", warpkit.get("executables", {}).get("wk-apply-warp", "unavailable")),
        ("niimath", "%s (%s)" % (niimath.get("version", "unavailable"), niimath.get("executable", ""))),
        ("niimath source", niimath.get("source_commit", "unavailable")),
        ("niimath compiler", compiler.get("version", "unavailable")),
        (
            "OpenMP",
            "%s %s" % (openmp.get("runtime", "unavailable"), openmp.get("version", "")),
        ),
        (
            "medic_bench",
            "%s%s"
            % (bench.get("commit", "unavailable"), " (dirty)" if bench.get("dirty") else ""),
        ),
    ]
    def markdown_cell(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    lines = ["| software | version / path |", "| --- | --- |"]
    lines.extend("| %s | %s |" % (markdown_cell(name), markdown_cell(value)) for name, value in rows)
    return "\n".join(lines)


def dataset_markdown(results: Dict) -> str:
    lines = [
        "| dataset | accession | snapshot / commit | subject | task | run | echoes | frames | "
        "dimensions | voxel (mm) | TE (ms) | readout (s) | PE |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- |",
    ]
    for key, result in results.items():
        dataset = result.get("dataset", {})
        lines.append(
            "| %s | %s | %s / %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                key,
                dataset.get("accession", "unavailable"),
                dataset.get("snapshot", "unavailable"),
                dataset.get("resolved_commit", "unavailable"),
                dataset.get("subject", "unavailable"),
                dataset.get("task", "unavailable"),
                dataset.get("run", "unavailable"),
                dataset.get("echo_count", "unavailable"),
                dataset.get("frame_count", "unavailable"),
                " × ".join(str(x) for x in dataset.get("image_dimensions", [])),
                ", ".join("%.4g" % x for x in dataset.get("voxel_size_mm", [])),
                ", ".join("%.4g" % x for x in dataset.get("echo_times_ms", [])),
                dataset.get("total_readout_time_seconds", "unavailable"),
                dataset.get("phase_encoding_direction", "unavailable"),
            )
        )
    return "\n".join(lines)


def render_payload(payload: Dict) -> str:
    label = payload.get("machine", {}).get("label", "unlabeled machine")
    lines = [
        "# MEDIC benchmark — %s" % label,
        "",
        "Status: **%s**. Started `%s`." % (payload.get("status", "unknown"), payload.get("started_at", "unavailable")),
        "",
        "## Machine",
        "",
        machine_markdown(payload.get("machine", {})),
        "",
        "The hostname is intentionally retained only in raw JSON.",
        "",
        "## Software",
        "",
        software_markdown(payload),
        "",
        "## Datasets",
        "",
        dataset_markdown(payload.get("results", {})),
        "",
        "## Measurements",
        "",
        tables(payload.get("results", {}), payload.get("threads", [])),
    ]
    notes = payload.get("notes", [])
    failures = payload.get("failures", [])
    if notes or failures:
        lines.extend(["", "## Notes and incomplete work", ""])
        lines.extend("- " + value for value in notes + failures)
    return "\n".join(lines).rstrip() + "\n"


def provenance(payload: Dict) -> str:
    machine = payload["machine"]
    software = payload["software"]
    return (
        "Measured on %s (%s %s, %s, %s logical CPUs) with warpkit %s and niimath %s "
        "from %s. Uncompressed NIfTI on both sides; thread counts pinned by arguments "
        "and environment."
        % (
            machine["label"],
            machine["operating_system"],
            machine["os_version"],
            machine["architecture"],
            machine["logical_cpus"],
            software["warpkit"].get("version", "unavailable"),
            software["niimath"].get("version", "unavailable"),
            software["niimath"].get("source_commit", "unavailable"),
        )
    )


def merge_previous(results: Dict, merge_path: Path) -> None:
    try:
        old = json.loads(merge_path.read_text()).get("results", {})
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError("cannot merge %s: %s" % (merge_path, exc))
    for key, result in results.items():
        for thread, run in result["runs"].items():
            for tool in ("warpkit", "niimath"):
                if tool in run:
                    continue
                previous = old.get(key, {}).get("runs", {}).get(thread, {}).get(tool)
                if previous:
                    run[tool] = (
                        previous
                        if "measurements" in previous
                        else {"measurements": [previous], "carried_from": str(merge_path)}
                    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--datasets", nargs="+", default=sorted(DATASETS))
    parser.add_argument(
        "--dataset-manifest",
        action="append",
        type=Path,
        default=[],
        help="additional portable external-dataset manifest (repeatable)",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=default_cache_root(),
        help="OpenNeuro cache parent (default: $MEDIC_BENCH_CACHE or ~/.cache/medic_bench/openneuro)",
    )
    parser.add_argument(
        "--bids-root",
        type=Path,
        default=None,
        help="override the data root for one selected external manifest",
    )
    parser.add_argument("--threads", type=int, nargs="+", default=None)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--machine-label", default=os.environ.get("MEDIC_BENCH_MACHINE"))
    parser.add_argument("--niimath", default=os.environ.get("NIIMATH", "niimath"))
    parser.add_argument("--out-dir", type=Path, default=HERE / "bench_out")
    parser.add_argument(
        "--tools",
        nargs="+",
        choices=["warpkit", "niimath"],
        default=["warpkit", "niimath"],
    )
    parser.add_argument("--compare-dir", type=Path, default=None)
    parser.add_argument("--merge", type=Path, default=None)
    parser.add_argument("--no-mask", action="store_true")
    parser.add_argument("--allow-older", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", type=Path, default=HERE / "bench_results.json")
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--update-readme", action="store_true")
    args = parser.parse_args(argv)

    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    if any(thread < 1 for thread in (args.threads or [])):
        parser.error("--threads values must be positive")

    manifests = available_manifests(args.dataset_manifest)
    known = set(DATASETS) | set(manifests)
    unknown = [key for key in args.datasets if key not in known]
    if unknown:
        parser.error(
            "unknown dataset(s): %s (available: %s)"
            % (", ".join(unknown), ", ".join(sorted(known)))
        )
    selected_external = [key for key in args.datasets if key in manifests]
    if args.bids_root and len(selected_external) != 1:
        parser.error("--bids-root requires exactly one selected external dataset")

    threads = args.threads or sorted({1, default_threads()})
    label = args.machine_label or socket.gethostname()
    started_at = iso_now()
    try:
        software = (
            {
                "warpkit": {
                    "version": "dry-run",
                    "executables": {"wk-medic": "wk-medic", "wk-apply-warp": "wk-apply-warp"},
                },
                "niimath": {
                    "version": "dry-run",
                    "executable": args.niimath,
                    "source_commit": "not checked in dry-run",
                    "compiler": "not checked in dry-run",
                    "openmp": "not checked in dry-run",
                },
            }
            if args.dry_run
            else check_tools(args.niimath, args.allow_older)
        )
        software["python"] = python_info()
        software["medic_bench"] = git_info(HERE)

        datasets = {}
        for key in args.datasets:
            datasets[key] = (
                builtin_dataset(key)
                if key in DATASETS
                else external_dataset(manifests[key], args.cache_root, args.bids_root)
            )
    except (BenchmarkError, SystemExit) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    print(
        "machine : %s (%s %s, %s)" % (label, platform.system(), platform.release(), platform.machine())
    )
    print("threads : %s" % ", ".join(str(value) for value in threads))
    print("warpkit : %s" % software["warpkit"].get("version", "unavailable"))
    print("niimath : %s" % software["niimath"].get("version", "unavailable"))
    print()

    results = {}
    all_failures = []
    for key, dataset in datasets.items():
        results[key] = {
            "dataset": public_dataset_metadata(dataset),
            "mask": (
                "built-in for both"
                if args.no_mask
                else ("supplied to niimath only" if dataset.get("mask") else "built-in for both")
            ),
            "runs": {},
            "agreement": {},
            "failures": [],
        }
        for thread in threads:
            run = {}
            results[key]["runs"][str(thread)] = run
            for tool in args.tools:
                cell = {"measurements": []}
                run[tool] = cell
                for repetition in range(1, args.repetitions + 1):
                    repeat_suffix = (
                        Path("repeat-%d" % repetition) if args.repetitions > 1 else Path()
                    )
                    output = args.out_dir / key / tool / str(thread) / repeat_suffix
                    print(
                        "  %-24s %-8s %d thread(s), measurement %d/%d ..."
                        % (key, tool, thread, repetition, args.repetitions),
                        flush=True,
                    )
                    measurement = run_one(
                        tool,
                        dataset,
                        output,
                        thread,
                        software,
                        not args.no_mask,
                        args.dry_run,
                    )
                    cell["measurements"].append(measurement)
                    if measurement.get("status") != "complete":
                        failure = "%s/%s/%s/repetition-%d: %s" % (
                            key,
                            thread,
                            tool,
                            repetition,
                            measurement.get("error", "incomplete"),
                        )
                        results[key]["failures"].append(failure)
                        all_failures.append(failure)
                    estimate = measurement.get("estimate", {})
                    apply = measurement.get("apply", {})
                    print(
                        "    estimate %s, apply %s, status %s"
                        % (
                            fmt(estimate.get("wall"), "s"),
                            fmt(apply.get("wall"), "s"),
                            measurement.get("status"),
                        )
                    )

    if args.dry_run:
        return 0

    if args.merge and args.merge.is_file():
        try:
            merge_previous(results, args.merge)
        except BenchmarkError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2

    for key in results:
        for thread in threads:
            repetition = args.repetitions if args.repetitions > 1 else None
            quality = agreement(args.out_dir, key, thread, repetition)
            if not quality and args.compare_dir:
                quality = agreement(args.compare_dir, key, thread, repetition)
            results[key]["agreement"][str(thread)] = quality or {
                "status": "unavailable",
                "reason": "both corrected echo-1 outputs are required",
            }
            corr = results[key]["agreement"][str(thread)].get("corr")
            print(
                "  %-24s %d-thread corrected-image correlation: %s"
                % (key, thread, fmt(corr))
            )

    notes = list(args.note)
    if any(dataset.get("mask") is None for dataset in datasets.values()) and not args.no_mask:
        notes.append("No external mask exists for the OpenNeuro run; both tools used internal masks.")
    payload = {
        "schema_version": 2,
        "status": "incomplete" if all_failures else "complete",
        "started_at": started_at,
        "completed_at": iso_now(),
        "machine": machine_info(label),
        "software": software,
        "threads": threads,
        "thread_environment_variables": list(THREAD_ENV),
        "benchmark_command": [sys.executable] + sys.argv,
        "mask_policy": "built-in for both" if args.no_mask else "dataset-specific",
        "repetitions": args.repetitions,
        "notes": notes,
        "failures": all_failures,
        "results": results,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    markdown = render_payload(payload)
    print("\n" + tables(results, threads))
    print("wrote %s" % args.json)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown)
        print("wrote %s" % args.markdown)

    if args.update_readme:
        readme = HERE / "README.md"
        text = readme.read_text()
        marker = "<!-- BENCH_TABLES -->"
        if marker not in text:
            print("README.md has no %s marker; tables not inserted" % marker, file=sys.stderr)
        else:
            head, _, tail = text.partition(marker)
            rest = tail.split("\n## ", 1)
            body = marker + "\n\n" + provenance(payload) + "\n\n" + tables(results, threads)
            readme.write_text(head + body + ("\n## " + rest[1] if len(rest) > 1 else ""))
            print("updated %s" % readme)
    return 1 if all_failures else 0


if __name__ == "__main__":
    sys.exit(main())
