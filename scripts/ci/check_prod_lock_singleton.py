#!/usr/bin/env python3
"""Enforce a single production dependency lockfile (iteration 193 P0-1/Task B).

The production lockfile SSOT is ``config/requirements-prod.lock``. A second
copy elsewhere (e.g. ``src/backend/requirements-prod.lock``) historically
drifted from the CI-audited one, so the image shipped dependencies that were
never vulnerability-scanned. This guard fails if any other
``requirements-prod.lock`` exists in the tree (excluding worktrees / venvs),
keeping the audit target equal to the shipped artifact (SLSA L2).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SSOT_LOCK = REPO_ROOT / "config" / "requirements-prod.lock"
EXCLUDED_PARTS = {".worktrees", ".git", ".venv", "node_modules", "__pycache__"}


def find_extra_lockfiles() -> list[Path]:
    """Return any requirements-prod.lock outside the SSOT location."""
    extras: list[Path] = []
    for path in REPO_ROOT.rglob("requirements-prod.lock"):
        if EXCLUDED_PARTS.intersection(path.parts):
            continue
        if path.resolve() != SSOT_LOCK.resolve():
            extras.append(path)
    return extras


def main() -> int:
    if not SSOT_LOCK.is_file():
        print(
            f"check_prod_lock_singleton: SSOT lock missing: {SSOT_LOCK}",
            file=sys.stderr,
        )
        return 1

    extras = find_extra_lockfiles()
    if extras:
        print(
            "check_prod_lock_singleton: extra requirements-prod.lock found "
            "(must keep only config/requirements-prod.lock as SSOT):",
            file=sys.stderr,
        )
        for path in extras:
            print(f"  - {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    print(
        f"check_prod_lock_singleton: passed (single SSOT at "
        f"{SSOT_LOCK.relative_to(REPO_ROOT)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
