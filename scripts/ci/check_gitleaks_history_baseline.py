#!/usr/bin/env python3
"""Validate the audited full-history gitleaks fingerprint baseline."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
IGNORE_PATH = REPO_ROOT / ".gitleaksignore"
BASELINE_PATH = Path(__file__).with_name("gitleaks_history_baseline.json")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{40}:.+:[a-z0-9][a-z0-9-]*:[1-9][0-9]*$")


def load_fingerprints() -> list[str]:
    """Return non-comment fingerprints from the repository ignore file."""
    return [
        line.strip()
        for line in IGNORE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> int:
    """Fail when the fingerprint file drifts from its audited metadata."""
    metadata = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    fingerprints = load_fingerprints()
    failures: list[str] = []

    invalid = [item for item in fingerprints if not FINGERPRINT_RE.fullmatch(item)]
    if invalid:
        failures.append(f"{len(invalid)} fingerprint(s) have an invalid format")

    duplicate_count = len(fingerprints) - len(set(fingerprints))
    if duplicate_count:
        failures.append(f"{duplicate_count} duplicate fingerprint(s)")

    expected = metadata.get("accepted_fingerprints")
    if len(fingerprints) != expected:
        failures.append(
            f"accepted fingerprint count is {len(fingerprints)}, baseline requires {expected}"
        )

    unresolved = metadata.get("unresolved_findings")
    blocking_ready = metadata.get("blocking_ready")
    if not isinstance(unresolved, int) or unresolved < 0:
        failures.append("unresolved_findings must be a non-negative integer")
    if blocking_ready is not (unresolved == 0):
        failures.append("blocking_ready must be true exactly when unresolved_findings is zero")

    if failures:
        print("Gitleaks history baseline check failed:")
        for failure in failures:
            print(f"- {failure}")
        print(
            "Update fingerprints and gitleaks_history_baseline.json together only after "
            "documented owner review."
        )
        return 1

    print(
        "Gitleaks history baseline check passed "
        f"(accepted={len(fingerprints)}, unresolved={unresolved}, "
        f"blocking_ready={str(blocking_ready).lower()})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
