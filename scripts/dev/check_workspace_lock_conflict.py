#!/usr/bin/env python3
"""Iteration 175 §9.4/§9.5 — workspace lock vs SSOT lock conflict detector.

Compares versions pinned in `uv.lock` (root, produced by `uv sync --workspace`)
against `config/requirements-dev.lock` (the legacy SSOT lock for backend dev).
A package present in both files with mismatched versions is reported as a
conflict; mismatches cause exit code 1.

Usage:
    python scripts/dev/check_workspace_lock_conflict.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_LOCK = REPO_ROOT / "uv.lock"
SSOT_LOCK = REPO_ROOT / "config" / "requirements-dev.lock"


def _parse_pip_lock(path: Path) -> dict[str, str]:
    """Parse a pip-style lockfile into {package_name_lower: version}."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip inline comments / markers.
        for sep in (";", " "):
            if sep in line:
                line = line.split(sep, 1)[0].strip()
                break
        m = re.match(r"^([A-Za-z0-9._-]+)==([A-Za-z0-9._+!-]+)$", line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def _parse_uv_lock(path: Path) -> dict[str, str]:
    """Naive TOML parser for uv.lock; only extracts [[package]] name+version pairs."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    name = None
    version = None
    in_pkg = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "[[package]]":
            if name and version:
                out[name.lower()] = version
            name = version = None
            in_pkg = True
            continue
        if line.startswith("["):
            if name and version:
                out[name.lower()] = version
            name = version = None
            in_pkg = False
            continue
        if not in_pkg:
            continue
        m = re.match(r'^name\s*=\s*"([^"]+)"\s*$', line)
        if m:
            name = m.group(1)
            continue
        m = re.match(r'^version\s*=\s*"([^"]+)"\s*$', line)
        if m:
            version = m.group(1)
            continue
    if name and version:
        out[name.lower()] = version
    return out


def main() -> int:
    if not WORKSPACE_LOCK.exists():
        print(
            f"NOTE: {WORKSPACE_LOCK.relative_to(REPO_ROOT)} not present yet — "
            f"run `uv sync --workspace` first. Skipping conflict check.",
            file=sys.stderr,
        )
        return 0
    if not SSOT_LOCK.exists():
        print(
            f"ERROR: {SSOT_LOCK.relative_to(REPO_ROOT)} missing",
            file=sys.stderr,
        )
        return 1

    workspace = _parse_uv_lock(WORKSPACE_LOCK)
    ssot = _parse_pip_lock(SSOT_LOCK)

    common = workspace.keys() & ssot.keys()
    conflicts: list[str] = []
    for pkg in sorted(common):
        if workspace[pkg] != ssot[pkg]:
            conflicts.append(f"{pkg} workspace={workspace[pkg]} lock={ssot[pkg]}")

    if not conflicts:
        print(f"OK: workspace lock and SSOT lock agree on {len(common)} shared packages")
        return 0

    print("FAIL: workspace ↔ SSOT lock version conflicts:", file=sys.stderr)
    for line in conflicts:
        print(f"  {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
