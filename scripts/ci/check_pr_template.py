#!/usr/bin/env python3
"""Iteration 175 §4.7 — verify the PR description includes the mandatory
"i18n 变更清单" section with all 4 sub-fields filled in (non-placeholder).

Inputs:
  - PR_BODY env var (set by GitHub Actions: github.event.pull_request.body)

Exit codes:
  0 - PR body has all required sub-fields filled
  1 - missing field or placeholder still present
  2 - PR_BODY env var unset (don't fail in non-PR contexts)
"""

from __future__ import annotations

import os
import re
import sys

REQUIRED_FIELDS = [
    ("zh-CN key 数量", r"zh-CN\s*key\s*数量\s*[\(（][^)）]*[\)）]?\s*[:：]\s*([^\n]+)"),
    ("en-US key 数量", r"en-US\s*key\s*数量\s*[\(（][^)）]*[\)）]?\s*[:：]\s*([^\n]+)"),
]

ADDED_HEADING = re.compile(r"本\s*PR\s*新增\s*key", re.UNICODE)
REMOVED_HEADING = re.compile(r"本\s*PR\s*删除\s*key", re.UNICODE)

PLACEHOLDER = re.compile(r"<\s*fill\s*in.*?>|`<fill\s*in>`", re.IGNORECASE)


def main() -> int:
    body = os.environ.get("PR_BODY")
    if body is None or body.strip() == "":
        print("WARN: PR_BODY env var is empty; skipping check (non-PR context).")
        return 2

    issues: list[str] = []

    for label, pattern in REQUIRED_FIELDS:
        m = re.search(pattern, body, re.IGNORECASE)
        if not m:
            issues.append(f"missing field: {label}")
            continue
        value = m.group(1).strip().rstrip(".`*\u3002")
        if not value or PLACEHOLDER.search(value):
            issues.append(f"unfilled placeholder: {label} = {value!r}")

    if not ADDED_HEADING.search(body):
        issues.append("missing field: 本 PR 新增 key")
    if not REMOVED_HEADING.search(body):
        issues.append("missing field: 本 PR 删除 key")

    if PLACEHOLDER.search(body):
        # Some `<fill in>` survived on the added/removed lists — only
        # block if they are inside the i18n section.
        section_match = re.search(
            r"i18n\s*变更清单(.*?)(##\s|\Z)", body, re.IGNORECASE | re.DOTALL
        )
        if section_match and PLACEHOLDER.search(section_match.group(1)):
            issues.append("placeholder text still present inside i18n section")

    if issues:
        print("FAIL: i18n change manifest incomplete in PR description:")
        for line in issues:
            print(f"  - {line}")
        return 1

    print("OK: i18n change manifest present and filled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
