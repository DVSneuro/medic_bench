#!/usr/bin/env python3
"""Discover, summarize, and compare MEDIC field-map outputs.

The QA calculations deliberately sample the first, middle, and last frames of
4D files. This keeps routine checks inexpensive while still catching common
failures such as non-finite values, empty maps, malformed geometry, and
cross-tool grid mismatches. The interactive notebook provides full 4D visual
inspection with ipyniivue.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import nibabel as nib
import numpy as np


TOOLS = ("warpkit", "niimath")
MAP_KINDS = ("fieldmaps", "fieldmaps_native", "displacementmaps")


@dataclass(frozen=True)
class MapOutput:
    """One generated MEDIC map and the labels encoded in its path."""

    path: Path
    machine: str
    dataset: str
    tool: str
    threads: int
    kind: str
    repetition: Optional[str] = None

    @property
    def label(self) -> str:
        repeat = "/%s" % self.repetition if self.repetition else ""
        return "%s/%s/%s/%s%s/%s" % (
            self.machine,
            self.dataset,
            self.tool,
            self.threads,
            repeat,
            self.kind,
        )

    def public_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        payload["label"] = self.label
        return payload


def _strip_nifti_suffix(path: Path) -> str:
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


def _map_kind(path: Path) -> Optional[str]:
    stem = _strip_nifti_suffix(path)
    if not stem.startswith("fmap_"):
        return None
    kind = stem[len("fmap_") :]
    return kind if kind in MAP_KINDS else None


def discover_maps(root: Path) -> List[MapOutput]:
    """Find benchmark map outputs beneath ``root``.

    ``root`` may be ``bench_out`` (multiple machine labels) or one machine
    directory such as ``bench_out/linux1``.
    """

    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError("QA root does not exist or is not a directory: %s" % root)

    records: List[MapOutput] = []
    for path in sorted(root.rglob("fmap_*.nii*")):
        kind = _map_kind(path)
        if kind is None or not path.is_file():
            continue

        relative = path.relative_to(root)
        parts = relative.parts
        tool_positions = [index for index, part in enumerate(parts) if part in TOOLS]
        if len(tool_positions) != 1:
            continue
        tool_index = tool_positions[0]
        if tool_index < 1 or tool_index + 1 >= len(parts):
            continue
        try:
            threads = int(parts[tool_index + 1])
        except ValueError:
            continue

        dataset = parts[tool_index - 1]
        prefix = parts[: tool_index - 1]
        machine = "/".join(prefix) if prefix else root.name
        repetition_parts = parts[tool_index + 2 : -1]
        repetition = "/".join(repetition_parts) if repetition_parts else None
        records.append(
            MapOutput(
                path=path,
                machine=machine,
                dataset=dataset,
                tool=parts[tool_index],
                threads=threads,
                kind=kind,
                repetition=repetition,
            )
        )
    return records


def filter_maps(
    records: Iterable[MapOutput],
    machine: Optional[str] = None,
    dataset: Optional[str] = None,
    tool: Optional[str] = None,
    threads: Optional[int] = None,
    kind: Optional[str] = None,
) -> List[MapOutput]:
    """Return records matching the provided labels."""

    return [
        record
        for record in records
        if (machine is None or record.machine == machine)
        and (dataset is None or record.dataset == dataset)
        and (tool is None or record.tool == tool)
        and (threads is None or record.threads == threads)
        and (kind is None or record.kind == kind)
    ]


def frame_indices(shape: Sequence[int]) -> List[int]:
    """Choose first, middle, and last frames without duplicates."""

    if len(shape) <= 3:
        return [0]
    if len(shape) != 4:
        raise ValueError("QA supports 3D or 4D NIfTI files; got shape %r" % (tuple(shape),))
    frame_count = int(shape[3])
    if frame_count < 1:
        raise ValueError("4D NIfTI file has no frames")
    return sorted({0, frame_count // 2, frame_count - 1})


def _read_frame(image: nib.spatialimages.SpatialImage, frame: int) -> np.ndarray:
    if len(image.shape) == 3:
        data = np.asanyarray(image.dataobj)
    elif len(image.shape) == 4:
        data = np.asanyarray(image.dataobj[..., frame])
    else:
        raise ValueError("QA supports 3D or 4D NIfTI files; got shape %r" % (image.shape,))
    return np.asarray(data, dtype=np.float64)


def _number(value: Any) -> Optional[float]:
    result = float(value)
    return result if math.isfinite(result) else None


def frame_statistics(data: np.ndarray, frame: int) -> Dict[str, Any]:
    """Compute descriptive statistics for one sampled 3D frame."""

    finite = np.isfinite(data)
    finite_values = data[finite]
    result: Dict[str, Any] = {
        "frame": int(frame),
        "voxels": int(data.size),
        "finite_voxels": int(finite.sum()),
        "finite_fraction": float(finite.mean()) if data.size else 0.0,
    }
    if not finite_values.size:
        result.update(
            {
                "zero_fraction": None,
                "min": None,
                "p01": None,
                "median": None,
                "p99": None,
                "max": None,
                "mean": None,
                "std": None,
            }
        )
        return result

    percentiles = np.percentile(finite_values, [1, 50, 99])
    result.update(
        {
            "zero_fraction": float(np.count_nonzero(finite_values == 0) / finite_values.size),
            "min": _number(finite_values.min()),
            "p01": _number(percentiles[0]),
            "median": _number(percentiles[1]),
            "p99": _number(percentiles[2]),
            "max": _number(finite_values.max()),
            "mean": _number(finite_values.mean(dtype=np.float64)),
            "std": _number(finite_values.std(dtype=np.float64)),
        }
    )
    return result


def summarize_map(record: MapOutput) -> Dict[str, Any]:
    """Return structural checks and sampled-value statistics for one map."""

    image = nib.load(str(record.path), mmap=True)
    shape = tuple(int(value) for value in image.shape)
    spatial_zooms = tuple(float(value) for value in image.header.get_zooms()[:3])
    affine = np.asarray(image.affine, dtype=np.float64)
    affine_finite = bool(np.isfinite(affine).all())
    determinant = float(np.linalg.det(affine[:3, :3])) if affine_finite else float("nan")
    indices = frame_indices(shape)
    samples = [frame_statistics(_read_frame(image, index), index) for index in indices]

    checks = {
        "supported_dimensions": len(shape) in (3, 4),
        "nonempty_spatial_grid": len(shape) >= 3 and all(value > 0 for value in shape[:3]),
        "finite_affine": affine_finite,
        "nonsingular_affine": math.isfinite(determinant) and abs(determinant) > 1e-8,
        "positive_spatial_zooms": len(spatial_zooms) == 3
        and all(value > 0 and math.isfinite(value) for value in spatial_zooms),
        "sampled_values_finite": all(sample["finite_fraction"] == 1.0 for sample in samples),
        "sampled_map_not_all_zero": any(
            sample["zero_fraction"] is not None and sample["zero_fraction"] < 1.0
            for sample in samples
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    status = "pass" if not failed else "warn"

    finite_fractions = [sample["finite_fraction"] for sample in samples]
    zero_fractions = [
        sample["zero_fraction"] for sample in samples if sample["zero_fraction"] is not None
    ]
    robust_lows = [sample["p01"] for sample in samples if sample["p01"] is not None]
    robust_highs = [sample["p99"] for sample in samples if sample["p99"] is not None]
    return {
        "record": record.public_dict(),
        "status": status,
        "warnings": failed,
        "file_size_bytes": record.path.stat().st_size,
        "shape": list(shape),
        "dtype": str(image.get_data_dtype()),
        "spatial_zooms": list(spatial_zooms),
        "orientation": list(nib.aff2axcodes(affine)) if affine_finite else None,
        "affine_determinant": _number(determinant),
        "qform_code": int(image.header["qform_code"]),
        "sform_code": int(image.header["sform_code"]),
        "sampled": {
            "policy": "first, middle, and last frame (unique)",
            "frames": indices,
            "finite_fraction_min": min(finite_fractions),
            "zero_fraction_min": min(zero_fractions) if zero_fractions else None,
            "zero_fraction_max": max(zero_fractions) if zero_fractions else None,
            "robust_min": min(robust_lows) if robust_lows else None,
            "robust_max": max(robust_highs) if robust_highs else None,
            "frame_statistics": samples,
        },
        "checks": checks,
    }


def compare_maps(first: MapOutput, second: MapOutput) -> Dict[str, Any]:
    """Compare sampled values and geometry for a pair of maps."""

    first_image = nib.load(str(first.path), mmap=True)
    second_image = nib.load(str(second.path), mmap=True)
    same_shape = tuple(first_image.shape) == tuple(second_image.shape)
    affine_delta = float(
        np.max(np.abs(np.asarray(first_image.affine) - np.asarray(second_image.affine)))
    )
    affine_close = bool(
        np.allclose(first_image.affine, second_image.affine, rtol=1e-6, atol=1e-5)
    )
    result: Dict[str, Any] = {
        "first": first.public_dict(),
        "second": second.public_dict(),
        "checks": {
            "same_shape": same_shape,
            "affine_close": affine_close,
        },
        "affine_max_abs_difference": affine_delta,
    }
    if not same_shape:
        result.update(
            {
                "status": "fail",
                "reason": "shape mismatch",
                "sampled_comparison": None,
            }
        )
        return result

    indices = frame_indices(first_image.shape)
    first_values: List[np.ndarray] = []
    second_values: List[np.ndarray] = []
    sampled_voxels = 0
    finite_overlap = 0
    per_frame: List[Dict[str, Any]] = []
    for index in indices:
        first_data = _read_frame(first_image, index)
        second_data = _read_frame(second_image, index)
        valid = np.isfinite(first_data) & np.isfinite(second_data)
        sampled_voxels += int(valid.size)
        finite_overlap += int(valid.sum())
        x = first_data[valid]
        y = second_data[valid]
        first_values.append(x)
        second_values.append(y)
        per_frame.append(
            {
                "frame": int(index),
                "finite_overlap_fraction": float(valid.mean()),
                "voxels_compared": int(valid.sum()),
            }
        )

    x_all = np.concatenate(first_values) if first_values else np.array([], dtype=np.float64)
    y_all = np.concatenate(second_values) if second_values else np.array([], dtype=np.float64)
    if not x_all.size:
        result.update(
            {
                "status": "fail",
                "reason": "no finite overlapping sampled voxels",
                "sampled_comparison": None,
            }
        )
        return result

    delta = x_all - y_all
    x_std = float(x_all.std(dtype=np.float64))
    y_std = float(y_all.std(dtype=np.float64))
    correlation = (
        float(np.corrcoef(x_all, y_all)[0, 1])
        if x_all.size > 1 and x_std > 0 and y_std > 0
        else None
    )
    abs_delta = np.abs(delta)
    result.update(
        {
            "status": "pass" if affine_close else "fail",
            "reason": None if affine_close else "affine mismatch",
            "sampled_comparison": {
                "policy": "first, middle, and last frame (unique)",
                "frames": indices,
                "sampled_voxels": sampled_voxels,
                "voxels_compared": int(x_all.size),
                "finite_overlap_fraction": float(finite_overlap / sampled_voxels),
                "correlation": _number(correlation) if correlation is not None else None,
                "mean_absolute_difference": _number(abs_delta.mean(dtype=np.float64)),
                "root_mean_square_difference": _number(
                    np.sqrt(np.mean(delta * delta, dtype=np.float64))
                ),
                "p99_absolute_difference": _number(np.percentile(abs_delta, 99)),
                "max_absolute_difference": _number(abs_delta.max()),
                "exact_equal_fraction": float(np.count_nonzero(x_all == y_all) / x_all.size),
                "per_frame": per_frame,
            },
        }
    )
    return result


def matched_pairs(records: Iterable[MapOutput]) -> List[Tuple[MapOutput, MapOutput]]:
    """Pair Warpkit and niimath records with identical output labels."""

    grouped: Dict[Tuple[str, str, int, Optional[str], str], Dict[str, MapOutput]] = {}
    for record in records:
        key = (
            record.machine,
            record.dataset,
            record.threads,
            record.repetition,
            record.kind,
        )
        grouped.setdefault(key, {})[record.tool] = record
    return [
        (tools["warpkit"], tools["niimath"])
        for _, tools in sorted(grouped.items(), key=lambda item: str(item[0]))
        if "warpkit" in tools and "niimath" in tools
    ]


def _fmt(value: Optional[float], digits: int = 4) -> str:
    return "n/a" if value is None else ("%.*g" % (digits, value))


def print_report(report: Dict[str, Any]) -> None:
    """Print a compact human-readable report."""

    print("Map QA (sampled first/middle/last frames)")
    print(
        "%-5s %-12s %-24s %7s %-18s %-16s %9s %19s"
        % (
            "state",
            "machine",
            "dataset",
            "threads",
            "tool/kind",
            "shape",
            "finite",
            "robust range",
        )
    )
    for summary in report["maps"]:
        record = summary["record"]
        sampled = summary["sampled"]
        print(
            "%-5s %-12s %-24s %7d %-18s %-16s %8.3f%% %9s .. %-9s"
            % (
                summary["status"],
                record["machine"][-12:],
                record["dataset"][:24],
                record["threads"],
                (record["tool"] + "/" + record["kind"])[:18],
                "x".join(str(value) for value in summary["shape"]),
                100.0 * sampled["finite_fraction_min"],
                _fmt(sampled["robust_min"]),
                _fmt(sampled["robust_max"]),
            )
        )
    if report["comparisons"]:
        print("\nCross-tool sampled comparisons")
        for comparison in report["comparisons"]:
            first = comparison["first"]
            metrics = comparison["sampled_comparison"]
            if metrics is None:
                print("  FAIL %s: %s" % (first["label"], comparison["reason"]))
                continue
            print(
                "  %-56s r=%-10s RMSE=%-10s p99|diff|=%s"
                % (
                    first["label"],
                    _fmt(metrics["correlation"], 7),
                    _fmt(metrics["root_mean_square_difference"]),
                    _fmt(metrics["p99_absolute_difference"]),
                )
            )


def build_report(records: Sequence[MapOutput], include_comparisons: bool = True) -> Dict[str, Any]:
    maps = [summarize_map(record) for record in records]
    comparisons = (
        [compare_maps(first, second) for first, second in matched_pairs(records)]
        if include_comparisons
        else []
    )
    return {
        "schema_version": 1,
        "sample_policy": "first, middle, and last frame (unique)",
        "maps": maps,
        "comparisons": comparisons,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sample generated MEDIC maps for structural/value QA and "
            "cross-tool comparison."
        )
    )
    parser.add_argument("--root", type=Path, default=Path("bench_out"))
    parser.add_argument("--machine")
    parser.add_argument("--dataset")
    parser.add_argument("--tool", choices=TOOLS)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--kind", choices=MAP_KINDS)
    parser.add_argument("--no-compare", action="store_true")
    parser.add_argument("--json", type=Path, help="also write the QA report as JSON")
    args = parser.parse_args(argv)

    try:
        records = filter_maps(
            discover_maps(args.root),
            machine=args.machine,
            dataset=args.dataset,
            tool=args.tool,
            threads=args.threads,
            kind=args.kind,
        )
        if not records:
            parser.error("no generated maps matched the requested root and filters")
        report = build_report(records, include_comparisons=not args.no_compare)
    except (FileNotFoundError, OSError, ValueError) as exc:
        parser.error(str(exc))

    print_report(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print("\nwrote %s" % args.json)

    failures = [item for item in report["maps"] if item["status"] == "fail"]
    failures.extend(item for item in report["comparisons"] if item["status"] == "fail")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
