#!/usr/bin/env python3
"""Render one result JSON or a cross-machine comparison as Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from bench import end_to_end, machine_markdown, render_payload, software_markdown, stage_for


def load_result(path: Path) -> Dict:
    try:
        result = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))
    if "machine" not in result or "results" not in result:
        raise SystemExit("%s is not a medic_bench result JSON" % path)
    return result


def native_thread(payload: Dict) -> Optional[int]:
    threads = [int(value) for value in payload.get("threads", [])]
    return max(threads) if threads else None


def scenario_thread(payload: Dict, scenario: str) -> Optional[int]:
    return 1 if scenario == "one thread" else native_thread(payload)


def cell_value(payload: Dict, dataset: str, scenario: str, tool: str, stage: str) -> Optional[float]:
    thread = scenario_thread(payload, scenario)
    if thread is None:
        return None
    cell = (
        payload.get("results", {})
        .get(dataset, {})
        .get("runs", {})
        .get(str(thread), {})
        .get(tool)
    )
    if not cell:
        return None
    if stage == "end to end":
        return end_to_end(cell)
    measurement = stage_for(cell, stage)
    return measurement.get("wall") if measurement else None


def cell_peak(payload: Dict, dataset: str, scenario: str, tool: str, stage: str) -> Optional[float]:
    thread = scenario_thread(payload, scenario)
    if thread is None:
        return None
    cell = (
        payload.get("results", {})
        .get(dataset, {})
        .get("runs", {})
        .get(str(thread), {})
        .get(tool)
    )
    measurement = stage_for(cell, stage) if cell else None
    return measurement.get("peak_gb") if measurement else None


def display_seconds(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.2f s" % value


def cross_machine_table(first: Dict, second: Dict) -> str:
    common = sorted(set(first.get("results", {})) & set(second.get("results", {})))
    first_label = first["machine"].get("label", "machine 1")
    second_label = second["machine"].get("label", "machine 2")
    lines = [
        "| dataset | setting | tool | stage | %s | %s | %s / %s |"
        % (first_label, second_label, second_label, first_label),
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for dataset in common:
        for scenario in ("one thread", "native"):
            first_thread = scenario_thread(first, scenario)
            second_thread = scenario_thread(second, scenario)
            setting = (
                "1 thread"
                if scenario == "one thread"
                else "native (%s vs %s threads)" % (first_thread, second_thread)
            )
            for tool in ("warpkit", "niimath"):
                for stage in ("estimate", "apply", "end to end"):
                    a = cell_value(first, dataset, scenario, tool, stage)
                    b = cell_value(second, dataset, scenario, tool, stage)
                    ratio = "n/a" if a in (None, 0) or b is None else "%.2fx" % (b / a)
                    lines.append(
                        "| %s | %s | %s | %s | %s | %s | %s |"
                        % (
                            dataset,
                            setting,
                            tool,
                            stage,
                            display_seconds(a),
                            display_seconds(b),
                            ratio,
                        )
                    )
    if not common:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | no common completed datasets |")
    return "\n".join(lines)


def cross_machine_memory_table(first: Dict, second: Dict) -> str:
    common = sorted(set(first.get("results", {})) & set(second.get("results", {})))
    first_label = first["machine"].get("label", "machine 1")
    second_label = second["machine"].get("label", "machine 2")
    lines = [
        "| dataset | setting | tool | stage | %s peak | %s peak | %s / %s |"
        % (first_label, second_label, second_label, first_label),
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for dataset in common:
        for scenario in ("one thread", "native"):
            first_thread = scenario_thread(first, scenario)
            second_thread = scenario_thread(second, scenario)
            setting = (
                "1 thread"
                if scenario == "one thread"
                else "native (%s vs %s threads)" % (first_thread, second_thread)
            )
            for tool in ("warpkit", "niimath"):
                for stage in ("estimate", "apply"):
                    a = cell_peak(first, dataset, scenario, tool, stage)
                    b = cell_peak(second, dataset, scenario, tool, stage)
                    ratio = "n/a" if a in (None, 0) or b is None else "%.2fx" % (b / a)
                    lines.append(
                        "| %s | %s | %s | %s | %s | %s | %s |"
                        % (
                            dataset,
                            setting,
                            tool,
                            stage,
                            "n/a" if a is None else "%.2f GB" % a,
                            "n/a" if b is None else "%.2f GB" % b,
                            ratio,
                        )
                    )
    if not common:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | no common completed datasets |")
    return "\n".join(lines)


def dataset_identity(payload: Dict, key: str) -> Tuple:
    dataset = payload.get("results", {}).get(key, {}).get("dataset", {})
    fields = (
        "accession",
        "snapshot",
        "resolved_commit",
        "echo_count",
        "frame_count",
        "image_dimensions",
        "voxel_size_mm",
        "echo_times_ms",
        "total_readout_time_seconds",
        "phase_encoding_direction",
    )
    return tuple(json.dumps(dataset.get(field), sort_keys=True) for field in fields)


def comparison_report(payloads: List[Dict]) -> str:
    if len(payloads) == 1:
        return render_payload(payloads[0])
    if len(payloads) != 2:
        raise SystemExit("comparison rendering currently accepts one or two result JSON files")
    first, second = payloads
    first_label = first["machine"].get("label", "machine 1")
    second_label = second["machine"].get("label", "machine 2")
    lines = [
        "# MEDIC cross-platform benchmark",
        "",
        "This report separates computational efficiency (wall time and peak RSS) from "
        "corrected-image agreement (correlation). Correlation alone does not establish "
        "numerical equivalence.",
        "",
        "## %s machine" % first_label,
        "",
        machine_markdown(first.get("machine", {})),
        "",
        "## %s machine" % second_label,
        "",
        machine_markdown(second.get("machine", {})),
        "",
        "Hostnames are retained only in the raw JSON files.",
        "",
        "## Software",
        "",
        "### %s" % first_label,
        "",
        software_markdown(first),
        "",
        "### %s" % second_label,
        "",
        software_markdown(second),
        "",
        "## Per-machine measurements",
        "",
        "### %s" % first_label,
        "",
        render_payload(first).split("## Measurements\n\n", 1)[-1].strip(),
        "",
        "### %s" % second_label,
        "",
        render_payload(second).split("## Measurements\n\n", 1)[-1].strip(),
        "",
        "## Direct cross-system wall-time comparison",
        "",
        "A ratio above 1 means the second machine took longer. Native rows compare each "
        "platform's recorded default multithreaded count, which can differ.",
        "",
        cross_machine_table(first, second),
        "",
        "## Direct cross-system peak-RSS comparison",
        "",
        "Peak RSS uses platform-correct units: bytes from macOS `getrusage`, KiB from Linux.",
        "",
        cross_machine_memory_table(first, second),
        "",
        "## Dataset identity checks",
        "",
    ]
    common = sorted(set(first.get("results", {})) & set(second.get("results", {})))
    if not common:
        lines.append("- No dataset was present in both result files.")
    else:
        for key in common:
            same = dataset_identity(first, key) == dataset_identity(second, key)
            lines.append(
                "- `%s`: %s across the two raw results."
                % (key, "metadata match" if same else "WARNING — metadata differ")
            )
    lines.extend(["", "## Failures, warnings, and run notes", ""])
    for payload in payloads:
        label = payload["machine"].get("label", "unlabeled")
        notes = payload.get("notes", [])
        failures = payload.get("failures", [])
        if not notes and not failures:
            lines.append("- %s: none recorded." % label)
        else:
            lines.extend("- %s: %s" % (label, value) for value in notes + failures)
    lines.extend(
        [
            "",
            "Thermal state and memory pressure are reported only when explicitly recorded in "
            "the raw result notes; neither is inferred from timing alone.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payloads = [load_result(path) for path in args.json]
    markdown = comparison_report(payloads)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown)
        print("wrote %s" % args.output)
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
