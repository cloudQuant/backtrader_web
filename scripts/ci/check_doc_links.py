#!/usr/bin/env python3
"""
Validate local relative links in docs/*.md files.

Checks that linked files exist to reduce documentation drift.
Run from project root: python scripts/check_doc_links.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"


def extract_links(content: str, base_path: Path) -> list[tuple[int, str, str]]:
    """Extract [text](path) and [text](path#anchor) markdown links.

    Returns list of (line_no, link_text, path_without_anchor).
    """
    # Match [text](path) or [text](path#anchor)
    pattern = re.compile(r"\[([^\]]*)\]\(([^)#]+)(?:#([^)]*))?\)")
    results = []
    for i, line in enumerate(content.splitlines(), 1):
        for m in pattern.finditer(line):
            path_part = m.group(2).strip()
            if path_part.startswith(("http://", "https://", "mailto:")):
                continue
            if path_part.startswith("#"):
                continue
            results.append((i, m.group(1), path_part))
    return results


def resolve_path(link_path: str, base_file: Path) -> Path:
    """Resolve relative link path to absolute path."""
    base_dir = base_file.parent
    resolved = (base_dir / link_path).resolve()
    return resolved


def main() -> int:
    """Validate all local links in docs/*.md."""
    if not DOCS_DIR.is_dir():
        print("Docs directory not found:", DOCS_DIR)
        return 1

    errors = []
    for md_file in DOCS_DIR.rglob("*.md"):
        if "archived" in md_file.parts:
            continue
        content = md_file.read_text(encoding="utf-8")
        links = extract_links(content, md_file)
        for line_no, text, path in links:
            if path.startswith(("http", "mailto")):
                continue
            resolved = resolve_path(path, md_file)
            # 仅校验项目内链接
            try:
                if not resolved.resolve().is_relative_to(PROJECT_ROOT.resolve()):
                    continue
            except ValueError:
                continue
            if not resolved.exists():
                rel = md_file.relative_to(PROJECT_ROOT)
                errors.append((str(rel), line_no, path, str(resolved)))

    if not errors:
        print("OK: All local doc links resolve correctly.")
        return 0

    print("Broken or missing doc links:\n")
    for rel_file, line_no, link_path, resolved in sorted(errors):
        print(f"  {rel_file}:{line_no}")
        print(f"    Link: {link_path}")
        print(f"    Resolved: {resolved}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
