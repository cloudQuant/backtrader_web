#!/usr/bin/env python3
"""Prevent source files that are already large from growing further.

The checked-in baseline captures the current size of production Python,
TypeScript, and Vue sources. Existing large files may only shrink; a newly
introduced production file may not exceed ``NEW_FILE_LINE_LIMIT`` without an
explicit baseline update and review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_update_guard import assert_update_allowed  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("large_file_baseline.json")
SOURCE_ROOTS = (REPO_ROOT / "src/backend/app", REPO_ROOT / "src/frontend/src")
SOURCE_SUFFIXES = {".py", ".ts", ".vue"}
EXCLUDED_PARTS = {"__tests__", "e2e", "locales"}
NEW_FILE_LINE_LIMIT = 1000


def source_line_counts() -> dict[str, int]:
    """Return line counts for production source files subject to the gate."""
    counts: dict[str, int] = {}
    for source_root in SOURCE_ROOTS:
        for path in source_root.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if EXCLUDED_PARTS.intersection(path.parts):
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            counts[relative] = sum(1 for _ in path.open(encoding="utf-8"))
    return counts


def write_baseline(counts: dict[str, int]) -> None:
    """Write the current large-file baseline in stable path order."""
    tracked = {
        path: count for path, count in counts.items() if count >= NEW_FILE_LINE_LIMIT
    }
    payload = {
        "_comment": (
            "Iteration 183 large-file ratchet. Existing files listed here may not grow; "
            "new production source files may not exceed new_file_line_limit. "
            "Update only after a reviewed intentional decomposition."
        ),
        "new_file_line_limit": NEW_FILE_LINE_LIMIT,
        "files": dict(sorted(tracked.items())),
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def validate(counts: dict[str, int], baseline: dict[str, object]) -> list[str]:
    """Return all baseline regressions without stopping at the first one."""
    errors: list[str] = []
    baseline_files = dict(baseline.get("files") or {})
    new_file_limit = int(baseline.get("new_file_line_limit", NEW_FILE_LINE_LIMIT))

    for path, allowed_count in sorted(baseline_files.items()):
        current_count = counts.get(path)
        if current_count is None:
            continue
        if current_count > int(allowed_count):
            errors.append(
                f"{path}: {current_count} lines exceeds baseline {allowed_count}"
            )

    for path, current_count in sorted(counts.items()):
        if path not in baseline_files and current_count > new_file_limit:
            errors.append(
                f"{path}: new production file has {current_count} lines "
                f"(limit {new_file_limit})"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="write the current baseline"
    )
    args = parser.parse_args()

    counts = source_line_counts()
    if args.update:
        assert_update_allowed("large_file_ratchet")
        write_baseline(counts)
        print(f"large_file_ratchet: baseline updated ({len(counts)} files scanned)")
        return 0

    if not BASELINE_PATH.is_file():
        print(f"large_file_ratchet: baseline missing: {BASELINE_PATH}", file=sys.stderr)
        return 1
    errors = validate(counts, json.loads(BASELINE_PATH.read_text(encoding="utf-8")))
    if errors:
        print("large_file_ratchet: regressions detected:", file=sys.stderr)
        print(*[f"- {error}" for error in errors], sep="\n", file=sys.stderr)
        return 1
    print("large_file_ratchet: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
