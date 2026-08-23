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
)

_FIELD_LINE = r"^\s*[-*]\s*(?:\*\*)?{label}(?:\*\*)?\s*[:：]\s*(?P<value>[^\n]*)$"
_INCIDENT_RE = re.compile(r"\binc[- #]?\d+\b|\bincident\b|事故|披露", re.IGNORECASE)
_FORWARD_PORT_RE = re.compile(r"\bdev\b|forward[- ]?port|backport|前移", re.IGNORECASE)
_TARGET_RE = re.compile(r"\b(dev|master)\b", re.IGNORECASE)
_RISK_RE = re.compile(r"\b(R[0-3])\b", re.IGNORECASE)


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


def _field_value(body: str, label: str) -> str | None:
    pattern = re.compile(_FIELD_LINE.format(label=re.escape(label)), re.IGNORECASE | re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return None
    value = match.group("value").strip().strip("`").rstrip("。.")
    return value or None


def _declared_target(body: str) -> str | None:
    value = _field_value(body, "目标分支")
    match = _TARGET_RE.search(value or "")
    return match.group(1).casefold() if match else None


def _declared_risk(body: str) -> str | None:
    value = _field_value(body, "风险等级")
    match = _RISK_RE.search(value or "")
    return match.group(1).upper() if match else None


def _pr_kind(base_branch: str, head_branch: str) -> str:
    if base_branch == "master" and HOTFIX_BRANCH.fullmatch(head_branch):
        return "hotfix"
    if base_branch == "master" and RELEASE_BRANCH.fullmatch(head_branch):
        return "release"
    return "normal"


def _branch_evidence(body: str, kind: str) -> dict[str, str]:
    """Derive the branch-contract evidence that the current template exposes."""
    test_evidence = _field_value(body, "测试证据") or ""
    hotfix_plan = _field_value(body, "前移计划") or ""
    release_checklist = _field_value(body, "Release 清单") or ""
    evidence: dict[str, str] = {}
    if kind == "hotfix":
        if _INCIDENT_RE.search(hotfix_plan):
            evidence["incident"] = hotfix_plan
        if _FORWARD_PORT_RE.search(hotfix_plan):
            evidence["forward_port_plan"] = hotfix_plan
    if kind == "release":
        if release_checklist:
            evidence["release_checklist"] = release_checklist
        if test_evidence:
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


def _latest_reviews(reviews: Sequence[Any], author: str) -> dict[str, str]:
    """Return each non-author reviewer's latest normalized review state."""
    latest: dict[str, tuple[tuple[datetime, int], str]] = {}
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
        candidate = (_review_timestamp(review.get("submitted_at"), position), state.strip().upper())
        if key not in latest or candidate[0] >= latest[key][0]:
            latest[key] = candidate
    return {login: state for login, (_, state) in sorted(latest.items())}


def _review_summary(reviews: Sequence[Any], author: str) -> dict[str, list[str]]:
    latest = _latest_reviews(reviews, author)
    approvals = sorted(login for login, state in latest.items() if state == "APPROVED")
    changes_requested = sorted(
        login for login, state in latest.items() if state == "CHANGES_REQUESTED"
    )
    return {
        "effective_approvals": approvals,
        "changes_requested_by": changes_requested,
        "reviewers": sorted(latest),
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


def evaluate_pr_governance(
    pr: Mapping[str, Any],
    reviews: Sequence[Any],
    changed_files: Sequence[str],
    *,
    risk_map: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
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
    classification = classify_changed_files(changed_files, risk_map)
    labels = _labels(pr_data)
    manifest = _branch_manifest(manifests, base_branch)
    approval_floor: int | None = None
    if manifest is not None:
        pull_request = _mapping(
            manifest.get("pull_request"), f"{base_branch} manifest pull_request"
        )
        approval_floor = pull_request.get("required_approvals")
        if not isinstance(approval_floor, int) or isinstance(approval_floor, bool):
            raise ValueError(f"{base_branch} manifest required_approvals must be an integer")

    issues = list(governance_declaration_issues(body, kind))
    declared_target = _declared_target(body)
    if declared_target != base_branch:
        issues.append(
            f"governance declaration target branch {declared_target!r} does not match actual "
            f"PR base {base_branch!r}; update the declaration or retarget the PR"
        )

    declared_risk = _declared_risk(body)
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

    issues.extend(validate_branch_contract(base_branch, head_branch, _branch_evidence(body, kind)))
    if base_branch == "master" and kind == "normal":
        issues.append("regular contribution branches must target dev; retarget this PR to dev")

    review_summary = _review_summary(reviews, author)
    effective_approvals = review_summary["effective_approvals"]
    changes_requested_by = review_summary["changes_requested_by"]
    if approval_floor is not None and len(effective_approvals) < approval_floor:
        issues.append(
            f"{base_branch} requires {approval_floor} non-author approvals but has "
            f"{len(effective_approvals)}; request an additional maintainer review"
        )
    for reviewer in changes_requested_by:
        issues.append(
            f"latest review from {reviewer} is CHANGES_REQUESTED; resolve it before merge"
        )

    requested_reviewers = _requested_reviewer_logins(pr_data, author)
    protective_reviewers = sorted(set(review_summary["reviewers"]) | set(requested_reviewers))
    if computed_risk in {"R2", "R3"}:
        if not _field_value(body, "测试证据"):
            issues.append(
                f"{computed_risk} change requires concrete test evidence in the governance declaration"
            )
        if not protective_reviewers:
            issues.append(
                f"{computed_risk} change requires a readable protective reviewer or "
                "requested-reviewer record; request a maintainer review"
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
        "protective_reviewers": protective_reviewers,
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
        result = evaluate_pr_governance(
            _load_json(args.pr),
            _flatten_pages(_load_json(args.reviews)),
            changed_file_paths(_load_json(args.changed_files)),
            risk_map=load_risk_map(args.risk_map),
            manifests=load_manifests(args.manifest_dir),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "issues": [str(error)]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
