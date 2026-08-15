#!/usr/bin/env python3
"""
Validate local relative links in all repo *.md files.

Checks that linked files exist to reduce documentation drift. Iteration 193
Task L (D-8): expanded scope from ``docs/**`` only to the whole repo root so
root-level entry docs (README, CONTRIBUTING, AGENTS, CHANGELOG, ...) are no
longer exempt--the Diátaxis migration had left 16+ dead links there because
the gate never scanned them.

Run from project root: python scripts/ci/check_doc_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"

# Directories never scanned: vendored / generated / worktree / archive trees
# whose links are either not ours to fix or intentionally frozen.
EXCLUDED_PARTS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    ".worktrees",
    "archived",
    "dist",
    "build",
    "__pycache__",
    ".kiro",
    "clientportal.gw",  # vendored IB gateway product docs (Task F: tracked separately)
}


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


def iter_markdown_files() -> list[Path]:
    """Yield every *.md file under the repo root, minus excluded trees."""
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*.md"):
        if EXCLUDED_PARTS.intersection(path.parts):
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    """Validate all local links in repo *.md files."""
    if not PROJECT_ROOT.is_dir():
        print("Project root not found:", PROJECT_ROOT)
        return 1

    errors = []
    for md_file in iter_markdown_files():
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

    print(f"Broken or missing doc links ({len(errors)}):\n")
    for rel_file, line_no, link_path, resolved in sorted(errors):
        print(f"  {rel_file}:{line_no}")
        print(f"    Link: {link_path}")
        print(f"    Resolved: {resolved}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
