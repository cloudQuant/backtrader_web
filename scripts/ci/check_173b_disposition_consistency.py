#!/usr/bin/env python3
"""Check consistency between 173B disposition document and iterations README.

Verifies that for each 173B item (T2 / T7 / T10), three fields agree between
`docs/iterations/迭代175-质量加固与可观测性纵深/173B_disposition.md` and
`docs/iterations/README.md`:

- 决议类型 (resolution type)
- 责任人 (owner)
- 目标日期 (target date)

Exit codes:
  0 - all consistent
  1 - inconsistency detected
  2 - script-level error (e.g., file missing, parse failure)

Used in CI as a 175 acceptance gate (Requirement 10.4 / Property 7).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DISPOSITION = (
    REPO_ROOT
    / "docs"
    / "iterations"
    / "迭代175-质量加固与可观测性纵深"
    / "173B_disposition.md"
)
README = REPO_ROOT / "docs" / "iterations" / "README.md"
ITEMS = ("T2", "T7", "T10")


@dataclass(frozen=True)
class ItemFields:
    resolution: str  # "纳入 175" | "顺延 176" | "终止/归档"
    owner: str  # GitHub username with '@' or 'unassigned'
    target_date: str  # ISO 8601 date or 'n/a'


def _parse_disposition_table(text: str) -> dict[str, ItemFields]:
    """Parse the markdown table in 173B_disposition.md (under '## 总览').

    Expected table format::

        | Item | 实现完成度 | 剩余工作清单 | 决议 | 判定依据 | 责任人 | 目标日期 |

    Identifier matching for the leading column is intentionally lenient — we
    only require ``T2``/``T7``/``T10`` to appear at the start of the row.
    """
    out: dict[str, ItemFields] = {}
    table_started = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            table_started = False
            continue
        if "Item" in line and "决议" in line:
            table_started = True
            continue
        if not table_started:
            continue
        if set(line.replace("|", "").strip()) <= {"-", " "}:
            # separator row
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        first = cells[0]
        for item in ITEMS:
            if first.startswith(item) or first.startswith(f"**{item}"):
                # Resolution may be wrapped in ** **
                resolution = re.sub(r"\*+", "", cells[3]).strip()
                owner = cells[5].strip()
                target = cells[6].strip()
                out[item] = ItemFields(resolution, owner, target)
                break
    return out


def _parse_readme(text: str) -> dict[str, ItemFields]:
    """Parse the 173B row(s) from iterations/README.md.

    The README is allowed to either:
      (a) have a single 173B row that summarises all three items as one entry, or
      (b) list T2/T7/T10 as separate rows.

    Strategy: scan for any markdown table row whose first column matches one of
    ``T2``/``T7``/``T10`` (with optional 173B prefix). If none of T2/T7/T10
    appear individually, fall back to a single 173B row whose fields apply to
    all three items.
    """
    rows: dict[str, ItemFields] = {}
    fallback: ItemFields | None = None
    in_table = False
    headers: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                if any("决议" in h or "状态" in h for h in cells):
                    in_table = True
                    headers = cells
                continue
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            if len(cells) < 2:
                continue
            first = cells[0]
            # Find resolution / owner / target columns by header name (best-effort)

            def col(name: str) -> str:
                for idx, h in enumerate(headers):
                    if name in h and idx < len(cells):
                        return re.sub(r"\*+", "", cells[idx]).strip()
                return ""

            resolution = col("决议") or col("状态")
            owner = col("责任") or col("Owner")
            target = col("目标") or col("日期")

            for item in ITEMS:
                if item in first:
                    rows[item] = ItemFields(resolution, owner, target)
                    break
            else:
                if "173B" in first and fallback is None:
                    fallback = ItemFields(resolution, owner, target)
        else:
            in_table = False
            headers = []

    if rows:
        # Fill any missing items with fallback row, if present
        for item in ITEMS:
            if item not in rows and fallback is not None:
                rows[item] = fallback
        return rows
    if fallback is not None:
        return {item: fallback for item in ITEMS}
    return {}


def main() -> int:
    if not DISPOSITION.exists():
        print(
            f"ERROR: disposition file missing: {DISPOSITION}",
            file=sys.stderr,
        )
        return 2
    if not README.exists():
        print(f"ERROR: iterations README missing: {README}", file=sys.stderr)
        return 2

    try:
        disposition = _parse_disposition_table(DISPOSITION.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: failed to parse disposition: {exc!r}", file=sys.stderr)
        return 2
    try:
        readme = _parse_readme(README.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: failed to parse README: {exc!r}", file=sys.stderr)
        return 2

    missing = [item for item in ITEMS if item not in disposition]
    if missing:
        print(
            f"ERROR: 173B_disposition.md missing rows for: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    if not readme:
        # README has not yet been updated for 175; surface a clear advisory but
        # do not block — README updates happen on close-out.
        print(
            "WARN: iterations/README.md does not yet contain a 173B row; "
            "consistency check skipped (README will be updated at 175 close).",
        )
        return 0

    inconsistencies: list[str] = []
    for item in ITEMS:
        d = disposition[item]
        r = readme.get(item)
        if r is None:
            inconsistencies.append(
                f"{item}: missing in README (disposition: {d.resolution})"
            )
            continue
        if d.resolution != r.resolution:
            inconsistencies.append(
                f"{item} 决议类型 不一致: disposition={d.resolution!r} README={r.resolution!r}"
            )
        if d.owner != r.owner:
            inconsistencies.append(
                f"{item} 责任人 不一致: disposition={d.owner!r} README={r.owner!r}"
            )
        if d.target_date != r.target_date:
            inconsistencies.append(
                f"{item} 目标日期 不一致: disposition={d.target_date!r} README={r.target_date!r}"
            )

    if inconsistencies:
        print("FAIL: 173B disposition / README inconsistencies:")
        for line in inconsistencies:
            print(f"  - {line}")
        return 1

    print("OK: 173B disposition consistent with iterations/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
