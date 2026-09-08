from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchCandidate,
    ResearchQuotaBucket,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.artifact_broker import ArtifactDescriptor
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.quota import QuotaReservationRequest, QuotaService
from app.services.research.sandbox_runner import (
    SandboxExecutionReceipt,
    SandboxExecutionRequest,
    SandboxPolicy,
    SandboxRunner,
)


@pytest.mark.asyncio
async def test_sandbox_runner_requires_current_capability_fenced_quota_and_exact_frozen_identity() -> (
    None
):
    context = await _context()
    receipt = await _reservation(context)
    request = _request(context, receipt)
    executor = _FakeExecutor(_receipt(request))

    result = await SandboxRunner(executor).execute(request)

    assert result.status == "SUCCEEDED"
    assert executor.calls == 1
    assert result.artifacts[0].storage_uri.startswith("controlled://")

    unsafe = replace(request, policy=replace(request.policy, network_mode="egress-allowed"))
    with pytest.raises(ValueError, match="SANDBOX_POLICY_NETWORK_DENIED"):
        await SandboxRunner(executor).execute(unsafe)

    stale = replace(request, quota_fencing_token=receipt.fencing_token + 1)
    with pytest.raises(ValueError, match="SANDBOX_STAGE_ATTEMPT_FENCING_DENIED"):
        await SandboxRunner(executor).execute(stale)

    unbound = replace(request, stage_attempt_id="missing")
    with pytest.raises(ValueError, match="SANDBOX_STAGE_ATTEMPT_FENCING_DENIED"):
        await SandboxRunner(executor).execute(unbound)


@pytest.mark.asyncio
async def test_sandbox_runner_rejects_mismatched_runner_receipt_before_artifact_registration() -> (
    None
):
    context = await _context()
    quota_receipt = await _reservation(context)
    request = _request(context, quota_receipt)
    mismatched = replace(_receipt(request), code_artifact_hash="f" * 64)

    with pytest.raises(ValueError, match="SANDBOX_RECEIPT_CODE_HASH_MISMATCH"):
        await SandboxRunner(_FakeExecutor(mismatched)).execute(request)


@pytest.mark.asyncio
async def test_sandbox_runner_refuses_duplicate_dispatch() -> None:
    context = await _context()
    quota_receipt = await _reservation(context)
    request = _request(context, quota_receipt)
    executor = _FakeExecutor(_receipt(request))

    await SandboxRunner(executor).execute(request)
    with pytest.raises(ValueError, match="SANDBOX_DISPATCH_ALREADY_CLAIMED"):
        await SandboxRunner(executor).execute(request)
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_sandbox_runner_rechecks_cancellation_at_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = await _context()
    quota_receipt = await _reservation(context)
    request = _request(context, quota_receipt)
    executor = _FakeExecutor(_receipt(request))
    runner = SandboxRunner(executor)
    original = runner._quota.validate_stage_attempt_fencing

    async def cancel_after_read(*args: Any, **kwargs: Any) -> bool:
        allowed = await original(*args, **kwargs)
        assert allowed
        async with async_session_maker() as session:
            task = await session.get(ResearchTask, request.task_id)
            assert task is not None
            task.cancel_requested_at = datetime.now(timezone.utc)
            await session.commit()
        return allowed

    monkeypatch.setattr(runner._quota, "validate_stage_attempt_fencing", cancel_after_read)
    with pytest.raises(ValueError, match="SANDBOX_DISPATCH_ALREADY_CLAIMED"):
        await runner.execute(request)
    assert executor.calls == 0


class _FakeExecutor:
    def __init__(self, receipt: SandboxExecutionReceipt) -> None:
        self.receipt = receipt
        self.calls = 0

    async def run(self, request: SandboxExecutionRequest) -> SandboxExecutionReceipt:
        del request
        self.calls += 1
        return self.receipt


async def _context() -> dict[str, object]:
    profile = CapabilityProfile(
        profile_id="isolated-runner",
        version="v1",
        service_identities={
            "explorer": "explorer",
            "evaluator": "evaluator",
            "runner": "sandbox-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    await CapabilityRegistry().register(profile)
    code = ResearchArtifact(
        kind="strategy_code",
        content_hash="a" * 64,
        storage_uri="controlled://inputs/strategy.py",
        size_bytes=100,
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="test",
    )
    dependencies = ResearchArtifact(
        kind="dependency_lock",
        content_hash="b" * 64,
        storage_uri="controlled://inputs/requirements.lock",
        size_bytes=100,
        media_type="text/plain",
        schema_version="v1",
        producer_identity="test",
    )
    now = datetime.now(timezone.utc)
    bucket = ResearchQuotaBucket(
        scope_type="user",
        scope_id="test-user",
        policy_version="quota-v1",
        resource_type="sandbox_seconds",
        window_start=now - timedelta(minutes=1),
        window_end=now + timedelta(hours=1),
        hard_limit=100,
        concurrency_limit=5,
    )
    async with async_session_maker() as session:
        session.add_all([code, dependencies, bucket])
        await session.commit()
        for model in (code, dependencies, bucket):
            await session.refresh(model)
    candidate = ResearchCandidate(
        user_id="test-user",
        run_id="run-1",
        experiment_epoch_id="epoch-1",
        dataset_snapshot_id="dataset-1",
        code_artifact_id=code.id,
        dependency_artifact_id=dependencies.id,
        candidate_hash="c" * 64,
        environment_hash="d" * 64,
        cost_model_hash="e" * 64,
        params={"lookback": 20},
        freeze_status="FROZEN",
    )
    lease_token = "lease-sandbox"
    async with async_session_maker() as session:
        task = ResearchTask(
            user_id="test-user",
            run_id="run-1",
            status="RUNNING",
            stage_cursor="VALIDATE",
            request_json={},
            idempotency_key="sandbox-task",
            idempotency_request_hash="a" * 64,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(hours=1),
            lease_heartbeat_at=now,
        )
        session.add_all([candidate, task])
        await session.commit()
        await session.refresh(candidate)
        await session.refresh(task)
        stage_attempt = ResearchStageAttempt(
            run_id="run-1",
            task_id=task.id,
            stage="VALIDATE",
            attempt_no=1,
            idempotency_key="sandbox-validate",
            status="RUNNING",
            lease_token=lease_token,
            input_hash="f" * 64,
        )
        session.add(stage_attempt)
        await session.commit()
        await session.refresh(stage_attempt)
    return {
        "profile": profile,
        "code": code,
        "dependencies": dependencies,
        "candidate": candidate,
        "bucket": bucket,
        "task": task,
        "stage_attempt": stage_attempt,
        "lease_token": lease_token,
    }


async def _reservation(context: dict[str, object]):
    bucket = context["bucket"]
    task = context["task"]
    stage_attempt = context["stage_attempt"]
    assert isinstance(bucket, ResearchQuotaBucket)
    assert isinstance(task, ResearchTask)
    assert isinstance(stage_attempt, ResearchStageAttempt)
    return (
        await QuotaService().reserve(
            task_id=task.id,
            policy_version="quota-v1",
            idempotency_key=f"sandbox-{bucket.id}",
            request_hash="9" * 64,
            requests=(QuotaReservationRequest(bucket.id, "sandbox_seconds", 10, "seconds"),),
            stage_attempt_id=stage_attempt.id,
        )
    )[0]


def _request(context: dict[str, object], quota_receipt) -> SandboxExecutionRequest:
    profile = context["profile"]
    code = context["code"]
    dependencies = context["dependencies"]
    candidate = context["candidate"]
    task = context["task"]
    stage_attempt = context["stage_attempt"]
    lease_token = context["lease_token"]
    assert isinstance(profile, CapabilityProfile)
    assert isinstance(code, ResearchArtifact)
    assert isinstance(dependencies, ResearchArtifact)
    assert isinstance(candidate, ResearchCandidate)
    assert isinstance(task, ResearchTask)
    assert isinstance(stage_attempt, ResearchStageAttempt)
    assert isinstance(lease_token, str)
    policy = SandboxPolicy(
        version="sandbox-policy-v1",
        image_digest=f"sha256:{'1' * 64}",
        network_mode="none",
        input_read_only=True,
        output_path="/sandbox/output",
        cpu_limit=1,
        memory_limit_mb=256,
        pid_limit=64,
        wall_timeout_seconds=60,
        output_limit_bytes=1_000_000,
    )
    return SandboxExecutionRequest(
        task_id=task.id,
        stage_attempt_id=stage_attempt.id,
        lease_token=lease_token,
        candidate_id=candidate.id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        runner_identity="sandbox-runner",
        stage="VALIDATE",
        policy=policy,
        code_artifact_hash=code.content_hash,
        dependency_artifact_hash=dependencies.content_hash,
        environment_hash=candidate.environment_hash,
        quota_reservation_id=quota_receipt.reservation_id,
        quota_fencing_token=quota_receipt.fencing_token,
    )


def _receipt(request: SandboxExecutionRequest) -> SandboxExecutionReceipt:
    return SandboxExecutionReceipt(
        status="SUCCEEDED",
        exit_code=0,
        image_digest=request.policy.image_digest,
        policy_version=request.policy.version,
        code_artifact_hash=request.code_artifact_hash,
        dependency_artifact_hash=request.dependency_artifact_hash,
        environment_hash=request.environment_hash,
        artifacts=(
            ArtifactDescriptor(
                kind="backtest_metrics",
                content_hash="f" * 64,
                storage_uri="controlled://research-output/metrics.json",
                size_bytes=128,
                media_type="application/json",
                schema_version="v1",
                producer_identity="sandbox-runner",
                container_image_digest=request.policy.image_digest,
            ),
        ),
    )
