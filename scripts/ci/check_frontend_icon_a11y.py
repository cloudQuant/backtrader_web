#!/usr/bin/env python3
"""Fail when a Vue Element Plus icon lacks an explicit accessibility role."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ICON_TAG = re.compile(r"<el-icon(?P<attributes>\s[^>]*?)?>")


def has_accessibility_attribute(attributes: str) -> bool:
    """Return whether an icon explicitly has a label or is decorative."""
    return bool(re.search(r"\baria-(?:hidden|label)\s*=", attributes))


def main() -> int:
    """Check every frontend Vue source file and report unlabelled icons."""
    project_root = Path(__file__).resolve().parents[2]
    frontend_source = project_root / "src" / "frontend" / "src"
    failures: list[str] = []

    for source_file in sorted(frontend_source.rglob("*.vue")):
        source = source_file.read_text(encoding="utf-8")
        for match in ICON_TAG.finditer(source):
            if not has_accessibility_attribute(match.group("attributes") or ""):
                line_number = source.count("\n", 0, match.start()) + 1
                failures.append(f"{source_file.relative_to(project_root)}:{line_number}: {match.group(0)}")

    if failures:
        print("Element Plus icons must use aria-hidden=\"true\" or aria-label:")
        print("\n".join(failures))
        return 1

    print("frontend_icon_a11y: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
