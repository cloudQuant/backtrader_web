"""Local fixtures for the trusted-base Iteration 195 Governance Gate."""

from __future__ import annotations

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
) -> dict[str, object]:
    return {
        "number": 195,
        "base": {"ref": base},
        "head": {"ref": head},
        "user": {"login": author},
        "body": body,
        "labels": [{"name": label} for label in labels],
        "requested_reviewers": [{"login": login} for login in requested_reviewers],
    }


def _review(login: str, state: str, submitted_at: str) -> dict[str, object]:
    return {
        "user": {"login": login},
        "state": state,
        "submitted_at": submitted_at,
    }


def _evaluate(
    checker: ModuleType,
    pr: dict[str, object],
    reviews: list[dict[str, object]],
    changed_files: list[str],
) -> dict[str, object]:
    return checker.evaluate_pr_governance(
        pr,
        reviews,
        changed_files,
        risk_map=_risk_map(),
        manifests=_manifests(checker),
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
    assert any(
        "protective reviewer or requested-reviewer record" in issue for issue in result["issues"]
    )
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


def test_cli_uses_local_json_inputs_and_returns_a_machine_readable_result(tmp_path: Path) -> None:
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
        json.dumps([_review("maintainer", "APPROVED", "2026-08-24T00:01:00Z")]),
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
