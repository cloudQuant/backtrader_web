"""Iteration 195 Task 2 workflow-security contract tests.

These tests parse workflow YAML structurally before enforcing the event,
permission, side-effect, and action-pinning boundaries. They do not evaluate
untrusted workflow content.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PR_CHECK = WORKFLOWS / "pr-check.yml"
PR_GOVERNANCE = WORKFLOWS / "pr-governance.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _uses_lines(workflow: str) -> list[str]:
    return [line.strip() for line in workflow.splitlines() if "uses:" in line]


def _workflow_mapping(workflow: str) -> dict[str, object]:
    """Load workflow YAML without coercing GitHub's ``on`` key to a boolean."""
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict), "workflow must be a YAML mapping"
    return parsed


def _top_level_permissions(workflow: str) -> dict[str, object]:
    permissions = _workflow_mapping(workflow).get("permissions")
    assert isinstance(permissions, dict), "workflow must declare permissions as a mapping"
    return permissions


def _event_issues(workflow: str, expected: set[str]) -> list[str]:
    events = _workflow_mapping(workflow).get("on")
    if not isinstance(events, dict):
        return ["on must be a mapping of workflow events"]

    actual = {str(event) for event in events}
    if actual != expected:
        return [f"expected events {sorted(expected)!r}, got {sorted(actual)!r}"]
    return []


def _permission_issues(workflow: str) -> list[str]:
    """Return every write-capable permission at any YAML nesting level."""
    issues: list[str] = []

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if key_text == "permissions":
                    issues.extend(_permission_declaration_issues(value, child_path))
                visit(value, child_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    visit(_workflow_mapping(workflow), "")
    return issues


def _permission_declaration_issues(declaration: object, path: str) -> list[str]:
    if isinstance(declaration, dict):
        return [
            f"{path}.{scope} grants {level}"
            for scope, level in declaration.items()
            if str(level).strip().lower() in {"write", "write-all"}
        ]
    if str(declaration).strip().lower() == "write-all":
        return [f"{path} grants write-all"]
    return []


class TestPrCheckWorkflowContract:
    def test_pr_check_rejects_job_level_write_all_permissions(self) -> None:
        workflow = _read(PR_CHECK).replace(
            "  pr-validation:\n", "  pr-validation:\n    permissions: write-all\n", 1
        )

        assert _permission_issues(workflow)

    def test_pr_code_checks_use_only_the_unprivileged_pr_event(self) -> None:
        workflow = _read(PR_CHECK)

        assert _event_issues(workflow, {"pull_request"}) == []

    def test_pr_check_rejects_additional_trigger(self) -> None:
        workflow = _read(PR_CHECK).replace(
            "    types: [opened, synchronize, reopened]\n",
            "    types: [opened, synchronize, reopened]\n  push:\n",
            1,
        )

        assert _event_issues(workflow, {"pull_request"})

    def test_pr_check_permissions_are_read_only(self) -> None:
        workflow = _read(PR_CHECK)

        assert _top_level_permissions(workflow) == {
            "contents": "read",
            "pull-requests": "read",
        }
        assert _permission_issues(workflow) == []

    def test_pr_check_has_no_automatic_merge_qualification_side_effects(self) -> None:
        workflow = _read(PR_CHECK).lower()

        for forbidden in (
            "merge-ready",
            "github-script",
            "createcomment",
            "addlabels",
            "removelabel",
            "issues.createcomment",
            "issues.addlabels",
            "issues.removelabel",
        ):
            assert forbidden not in workflow

    def test_pr_check_actions_are_sha_pinned_with_version_comments(self) -> None:
        workflow = _read(PR_CHECK)
        uses_lines = _uses_lines(workflow)

        assert uses_lines, "PR code checks must explicitly pin their checkout action"
        for line in uses_lines:
            assert re.search(r"uses:\s+[^\s@]+@[0-9a-f]{40}\s+#\s+v\d", line), line


class TestPrGovernanceWorkflowContract:
    def test_governance_uses_only_pull_request_target(self) -> None:
        assert _event_issues(_read(PR_GOVERNANCE), {"pull_request_target"}) == []

    def test_governance_rejects_additional_trigger(self) -> None:
        workflow = _read(PR_GOVERNANCE).replace(
            "    types: [opened, synchronize, reopened]\n",
            "    types: [opened, synchronize, reopened]\n  issue_comment:\n",
            1,
        )

        assert _event_issues(workflow, {"pull_request_target"})

    def test_governance_rejects_job_level_flow_mapping_write_permission(self) -> None:
        workflow = _read(PR_GOVERNANCE).replace(
            "  governance-bootstrap:\n",
            "  governance-bootstrap:\n    permissions: {contents: write}\n",
            1,
        )

        assert _permission_issues(workflow)

    def test_governance_workflow_is_a_read_only_metadata_bootstrap(self) -> None:
        workflow = _read(PR_GOVERNANCE)

        assert re.search(r"^\s{2}pull_request_target:\s*$", workflow, re.MULTILINE)
        assert _top_level_permissions(workflow) == {
            "contents": "read",
            "pull-requests": "read",
        }
        assert _permission_issues(workflow) == []

    def test_governance_workflow_does_not_touch_untrusted_pr_code_or_write_state(self) -> None:
        workflow = _read(PR_GOVERNANCE).lower()

        for forbidden in (
            "checkout",
            "github.event.pull_request.head",
            "secrets.",
            "pip install",
            "npm install",
            "npm ci",
            "createcomment",
            "addlabels",
            "removelabel",
            "github-script",
            "check_pr_governance.py",
        ):
            assert forbidden not in workflow

        assert (
            'run: echo "read-only governance bootstrap; awaiting default-branch promotion."'
            in workflow
        )
