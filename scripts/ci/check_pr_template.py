#!/usr/bin/env python3
"""Iteration 175 §4.7 — verify the PR description includes the mandatory
"i18n 变更清单" section with all 4 sub-fields filled in (non-placeholder).

Iteration 179 §D made this diff-aware so it can be a *blocking* gate without
nagging PRs that touch no translations: the manifest is only required when the
PR actually changes a locale file. PRs with no locale changes pass immediately.

Inputs:
  - PR_BODY env var (set by GitHub Actions: github.event.pull_request.body)
  - CHANGED_FILES env var (optional, newline- or space-separated list of files
    changed in the PR). When provided and it contains no i18n locale file, the
    check passes without requiring a manifest. When unset, the check runs
    unconditionally (backwards-compatible with the pre-179 behaviour).

Exit codes:
  0 - manifest present & filled, OR PR changes no locale files
  1 - locale files changed but manifest missing / has placeholders
  2 - PR_BODY env var unset (don't fail in non-PR contexts)
"""

from __future__ import annotations

import os
import re
import sys

# Locale source files whose changes require an i18n manifest in the PR body.
LOCALE_PATH_MARKERS = (
    "src/frontend/src/i18n/locales/",
    "/i18n/locales/",
)

# Iteration 195 — tolerate the repo template's markdown-bold form
# ("- **zh-CN key 数量 (count)**: 12") as well as the historical plain form.
REQUIRED_FIELDS = [
    ("zh-CN key 数量", r"zh-CN\s*key\s*数量\s*[\(（][^)）]*[\)）]?\s*\*{0,2}\s*[:：]\s*([^\n]+)"),
    ("en-US key 数量", r"en-US\s*key\s*数量\s*[\(（][^)）]*[\)）]?\s*\*{0,2}\s*[:：]\s*([^\n]+)"),
]

ADDED_HEADING = re.compile(r"本\s*PR\s*新增\s*key", re.UNICODE)
REMOVED_HEADING = re.compile(r"本\s*PR\s*删除\s*key", re.UNICODE)

PLACEHOLDER = re.compile(
    r"<\s*fill\s*in.*?>|`<fill\s*in>`|<!--.*?-->", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Iteration 195 — static governance-declaration contract. Dynamic base/head
# branch + review validation lives in scripts/ci/check_pr_governance.py.
# ---------------------------------------------------------------------------

GOVERNANCE_HEADING = "## Governance declaration"

_GOVERNANCE_SECTION_RE = re.compile(
    r"^##\s+Governance declaration\s*$", re.MULTILINE | re.IGNORECASE
)

_PR_KINDS = ("normal", "hotfix", "release")

_COMMON_FIELDS = ("目标分支", "风险等级", "测试证据")
_KIND_FIELDS = {
    "normal": (),
    "hotfix": ("前移计划",),
    "release": ("Release 清单",),
}

_FIELD_LINE_RE_TEMPLATE = r"^\s*[-*]?\s*\**\s*{label}\s*\**\s*[:：]\s*(.*)$"


def _field_value(section: str, label: str) -> str | None:
    """Return the raw value of ``label`` inside the governance section."""
    pattern = re.compile(
        _FIELD_LINE_RE_TEMPLATE.format(label=re.escape(label)), re.UNICODE | re.MULTILINE
    )
    m = pattern.search(section)
    if not m:
        return None
    return m.group(1).strip().strip("`").rstrip("。.")


def governance_declaration_issues(body: str, pr_kind: str = "normal") -> list[str]:
    """Validate the ``## Governance declaration`` section of a PR body.

    ``pr_kind`` is one of ``normal`` (feature/fix/docs → dev), ``hotfix``
    (hotfix/master-* → master) or ``release`` (release/vX.Y.Z → master).
    Returns a list of human-readable issues; empty means accepted.
    """
    issues: list[str] = []
    if pr_kind not in _PR_KINDS:
        return [f"unknown governance pr_kind: {pr_kind!r}"]

    if not _GOVERNANCE_SECTION_RE.search(body):
        return [f"missing required section: {GOVERNANCE_HEADING}"]

    start = _GOVERNANCE_SECTION_RE.search(body).end()
    rest = body[start:]
    next_heading = re.search(r"^##\s+", rest[1:], re.MULTILINE)
    section = rest[: next_heading.start() + 1] if next_heading else rest

    labels = list(_COMMON_FIELDS) + list(_KIND_FIELDS.get(pr_kind, ()))
    for label in labels:
        value = _field_value(section, label)
        if value is None:
            issues.append(f"governance field missing: {label}")
        elif not value or PLACEHOLDER.search(value):
            issues.append(f"governance field unfilled: {label} = {value!r}")
    return issues


def _locale_files_changed() -> bool | None:
    """Return True/False if CHANGED_FILES is set, else None (unknown)."""
    raw = os.environ.get("CHANGED_FILES")
    if raw is None:
        return None
    files = [f.strip() for f in re.split(r"[\s,]+", raw) if f.strip()]
    if not files:
        return False
    return any(marker in f for f in files for marker in LOCALE_PATH_MARKERS)


def _report_fail(issues: list[str]) -> int:
    print("FAIL: PR description contract incomplete:")
    for line in issues:
        print(f"  - {line}")
    return 1


def main() -> int:
    body = os.environ.get("PR_BODY")
    if body is None or body.strip() == "":
        print("WARN: PR_BODY env var is empty; skipping check (non-PR context).")
        return 2

    issues: list[str] = []

    gov_kind = os.environ.get("GOVERNANCE_PR_KIND", "").strip()
    if gov_kind:
        issues.extend(governance_declaration_issues(body, gov_kind))

    locale_changed = _locale_files_changed()
    if locale_changed is False:
        if issues:
            return _report_fail(issues)
        print("OK: PR changes no i18n locale files; manifest not required.")
        return 0

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
        return _report_fail(issues)

    if gov_kind:
        print(f"OK: governance declaration complete for kind {gov_kind!r}.")
    print("OK: i18n change manifest present and filled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
