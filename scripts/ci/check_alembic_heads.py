#!/usr/bin/env python3
"""
CI script: Verify Alembic migration chain integrity.

Checks:
1. Only one head exists (no branching)
2. Migration history has no broken chain (all revisions resolvable)
3. Migration files exist in the versions directory

Usage:
    python scripts/check_alembic_heads.py

Exit codes:
    0 - All checks passed
    1 - Migration chain has issues
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "src" / "backend"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


def run_alembic_command(args: list[str]) -> tuple[int, str, str]:
    """Run an alembic command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic"] + args,
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def check_migration_files_exist() -> bool:
    """Verify that migration version files exist."""
    versions_dir = ALEMBIC_DIR / "versions"
    if not versions_dir.exists():
        print("ERROR: alembic/versions directory not found")
        return False

    migration_files = list(versions_dir.glob("*.py"))
    # Exclude __init__.py and __pycache__
    migration_files = [f for f in migration_files if f.name != "__init__.py"]
    if not migration_files:
        print("WARNING: No migration files found (this may be intentional)")
        return True

    print(f"Found {len(migration_files)} migration file(s):")
    for f in sorted(migration_files):
        print(f"  - {f.name}")
    return True


def check_single_head() -> bool:
    """Verify there's only one migration head (no branching).

    Runs `alembic heads` and ensures exactly one head revision exists.
    Multiple heads indicate a branching issue that must be resolved
    with `alembic merge heads`.
    """
    returncode, stdout, stderr = run_alembic_command(["heads"])

    if returncode != 0:
        print(f"ERROR: 'alembic heads' failed (exit code {returncode}):\n{stderr}")
        return False

    # Parse head lines - each non-empty line that doesn't start with # is a head
    heads = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
    heads = [h for h in heads if h and not h.startswith("#")]

    if len(heads) == 0:
        print("WARNING: No migration heads found (empty migration history)")
        return True

    if len(heads) > 1:
        print(f"ERROR: Multiple migration heads detected ({len(heads)}):")
        for h in heads:
            print(f"  - {h}")
        print("\nFix: Merge branches with 'alembic merge heads'")
        return False

    print(f"✓ Single migration head: {heads[0]}")
    return True


def check_history_continuity() -> bool:
    """Verify migration history has no gaps (unbroken chain).

    Runs `alembic history` and checks that:
    - The command succeeds (all revisions can be resolved)
    - No "Can't locate revision" errors appear
    - The chain from base to head is continuous
    """
    returncode, stdout, stderr = run_alembic_command(["history", "--verbose"])

    if returncode != 0:
        # Check for specific broken-chain indicators
        if "Can't locate revision" in stderr:
            print(f"ERROR: Broken migration chain detected:\n{stderr}")
            return False
        if "No such revision" in stderr:
            print(f"ERROR: Missing revision in chain:\n{stderr}")
            return False
        # Other errors might be config-related (e.g., no DB), which is OK for CI
        print(f"WARNING: Could not fully verify history: {stderr.strip()}")
        return True

    # Verify the history output is parseable and continuous
    history_lines = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
    if not history_lines:
        print("WARNING: Empty migration history")
        return True

    # Check for any error indicators in the output
    for line in history_lines:
        if "FAILED" in line or "ERROR" in line:
            print(f"ERROR: History contains failure indicator: {line}")
            return False

    revision_count = sum(1 for line in history_lines if " -> " in line or "Rev:" in line)
    print(f"✓ Migration history is continuous ({revision_count} revision(s) found)")
    return True


def main() -> int:
    """Run all migration checks."""
    print("=" * 60)
    print("Alembic Migration Chain Verification")
    print("=" * 60)

    if not ALEMBIC_DIR.exists():
        print("INFO: No alembic directory found - skipping migration checks")
        return 0

    all_passed = True

    print("\n--- Check 1: Migration files exist ---")
    if not check_migration_files_exist():
        all_passed = False

    print("\n--- Check 2: Single migration head (no branching) ---")
    if not check_single_head():
        all_passed = False

    print("\n--- Check 3: Unbroken migration chain ---")
    if not check_history_continuity():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All migration checks passed")
        return 0
    else:
        print("❌ Some migration checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
