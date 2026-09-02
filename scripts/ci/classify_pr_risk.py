#!/usr/bin/env python3
"""Classify local changed-file JSON with the Iteration 195 risk map.

The module deliberately has no GitHub client, environment-token handling, or
PR-label input.  The trusted workflow obtains metadata separately, then passes
only a local changed-files payload to this deterministic classifier.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from governance_contract import classify_paths, load_risk_map


def _flatten_payload(value: Any) -> list[Any]:
    """Flatten GitHub API ``--slurp`` pages into individual file entries."""
    if not isinstance(value, list):
        raise ValueError("changed-files payload must be a JSON list")
    entries: list[Any] = []
    for item in value:
        if isinstance(item, list):
            entries.extend(_flatten_payload(item))
        else:
            entries.append(item)
    return entries


def changed_file_paths(payload: Any) -> list[str]:
    """Return repository-relative paths from GitHub files API JSON.

    A local fixture may use a plain list of paths.  The live workflow uses the
    GitHub REST representation with a ``filename`` field.  No arbitrary PR
    fields are accepted here because path classification must remain isolated.
    """
    paths: list[str] = []
    seen: set[str] = set()

    def add_path(path: str) -> None:
        if path not in seen:
            seen.add(path)
            paths.append(path)

    for entry in _flatten_payload(payload):
        if isinstance(entry, str) and entry.strip():
            add_path(entry.strip())
            continue
        if isinstance(entry, Mapping):
            filename = entry.get("filename")
            if isinstance(filename, str) and filename.strip():
                add_path(filename.strip())
                status = entry.get("status")
                if isinstance(status, str) and status.casefold() == "renamed":
                    previous_filename = entry.get("previous_filename")
                    if not isinstance(previous_filename, str) or not previous_filename.strip():
                        raise ValueError(
                            "renamed changed-files entries must include a non-empty previous_filename"
                        )
                    add_path(previous_filename.strip())
                continue
        raise ValueError("each changed-files entry must be a path string or filename object")
    return paths


def load_changed_file_paths(path: Path | str) -> list[str]:
    """Load a local JSON changed-files payload."""
    with Path(path).open(encoding="utf-8") as handle:
        return changed_file_paths(json.load(handle))


def classify_changed_files(
    changed_files: Sequence[str], risk_map: Mapping[str, Any]
) -> dict[str, Any]:
    """Return highest path-derived risk without any label downgrade channel."""
    classified = classify_paths(changed_files, risk_map)
    return {
        "risk": classified["risk"],
        "matches": classified["matches"],
        "labels_can_lower_risk": False,
        "downgrade_policy": (
            "PR labels and contributor declarations may request stricter review but cannot "
            "lower path-derived risk."
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", required=True, type=Path)
    parser.add_argument("--risk-map", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Print a stable JSON classification for a local payload."""
    args = _parse_args()
    try:
        result = classify_changed_files(
            load_changed_file_paths(args.changed_files), load_risk_map(args.risk_map)
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "issues": [str(error)]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
