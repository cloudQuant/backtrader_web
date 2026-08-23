"""Task 5 static contracts for release, preview, and nightly evidence workflows."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DOCKER_PUBLISH = WORKFLOWS / "docker-publish.yml"
PREVIEW = WORKFLOWS / "deploy-preview.yml"
NIGHTLY = WORKFLOWS / "nightly.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow(path: Path) -> dict[str, object]:
    parsed = yaml.load(_read(path), Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict), f"{path.name} must be a YAML mapping"
    return parsed


def _walk(node: object) -> list[object]:
    values = [node]
    if isinstance(node, dict):
        for value in node.values():
            values.extend(_walk(value))
    elif isinstance(node, list):
        for value in node:
            values.extend(_walk(value))
    return values


def _release_issues(workflow: str) -> list[str]:
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    issues: list[str] = []
    events = parsed.get("on")
    if not isinstance(events, dict) or "push" not in events or "workflow_dispatch" not in events:
        issues.append("release must support protected tag pushes and an explicit dry-run dispatch")
    if "image_tag" in workflow:
        issues.append("manual image tag input is prohibited")
    if "fetch-depth: 0" not in workflow or "origin/master" not in workflow:
        issues.append("release must compare a tag commit to fully fetched origin/master")
    if "TAG_COMMIT" not in workflow or "MASTER_COMMIT" not in workflow or '"$TAG_COMMIT" != "$MASTER_COMMIT"' not in workflow:
        issues.append("tag provenance must require commit equality, not ancestry")
    if "docker/login-action" in workflow or "DOCKERHUB_TOKEN" in workflow or "push: true" in workflow:
        issues.append("D6 artifact-only workflow must not use production credentials or push")
    if "environment: release" not in workflow:
        issues.append("release boundary must be represented by the protected release environment")
    if "backend_digest" not in workflow or "frontend_digest" not in workflow or "commit_sha" not in workflow:
        issues.append("release metadata must contain immutable image digests, tag, and commit SHA")
    if "release-metadata" not in workflow or "GITHUB_STEP_SUMMARY" not in workflow:
        issues.append("release metadata must be retained as an artifact and job summary")
    if "dry-run" not in workflow.lower():
        issues.append("workflow_dispatch must be visibly dry-run")
    return issues


def _preview_issues(workflow: str) -> list[str]:
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    issues: list[str] = []
    if parsed.get("name") != "Preview Build Artifact":
        issues.append("preview workflow must identify itself as an artifact build")
    if "pull-requests: write" in workflow or "github-script" in workflow:
        issues.append("preview build must not comment on pull requests")
    if "preview_url" in workflow or "Preview URL" in workflow or "Deployed" in workflow:
        issues.append("preview build must not promise a hosted URL or deployment")
    if "upload-artifact" not in workflow or "non-hosted preview" not in workflow.lower():
        issues.append("preview workflow must upload and describe a non-hosted artifact")
    return issues


def _nightly_issues(workflow: str) -> list[str]:
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    issues: list[str] = []
    if "remote-sync-evidence" not in workflow or "check_remote_sync.py" not in workflow:
        issues.append("nightly must retain read-only remote sync evidence")
    if "git ls-remote --heads" in workflow:
        issues.append("nightly must delegate remote reads to the checked script")
    if "notification sent" in workflow.lower() or "notify owner" in workflow.lower():
        issues.append("nightly cannot claim an unavailable D1 notification integration")
    return issues


def test_workflows_parse_with_yaml_base_loader() -> None:
    for path in (DOCKER_PUBLISH, PREVIEW, NIGHTLY):
        assert _workflow(path)


def test_release_requires_exact_tag_provenance_and_artifact_only_boundary() -> None:
    assert _release_issues(_read(DOCKER_PUBLISH)) == []


def test_release_contract_rejects_ancestry_only_provenance() -> None:
    unsafe = _read(DOCKER_PUBLISH).replace(
        '"$TAG_COMMIT" != "$MASTER_COMMIT"',
        '"$TAG_COMMIT" "!=" "$MASTER_COMMIT"',
        1,
    )

    assert "tag provenance" in " ".join(_release_issues(unsafe))


def test_preview_is_non_hosted_artifact_without_pull_request_writes() -> None:
    assert _preview_issues(_read(PREVIEW)) == []


def test_nightly_keeps_read_only_remote_sync_artifact() -> None:
    assert _nightly_issues(_read(NIGHTLY)) == []
