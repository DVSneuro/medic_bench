#!/usr/bin/env python3
"""Build the pinned niimath revision with OpenMP in a user-owned directory."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_FILE = REPO_ROOT / "config" / "benchmark-versions.json"


class BuildError(RuntimeError):
    pass


def run(argv: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    print("+ " + " ".join(quote(x) for x in argv), flush=True)
    proc = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if check and proc.returncode:
        raise BuildError("command failed with exit %d: %s" % (proc.returncode, " ".join(argv)))
    return proc


def quote(value: str) -> str:
    if value and all(c.isalnum() or c in "-_./=,:+@" for c in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def version_output(argv: List[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return (proc.stdout or proc.stderr).strip()


def pinned_version() -> Dict:
    return json.loads(VERSIONS_FILE.read_text())["niimath"]


def default_prefix(commit: str) -> Path:
    return REPO_ROOT / ".benchmark-tools" / ("niimath-" + commit[:12])


def find_libomp() -> Tuple[Path, str]:
    configured = os.environ.get("LIBOMP_ROOT")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path("/opt/homebrew/opt/libomp"))
    fsldir = os.environ.get("FSLDIR")
    if fsldir:
        candidates.append(Path(fsldir).expanduser())
    candidates.append(Path.home() / "fsl")
    for root in candidates:
        if (root / "include" / "omp.h").is_file() and (root / "lib" / "libomp.dylib").is_file():
            version = "unavailable"
            conda_meta = sorted((root / "conda-meta").glob("llvm-openmp-*.json"))
            if conda_meta:
                try:
                    version = str(json.loads(conda_meta[-1].read_text()).get("version", "unavailable"))
                except (OSError, json.JSONDecodeError):
                    pass
            receipt = root / "INSTALL_RECEIPT.json"
            if receipt.is_file():
                try:
                    version = str(json.loads(receipt.read_text()).get("version", version))
                except (OSError, json.JSONDecodeError):
                    pass
            return root, version
    raise BuildError(
        "OpenMP is required but libomp was not found. Install Homebrew libomp, set "
        "LIBOMP_ROOT to a prefix containing include/omp.h and lib/libomp.dylib, or use "
        "an existing FSL installation that provides those files."
    )


def checkout_source(source: Path, repository: str, commit: str) -> None:
    if not (source / ".git").exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", repository, str(source)])
    dirty = run(["git", "status", "--porcelain"], cwd=source).stdout.strip()
    if dirty:
        raise BuildError("%s has local changes; refusing to replace or clean them" % source)
    have = run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=source, check=False)
    if have.returncode:
        run(["git", "fetch", "origin", commit], cwd=source)
    run(["git", "checkout", "--detach", commit], cwd=source)
    resolved = run(["git", "rev-parse", "HEAD"], cwd=source).stdout.strip()
    if resolved != commit:
        raise BuildError("checked out %s, expected %s" % (resolved, commit))


def linked_libraries(binary: Path) -> str:
    command = ["otool", "-L", str(binary)] if platform.system() == "Darwin" else ["ldd", str(binary)]
    exe = shutil.which(command[0])
    if not exe:
        return "unavailable"
    proc = subprocess.run(command, capture_output=True, text=True)
    return (proc.stdout or proc.stderr).strip()


def main(argv: Optional[List[str]] = None) -> int:
    pinned = pinned_version()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default=pinned["commit"])
    parser.add_argument("--repository", default=pinned["repository"])
    parser.add_argument("--prefix", type=Path, default=None)
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args(argv)

    prefix = (args.prefix or default_prefix(args.commit)).expanduser().resolve()
    source = prefix / "src"
    binary_dir = prefix / "bin"
    binary = binary_dir / "niimath"
    build_dir = source / "src"

    try:
        checkout_source(source, args.repository, args.commit)
        compiler = shutil.which(args.cc) or args.cc
        compiler_version = version_output([compiler, "--version"])

        openmp: Dict[str, object]
        # niimath's Makefile intentionally has no clean target. -B forces every
        # object to be rebuilt, so a previous compiler/OpenMP flag set cannot leak
        # into the pinned binary.
        build = [
            "make",
            "-B",
            "-C",
            str(build_dir),
            "-j%d" % max(1, args.jobs),
            "CNAME=" + compiler,
        ]
        if platform.system() == "Darwin":
            omp_root, omp_version = find_libomp()
            omp_flags = "-Xpreprocessor -fopenmp -I%s" % (omp_root / "include")
            omp_link = "-L%s -Wl,-rpath,%s -lomp" % (omp_root / "lib", omp_root / "lib")
            build.extend(("OMPFLAGS=" + omp_flags, "OMPLINK=" + omp_link))
            openmp = {
                "runtime": "LLVM libomp",
                "version": omp_version,
                "prefix": str(omp_root),
                "compile_flags": omp_flags,
                "link_flags": omp_link,
            }
        else:
            openmp = {
                "runtime": "compiler default (normally libgomp for GCC or libomp for Clang)",
                "version": "discover from linked_libraries",
                "compile_flags": "-fopenmp",
                "link_flags": "-fopenmp",
            }
        run(build)

        built = build_dir / "niimath"
        if not built.is_file():
            raise BuildError("build completed but %s was not produced" % built)
        binary_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, binary)
        binary.chmod(binary.stat().st_mode | 0o111)
        libraries = linked_libraries(binary)
        openmp["linked_libraries"] = libraries
        niimath_version = version_output([str(binary), "--version"])
        provenance = {
            "schema_version": 1,
            "built_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "source_repository": args.repository,
            "source_commit": args.commit,
            "source_dir": str(source),
            "binary": str(binary),
            "niimath_version": niimath_version,
            "compiler": {"path": compiler, "version": compiler_version},
            "openmp": openmp,
            "build_command": build,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "architecture": platform.machine(),
            },
        }
        (prefix / "build-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        print("\nBuilt:      %s" % binary)
        print("Version:    %s" % niimath_version)
        print("Commit:     %s" % args.commit)
        print("Provenance: %s" % (prefix / "build-provenance.json"))
        return 0
    except (BuildError, OSError, json.JSONDecodeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
