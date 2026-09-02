"""Local fixtures for the trusted-base Iteration 195 Governance Gate."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_CI = REPO_ROOT / "scripts" / "ci"
CHECKER_PATH = SCRIPTS_CI / "check_pr_governance.py"
RISK_MAP_PATH = REPO_ROOT / ".github" / "governance" / "risk-paths.json"
MANIFEST_DIR = REPO_ROOT / ".github" / "governance" / "rulesets"
REVIEWER_AUTHORIZATION_PATH = REPO_ROOT / ".github" / "governance" / "reviewer-authorization.json"
_DEFAULT_CHANGED_FILE_COUNT = object()
_CURRENT_HEAD_SHA = "c" * 40


def _authorization(*, approved: bool = True) -> dict[str, object]:
    """Return an explicit D2 authorization fixture for trusted-review tests."""
    status = "approved" if approved else "owner_baseline_pending_second_maintainer"
    reviewers = [
        {
            "login": login,
            "author_associations": ["OWNER"],
            "evidence": {
                "gate": "D2",
                "status": "approved" if approved else "owner_baseline",
                "reference": ".github/governance/decisions/iteration-195.md",
            },
        }
        for login in (
            "maintainer",
            "maintainer-a",
            "maintainer-b",
            "maintainer-c",
            "repository-owner",
        )
    ]
    return {
        "schema_version": 1,
        "decision": {
            "gate": "D2",
            "status": status,
            "reference": ".github/governance/decisions/iteration-195.md",
            "reason": "Synthetic test authorization only.",
        },
        "reviewers": reviewers,
    }


def _load_checker() -> ModuleType:
    assert CHECKER_PATH.is_file(), "Task 4 Governance Gate checker is not implemented"
    sys.path.insert(0, str(SCRIPTS_CI))
    try:
        spec = importlib.util.spec_from_file_location(
            "check_pr_governance_under_test", CHECKER_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _risk_map() -> dict[str, object]:
    return json.loads(RISK_MAP_PATH.read_text(encoding="utf-8"))


def _manifests(checker: ModuleType) -> dict[str, dict[str, object]]:
    return checker.load_manifests(MANIFEST_DIR)


def _body(
    *,
    target: str,
    risk: str,
    test_evidence: str = "pytest scripts/ci/tests/test_check_pr_governance.py -q passed",
    hotfix_plan: str | None = None,
    release_checklist: str | None = None,
) -> str:
    body = (
        "## Governance declaration\n\n"
        f"- **目标分支**: {target}\n"
        f"- **风险等级**: {risk}\n"
        f"- **测试证据**: {test_evidence}\n"
    )
    if hotfix_plan is not None:
        body += f"\n## Hotfix 前移计划\n\n- **前移计划**: {hotfix_plan}\n"
    if release_checklist is not None:
        body += f"\n## Release 清单\n\n- **Release 清单**: {release_checklist}\n"
    return body


def _pr(
    *,
    base: str,
    head: str,
    body: str,
    author: str = "contributor",
    labels: tuple[str, ...] = (),
    requested_reviewers: tuple[str, ...] = (),
    changed_file_count: object = 1,
) -> dict[str, object]:
    return {
        "number": 195,
        "base": {"ref": base},
        "head": {"ref": head, "sha": _CURRENT_HEAD_SHA},
        "user": {"login": author},
        "body": body,
        "labels": [{"name": label} for label in labels],
        "requested_reviewers": [{"login": login} for login in requested_reviewers],
        "changed_files": changed_file_count,
    }


def _review(
    login: str,
    state: str,
    submitted_at: str,
    author_association: str | None = "OWNER",
    commit_id: object = _CURRENT_HEAD_SHA,
) -> dict[str, object]:
    review: dict[str, object] = {
        "user": {"login": login},
        "state": state,
        "submitted_at": submitted_at,
    }
    if author_association is not None:
        review["author_association"] = author_association
    if commit_id is not None:
        review["commit_id"] = commit_id
    return review


def _evaluate(
    checker: ModuleType,
    pr: dict[str, object],
    reviews: list[dict[str, object]],
    changed_files: list[str],
    *,
    metadata_changed_file_count: object = _DEFAULT_CHANGED_FILE_COUNT,
    raw_file_entry_count: int | None = None,
    manifests: dict[str, dict[str, object]] | None = None,
    reviewer_authorization: dict[str, object] | None = None,
) -> dict[str, object]:
    pr_with_count = dict(pr)
    pr_with_count["changed_files"] = (
        len(changed_files)
        if metadata_changed_file_count is _DEFAULT_CHANGED_FILE_COUNT
        else metadata_changed_file_count
    )
    return checker.evaluate_pr_governance(
        pr_with_count,
        reviews,
        changed_files,
        risk_map=_risk_map(),
        manifests=_manifests(checker) if manifests is None else manifests,
        changed_file_entry_count=(
            len(changed_files) if raw_file_entry_count is None else raw_file_entry_count
        ),
        reviewer_authorization=(
            _authorization() if reviewer_authorization is None else reviewer_authorization
        ),
    )


def test_feature_to_dev_r1_with_complete_evidence_and_approval_passes() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is True
    assert result["pr_kind"] == "normal"
    assert result["risk"] == "R1"
    assert result["approval_floor"] == 1
    assert result["effective_approvals"] == ["maintainer"]
    assert result["code_owner_review"]["status"] == "disabled_pending_D2"
    assert result["issues"] == []


def test_matching_changed_file_metadata_and_files_inventory_is_accepted() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        metadata_changed_file_count=1,
        raw_file_entry_count=1,
    )

    assert result["ok"] is True
    assert not any(
        "complete changed-file inventory unavailable" in issue for issue in result["issues"]
    )


def test_truncated_files_api_inventory_is_rejected_before_path_risk_can_be_trusted() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/ci-cleanup",
        body=_body(target="dev", risk="R3"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        [".github/workflows/ci.yml"],
        metadata_changed_file_count=3001,
        raw_file_entry_count=3000,
    )

    assert result["risk"] == "R3"
    assert result["ok"] is False
    assert any("complete changed-file inventory unavailable" in issue for issue in result["issues"])


def test_malformed_changed_file_metadata_is_rejected_before_path_risk_can_be_trusted() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/ci-cleanup",
        body=_body(target="dev", risk="R3"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        [".github/workflows/ci.yml"],
        metadata_changed_file_count=True,
        raw_file_entry_count=1,
    )

    assert result["ok"] is False
    assert any("complete changed-file inventory unavailable" in issue for issue in result["issues"])


def test_empty_ruleset_manifest_set_blocks_supported_branch_governance() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        manifests={},
    )

    assert result["ok"] is False
    assert any("missing Ruleset manifest: dev" in issue for issue in result["issues"])


def test_missing_dev_or_master_ruleset_manifest_blocks_the_gate() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )
    missing_dev = _manifests(checker)
    missing_dev.pop("dev")
    missing_master = _manifests(checker)
    missing_master.pop("master")

    dev_result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        manifests=missing_dev,
    )
    master_result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        manifests=missing_master,
    )

    assert any("missing Ruleset manifest: dev" in issue for issue in dev_result["issues"])
    assert any("missing Ruleset manifest: master" in issue for issue in master_result["issues"])


def test_non_mapping_ruleset_manifest_blocks_the_gate_without_an_exception() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )
    manifests = _manifests(checker)
    manifests["dev"] = []  # type: ignore[assignment]

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        manifests=manifests,
    )

    assert result["ok"] is False
    assert any("missing Ruleset manifest: dev" in issue for issue in result["issues"])


def test_malformed_required_approvals_blocks_the_gate() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )
    manifests = copy.deepcopy(_manifests(checker))
    manifests["dev"]["pull_request"]["required_approvals"] = False

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        manifests=manifests,
    )

    assert result["ok"] is False
    assert any("required_approvals" in issue for issue in result["issues"])


def test_declared_target_must_match_actual_pr_base() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="master", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any("does not match actual PR base 'dev'" in issue for issue in result["issues"])


def test_governance_target_and_risk_values_must_be_unambiguous() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev or master", risk="R1 or R3"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any(
        "target branch None does not match actual PR base 'dev'" in issue
        for issue in result["issues"]
    )
    assert any("must name R0-R3" in issue for issue in result["issues"])


def test_governance_target_allows_a_single_template_compatible_branch_explanation() -> None:
    checker = _load_checker()
    cases = (
        (
            _pr(
                base="dev",
                head="feature/market-screen",
                body=_body(target="dev（常规变更走 dev 集成分支）", risk="R1"),
            ),
            [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
            ["src/backend/app/services/market_data.py"],
        ),
        (
            _pr(
                base="master",
                head="hotfix/master-session-expiry",
                body=_body(
                    target="master + hotfix/master-session-expiry 生产事故修复理由",
                    risk="R3",
                    hotfix_plan="INC-195: session expiry; dev PR #196 carries the forward-port fix",
                ),
            ),
            [
                _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
                _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
            ],
            ["src/backend/app/api/auth.py"],
        ),
        (
            _pr(
                base="master",
                head="release/v1.2.3",
                body=_body(
                    target="master + release/v1.2.3 promotion 理由",
                    risk="R3",
                    release_checklist="v1.2.3 changelog, regression results, and rollback point",
                ),
            ),
            [
                _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
                _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
            ],
            ["scripts/ops/release.sh"],
        ),
    )

    for pr, reviews, changed_files in cases:
        result = _evaluate(checker, pr, reviews, changed_files)

        assert result["ok"] is True


def test_common_fields_are_bound_to_governance_section_not_preamble_decoys() -> None:
    checker = _load_checker()
    body = """\
## What & Why

- **目标分支**: dev
- **风险等级**: R1
- **测试证据**: pytest preamble-decoy

## Governance declaration

- **目标分支**: master
- **风险等级**: R1
- **测试证据**: pytest scripts/ci/tests/test_check_pr_governance.py -q passed
"""
    pr = _pr(base="dev", head="feature/market-screen", body=body)

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any(
        "target branch 'master' does not match actual PR base 'dev'" in issue
        for issue in result["issues"]
    )


def test_html_comment_decoys_cannot_supply_risk_or_test_evidence() -> None:
    checker = _load_checker()
    body = """\
<!--
- **风险等级**: R3
- **测试证据**: pytest html-comment-decoy
-->

## Governance declaration

- **目标分支**: dev
- **风险等级**: R1
- **测试证据**:
"""
    pr = _pr(base="dev", head="feature/ci-cleanup", body=body)

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        [".github/workflows/ci.yml"],
    )

    assert result["risk"] == "R3"
    assert any("declares R1 but changed paths require R3" in issue for issue in result["issues"])
    assert any("R3 change requires concrete test evidence" in issue for issue in result["issues"])


def test_hidden_html_comment_declaration_does_not_satisfy_the_gate() -> None:
    checker = _load_checker()
    body = """\
<!--
## Governance declaration

- **目标分支**: dev
- **风险等级**: R1
- **测试证据**: pytest hidden-comment-decoy
-->
"""
    pr = _pr(base="dev", head="feature/market-screen", body=body)

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any(
        "missing required section: ## Governance declaration" in issue for issue in result["issues"]
    )


def test_fenced_code_declaration_does_not_satisfy_the_gate() -> None:
    checker = _load_checker()
    body = """\
```markdown
## Governance declaration

- **目标分支**: dev
- **风险等级**: R1
- **测试证据**: pytest fenced-code-decoy
```
"""
    pr = _pr(base="dev", head="feature/market-screen", body=body)

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any(
        "missing required section: ## Governance declaration" in issue for issue in result["issues"]
    )


def test_mixed_length_fences_do_not_expose_hidden_governance_declarations() -> None:
    checker = _load_checker()
    hidden_declaration = """\
## Governance declaration

- **目标分支**: dev
- **风险等级**: R1
- **测试证据**: pytest hidden-fence-decoy
"""

    for opening_fence, inner_fence in (
        ("````", "```"),
        ("`````", "````"),
        ("~~~~", "~~~"),
    ):
        body = f"{opening_fence}markdown\n{inner_fence}\n{hidden_declaration}{opening_fence}\n"
        pr = _pr(base="dev", head="feature/market-screen", body=body)

        result = _evaluate(
            checker,
            pr,
            [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
            ["src/backend/app/services/market_data.py"],
        )

        assert result["ok"] is False
        assert any(
            "missing required section: ## Governance declaration" in issue
            for issue in result["issues"]
        )


def test_visible_governance_fields_must_appear_exactly_once() -> None:
    checker = _load_checker()
    for label, value in (
        ("目标分支", "dev"),
        ("风险等级", "R1"),
        ("测试证据", "pytest scripts/ci/tests/test_check_pr_governance.py -q passed"),
    ):
        body = _body(target="dev", risk="R1") + f"- **{label}**: {value}\n"
        pr = _pr(base="dev", head="feature/market-screen", body=body)

        result = _evaluate(
            checker,
            pr,
            [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
            ["src/backend/app/services/market_data.py"],
        )

        assert result["ok"] is False
        assert any(
            f"Governance declaration field {label!r} must appear exactly once" in issue
            for issue in result["issues"]
        )


def test_feature_to_master_is_blocked_with_the_dev_routing_remedy() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="feature/market-screen",
        body=_body(target="master", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any(
        "master only accepts release/vX.Y.Z or hotfix/master-*" in issue
        for issue in result["issues"]
    )
    assert any("target dev" in issue for issue in result["issues"])


def test_unsupported_target_branch_returns_a_retargeting_diagnostic() -> None:
    checker = _load_checker()
    pr = _pr(
        base="staging",
        head="feature/market-screen",
        body=_body(target="staging", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert any("unsupported target branch: staging" in issue for issue in result["issues"])


def test_r2_auth_change_requires_matching_declaration_and_protective_record() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/auth-refresh",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [],
        ["src/backend/app/api/auth.py"],
    )

    assert result["risk"] == "R2"
    assert result["labels_can_lower_risk"] is False
    assert any("declares R1 but changed paths require R2" in issue for issue in result["issues"])
    assert any("verified authorized protective approval" in issue for issue in result["issues"])
    assert result["code_owner_review"]["verified"] is False


def test_r3_changes_cannot_be_downgraded_by_a_label() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/ci-cleanup",
        body=_body(target="dev", risk="R1"),
        labels=("risk:R0",),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        [".github/workflows/ci.yml", "config/requirements-dev.lock"],
    )

    assert result["risk"] == "R3"
    assert result["labels_can_lower_risk"] is False
    assert result["ignored_labels"] == ["risk:R0"]
    assert any("declares R1 but changed paths require R3" in issue for issue in result["issues"])


def test_hotfix_missing_incident_and_forward_port_fields_is_actionably_rejected() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="hotfix/master-session-expiry",
        body=_body(target="master", risk="R3"),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["src/backend/app/api/auth.py"],
    )

    assert result["pr_kind"] == "hotfix"
    assert result["ok"] is False
    assert any("incident or private disclosure record" in issue for issue in result["issues"])
    assert any("forward-port plan for dev" in issue for issue in result["issues"])


def test_hotfix_fields_outside_hotfix_section_cannot_satisfy_branch_contract() -> None:
    checker = _load_checker()
    body = """\
- **前移计划**: INC-195; forward-port to dev in PR #196

## Governance declaration

- **目标分支**: master
- **风险等级**: R3
- **测试证据**: pytest scripts/ci/tests/test_check_pr_governance.py -q passed

## Hotfix 前移计划
"""
    pr = _pr(base="master", head="hotfix/master-session-expiry", body=body)

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["src/backend/app/api/auth.py"],
    )

    assert any("incident or private disclosure record" in issue for issue in result["issues"])
    assert any("forward-port plan for dev" in issue for issue in result["issues"])


def test_visible_hotfix_and_release_fields_must_appear_exactly_once() -> None:
    checker = _load_checker()
    hotfix_body = (
        _body(
            target="master",
            risk="R3",
            hotfix_plan="INC-195; dev PR #196 carries the forward-port",
        )
        + "- **前移计划**: INC-195; dev PR #196 carries the forward-port\n"
    )
    release_body = (
        _body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        )
        + "- **Release 清单**: v1.2.3 changelog, regression results, and rollback point\n"
    )

    hotfix_result = _evaluate(
        checker,
        _pr(base="master", head="hotfix/master-session-expiry", body=hotfix_body),
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["src/backend/app/api/auth.py"],
    )
    release_result = _evaluate(
        checker,
        _pr(base="master", head="release/v1.2.3", body=release_body),
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert any(
        "Hotfix 前移计划 field '前移计划' must appear exactly once" in issue
        for issue in hotfix_result["issues"]
    )
    assert any(
        "Release 清单 field 'Release 清单' must appear exactly once" in issue
        for issue in release_result["issues"]
    )


def test_structured_hotfix_incident_and_dev_forward_port_evidence_passes() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="hotfix/master-session-expiry",
        body=_body(
            target="master",
            risk="R3",
            hotfix_plan="INC-195: session expiry; dev PR #196 carries the forward-port fix",
        ),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["src/backend/app/api/auth.py"],
    )

    assert result["ok"] is True


def test_hotfix_negative_or_placeholder_plan_cannot_satisfy_incident_or_forward_port() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="hotfix/master-session-expiry",
        body=_body(
            target="master",
            risk="R3",
            hotfix_plan="no incident; no forward-port; TBD",
        ),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["src/backend/app/api/auth.py"],
    )

    assert result["ok"] is False
    assert any("incident or private disclosure record" in issue for issue in result["issues"])
    assert any("forward-port plan for dev" in issue for issue in result["issues"])


def test_release_missing_checklist_is_rejected() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(target="master", risk="R3"),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert result["pr_kind"] == "release"
    assert result["ok"] is False
    assert any("Release 清单" in issue for issue in result["issues"])


def test_release_checklist_outside_release_section_cannot_satisfy_branch_contract() -> None:
    checker = _load_checker()
    body = """\
- **Release 清单**: v1.2.3 changelog, regression results, and rollback point

## Governance declaration

- **目标分支**: master
- **风险等级**: R3
- **测试证据**: pytest scripts/ci/tests/test_check_pr_governance.py -q passed

## Release 清单
"""
    pr = _pr(base="master", head="release/v1.2.3", body=body)

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert any("completed release checklist" in issue for issue in result["issues"])


def test_placeholder_high_risk_test_evidence_is_rejected() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/ci-cleanup",
        body=_body(target="dev", risk="R3", test_evidence="TBD"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        [".github/workflows/ci.yml"],
    )

    assert result["ok"] is False
    assert any("R3 change requires concrete test evidence" in issue for issue in result["issues"])


def test_placeholder_release_checklist_and_validation_are_rejected() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(target="master", risk="R3", test_evidence="none", release_checklist="TBD"),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert result["ok"] is False
    assert any("completed release checklist" in issue for issue in result["issues"])
    assert any("release validation evidence" in issue for issue in result["issues"])


def test_latest_non_author_review_state_controls_approval_floor_and_blocks_changes_requested() -> (
    None
):
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        ),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("contributor", "APPROVED", "2026-08-24T00:00:00Z"),
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-a", "CHANGES_REQUESTED", "2026-08-24T00:03:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert result["effective_approvals"] == ["maintainer-b"]
    assert result["changes_requested_by"] == ["maintainer-a"]
    assert any(
        "latest review from maintainer-a is CHANGES_REQUESTED" in issue
        for issue in result["issues"]
    )
    assert any("requires 2 non-author approvals but has 1" in issue for issue in result["issues"])


def test_nonterminal_review_after_changes_requested_does_not_clear_the_block() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        ),
    )

    for nonterminal_state in ("COMMENTED", "PENDING"):
        result = _evaluate(
            checker,
            pr,
            [
                _review("maintainer-a", "CHANGES_REQUESTED", "2026-08-24T00:01:00Z"),
                _review("maintainer-a", nonterminal_state, "2026-08-24T00:01:00Z"),
                _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
                _review("maintainer-c", "APPROVED", "2026-08-24T00:03:00Z"),
            ],
            ["scripts/ops/release.sh"],
        )

        assert result["changes_requested_by"] == ["maintainer-a"]
        assert result["effective_approvals"] == ["maintainer-b", "maintainer-c"]
        assert any(
            "latest review from maintainer-a is CHANGES_REQUESTED" in issue
            for issue in result["issues"]
        )


def test_approved_review_after_changes_requested_clears_the_block_by_time_and_input_order() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        ),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "CHANGES_REQUESTED", "2026-08-24T00:01:00Z"),
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:02:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert result["ok"] is True
    assert result["changes_requested_by"] == []
    assert result["effective_approvals"] == ["maintainer-a", "maintainer-b"]


def test_dismissed_review_after_changes_requested_clears_the_block_without_counting_as_approval() -> (
    None
):
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        ),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "CHANGES_REQUESTED", "2026-08-24T00:01:00Z"),
            _review("maintainer-a", "DISMISSED", "2026-08-24T00:02:00Z"),
            _review("maintainer-b", "APPROVED", "2026-08-24T00:03:00Z"),
            _review("maintainer-c", "APPROVED", "2026-08-24T00:04:00Z"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert result["ok"] is True
    assert result["changes_requested_by"] == []
    assert result["effective_approvals"] == ["maintainer-b", "maintainer-c"]


def test_comment_after_approval_does_not_remove_the_approval() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer", "APPROVED", "2026-08-24T00:01:00Z"),
            _review("maintainer", "COMMENTED", "2026-08-24T00:02:00Z"),
        ],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is True
    assert result["effective_approvals"] == ["maintainer"]


def test_owner_approval_counts_toward_the_dev_floor() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z", "OWNER")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is True
    assert result["effective_approvals"] == ["maintainer"]


def test_stale_approval_does_not_survive_a_pull_request_head_change() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )
    pr["head"] = {"ref": "feature/market-screen", "sha": "d" * 40}

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z", commit_id="c" * 40)],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == []
    assert result["stale_approvals"] == ["maintainer"]
    assert any("not tied to the current PR head" in issue for issue in result["issues"])


def test_current_head_approval_replaces_an_older_approval_from_the_same_reviewer() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )
    pr["head"] = {"ref": "feature/market-screen", "sha": "d" * 40}

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer", "APPROVED", "2026-08-24T00:01:00Z", commit_id="c" * 40),
            _review("maintainer", "APPROVED", "2026-08-24T00:02:00Z", commit_id="d" * 40),
        ],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is True
    assert result["effective_approvals"] == ["maintainer"]
    assert result["stale_approvals"] == []


def test_missing_or_malformed_approval_commit_id_fails_closed() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    for commit_id in (None, "not-a-git-sha", 195):
        result = _evaluate(
            checker,
            pr,
            [
                _review(
                    "maintainer",
                    "APPROVED",
                    "2026-08-24T00:01:00Z",
                    commit_id=commit_id,
                )
            ],
            ["src/backend/app/services/market_data.py"],
        )

        assert result["ok"] is False
        assert result["effective_approvals"] == []
        assert result["stale_approvals"] == ["maintainer"]
        assert any("not tied to the current PR head" in issue for issue in result["issues"])


def test_repository_authorization_is_owner_only_while_d2_has_no_second_maintainer() -> None:
    checker = _load_checker()

    authorization = checker.load_reviewer_authorization(REVIEWER_AUTHORIZATION_PATH)

    assert authorization == {"cloudquant": frozenset({"OWNER"})}


def test_malformed_reviewer_authorization_fails_closed_before_any_review_counts() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )
    authorization = _authorization()
    reviewers = authorization["reviewers"]
    assert isinstance(reviewers, list)
    reviewers[0]["author_associations"] = ["OWNER", "OWNER"]

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")],
        ["src/backend/app/services/market_data.py"],
        reviewer_authorization=authorization,
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == []
    assert any(
        "reviewer authorization configuration is invalid" in issue for issue in result["issues"]
    )


def test_unauthorized_collaborator_approval_does_not_count() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review(
                "unapproved-collaborator",
                "APPROVED",
                "2026-08-24T00:01:00Z",
                "COLLABORATOR",
            )
        ],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == []
    assert result["unverified_reviews"] == ["unapproved-collaborator"]


def test_d2_approved_collaborator_can_complete_the_master_two_review_floor() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        ),
    )
    authorization = _authorization()
    reviewers = authorization["reviewers"]
    assert isinstance(reviewers, list)
    reviewers.append(
        {
            "login": "approved-collaborator",
            "author_associations": ["COLLABORATOR"],
            "evidence": {
                "gate": "D2",
                "status": "approved",
                "reference": ".github/governance/decisions/iteration-195.md",
            },
        }
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("maintainer-a", "APPROVED", "2026-08-24T00:01:00Z", "OWNER"),
            _review(
                "approved-collaborator",
                "APPROVED",
                "2026-08-24T00:02:00Z",
                "COLLABORATOR",
            ),
        ],
        ["scripts/ops/release.sh"],
        reviewer_authorization=authorization,
    )

    assert result["ok"] is True
    assert result["effective_approvals"] == ["approved-collaborator", "maintainer-a"]


def test_unverified_none_approval_does_not_count_toward_the_floor() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("random-reviewer", "APPROVED", "2026-08-24T00:01:00Z", "NONE")],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == []
    assert any("authorization not verified" in issue for issue in result["issues"])
    assert any("request verified maintainer review" in issue for issue in result["issues"])


def test_unverified_review_is_metadata_only_when_verified_owner_floor_is_already_met() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("repository-owner", "APPROVED", "2026-08-24T00:01:00Z", "OWNER"),
            _review("member", "APPROVED", "2026-08-24T00:02:00Z", "MEMBER"),
        ],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is True
    assert result["effective_approvals"] == ["repository-owner"]
    assert result["unverified_reviews"] == ["member"]
    assert not any("authorization not verified" in issue for issue in result["issues"])


def test_author_owner_approval_does_not_count_toward_the_floor() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
        author="repository-owner",
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("repository-owner", "APPROVED", "2026-08-24T00:01:00Z", "OWNER"),
            _review("random-reviewer", "APPROVED", "2026-08-24T00:02:00Z", "MEMBER"),
        ],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == []


def test_missing_review_authorization_fails_closed() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/market-screen",
        body=_body(target="dev", risk="R1"),
    )

    result = _evaluate(
        checker,
        pr,
        [_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z", None)],
        ["src/backend/app/services/market_data.py"],
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == []
    assert any("authorization not verified" in issue for issue in result["issues"])


def test_master_floor_stays_red_without_two_verified_owner_approvals() -> None:
    checker = _load_checker()
    pr = _pr(
        base="master",
        head="release/v1.2.3",
        body=_body(
            target="master",
            risk="R3",
            release_checklist="v1.2.3 changelog, regression results, and rollback point",
        ),
    )

    result = _evaluate(
        checker,
        pr,
        [
            _review("repository-owner", "APPROVED", "2026-08-24T00:01:00Z", "OWNER"),
            _review("member", "APPROVED", "2026-08-24T00:02:00Z", "MEMBER"),
        ],
        ["scripts/ops/release.sh"],
    )

    assert result["ok"] is False
    assert result["effective_approvals"] == ["repository-owner"]
    assert any("requires 2 non-author approvals but has 1" in issue for issue in result["issues"])


def test_requested_reviewer_does_not_satisfy_r2_protective_review_requirement() -> None:
    checker = _load_checker()
    pr = _pr(
        base="dev",
        head="feature/auth-refresh",
        body=_body(target="dev", risk="R2"),
        requested_reviewers=("unverified-request",),
    )

    result = _evaluate(
        checker,
        pr,
        [],
        ["src/backend/app/api/auth.py"],
    )

    assert result["ok"] is False
    assert result["protective_reviewers"] == []
    assert any("verified authorized protective approval" in issue for issue in result["issues"])


def test_cli_uses_local_json_inputs_and_returns_a_machine_readable_result(
    tmp_path: Path,
) -> None:
    pr_path = tmp_path / "pr.json"
    reviews_path = tmp_path / "reviews.json"
    files_path = tmp_path / "files.json"
    pr_path.write_text(
        json.dumps(
            _pr(
                base="dev",
                head="feature/market-screen",
                body=_body(target="dev", risk="R1"),
            )
        ),
        encoding="utf-8",
    )
    reviews_path.write_text(
        json.dumps([_review("cloudQuant", "APPROVED", "2026-08-24T00:01:00Z")]),
        encoding="utf-8",
    )
    files_path.write_text(
        json.dumps([{"filename": "src/backend/app/services/market_data.py"}]),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(CHECKER_PATH),
            "--pr",
            str(pr_path),
            "--reviews",
            str(reviews_path),
            "--changed-files",
            str(files_path),
            "--risk-map",
            str(RISK_MAP_PATH),
            "--manifest-dir",
            str(MANIFEST_DIR),
            "--reviewer-authorization",
            str(REVIEWER_AUTHORIZATION_PATH),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["risk"] == "R1"
