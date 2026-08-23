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


def _governance_gate(workflow: str) -> dict[str, object]:
    parsed = _workflow_mapping(workflow)
    jobs = parsed.get("jobs")
    assert isinstance(jobs, dict), "workflow jobs must be a mapping"
    gate = jobs.get("governance-gate")
    assert isinstance(gate, dict), "workflow must declare governance-gate"
    return gate


def _all_uses(node: object) -> list[str]:
    if isinstance(node, dict):
        values = [str(node["uses"])] if "uses" in node else []
        for value in node.values():
            values.extend(_all_uses(value))
        return values
    if isinstance(node, list):
        return [use for value in node for use in _all_uses(value)]
    return []


def _run_steps(gate: dict[str, object]) -> list[tuple[str | None, str]]:
    steps = gate.get("steps")
    assert isinstance(steps, list), "governance-gate steps must be a list"
    runs: list[tuple[str | None, str]] = []
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("run"), str):
            name = step.get("name")
            runs.append((name if isinstance(name, str) else None, step["run"]))
    return runs


def _normalized_command(script: str) -> str:
    return " ".join(re.sub(r"\\[ \t]*\n[ \t]*", " ", script).split())


def _uses_issues(workflow: str) -> list[str]:
    parsed = _workflow_mapping(workflow)
    gate = _governance_gate(workflow)
    expected = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
    issues: list[str] = []
    if _all_uses(parsed) != [expected]:
        issues.append("workflow must use only the pinned trusted checkout action")
    for key in ("container", "services"):
        if key in gate:
            issues.append(f"governance gate must not configure {key}")
    return issues


def _governance_run_issues(workflow: str) -> list[str]:
    gate = _governance_gate(workflow)
    run_steps = _run_steps(gate)
    issues: list[str] = []
    steps = gate.get("steps")
    assert isinstance(steps, list)
    if "if" in gate or any(isinstance(step, dict) and "if" in step for step in steps):
        issues.append("governance gate and its steps must not conditionally skip evaluation")
    expected_names = {
        "Read pull request metadata",
        "Evaluate trusted governance policy",
    }
    names = [name for name, _ in run_steps]
    if len(names) != len(expected_names) or set(names) != expected_names:
        issues.append("gate must contain only the two allowlisted named run steps")
    runs = {name: script for name, script in run_steps if name is not None}

    metadata = runs.get("Read pull request metadata")
    if metadata is None:
        issues.append("missing metadata read step")
    else:
        actual_lines = [line.strip() for line in metadata.splitlines() if line.strip()]
        expected_lines = [
            'mkdir -p "$GOVERNANCE_TMP"',
            'gh api --method GET "repos/$PR_REPOSITORY/pulls/$PR_NUMBER" > "$GOVERNANCE_TMP/pr.json"',
            'gh api --method GET --paginate --slurp "repos/$PR_REPOSITORY/pulls/$PR_NUMBER/reviews" > "$GOVERNANCE_TMP/reviews.json"',
            'gh api --method GET --paginate --slurp "repos/$PR_REPOSITORY/pulls/$PR_NUMBER/files?per_page=100" > "$GOVERNANCE_TMP/files.json"',
        ]
        if actual_lines != expected_lines:
            issues.append(
                "metadata step must contain only the allowlisted mkdir and three GET calls"
            )

    evaluate = runs.get("Evaluate trusted governance policy")
    expected_evaluate = (
        'python scripts/ci/check_pr_governance.py --pr "$GOVERNANCE_TMP/pr.json" '
        '--reviews "$GOVERNANCE_TMP/reviews.json" --changed-files "$GOVERNANCE_TMP/files.json" '
        "--risk-map .github/governance/risk-paths.json --manifest-dir .github/governance/rulesets"
    )
    if evaluate is None or _normalized_command(evaluate) != expected_evaluate:
        issues.append(
            "evaluation step must contain only the allowlisted governance checker command"
        )

    prohibited = re.compile(
        r"`|\$\(|\b(?:curl|wget|eval|source|bash|sh)\b|\bpython\s+-c\b|"
        r"\bgit\s+(?:fetch|checkout|clone)\b|\bgh\s+(?!api\b)|"
        r"github\.event\.pull_request\.(?:head|merge)|refs/pull/",
        re.IGNORECASE,
    )
    if any(prohibited.search(script) for _, script in run_steps):
        issues.append("run steps contain a prohibited shell construct")
    return issues


def _checkout_issues(workflow: str) -> list[str]:
    gate = _governance_gate(workflow)
    steps = gate.get("steps")
    assert isinstance(steps, list)
    checkout_steps = [
        step
        for step in steps
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    issues = _uses_issues(workflow)
    if len(checkout_steps) != 1:
        return issues + ["exactly one checkout step is required"]
    checkout_with = checkout_steps[0].get("with")
    if not isinstance(checkout_with, dict):
        return issues + ["checkout must include a with mapping"]
    if checkout_with.get("ref") != "${{ github.event.pull_request.base.sha }}":
        issues.append("checkout must use only the pull request base SHA")
    if checkout_with.get("persist-credentials") != "false":
        issues.append("checkout must disable persisted credentials")
    return issues


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
        assert set(self._governance_event()) == {"types"}
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
        assert all(not isinstance(step, dict) or "if" not in step for step in gate.get("steps", []))
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
        assert _checkout_issues(workflow) == []

    def test_governance_has_exactly_one_pinned_action_and_no_container_or_services(self) -> None:
        workflow = _read(PR_GOVERNANCE)
        parsed = _workflow_mapping(workflow)
        gate = _governance_gate(workflow)

        assert _all_uses(parsed) == ["actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"]
        assert "container" not in gate
        assert "services" not in gate

        extra_action = workflow.replace(
            "      - name: Read pull request metadata\n",
            "      - uses: actions/setup-python@11bd71901bbe5b1630ceea73d27597364c9af683\n"
            "      - name: Read pull request metadata\n",
            1,
        )
        containerized = workflow.replace(
            "    runs-on: ubuntu-latest\n",
            "    runs-on: ubuntu-latest\n    container: alpine:3.20\n",
            1,
        )
        serviced = workflow.replace(
            "    runs-on: ubuntu-latest\n",
            "    runs-on: ubuntu-latest\n    services: {cache: {image: redis:7}}\n",
            1,
        )

        assert _uses_issues(workflow) == []
        assert _uses_issues(extra_action)
        assert _uses_issues(containerized)
        assert _uses_issues(serviced)

    def test_governance_shell_steps_match_the_metadata_and_evaluator_allowlists(self) -> None:
        workflow = _read(PR_GOVERNANCE)
        conditional = workflow.replace(
            "      - name: Read pull request metadata\n",
            "      - if: github.event.action != 'opened'\n"
            "        name: Read pull request metadata\n",
            1,
        )

        assert _governance_run_issues(workflow) == []
        assert _governance_run_issues(conditional)

    def test_governance_rejects_metadata_api_write_or_pr_comment_mutations(self) -> None:
        workflow = _read(PR_GOVERNANCE)
        api_write = workflow.replace(
            'gh api --method GET "repos/$PR_REPOSITORY/pulls/$PR_NUMBER"',
            'gh api -X POST "repos/$PR_REPOSITORY/pulls/$PR_NUMBER"',
            1,
        )
        pr_comment = workflow.replace(
            "          python scripts/ci/check_pr_governance.py \\\n",
            '          gh pr comment "$PR_NUMBER" --body blocked\n'
            "          python scripts/ci/check_pr_governance.py \\\n",
            1,
        )
        pr_checkout = workflow.replace(
            '          mkdir -p "$GOVERNANCE_TMP"\n',
            '          mkdir -p "$GOVERNANCE_TMP"\n          gh pr checkout "$PR_NUMBER"\n',
            1,
        )

        assert _governance_run_issues(api_write)
        assert _governance_run_issues(pr_comment)
        assert _governance_run_issues(pr_checkout)

    def test_governance_rejects_fetching_pr_head_or_checkout_head_mutations(self) -> None:
        workflow = _read(PR_GOVERNANCE)
        fetch_head = workflow.replace(
            '          mkdir -p "$GOVERNANCE_TMP"\n',
            '          mkdir -p "$GOVERNANCE_TMP"\n'
            '          git fetch origin "${{ github.event.pull_request.head.sha }}"\n',
            1,
        )
        checkout_head = workflow.replace(
            "github.event.pull_request.base.sha", "github.event.pull_request.head.sha", 1
        )
        merge_ref = workflow.replace(
            '          mkdir -p "$GOVERNANCE_TMP"\n',
            '          mkdir -p "$GOVERNANCE_TMP"\n          git status refs/pull/195/merge\n',
            1,
        )

        assert _governance_run_issues(fetch_head)
        assert _checkout_issues(checkout_head)
        assert _governance_run_issues(merge_ref)

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
