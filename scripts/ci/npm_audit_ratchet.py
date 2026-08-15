#!/usr/bin/env python3
"""Baseline-gate production npm high/critical vulnerability counts.

Some npm versions return success from ``npm audit --audit-level`` even when
high-severity findings are present. This script parses audit JSON directly,
binds the approved baseline to the lockfile hash, and fails when either count
increases or the lockfile changes without an intentional baseline review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_update_guard import assert_update_allowed  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "src/frontend"
LOCKFILE = FRONTEND_ROOT / "package-lock.json"
BASELINE_PATH = Path(__file__).with_name("npm_audit_baseline.json")


def lockfile_hash() -> str:
    """Return the SHA-256 of the lockfile that defines the dependency graph."""
    return hashlib.sha256(LOCKFILE.read_bytes()).hexdigest()


def audit_counts() -> dict[str, int]:
    """Run npm audit and extract production high/critical counts from JSON."""
    process = subprocess.run(
        ["npm", "audit", "--omit=dev", "--json"],
        cwd=FRONTEND_ROOT,
        capture_output=True,
        text=True,
    )
    try:
        payload: dict[str, Any] = json.loads(process.stdout)
        vulnerabilities = dict(payload.get("metadata", {}).get("vulnerabilities", {}))
        return {
            "high": int(vulnerabilities.get("high", 0)),
            "critical": int(vulnerabilities.get("critical", 0)),
        }
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        details = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(
            f"npm audit did not return parseable JSON: {details}"
        ) from exc


def write_baseline(counts: dict[str, int]) -> None:
    """Record the reviewed audit result for the exact current lockfile."""
    payload = {
        "_comment": (
            "Iteration 183 npm audit ratchet. Update only after reviewing the npm audit JSON "
            "for the exact package-lock hash; high/critical counts may not increase."
        ),
        "lockfile_sha256": lockfile_hash(),
        "high": counts["high"],
        "critical": counts["critical"],
        "baseline_date": date.today().isoformat(),
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="write the current reviewed baseline"
    )
    args = parser.parse_args()

    try:
        counts = audit_counts()
    except RuntimeError as exc:
        print(f"npm_audit_ratchet: {exc}", file=sys.stderr)
        return 1

    if args.update:
        assert_update_allowed("npm_audit_ratchet")
        write_baseline(counts)
        print(
            f"npm_audit_ratchet: baseline updated (high={counts['high']} critical={counts['critical']})"
        )
        return 0

    if not BASELINE_PATH.is_file():
        print(f"npm_audit_ratchet: baseline missing: {BASELINE_PATH}", file=sys.stderr)
        return 1
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("lockfile_sha256") != lockfile_hash():
        print(
            "npm_audit_ratchet: package-lock.json changed; review audit results and update the baseline "
            + "intentionally.",
            file=sys.stderr,
        )
        return 1

    errors = [
        severity
        for severity in ("high", "critical")
        if counts[severity] > int(baseline.get(severity, 0))
    ]
    if errors:
        details = ", ".join(
            f"{severity} {baseline.get(severity, 0)} -> {counts[severity]}"
            for severity in errors
        )
        print(
            f"npm_audit_ratchet: vulnerability regression ({details})", file=sys.stderr
        )
        return 1
    print(
        f"npm_audit_ratchet: passed (high={counts['high']} critical={counts['critical']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
