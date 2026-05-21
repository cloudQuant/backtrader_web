#!/usr/bin/env python3
"""Check that installed packages match the lockfile versions.

Usage:
    python scripts/check_lockfile_sync.py <lockfile_path>

This script compares the output of `pip freeze` against the specified lockfile.
It exits with code 0 if all versions match, or code 1 if there are mismatches.

Typical CI usage:
    pip install -e ".[dev,backtrader]"
    python scripts/check_lockfile_sync.py requirements-dev.lock
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def parse_requirements(content: str) -> dict[str, str]:
    """Parse pip freeze or lockfile output into {package_name: version} dict.

    Handles lines like:
        package-name==1.2.3
        Package_Name==1.2.3

    Skips comments, blank lines, and lines without == (editable installs, etc).
    """
    packages: dict[str, str] = {}
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        # Normalize package name: lowercase, replace underscores/dots with hyphens
        normalized = name.lower().replace("_", "-").replace(".", "-")
        packages[normalized] = version
    return packages


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <lockfile_path>", file=sys.stderr)
        return 2

    lockfile_path = Path(sys.argv[1])
    if not lockfile_path.exists():
        print(f"Error: Lockfile not found: {lockfile_path}", file=sys.stderr)
        print(
            "Run ./scripts/generate_lockfiles.sh to generate lockfiles.",
            file=sys.stderr,
        )
        return 2

    # Get current installed packages
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
        capture_output=True,
        text=True,
        check=True,
    )
    installed = parse_requirements(result.stdout)

    # Parse lockfile
    lockfile_content = lockfile_path.read_text()
    locked = parse_requirements(lockfile_content)

    if not locked:
        print(
            f"⚠ Lockfile {lockfile_path} contains no pinned packages.",
            file=sys.stderr,
        )
        print(
            "  Run ./scripts/generate_lockfiles.sh to populate the lockfile.",
            file=sys.stderr,
        )
        return 1

    # Compare: check that every package in the lockfile matches installed version
    mismatches: list[str] = []
    missing: list[str] = []

    for pkg, locked_version in sorted(locked.items()):
        if pkg not in installed:
            missing.append(f"  {pkg}=={locked_version} (not installed)")
        elif installed[pkg] != locked_version:
            mismatches.append(
                f"  {pkg}: locked={locked_version}, installed={installed[pkg]}"
            )

    if not mismatches and not missing:
        print(f"✓ All {len(locked)} locked packages match installed versions.")
        return 0

    print("✗ Lockfile sync check FAILED", file=sys.stderr)
    print(f"  Lockfile: {lockfile_path}", file=sys.stderr)
    print("", file=sys.stderr)

    if mismatches:
        print(f"  Version mismatches ({len(mismatches)}):", file=sys.stderr)
        for m in mismatches:
            print(m, file=sys.stderr)
        print("", file=sys.stderr)

    if missing:
        print(f"  Missing packages ({len(missing)}):", file=sys.stderr)
        for m in missing:
            print(m, file=sys.stderr)
        print("", file=sys.stderr)

    print(
        "  Fix: run ./scripts/generate_lockfiles.sh and commit the updated lockfiles.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
