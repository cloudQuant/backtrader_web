#!/usr/bin/env python3
"""Repo-wide mypy error ratchet (iteration 177 §E).

Background
----------
``backend-lint`` runs a *blocking* ``mypy app`` step, but because CI never
fired on the ``dev`` branch (the F1 root cause fixed in 177 §A) the global
type-error count silently rotted to >1000. The per-package strict overrides in
``pyproject.toml`` only guard the enrolled packages; everything else is
unchecked. This script closes that gap *without* pretending the 1000+ existing
errors are fixed:

- It records the current whole-``app`` error count as a frozen baseline.
- CI fails only when the count *increases* (a regression / new debt).
- When the count drops, it nudges you to lower the baseline (the ratchet).

This is deliberately count-based (not a per-error allowlist) to stay simple and
fast. It is only meaningful when the mypy version matches the one used to
generate the baseline, so the baseline file pins that version and this script
fails on mismatch.

Usage
-----
    python scripts/ci/mypy_ratchet.py            # check against baseline
    python scripts/ci/mypy_ratchet.py --update   # rewrite baseline to current
    python scripts/ci/mypy_ratchet.py --advisory # never exit non-zero

Exit codes: 0 = ok / drop-allowed, 1 = regression (more errors than baseline).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_update_guard import assert_update_allowed  # noqa: E402

# Run mypy over the whole backend app package from the backend root.
_BACKEND_ROOT = Path(__file__).resolve().parents[2] / "src" / "backend"
_BASELINE_FILE = Path(__file__).resolve().parent / "mypy_app_baseline.json"
_TARGET = "app"

# mypy summary line, e.g. "Found 1055 errors in 103 files (checked 355 ...)".
_SUMMARY_RE = re.compile(r"Found (\d+) errors? in \d+ files?")


def _run_mypy() -> tuple[int, str]:
    """Return (error_count, raw_output). 0 errors when mypy prints Success."""
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", _TARGET],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    match = _SUMMARY_RE.search(out)
    if match:
        return int(match.group(1)), out
    if "Success: no issues found" in out:
        return 0, out
    # No recognizable summary — surface mypy's own output and treat as failure.
    print(out, file=sys.stderr)
    raise SystemExit("mypy_ratchet: could not parse mypy output (see above)")


def _mypy_version() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--version"],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() or "unknown"


def _load_baseline() -> dict:
    if not _BASELINE_FILE.is_file():
        raise SystemExit(
            f"mypy_ratchet: baseline file missing ({_BASELINE_FILE}). "
            "Run with --update to create it."
        )
    return json.loads(_BASELINE_FILE.read_text("utf-8"))


def _write_baseline(count: int, version: str) -> None:
    payload = {
        "_comment": (
            "Iteration 177 §E mypy repo-wide ratchet baseline. CI fails when "
            "`mypy app` reports MORE errors than baseline_errors. Lower this "
            "number whenever the count drops (the ratchet only turns one way). "
            "Regenerate with the pinned mypy version below via --update."
        ),
        "baseline_errors": count,
        "mypy_version": version,
        "baseline_date": date.today().isoformat(),
    }
    _BASELINE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="rewrite baseline to current count"
    )
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="report only; always exit 0 (use while stabilising)",
    )
    args = parser.parse_args()

    count, _ = _run_mypy()
    version = _mypy_version()

    if args.update:
        assert_update_allowed("mypy_ratchet")
        _write_baseline(count, version)
        print(f"mypy_ratchet: baseline updated -> {count} errors ({version})")
        return 0

    baseline = _load_baseline()
    expected = int(baseline["baseline_errors"])
    base_version = str(baseline.get("mypy_version", "unknown"))

    if base_version != version:
        print(
            f"::error::mypy_ratchet: mypy version mismatch "
            f"(baseline={base_version!r}, running={version!r}); "
            "install the pinned version or regenerate the baseline intentionally."
        )
        return 0 if args.advisory else 1

    delta = count - expected
    print(f"mypy_ratchet: errors={count} baseline={expected} delta={delta:+d}")

    if count > expected:
        print(
            f"::error::mypy_ratchet: type errors increased by {delta} "
            f"({expected} -> {count}). Fix the new errors or justify a baseline bump."
        )
        return 0 if args.advisory else 1

    if count < expected:
        print(
            f"mypy_ratchet: errors dropped by {-delta}. Ratchet down by running "
            "`python scripts/ci/mypy_ratchet.py --update` and commit the baseline."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
