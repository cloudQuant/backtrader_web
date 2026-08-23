#!/usr/bin/env python3
"""Evaluate the trusted-base Iteration 195 PR governance contract locally.

This checker is intentionally standard-library-only.  It consumes JSON that
the read-only workflow saved from GitHub's metadata APIs and never executes,
checks out, or imports pull-request head content.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from check_pr_template import governance_declaration_issues
from classify_pr_risk import changed_file_paths, classify_changed_files
from governance_contract import (
    HOTFIX_BRANCH,
    RELEASE_BRANCH,
    RISK_ORDER,
    load_manifests,
    load_risk_map,
    validate_branch_contract,
    validate_manifests,
)

_FIELD_LINE = r"^\s*[-*]\s*(?:\*\*)?{label}(?:\*\*)?\s*[:：]\s*(?P<value>[^\n]*)$"
_GOVERNANCE_HEADING_RE = re.compile(
    r"^##[ \t]+Governance declaration[ \t]*$", re.IGNORECASE | re.MULTILINE
)
_HOTFIX_HEADING_RE = re.compile(r"^##[ \t]+Hotfix[ \t]+前移计划(?:[ \t]+.*)?$", re.MULTILINE)
_RELEASE_HEADING_RE = re.compile(r"^##[ \t]+Release[ \t]+清单(?:[ \t]+.*)?$", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
_FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})[^\n]*$")
_INCIDENT_IDENTIFIER_RE = re.compile(
    r"\b(?:INC|SEC)-[A-Z0-9][A-Z0-9._-]*\b|\bGHSA-[A-Z0-9-]+\b", re.IGNORECASE
)
_PRIVATE_DISCLOSURE_RE = re.compile(
    r"https://[^\s]*(?:security|disclosure|advisory)[^\s]*", re.IGNORECASE
)
_NEGATIVE_INCIDENT_RE = re.compile(
    r"\b(?:no|none|without|not)\s+(?:incident|inc(?:ident)?|security)\b|无(?:事故|事件)|未(?:发生|提供).{0,8}(?:事故|事件)",
    re.IGNORECASE,
)
_FORWARD_PORT_REFERENCE_RE = re.compile(
    r"(?:\bdev\b.*?(?:\bpr\b|\bissue\b|https://|#\d+)|(?:\bpr\b|\bissue\b|https://|#\d+).*?\bdev\b)",
    re.IGNORECASE | re.DOTALL,
)
_NO_IMPACT_RE = re.compile(r"\bnot\s+affected\b|不受影响", re.IGNORECASE)
_NEGATIVE_FORWARD_PORT_RE = re.compile(
    r"\b(?:no|none|not)\s+(?:forward[- ]?port|backport|dev\s+(?:pr|issue))\b|无(?:前移|回迁)|未(?:前移|回迁)",
    re.IGNORECASE,
)
_PLACEHOLDER_EVIDENCE_RE = re.compile(
    r"^(?:none|n/?a|tbd|todo|nil|null|unknown|no\s+evidence|无|未填|待补充|待定|暂无)\s*[。.!！]*$",
    re.IGNORECASE,
)
_TARGET_RE = re.compile(r"\b(dev|master)\b", re.IGNORECASE)
_RISK_RE = re.compile(r"\b(R[0-3])\b", re.IGNORECASE)
_TERMINAL_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _login(value: Any) -> str | None:
    if isinstance(value, Mapping):
        login = value.get("login")
        if isinstance(login, str) and login.strip():
            return login.strip()
    return None


def _visible_body(body: str) -> str:
    """Discard hidden comments and fenced code before policy parsing."""
    without_comments = _HTML_COMMENT_RE.sub("", body)
    visible_lines: list[str] = []
    active_fence: str | None = None
    for line in without_comments.splitlines():
        if active_fence is not None:
            closing = re.compile(
                rf"^[ \t]*{re.escape(active_fence[0])}{{{len(active_fence)},}}[ \t]*$"
            )
            if closing.fullmatch(line):
                active_fence = None
            continue
        opening = _FENCE_RE.match(line)
        if opening:
            active_fence = opening.group("marker")
            continue
        visible_lines.append(line)
    return "\n".join(visible_lines)


def _section_content(body: str, heading: re.Pattern[str]) -> str | None:
    """Return a unique visible H2 section, excluding every other H2 section."""
    matches = list(heading.finditer(body))
    if len(matches) != 1:
        return None
    rest = body[matches[0].end() :]
    next_heading = re.search(r"^##[ \t]+", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _section_count(body: str, heading: re.Pattern[str]) -> int:
    return len(list(heading.finditer(body)))


def _field_values(section: str | None, label: str) -> list[str | None]:
    if section is None:
        return []
    pattern = re.compile(_FIELD_LINE.format(label=re.escape(label)), re.IGNORECASE | re.MULTILINE)
    values: list[str | None] = []
    for match in pattern.finditer(section):
        value = match.group("value").strip().strip("`").rstrip("。.")
        values.append(value or None)
    return values


def _field_value(section: str | None, label: str) -> str | None:
    """Return the sole non-empty field value, never selecting among duplicates."""
    values = _field_values(section, label)
    if len(values) != 1:
        return None
    return values[0]


def _governance_field(visible_body: str, label: str) -> str | None:
    return _field_value(_section_content(visible_body, _GOVERNANCE_HEADING_RE), label)


def _section_field_issues(visible_body: str, kind: str) -> list[str]:
    """Reject ambiguous or duplicated policy fields in their designated sections."""
    requirements: list[tuple[str, re.Pattern[str], tuple[str, ...]]] = [
        ("Governance declaration", _GOVERNANCE_HEADING_RE, ("目标分支", "风险等级", "测试证据"))
    ]
    if kind == "hotfix":
        requirements.append(("Hotfix 前移计划", _HOTFIX_HEADING_RE, ("前移计划",)))
    elif kind == "release":
        requirements.append(("Release 清单", _RELEASE_HEADING_RE, ("Release 清单",)))

    issues: list[str] = []
    for section_name, heading, labels in requirements:
        section_count = _section_count(visible_body, heading)
        if section_count != 1:
            issues.append(f"{section_name} section must appear exactly once in the visible PR body")
            continue
        section = _section_content(visible_body, heading)
        for label in labels:
            if len(_field_values(section, label)) != 1:
                issues.append(f"{section_name} field {label!r} must appear exactly once")
    return issues


def _declared_target(visible_body: str) -> str | None:
    value = _governance_field(visible_body, "目标分支")
    targets = {target.casefold() for target in _TARGET_RE.findall(value or "")}
    return next(iter(targets)) if len(targets) == 1 else None


def _declared_risk(visible_body: str) -> str | None:
    value = _governance_field(visible_body, "风险等级")
    match = _RISK_RE.fullmatch(value or "")
    return match.group(1).upper() if match else None


def _pr_kind(base_branch: str, head_branch: str) -> str:
    if base_branch == "master" and HOTFIX_BRANCH.fullmatch(head_branch):
        return "hotfix"
    if base_branch == "master" and RELEASE_BRANCH.fullmatch(head_branch):
        return "release"
    return "normal"


def _meaningful_evidence(value: str | None) -> bool:
    """Reject empty and common placeholder evidence values."""
    if value is None:
        return False
    normalized = value.strip()
    return bool(normalized) and _PLACEHOLDER_EVIDENCE_RE.fullmatch(normalized) is None


def _has_structured_incident(value: str) -> bool:
    return not _NEGATIVE_INCIDENT_RE.search(value) and bool(
        _INCIDENT_IDENTIFIER_RE.search(value) or _PRIVATE_DISCLOSURE_RE.search(value)
    )


def _has_forward_port_reference(value: str) -> bool:
    if _NEGATIVE_FORWARD_PORT_RE.search(value) or not _meaningful_evidence(value):
        return False
    if _FORWARD_PORT_REFERENCE_RE.search(value):
        return True
    no_impact = _NO_IMPACT_RE.search(value)
    if not no_impact:
        return False
    reason = value[no_impact.end() :].strip(" :：-—。.")
    return len(reason) >= 12 and _meaningful_evidence(reason)


def _branch_evidence(visible_body: str, kind: str) -> dict[str, str]:
    """Derive strict branch-contract evidence from its designated H2 sections."""
    test_evidence = _governance_field(visible_body, "测试证据")
    hotfix_plan = _field_value(_section_content(visible_body, _HOTFIX_HEADING_RE), "前移计划")
    release_checklist = _field_value(
        _section_content(visible_body, _RELEASE_HEADING_RE), "Release 清单"
    )
    evidence: dict[str, str] = {}
    if kind == "hotfix":
        if hotfix_plan and _has_structured_incident(hotfix_plan):
            evidence["incident"] = hotfix_plan
        if hotfix_plan and _has_forward_port_reference(hotfix_plan):
            evidence["forward_port_plan"] = hotfix_plan
    if kind == "release":
        if _meaningful_evidence(release_checklist):
            evidence["release_checklist"] = release_checklist
        if _meaningful_evidence(test_evidence):
            evidence["release_validation"] = test_evidence
    return evidence


def _labels(pr: Mapping[str, Any]) -> list[str]:
    raw_labels = pr.get("labels", [])
    if not isinstance(raw_labels, list):
        return []
    labels: list[str] = []
    for entry in raw_labels:
        if isinstance(entry, str) and entry.strip():
            labels.append(entry.strip())
        elif isinstance(entry, Mapping):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                labels.append(name.strip())
    return sorted(set(labels))


def _requested_reviewer_logins(pr: Mapping[str, Any], author: str) -> list[str]:
    requested = pr.get("requested_reviewers", [])
    if not isinstance(requested, list):
        return []
    return sorted(
        {
            login
            for item in requested
            if (login := _login(item)) is not None and login.casefold() != author.casefold()
        }
    )


def _review_timestamp(value: Any, position: int) -> tuple[datetime, int]:
    if isinstance(value, str) and value.strip():
        timestamp = value.strip()
        if timestamp.endswith("Z"):
            timestamp = f"{timestamp[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc), position
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc), position


def _review_authorization(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return None


def _latest_reviews(reviews: Sequence[Any], author: str) -> dict[str, tuple[str, str | None]]:
    """Return each reviewer's effective terminal state and authorization.

    Comments and pending reviews are non-terminal.  They cannot erase an
    earlier approval or change request.  An OWNER terminal review has
    precedence over subsequent unverified terminal events so an unverified
    actor cannot clear an OWNER change request or approval.
    """
    histories: dict[str, list[tuple[tuple[datetime, int], str, str | None]]] = {}
    for position, review in enumerate(reviews):
        if not isinstance(review, Mapping):
            continue
        login = _login(review.get("user"))
        if login is None or login.casefold() == author.casefold():
            continue
        state = review.get("state")
        if not isinstance(state, str) or not state.strip():
            continue
        key = login.casefold()
        histories.setdefault(key, []).append(
            (
                _review_timestamp(review.get("submitted_at"), position),
                state.strip().upper(),
                _review_authorization(review.get("author_association")),
            )
        )

    effective: dict[str, tuple[str, str | None]] = {}
    for login, history in sorted(histories.items()):
        latest_terminal: tuple[str, str | None] | None = None
        latest_nonterminal: tuple[str, str | None] | None = None
        owner_terminal: tuple[str, str | None] | None = None
        for _, state, authorization in sorted(history, key=lambda entry: entry[0]):
            if state in _TERMINAL_REVIEW_STATES:
                latest_terminal = (state, authorization)
                if authorization == "OWNER":
                    owner_terminal = (state, authorization)
            else:
                latest_nonterminal = (state, authorization)
        state = owner_terminal or latest_terminal or latest_nonterminal
        if state is not None:
            effective[login] = state
    return effective


def _review_summary(reviews: Sequence[Any], author: str) -> dict[str, list[str]]:
    latest = _latest_reviews(reviews, author)
    approvals = sorted(
        login
        for login, (state, authorization) in latest.items()
        if state == "APPROVED" and authorization == "OWNER"
    )
    changes_requested = sorted(
        login
        for login, (state, authorization) in latest.items()
        if state == "CHANGES_REQUESTED" and authorization == "OWNER"
    )
    unverified = sorted(
        login
        for login, (state, authorization) in latest.items()
        if state == "APPROVED" and authorization != "OWNER"
    )
    return {
        "effective_approvals": approvals,
        "changes_requested_by": changes_requested,
        "reviewers": sorted(latest),
        "unverified_reviews": unverified,
    }


def _code_owner_status(manifest: Mapping[str, Any]) -> dict[str, Any]:
    pull_request = manifest.get("pull_request")
    if not isinstance(pull_request, Mapping):
        return {"enabled": False, "status": "manifest_invalid", "verified": False}
    code_owner = pull_request.get("code_owner_review")
    if not isinstance(code_owner, Mapping):
        return {"enabled": False, "status": "manifest_invalid", "verified": False}
    enabled = code_owner.get("enabled") is True
    if not enabled:
        return {"enabled": False, "status": "disabled_pending_D2", "verified": False}
    return {
        "enabled": True,
        "status": "ruleset_required_not_verified_by_gate",
        "verified": False,
    }


def _branch_manifest(
    manifests: Mapping[str, Mapping[str, Any]], base_branch: str
) -> Mapping[str, Any] | None:
    manifest = manifests.get(base_branch)
    return manifest if isinstance(manifest, Mapping) else None


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _inventory_issues(pr: Mapping[str, Any], entry_count: Any) -> list[str]:
    """Fail closed when the GitHub files listing is incomplete or malformed."""
    reported_count = pr.get("changed_files")
    if not _is_nonnegative_int(reported_count):
        return [
            "complete changed-file inventory unavailable: PR metadata changed_files must be "
            "a non-negative integer"
        ]
    if not _is_nonnegative_int(entry_count):
        return [
            "complete changed-file inventory unavailable: files API entry count must be "
            "a non-negative integer"
        ]
    if reported_count != entry_count:
        return [
            "complete changed-file inventory unavailable: PR metadata reports "
            f"{reported_count} files but the files API returned {entry_count}; do not trust "
            "path-risk classification until the complete inventory is available"
        ]
    return []


def _manifest_policy_issues(manifests: Any) -> list[str]:
    """Validate the full Ruleset desired state before using any review floor."""
    if not isinstance(manifests, Mapping):
        return ["Ruleset manifests must be a mapping"]
    try:
        issues = list(validate_manifests(manifests))
    except (AttributeError, TypeError) as error:
        issues = [f"Ruleset manifests are invalid: {error}"]
    for branch in ("dev", "master"):
        if not isinstance(manifests.get(branch), Mapping):
            message = f"missing Ruleset manifest: {branch} (missing or invalid)"
            if message not in issues:
                issues.append(message)
    return issues


def evaluate_pr_governance(
    pr: Mapping[str, Any],
    reviews: Sequence[Any],
    changed_files: Sequence[str],
    *,
    risk_map: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    changed_file_entry_count: Any,
) -> dict[str, Any]:
    """Return an actionable, deterministic Governance Gate result.

    This function operates entirely on supplied data.  The caller owns safe
    collection of trusted-base configuration and read-only PR metadata.
    """
    pr_data = _mapping(pr, "PR metadata")
    base = _mapping(pr_data.get("base"), "PR base")
    head = _mapping(pr_data.get("head"), "PR head")
    author_data = _mapping(pr_data.get("user"), "PR author")
    base_branch = base.get("ref")
    head_branch = head.get("ref")
    author = _login(author_data)
    body = pr_data.get("body")
    if not isinstance(base_branch, str) or not base_branch.strip():
        raise ValueError("PR base.ref must be a non-empty string")
    if not isinstance(head_branch, str) or not head_branch.strip():
        raise ValueError("PR head.ref must be a non-empty string")
    if author is None:
        raise ValueError("PR user.login must be a non-empty string")
    if not isinstance(body, str):
        raise ValueError("PR body must be a string")
    if not isinstance(reviews, Sequence) or isinstance(reviews, (str, bytes)):
        raise ValueError("reviews must be a JSON list")

    base_branch = base_branch.strip()
    head_branch = head_branch.strip()
    kind = _pr_kind(base_branch, head_branch)
    visible_body = _visible_body(body)
    classification = classify_changed_files(changed_files, risk_map)
    labels = _labels(pr_data)
    manifest = _branch_manifest(manifests, base_branch) if isinstance(manifests, Mapping) else None
    issues = _manifest_policy_issues(manifests)
    issues.extend(_inventory_issues(pr_data, changed_file_entry_count))
    approval_floor: int | None = None
    if manifest is not None:
        pull_request = manifest.get("pull_request")
        if not isinstance(pull_request, Mapping):
            issues.append(f"{base_branch} Ruleset manifest pull_request must be an object")
        else:
            candidate_floor = pull_request.get("required_approvals")
            if _is_nonnegative_int(candidate_floor):
                approval_floor = candidate_floor
            else:
                issues.append(
                    f"{base_branch} Ruleset manifest required_approvals must be a "
                    "non-negative integer"
                )

    # The inherited static checker remains the compatibility authority for the
    # common declaration.  Its kind-specific H2 parser currently treats the
    # newline after a Chinese heading as whitespace inside the heading, so the
    # trusted gate intentionally calls its stable normal contract here and
    # enforces hotfix/release fields below with this module's strict parser.
    issues.extend(governance_declaration_issues(visible_body, "normal"))
    issues.extend(_section_field_issues(visible_body, kind))
    declared_target = _declared_target(visible_body)
    if declared_target != base_branch:
        issues.append(
            f"governance declaration target branch {declared_target!r} does not match actual "
            f"PR base {base_branch!r}; update the declaration or retarget the PR"
        )

    declared_risk = _declared_risk(visible_body)
    computed_risk = str(classification["risk"])
    if declared_risk not in RISK_ORDER:
        issues.append(
            f"governance declaration must name R0-R3; changed paths require {computed_risk}"
        )
    elif RISK_ORDER[declared_risk] < RISK_ORDER[computed_risk]:
        issues.append(
            f"governance declaration declares {declared_risk} but changed paths require "
            f"{computed_risk}; labels cannot lower path-derived risk"
        )

    issues.extend(
        validate_branch_contract(base_branch, head_branch, _branch_evidence(visible_body, kind))
    )
    if base_branch == "master" and kind == "normal":
        issues.append("regular contribution branches must target dev; retarget this PR to dev")

    review_summary = _review_summary(reviews, author)
    effective_approvals = review_summary["effective_approvals"]
    changes_requested_by = review_summary["changes_requested_by"]
    if approval_floor is not None and len(effective_approvals) < approval_floor:
        unverified_reviews = review_summary["unverified_reviews"]
        if unverified_reviews:
            reviewers = ", ".join(unverified_reviews)
            issues.append(
                f"review approval authorization not verified for {reviewers}; request verified "
                "maintainer review"
            )
        issues.append(
            f"{base_branch} requires {approval_floor} non-author approvals but has "
            f"{len(effective_approvals)}; request an additional maintainer review"
        )
    for reviewer in changes_requested_by:
        issues.append(
            f"latest review from {reviewer} is CHANGES_REQUESTED; resolve it before merge"
        )

    requested_reviewers = _requested_reviewer_logins(pr_data, author)
    protective_reviewers = effective_approvals
    if computed_risk in {"R2", "R3"}:
        if not _meaningful_evidence(_governance_field(visible_body, "测试证据")):
            issues.append(
                f"{computed_risk} change requires concrete test evidence in the governance declaration"
            )
        if not protective_reviewers:
            issues.append(
                f"{computed_risk} change requires a verified OWNER protective approval; "
                "requested reviewers alone do not satisfy it; request verified maintainer review"
            )

    code_owner_review = (
        _code_owner_status(manifest)
        if manifest is not None
        else {"enabled": False, "status": "unsupported_target", "verified": False}
    )
    return {
        "ok": not issues,
        "pr_kind": kind,
        "base_branch": base_branch,
        "head_branch": head_branch,
        "risk": computed_risk,
        "matched_rules": classification["matches"],
        "labels_can_lower_risk": False,
        "ignored_labels": labels,
        "approval_floor": approval_floor,
        "effective_approvals": effective_approvals,
        "changes_requested_by": changes_requested_by,
        "unverified_reviews": review_summary["unverified_reviews"],
        "protective_reviewers": protective_reviewers,
        "requested_reviewers": requested_reviewers,
        "code_owner_review": code_owner_review,
        "issues": issues,
    }


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _flatten_pages(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("reviews payload must be a JSON list")
    entries: list[Any] = []
    for item in value:
        if isinstance(item, list):
            entries.extend(_flatten_pages(item))
        else:
            entries.append(item)
    return entries


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, type=Path)
    parser.add_argument("--reviews", required=True, type=Path)
    parser.add_argument("--changed-files", required=True, type=Path)
    parser.add_argument("--risk-map", required=True, type=Path)
    parser.add_argument("--manifest-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Evaluate local inputs and use the exit status only as a gate result."""
    args = _parse_args()
    try:
        file_entries = _flatten_pages(_load_json(args.changed_files))
        result = evaluate_pr_governance(
            _load_json(args.pr),
            _flatten_pages(_load_json(args.reviews)),
            changed_file_paths(file_entries),
            risk_map=load_risk_map(args.risk_map),
            manifests=load_manifests(args.manifest_dir),
            changed_file_entry_count=len(file_entries),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "issues": [str(error)]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
