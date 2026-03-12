#!/usr/bin/env python3
"""
Validate pyproject.toml as single source of truth for dependencies.

Ensures key runtime dependencies exist in pyproject.toml.
If requirements.txt exists, also checks it stays in sync (legacy compatibility).
Run from project root: python scripts/check_deps_sync.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "src" / "backend" / "pyproject.toml"
REQUIREMENTS = PROJECT_ROOT / "src" / "backend" / "requirements.txt"

# Core runtime deps that must be in pyproject.toml [project.dependencies]
REQUIRED_DEPS = {
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "slowapi",
    "sqlalchemy",
    "aiosqlite",
    "python-jose",
    "passlib",
    "loguru",
    "python-multipart",
    "PyYAML",
    "fincore",
}


def parse_pyproject_deps() -> set[str]:
    """Extract package names from [project] dependencies in pyproject.toml."""
    if not PYPROJECT.exists():
        return set()

    text = PYPROJECT.read_text()
    deps = set()
    in_deps = False

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("dependencies ="):
            in_deps = True
            line_deps = re.findall(r'["\']([a-zA-Z0-9_-]+)', line)
            for p in line_deps:
                deps.add(p)
            continue
        if in_deps:
            if s.startswith("[") or s == "]":
                break
            for m in re.finditer(r'["\']([a-zA-Z0-9_-]+)', line):
                pkg = m.group(1)
                if "=" in line or ">" in line or "[" in line:
                    deps.add(pkg)
    return deps


def parse_requirements_names() -> set[str]:
    """Extract package names from requirements.txt."""
    if not REQUIREMENTS.exists():
        return set()

    names = set()
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([a-zA-Z0-9_-]+)", line)
        if m:
            names.add(m.group(1))
    return names


def main() -> int:
    """Validate pyproject.toml has required deps. Optionally check requirements.txt sync."""
    if not PYPROJECT.exists():
        print("ERROR: pyproject.toml not found")
        return 1

    pyproject_deps = parse_pyproject_deps()
    missing = REQUIRED_DEPS - pyproject_deps
    if missing:
        print("ERROR: These required deps are missing from pyproject.toml:")
        for p in sorted(missing):
            print(f"  - {p}")
        return 1

    if REQUIREMENTS.exists():
        req_names = parse_requirements_names()
        missing_in_req = pyproject_deps - req_names
        if missing_in_req:
            print("WARN: requirements.txt is outdated (pyproject is source of truth):")
            for p in sorted(missing_in_req):
                print(f"  - {p}")
            print("\nTip: Use pip install -e \".[postgres,redis,backtrader,data]\" for install.")
        else:
            print("OK: pyproject.toml and requirements.txt are consistent")
    else:
        print("OK: pyproject.toml is the single source of truth for dependencies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
