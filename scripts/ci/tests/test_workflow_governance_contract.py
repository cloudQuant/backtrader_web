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
    EXPECTED_EVENTS = {
        "opened",
        "synchronize",
        "reopened",
        "edited",
        "ready_for_review",
        "labeled",
        "unlabeled",
    }

    def _governance_event(self) -> dict[str, object]:
        workflow = _workflow_mapping(_read(PR_GOVERNANCE))
        events = workflow.get("on")
        assert isinstance(events, dict)
        event = events.get("pull_request_target")
        assert isinstance(event, dict)
        return event

    def test_governance_uses_only_trusted_pull_request_target_events(self) -> None:
        workflow = _read(PR_GOVERNANCE)

        assert _event_issues(workflow, {"pull_request_target"}) == []
        assert set(self._governance_event().get("types", [])) == self.EXPECTED_EVENTS
        assert "pull_request_review:" not in workflow

    def test_governance_rejects_a_pull_request_review_trigger(self) -> None:
        workflow = _read(PR_GOVERNANCE).replace(
            "  pull_request_target:\n", "  pull_request_review:\n", 1
        )

        assert _event_issues(workflow, {"pull_request_target"})

    def test_governance_rejects_job_level_write_permissions(self) -> None:
        workflow = _read(PR_GOVERNANCE).replace(
            "  governance-gate:\n",
            "  governance-gate:\n    permissions: {contents: write}\n",
            1,
        )

        assert _permission_issues(workflow)

    def test_governance_workflow_is_read_only_and_has_an_always_running_gate(self) -> None:
        workflow = _read(PR_GOVERNANCE)
        parsed = _workflow_mapping(workflow)
        jobs = parsed.get("jobs")

        assert parsed.get("name") == "PR Governance"
        assert _top_level_permissions(workflow) == {
            "contents": "read",
            "pull-requests": "read",
        }
        assert _permission_issues(workflow) == []
        assert isinstance(jobs, dict)
        assert set(jobs) == {"governance-gate"}
        gate = jobs["governance-gate"]
        assert isinstance(gate, dict)
        assert gate.get("name") == "Governance Gate"
        assert "if" not in gate
        assert "paths" not in self._governance_event()
        assert "paths-ignore" not in self._governance_event()

    def test_governance_checkout_is_pinned_to_the_trusted_base_sha_without_credentials(
        self,
    ) -> None:
        workflow = _read(PR_GOVERNANCE)
        parsed = _workflow_mapping(workflow)
        jobs = parsed["jobs"]
        assert isinstance(jobs, dict)
        gate = jobs["governance-gate"]
        assert isinstance(gate, dict)
        steps = gate.get("steps")
        assert isinstance(steps, list)
        checkout_steps = [
            step
            for step in steps
            if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")
        ]

        assert len(checkout_steps) == 1
        checkout = checkout_steps[0]
        assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", str(checkout["uses"]).split()[0])
        checkout_with = checkout.get("with")
        assert isinstance(checkout_with, dict)
        assert checkout_with.get("ref") == "${{ github.event.pull_request.base.sha }}"
        assert checkout_with.get("persist-credentials") == "false"
        assert "github.event.pull_request.head" not in workflow

    def test_governance_uses_only_read_only_metadata_requests_and_standard_library_checker(
        self,
    ) -> None:
        workflow = _read(PR_GOVERNANCE).lower()

        for forbidden in (
            "pull_request_review:",
            "github.event.pull_request.head",
            "secrets.",
            "pip install",
            "npm install",
            "npm ci",
            "createcomment",
            "addlabels",
            "removelabel",
            "github-script",
            "gh api --method post",
            "gh api --method patch",
            "gh api --method put",
            "gh api --method delete",
        ):
            assert forbidden not in workflow

        assert workflow.count("gh api --method get") == 3
        assert "check_pr_governance.py" in workflow
