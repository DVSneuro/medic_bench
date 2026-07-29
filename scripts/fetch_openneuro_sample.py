#!/usr/bin/env python3
"""Fetch and verify only the pinned OpenNeuro run used by medic_bench.

The dataset's Git/annex metadata is cloned, but `datalad get` is restricted to
the eight BOLD images and their eight exact JSON sidecars.  Re-running the
script is safe: git-annex resumes interrupted transfers and already-present
content is verified rather than downloaded again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "manifests" / "openneuro-ds005123-1.1.3.json"
PROVENANCE_NAME = "openneuro-sample-provenance.json"


class FetchError(RuntimeError):
    pass


def run(
    argv: List[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    quiet: bool = False,
) -> subprocess.CompletedProcess:
    if not quiet:
        print("+ " + " ".join(quote(x) for x in argv), flush=True)
    proc = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if check and proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise FetchError(
            "command failed with exit %d:\n  %s%s"
            % (proc.returncode, " ".join(quote(x) for x in argv), "\n" + detail if detail else "")
        )
    return proc


def quote(value: str) -> str:
    if value and all(c.isalnum() or c in "-_./=,:+@" for c in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def default_cache_root() -> Path:
    configured = os.environ.get("MEDIC_BENCH_CACHE")
    return Path(configured).expanduser() if configured else Path.home() / ".cache" / "medic_bench" / "openneuro"


def load_manifest(path: Path) -> Dict:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError("cannot read manifest %s: %s" % (path, exc))
    required = (
        "repository",
        "accession",
        "snapshot",
        "resolved_commit",
        "cache_relative",
        "func_dir",
        "run_stem",
        "echoes",
        "parts",
        "suffix",
    )
    missing = [key for key in required if key not in manifest]
    if missing:
        raise FetchError("%s is missing: %s" % (path, ", ".join(missing)))
    commit = str(manifest["resolved_commit"])
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit.lower()):
        raise FetchError("%s: resolved_commit must be a full 40-character Git hash" % path)
    return manifest


def required_paths(manifest: Dict) -> List[str]:
    paths = []
    func_dir = manifest["func_dir"].rstrip("/")
    stem = manifest["run_stem"]
    suffix = manifest["suffix"]
    for echo in manifest["echoes"]:
        for part in manifest["parts"]:
            base = "%s/%s_echo-%s_part-%s_%s" % (func_dir, stem, echo, part, suffix)
            paths.extend((base + ".nii.gz", base + ".json"))
    return paths


def require_tools() -> Dict[str, str]:
    paths = {name: shutil.which(name) for name in ("git", "datalad", "git-annex")}
    if not paths["datalad"] or not paths["git-annex"]:
        missing = [name for name in ("datalad", "git-annex") if not paths[name]]
        raise FetchError(
            "missing required command(s): %s\n"
            "Install DataLad and git-annex, then retry. Examples:\n"
            "  macOS:  brew install datalad git-annex\n"
            "  conda:  conda install -c conda-forge datalad git-annex\n"
            "No OpenNeuro account or API key is needed for this public dataset."
            % ", ".join(missing)
        )
    versions = {}
    for name, argv in (
        ("git", ["git", "--version"]),
        ("datalad", ["datalad", "--version"]),
        ("git_annex", ["git-annex", "version"]),
    ):
        proc = run(argv, check=False, quiet=True)
        versions[name] = (proc.stdout or proc.stderr).strip().splitlines()[0]
    return versions


def ensure_checkout(target: Path, manifest: Dict) -> str:
    if not (target / ".git").exists():
        if target.exists() and any(target.iterdir()):
            raise FetchError("%s exists and is not an empty Git checkout" % target)
        target.parent.mkdir(parents=True, exist_ok=True)
        run(["datalad", "clone", manifest["repository"], str(target)])

    origin = run(["git", "remote", "get-url", "origin"], cwd=target, quiet=True).stdout.strip()
    expected_name = manifest["repository"].rstrip("/").removesuffix(".git")
    if expected_name not in origin.rstrip("/").removesuffix(".git"):
        raise FetchError("%s has unexpected origin %s" % (target, origin))

    commit = manifest["resolved_commit"]
    have = run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=target, check=False, quiet=True)
    if have.returncode:
        run(["git", "fetch", "origin", "tag", str(manifest["snapshot"])], cwd=target)

    resolved = run(
        ["git", "rev-parse", "refs/tags/%s^{commit}" % manifest["snapshot"]],
        cwd=target,
        quiet=True,
    ).stdout.strip()
    if resolved != commit:
        raise FetchError(
            "snapshot %s resolved to %s, expected pinned commit %s"
            % (manifest["snapshot"], resolved, commit)
        )

    head = run(["git", "rev-parse", "HEAD"], cwd=target, quiet=True).stdout.strip()
    if head != commit:
        run(["git", "checkout", "--detach", commit], cwd=target)
    return run(["git", "rev-parse", "HEAD"], cwd=target, quiet=True).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_files(target: Path, relpaths: List[str], previous: Optional[Dict]) -> List[Dict]:
    previous_files = {
        entry["path"]: entry
        for entry in (previous or {}).get("files", [])
        if isinstance(entry, dict) and "path" in entry
    }
    records = []
    for relpath in relpaths:
        path = target / relpath
        if not path.is_file():
            raise FetchError("required file is unavailable after datalad get: %s" % path)
        size = path.stat().st_size
        checksum = sha256_file(path)
        annex = run(
            ["git", "annex", "lookupkey", "--", relpath],
            cwd=target,
            check=False,
            quiet=True,
        )
        annex_key = annex.stdout.strip() if annex.returncode == 0 else None
        record = {
            "path": relpath,
            "size_bytes": size,
            "sha256": checksum,
            "git_annex_key": annex_key,
        }
        old = previous_files.get(relpath)
        if old and (old.get("size_bytes") != size or old.get("sha256") != checksum):
            raise FetchError(
                "%s no longer matches the checksum retained by the previous verified fetch" % path
            )
        records.append(record)
        print("verified %-12s  %s" % (human_size(size), relpath))
    return records


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            return "%.1f %s" % (value, unit)
        value /= 1024.0
    return "%d B" % size


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=default_cache_root(),
        help="cache parent (default: $MEDIC_BENCH_CACHE or ~/.cache/medic_bench/openneuro)",
    )
    parser.add_argument("--verify-only", action="store_true", help="do not retrieve missing content")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        versions = require_tools()
        target = args.cache_root.expanduser().resolve() / manifest["cache_relative"]
        commit = ensure_checkout(target, manifest)
        relpaths = required_paths(manifest)
        provenance_path = target / PROVENANCE_NAME
        previous = None
        if provenance_path.is_file():
            try:
                previous = json.loads(provenance_path.read_text())
            except (OSError, json.JSONDecodeError):
                previous = None

        if not args.verify_only:
            run(["datalad", "get", "--"] + relpaths, cwd=target)
        records = verify_files(target, relpaths, previous)

        payload = {
            "schema_version": 1,
            "immutable_dataset_id": "%s@%s:%s"
            % (manifest["accession"], manifest["snapshot"], commit),
            "accession": manifest["accession"],
            "snapshot": manifest["snapshot"],
            "resolved_commit": commit,
            "repository": manifest["repository"],
            "verified_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "tools": versions,
            "files": records,
        }
        temp = provenance_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n")
        os.replace(temp, provenance_path)
        print("\nDataset root: %s" % target)
        print("Immutable ID: %s" % payload["immutable_dataset_id"])
        print("Provenance:   %s" % provenance_path)
        return 0
    except FetchError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
