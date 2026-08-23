#!/usr/bin/env python3
"""Iteration 195 Task 1 — PR template governance contract tests.

Validates, via fixtures only (no GitHub API):

1. A *normal* PR body carrying a complete ``## Governance declaration``
   section is accepted.
2. An R2 PR body is accepted when the declaration names the elevated risk,
   and rejected when the risk/test-evidence fields are placeholders.
3. A ``master`` hotfix body is rejected when the hotfix backport plan is
   missing, accepted when present.
4. A ``master`` release body is rejected when the release checklist is
   missing, accepted when present.
5. The pre-existing iteration 175/179 behaviour is preserved: an i18n
   manifest is still mandatory when locale files change, and the non-PR
   empty-environment exit semantics are unchanged.

Actual base/head branch and review-state validation belongs to Task 4
(``scripts/ci/check_pr_governance.py``); these tests deliberately do not
depend on GitHub event payloads.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "scripts" / "ci" / "check_pr_template.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_pr_template", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _run_cli(env_extra: dict[str, str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    return proc.returncode, proc.stdout + proc.stderr


GOV_COMPLETE = """\
## Governance declaration

- 目标分支: dev（常规变更走 dev 集成分支）
- 风险等级: R2（命中 src/bt_api_py/** 路径，不可下调）
- 测试证据: pytest src/backend/tests/test_x.py 通过；手工冒烟记录见下方 Test Plan
"""

GOV_MISSING_FIELDS = """\
## Governance declaration

- 目标分支: <fill in>
- 风险等级:
"""

HOTFIX_COMPLETE = """\
## Governance declaration

- 目标分支: master（hotfix/master-123 生产事故修复）
- 风险等级: R3（生产 hotfix）
- 测试证据: 回归复现脚本 + 单元测试输出已附
- 前移计划: 已创建等价修复 issue #456；dev 分支等价 PR #789 或"不受影响"结论见正文
"""

HOTFIX_NO_BACKPORT = """\
## Governance declaration

- 目标分支: master（hotfix/master-9 紧急修复）
- 风险等级: R3
- 测试证据: 最小复现已附
"""

RELEASE_COMPLETE = """\
## Governance declaration

- 目标分支: master（release/v1.3.0 promotion）
- 风险等级: R3（发布晋升）
- 测试证据: 完整 CI + e2e 汇总链接见下
- Release 清单: docs/releases/v1.3.0-checklist.md（版本、变更日志、回滚点齐备）
"""

RELEASE_NO_CHECKLIST = """\
## Governance declaration

- 目标分支: master（release/v1.4.0 promotion）
- 风险等级: R3
- 测试证据: CI 绿色截图
"""


class TestGovernanceDeclarationNormalPr:
    def test_complete_normal_declaration_accepted(self) -> None:
        assert checker.governance_declaration_issues(GOV_COMPLETE, "normal") == []

    def test_missing_risk_and_placeholder_rejected(self) -> None:
        issues = checker.governance_declaration_issues(GOV_MISSING_FIELDS, "normal")
        assert any("风险等级" in i for i in issues)
        assert any("目标分支" in i for i in issues)
        assert any("测试证据" in i for i in issues)

    def test_absent_section_rejected(self) -> None:
        issues = checker.governance_declaration_issues(
            "## What & Why\n\nsome change\n", "normal"
        )
        assert any("Governance declaration" in i for i in issues)

    def test_html_comment_placeholder_is_rejected(self) -> None:
        body = """\
## Governance declaration

- 目标分支: <!-- dev，或 master + release/hotfix 理由 -->
- 风险等级: <!-- R0 / R1 / R2 / R3 -->
- 测试证据: <!-- 命令与结果 -->
"""
        issues = checker.governance_declaration_issues(body, "normal")
        assert any("目标分支" in issue for issue in issues)
        assert any("风险等级" in issue for issue in issues)
        assert any("测试证据" in issue for issue in issues)


class TestGovernanceR2Pr:
    def test_r2_named_in_declaration_accepted(self) -> None:
        body = GOV_COMPLETE.replace("R2", "R2", 1)
        assert checker.governance_declaration_issues(body, "normal") == []

    def test_label_claiming_lower_risk_does_not_satisfy_placeholder(self) -> None:
        # A label cannot substitute for the filled-in declaration fields.
        body = GOV_MISSING_FIELDS + "\nLabels: risk-low\n"
        issues = checker.governance_declaration_issues(body, "normal")
        assert issues, "placeholder declaration must be rejected even with a low-risk label"


class TestMasterHotfixContract:
    def test_hotfix_with_backport_accepted(self) -> None:
        assert checker.governance_declaration_issues(HOTFIX_COMPLETE, "hotfix") == []

    def test_hotfix_without_backport_rejected(self) -> None:
        issues = checker.governance_declaration_issues(HOTFIX_NO_BACKPORT, "hotfix")
        assert any("前移" in i for i in issues)


class TestMasterReleaseContract:
    def test_release_with_checklist_accepted(self) -> None:
        assert checker.governance_declaration_issues(RELEASE_COMPLETE, "release") == []

    def test_release_without_checklist_rejected(self) -> None:
        issues = checker.governance_declaration_issues(RELEASE_NO_CHECKLIST, "release")
        assert any("Release 清单" in i for i in issues)


class TestI18nRegression:
    def test_locale_change_still_requires_manifest(self) -> None:
        body = "## Governance declaration\n\n- 目标分支: dev\n- 风险等级: R1\n- 测试证据: ok\n"
        code, _ = _run_cli({"PR_BODY": body, "CHANGED_FILES": "src/frontend/src/i18n/locales/zh-CN.ts"})
        assert code == 1, "locale change without i18n manifest must still fail"

    def test_locale_change_with_manifest_passes(self) -> None:
        body = (
            "## Governance declaration\n\n- 目标分支: dev\n- 风险等级: R1\n- 测试证据: ok\n\n"
            "## i18n 变更清单 (i18n change manifest, 175 §4.7)\n\n"
            "- **zh-CN key 数量 (count)**: 12\n"
            "- **en-US key 数量 (count)**: 12\n"
            "- **本 PR 新增 key (added)**:\n  - nav.newItem\n"
            "- **本 PR 删除 key (removed)**:\n  - 无 / none\n"
        )
        code, _ = _run_cli({"PR_BODY": body, "CHANGED_FILES": "src/frontend/src/i18n/locales/en-US.ts"})
        assert code == 0

    def test_non_pr_environment_exit_unchanged(self) -> None:
        # Empty environment keeps its historical "skip" semantics (exit 2),
        # including when governance checking is not requested.
        env = {k: v for k, v in os.environ.items() if k not in ("PR_BODY", "CHANGED_FILES")}
        proc = subprocess.run(
            [sys.executable, str(CHECKER_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert proc.returncode == 2


class TestCliGovernanceKindEnv:
    def test_governance_kind_env_enables_check(self) -> None:
        code, out = _run_cli({"PR_BODY": HOTFIX_NO_BACKPORT, "GOVERNANCE_PR_KIND": "hotfix"})
        assert code == 1
        assert "前移" in out

    def test_governance_kind_env_passes_complete_body(self) -> None:
        code, _ = _run_cli(
            {
                "PR_BODY": RELEASE_COMPLETE,
                "GOVERNANCE_PR_KIND": "release",
                "CHANGED_FILES": "",
            }
        )
        assert code == 0

    def test_invalid_governance_on_non_locale_change_reports_contract_error(self) -> None:
        code, out = _run_cli(
            {
                "PR_BODY": GOV_MISSING_FIELDS,
                "GOVERNANCE_PR_KIND": "normal",
                "CHANGED_FILES": "README.md",
            }
        )
        assert code == 1
        assert "governance field" in out
        assert "Traceback" not in out
