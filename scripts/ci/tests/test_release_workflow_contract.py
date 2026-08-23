"""Task 5 structural contracts for release, preview, and nightly workflows."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DOCKER_PUBLISH = WORKFLOWS / "docker-publish.yml"
PREVIEW = WORKFLOWS / "deploy-preview.yml"
NIGHTLY = WORKFLOWS / "nightly.yml"
CHECKOUT_PIN = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
UPLOAD_PIN = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
PINNED_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow(workflow: str) -> dict[str, object]:
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict), "workflow must be a YAML mapping"
    return parsed


def _jobs(workflow: str) -> dict[str, object]:
    jobs = _workflow(workflow).get("jobs")
    assert isinstance(jobs, dict), "workflow jobs must be a mapping"
    return jobs


def _job(workflow: str, job_id: str) -> dict[str, object]:
    job = _jobs(workflow).get(job_id)
    assert isinstance(job, dict), f"missing {job_id} job"
    return job


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps")
    assert isinstance(steps, list), "job steps must be a list"
    return [step for step in steps if isinstance(step, dict)]


def _step(job: dict[str, object], name: str) -> tuple[int, dict[str, object]]:
    for index, step in enumerate(_steps(job)):
        if step.get("name") == name:
            return index, step
    raise AssertionError(f"missing step: {name}")


def _run(step: dict[str, object]) -> str:
    run = step.get("run")
    assert isinstance(run, str), f"{step.get('name')} must be a run step"
    return "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))


def _uses(step: dict[str, object]) -> str:
    uses = step.get("uses")
    assert isinstance(uses, str), f"{step.get('name')} must use an action"
    return uses.split(" #", 1)[0]


def _provenance_result(
    workflow: str, *, protected: bool, tag_commit: str, master_commit: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the extracted workflow provenance step against a fake local Git."""
    release = _job(workflow, "release-artifact")
    _, provenance = _step(release, "Resolve and verify immutable release provenance")
    script = _run(provenance)
    script = script.replace("${{ github.event_name }}", "push")
    script = script.replace("${{ inputs.dry_run }}", "true")
    script = script.replace("${{ github.ref_protected }}", str(protected).lower())

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  fetch) exit 0 ;;\n"
            "  rev-list) printf '%s\\n' \"$FAKE_TAG_COMMIT\" ;;\n"
            "  rev-parse) printf '%s\\n' \"$FAKE_MASTER_COMMIT\" ;;\n"
            '  *) echo "unexpected fake git command: $*" >&2; exit 64 ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        output = root / "github-output"
        environment = {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_TAG_COMMIT": tag_commit,
            "FAKE_MASTER_COMMIT": master_commit,
            "GITHUB_REF_TYPE": "tag",
            "GITHUB_REF_NAME": "v1.2.3",
            "GITHUB_OUTPUT": str(output),
        }
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        return result, output.read_text(encoding="utf-8") if output.exists() else ""


def _provenance_semantic_issues(workflow: str) -> list[str]:
    equal_sha = "a" * 40
    unprotected, unprotected_output = _provenance_result(
        workflow, protected=False, tag_commit=equal_sha, master_commit=equal_sha
    )
    mismatch, mismatch_output = _provenance_result(
        workflow, protected=True, tag_commit="b" * 40, master_commit=equal_sha
    )
    accepted, accepted_output = _provenance_result(
        workflow, protected=True, tag_commit=equal_sha, master_commit=equal_sha
    )
    issues: list[str] = []
    if unprotected.returncode == 0 or unprotected_output:
        issues.append("semantic protection gate must fail before writing success output")
    if mismatch.returncode == 0 or mismatch_output:
        issues.append("semantic equality gate must fail before writing success output")
    if accepted.returncode != 0 or "tag=v1.2.3" not in accepted_output:
        issues.append("semantic protected exact tag must write success output")
    return issues


def _release_issues(workflow: str) -> list[str]:
    issues: list[str] = []
    parsed = _workflow(workflow)
    events = parsed.get("on")
    if not isinstance(events, dict) or not {"push", "workflow_dispatch"}.issubset(events):
        issues.append("release triggers must contain tag push and dry-run dispatch")
    elif not isinstance(events["push"], dict) or events["push"].get("tags") != ["v*"]:
        issues.append("release must only trigger on version tags")

    release = _job(workflow, "release-artifact")
    if release.get("environment") != "release":
        issues.append("release boundary must use the protected release environment")
    try:
        _, checkout = _step(release, "Checkout complete release history")
        checkout_with = checkout.get("with")
        if _uses(checkout) != CHECKOUT_PIN or not isinstance(checkout_with, dict):
            issues.append("release checkout must use the reviewed immutable action pin")
        elif (
            checkout_with.get("fetch-depth") != "0"
            or checkout_with.get("persist-credentials") != "false"
        ):
            issues.append("release checkout must fully fetch without persisted credentials")
        resolve_index, resolve = _step(release, "Resolve and verify immutable release provenance")
        resolve_script = _run(resolve)
        protected_gate = (
            'github.event_name }}" = "push"' in resolve_script
            and 'github.ref_protected }}" != "true"' in resolve_script
        )
        if not protected_gate:
            issues.append("tag-push release must reject an unprotected ref before build")
        if (
            "git fetch --no-tags origin +refs/heads/master:refs/remotes/origin/master"
            not in resolve_script
        ):
            issues.append("release must explicitly fetch origin/master before comparing it")
        if 'if [ "$TAG_COMMIT" != "$MASTER_COMMIT" ]; then' not in resolve_script:
            issues.append("tag provenance must require exact equality, not ancestry")
        if "merge-base --is-ancestor" in resolve_script:
            issues.append("tag provenance must not accept ancestry in place of equality")
        if (
            'github.event_name }}" = "workflow_dispatch"' not in resolve_script
            or "dry-run only" not in resolve_script
        ):
            issues.append("workflow_dispatch must remain visibly dry-run")
        issues.extend(_provenance_semantic_issues(workflow))
    except AssertionError as error:
        issues.append(str(error))
        resolve_index = -1

    raw = "\n".join(_run(step) for step in _steps(release) if isinstance(step.get("run"), str))
    if "image_tag" in workflow:
        issues.append("manual image tag input is prohibited")
    if re.search(
        r"\bdocker\s+(?:push|login)\b|\bdocker\s+buildx\s+build\b[^\n]*\B--push\b|"
        r"\B--output\s+type=registry\b|docker/login-action|\bpush:\s*true\b|secrets\.",
        workflow,
    ):
        issues.append("artifact-only release must not publish or access production credentials")
    if (
        "backend_digest" in raw.lower()
        or "frontend_digest" in raw.lower()
        or "immutable digest" in raw.lower()
    ):
        issues.append("artifact-only metadata must not call local image IDs registry digests")
    if "backend_image_id" not in raw or "frontend_image_id" not in raw or "commit_sha" not in raw:
        issues.append("release metadata must record tag, commit SHA, and both local image IDs")
    if "docker image inspect --format '{{.Id}}'" not in raw or "local Docker image ID" not in raw:
        issues.append(
            "release metadata must identify local image IDs without claiming a registry digest"
        )
    if "release-metadata" not in workflow or "GITHUB_STEP_SUMMARY" not in raw:
        issues.append("release metadata must be retained as an artifact and summary")

    build_indexes = [
        index
        for index, step in enumerate(_steps(release))
        if isinstance(step.get("run"), str) and "docker build" in _run(step)
    ]
    if not build_indexes or any(index <= resolve_index for index in build_indexes):
        issues.append("all artifact builds must follow protected tag provenance")
    try:
        _, upload = _step(release, "Upload release metadata artifact")
        if _uses(upload) != UPLOAD_PIN:
            issues.append("release artifact upload must use the reviewed immutable action pin")
    except AssertionError as error:
        issues.append(str(error))
    return issues


def _preview_issues(workflow: str) -> list[str]:
    issues: list[str] = []
    parsed = _workflow(workflow)
    if parsed.get("name") != "Preview Build Artifact":
        issues.append("preview workflow must identify itself as an artifact build")
    preview = _job(workflow, "preview-build")
    raw = _read(PREVIEW) if workflow == _read(PREVIEW) else workflow
    if re.search(r"pull-requests:\s*write|github-script|preview_url|Preview URL|Deployed", raw):
        issues.append("preview build must not write PR comments or promise a hosted deployment")
    try:
        _, upload = _step(preview, "Upload preview build artifact")
        if _uses(upload) != UPLOAD_PIN:
            issues.append("preview artifact upload must use the reviewed immutable action pin")
        _, scope = _step(preview, "Record non-hosted artifact scope")
        if "non-hosted preview" not in _run(scope).lower():
            issues.append("preview artifact must explicitly state it is non-hosted")
    except AssertionError as error:
        issues.append(str(error))
    return issues


def _nightly_issues(workflow: str) -> list[str]:
    issues: list[str] = []
    remote_sync = _job(workflow, "remote-sync-evidence")
    raw = "\n".join(_run(step) for step in _steps(remote_sync) if isinstance(step.get("run"), str))
    if "check_remote_sync.py" not in raw or "git ls-remote --heads" in raw:
        issues.append("nightly must call the checked read-only sync script, not inline Git")
    if re.search(r"notification sent|notify owner", workflow, flags=re.IGNORECASE):
        issues.append("nightly cannot claim an unavailable notification integration")
    try:
        _, evidence = _step(remote_sync, "Record remote head comparison")
        evidence_run = _run(evidence)
        if evidence.get("shell") != "bash" or "set -euo pipefail" not in evidence_run:
            issues.append("nightly remote sync pipeline must fail closed with Bash pipefail")
        if "2>&1 | tee remote-sync-summary.txt" not in evidence_run:
            issues.append(
                "nightly remote sync must retain both stdout and stderr in its human summary"
            )
        _, upload = _step(remote_sync, "Upload remote-sync evidence")
        if upload.get("if") != "always()" or _uses(upload) != UPLOAD_PIN:
            issues.append(
                "nightly must always upload evidence with the reviewed immutable action pin"
            )
    except AssertionError as error:
        issues.append(str(error))
    return issues


def test_workflows_parse_with_yaml_base_loader() -> None:
    for path in (DOCKER_PUBLISH, PREVIEW, NIGHTLY):
        assert _workflow(_read(path))


def test_release_requires_protected_tag_exact_provenance_and_image_ids() -> None:
    assert _release_issues(_read(DOCKER_PUBLISH)) == []


def test_release_contract_rejects_unprotected_tag_bypass() -> None:
    unsafe = _read(DOCKER_PUBLISH).replace(
        'github.ref_protected }}" != "true"', '"true" != "true"', 1
    )

    assert "unprotected ref" in " ".join(_release_issues(unsafe))


def test_release_contract_rejects_dead_or_ancestry_only_equality_snippet() -> None:
    unsafe = _read(DOCKER_PUBLISH).replace(
        'if [ "$TAG_COMMIT" != "$MASTER_COMMIT" ]; then',
        '# if [ "$TAG_COMMIT" != "$MASTER_COMMIT" ]; then\n          if git merge-base --is-ancestor "$TAG_COMMIT" "$MASTER_COMMIT"; then',
        1,
    )

    assert "exact equality" in " ".join(_release_issues(unsafe))


def test_release_contract_rejects_unreachable_protection_and_equality_guards() -> None:
    unsafe = (
        _read(DOCKER_PUBLISH)
        .replace(
            'if [ "${{ github.event_name }}" = "push" ] && [ "${{ github.ref_protected }}" != "true" ]; then\n'
            '            echo "::error::Tag-push artifact builds require a protected release tag."\n'
            "            exit 1\n"
            "          fi",
            "if false; then\n"
            '            if [ "${{ github.event_name }}" = "push" ] && [ "${{ github.ref_protected }}" != "true" ]; then\n'
            '              echo "::error::Tag-push artifact builds require a protected release tag."\n'
            "              exit 1\n"
            "            fi\n"
            "          fi",
            1,
        )
        .replace(
            'if [ "$TAG_COMMIT" != "$MASTER_COMMIT" ]; then\n'
            '            echo "::error::Tag $TAG resolves to $TAG_COMMIT, not origin/master $MASTER_COMMIT."\n'
            "            exit 1\n"
            "          fi",
            "if false; then\n"
            '            if [ "$TAG_COMMIT" != "$MASTER_COMMIT" ]; then\n'
            '              echo "::error::Tag $TAG resolves to $TAG_COMMIT, not origin/master $MASTER_COMMIT."\n'
            "              exit 1\n"
            "            fi\n"
            "          fi",
            1,
        )
    )

    issues = " ".join(_release_issues(unsafe))
    assert "semantic protection gate" in issues
    assert "semantic equality gate" in issues


def test_release_contract_rejects_digest_claims_or_mutable_upload_action() -> None:
    unsafe = _read(DOCKER_PUBLISH).replace("backend_image_id", "backend_digest", 1)
    unsafe = unsafe.replace(UPLOAD_PIN, "actions/upload-artifact@v4", 1)

    issues = " ".join(_release_issues(unsafe))
    assert "registry digests" in issues
    assert "immutable action pin" in issues


def test_release_contract_rejects_buildx_push_or_registry_login() -> None:
    unsafe = _read(DOCKER_PUBLISH).replace(
        "docker build --file", "docker buildx build --push --file", 1
    )

    assert "must not publish" in " ".join(_release_issues(unsafe))


def test_preview_is_non_hosted_artifact_without_pull_request_writes() -> None:
    assert _preview_issues(_read(PREVIEW)) == []


def test_nightly_failure_pipeline_is_fail_closed_and_evidence_is_always_uploaded() -> None:
    assert _nightly_issues(_read(NIGHTLY)) == []


def test_nightly_contract_rejects_missing_pipefail_stderr_capture_or_mutable_upload_action() -> (
    None
):
    unsafe = _read(NIGHTLY).replace("set -euo pipefail", "set -eu", 1)
    unsafe = unsafe.replace(
        "2>&1 | tee remote-sync-summary.txt", "| tee remote-sync-summary.txt", 1
    )
    unsafe = unsafe.replace(UPLOAD_PIN, "actions/upload-artifact@v4", 1)

    issues = " ".join(_nightly_issues(unsafe))
    assert "fail closed" in issues
    assert "stdout and stderr" in issues
    assert "immutable action pin" in issues
