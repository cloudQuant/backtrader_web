"""Iteration 195 Task 2 workflow-security contract tests.

These tests intentionally inspect workflow text with only the standard
library.  They guard the event, permission, side-effect, and action-pinning
boundaries without evaluating untrusted workflow content.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PR_CHECK = WORKFLOWS / "pr-check.yml"
PR_GOVERNANCE = WORKFLOWS / "pr-governance.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _uses_lines(workflow: str) -> list[str]:
    return [line.strip() for line in workflow.splitlines() if "uses:" in line]


class TestPrCheckWorkflowContract:
    def test_pr_code_checks_use_only_the_unprivileged_pr_event(self) -> None:
        workflow = _read(PR_CHECK)

        assert re.search(r"^\s{2}pull_request:\s*$", workflow, re.MULTILINE)
        assert "pull_request_target" not in workflow
        assert "workflow_dispatch" not in workflow

    def test_pr_check_permissions_are_read_only(self) -> None:
        workflow = _read(PR_CHECK)

        assert re.search(r"^permissions:\n\s+contents: read\n\s+pull-requests: read\s*$", workflow, re.MULTILINE)
        assert not re.search(r"^\s*[\w-]+:\s*write\s*$", workflow, re.MULTILINE)

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
    def test_governance_workflow_is_a_read_only_metadata_bootstrap(self) -> None:
        workflow = _read(PR_GOVERNANCE)

        assert re.search(r"^\s{2}pull_request_target:\s*$", workflow, re.MULTILINE)
        assert re.search(r"^permissions:\n\s+contents: read\n\s+pull-requests: read\s*$", workflow, re.MULTILINE)
        assert not re.search(r"^\s*[\w-]+:\s*write\s*$", workflow, re.MULTILINE)

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
