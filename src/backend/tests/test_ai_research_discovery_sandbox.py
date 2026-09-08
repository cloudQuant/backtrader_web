"""Discovery dispatch uses real identity/quota/journal services, not host execution."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchGenerationMaterialization,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.discovery_execution_contract import DiscoveryExecutionResult
from app.services.research.discovery_sandbox import DiscoverySandboxService
from app.services.research.generation_materialization import GenerationMaterializationProposal
from app.services.research.sandbox_runner import SandboxPolicy
from app.services.research.workflow_worker import StageExecutionContext
from tests.test_ai_research_generation_materialization import _context, _materializer


@pytest.mark.asyncio
async def test_discovery_dispatch_derives_mutable_candidate_and_records_exact_execution(auth_user):
    context = await _discovery_context(auth_user, "discovery-success")
    remote = _Remote()
    result = await _service(context, remote).execute(context["discovery_context"])

    assert len(remote.commands) == 1
    command = remote.commands[0]
    assert command.snapshot["candidate_id"] == context["candidate_id"]
    assert command.snapshot["dataset"]["partition_kind"] == "DISCOVERY"
    assert (
        command.snapshot["lease_token_hash"]
        == sha256(context["task"].lease_token.encode()).hexdigest()
    )
    assert "controlled://" not in command.payload.decode()
    assert context["task"].lease_token not in command.payload.decode()
    assert result.command.request_hash == command.request_hash
    assert result.result.snapshot["returns"] == [0.01, -0.005, 0.002]
    async with database.async_session_maker() as session:
        from app.models.ai_research_v2 import ResearchDiscoveryExecution

        journal = await session.get(ResearchDiscoveryExecution, result.journal_id)
        reservation = await session.scalar(
            select(ResearchQuotaReservation).where(
                ResearchQuotaReservation.stage_attempt_id
                == context["discovery_context"].stage_attempt_id
            )
        )
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        assert journal.status == "OBSERVED"
        assert journal.command_hash == command.request_hash
        assert reservation.status == "SETTLED"
        assert reservation.settled_amount == 2
        assert candidate.freeze_status == "MUTABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["owner", "lease", "candidate", "code_bytes", "dataset"])
async def test_discovery_drift_denies_before_remote_dispatch(auth_user, drift):
    context = await _discovery_context(auth_user, f"discovery-{drift}")
    stage_context = context["discovery_context"]
    if drift == "owner":
        stage_context = replace(stage_context, user_id="unrelated-owner")
    elif drift == "dataset":
        context["resolver"].register(
            replace(
                context["attestation"],
                receipt_id="changed-receipt",
                object_digest="f" * 64,
                object_version="changed",
            )
        )
    else:
        async with database.async_session_maker() as session:
            if drift == "lease":
                task = await session.get(ResearchTask, stage_context.task_id)
                task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            elif drift == "candidate":
                candidate = await session.get(ResearchCandidate, context["candidate_id"])
                candidate.params = {"lookback": 999}
            else:
                candidate = await session.get(ResearchCandidate, context["candidate_id"])
                blob = await session.get(ResearchArtifactContent, candidate.code_artifact_id)
                blob.content = b"changed bytes"
            await session.commit()
    remote = _Remote()
    expected_code = {
        "owner": "DISCOVERY_CONTEXT_DENIED",
        "lease": "DISCOVERY_CONTEXT_DENIED",
        "candidate": "CANDIDATE_CONTENT_HASH_MISMATCH",
        "code_bytes": "DISCOVERY_ARTIFACT_CONTENT_INVALID",
        "dataset": "DATASET_",
    }[drift]
    with pytest.raises(ValueError, match=expected_code):
        await _service(context, remote).execute(stage_context)
    assert remote.commands == []
    if drift == "dataset":
        async with database.async_session_maker() as session:
            candidate = await session.get(ResearchCandidate, context["candidate_id"])
            snapshot = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
            assert snapshot.integrity_status == "FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["context", "remaining_lease"])
async def test_discovery_revalidates_strict_quota_at_atomic_dispatch(auth_user, monkeypatch, drift):
    context = await _discovery_context(auth_user, f"discovery-dispatch-{drift}")
    remote = _Remote()
    service = _service(context, remote)
    prepare = service._journal.prepare

    async def prepare_then_drift(**kwargs):
        journal = await prepare(**kwargs)
        async with database.async_session_maker() as session:
            reservation = await session.get(ResearchQuotaReservation, journal.quota_reservation_id)
            if drift == "context":
                reservation.reservation_context = None
            else:
                from app.services.research.database_clock import database_utc_now

                reservation.lease_expires_at = await database_utc_now(session) + timedelta(
                    seconds=1
                )
            await session.commit()
        return journal

    monkeypatch.setattr(service._journal, "prepare", prepare_then_drift)
    with pytest.raises(ValueError, match="DISCOVERY_DISPATCH_ALREADY_CLAIMED"):
        await service.execute(context["discovery_context"])

    assert remote.commands == []
    async with database.async_session_maker() as session:
        reservation = await session.scalar(select(ResearchQuotaReservation))
        assert reservation.status == "RESERVED"
        assert reservation.provider_operation_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["lease", "cancel"])
async def test_discovery_checks_task_again_after_final_data_revalidation(
    auth_user, monkeypatch, drift
):
    context = await _discovery_context(auth_user, f"discovery-after-data-{drift}")
    remote = _Remote()
    service = _service(context, remote)
    revalidate = context["datasets"].revalidate_snapshot_in_session
    calls = 0

    async def revalidate_then_change(session, *, snapshot):
        nonlocal calls
        calls += 1
        result = await revalidate(session, snapshot=snapshot)
        if calls == 3:
            task = await session.get(ResearchTask, context["task"].id)
            if drift == "lease":
                task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            else:
                task.cancel_requested_at = datetime.now(timezone.utc)
            await session.flush()
        return result

    monkeypatch.setattr(
        context["datasets"], "revalidate_snapshot_in_session", revalidate_then_change
    )
    with pytest.raises(ValueError, match="DISCOVERY_CONTEXT_DENIED"):
        await service.execute(context["discovery_context"])

    assert remote.commands == []


@pytest.mark.asyncio
async def test_discovery_has_total_remote_deadline_and_preserves_unknown(auth_user, monkeypatch):
    import app.services.research.discovery_sandbox as discovery_module
    from app.models.ai_research_v2 import ResearchDiscoveryExecution

    context = await _discovery_context(auth_user, "discovery-timeout")
    timeouts = []
    sent = asyncio.Event()

    async def bounded_wait(awaitable, *, timeout):
        timeouts.append(timeout)
        return await asyncio.wait_for(awaitable, timeout=0.01)

    async def never_respond():
        sent.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(discovery_module, "_wait_for", bounded_wait, raising=False)
    remote = _Remote(after_send=never_respond)
    task = asyncio.create_task(_service(context, remote).execute(context["discovery_context"]))
    try:
        await asyncio.wait_for(sent.wait(), timeout=2)
        with pytest.raises(ValueError, match="DISCOVERY_REMOTE_OUTCOME_UNKNOWN"):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.3)
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    assert timeouts == [_policy().wall_timeout_seconds + 60]
    assert len(remote.commands) == 1
    async with database.async_session_maker() as session:
        journal = await session.scalar(select(ResearchDiscoveryExecution))
        reservation = await session.scalar(select(ResearchQuotaReservation))
        assert journal.status == "UNKNOWN"
        assert journal.error_code == "DISCOVERY_REMOTE_OUTCOME_UNKNOWN"
        assert reservation.status == "IN_FLIGHT"


@pytest.mark.asyncio
async def test_discovery_rejects_ambiguous_generation_materializations(auth_user):
    context = await _discovery_context(auth_user, "discovery-ambiguous")
    other = await _context(auth_user, suffix="second-materialization")
    materialized = await _materializer(other).materialize(
        context=other["stage_context"],
        proposal=GenerationMaterializationProposal(
            model_invocation_id=other["invocation"].id,
            model_output=other["model_output"],
        ),
    )
    async with database.async_session_maker() as session:
        relation = await session.scalar(
            select(ResearchGenerationMaterialization).where(
                ResearchGenerationMaterialization.candidate_id == materialized.candidate_id
            )
        )
        relation.task_id = context["task"].id
        await session.commit()
    remote = _Remote()

    with pytest.raises(ValueError, match="DISCOVERY_GENERATION_MATERIALIZATION_AMBIGUOUS"):
        await _service(context, remote).execute(context["discovery_context"])

    assert remote.commands == []


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["user_id", "run_id"])
async def test_discovery_rejects_materialization_binding_drift(auth_user, drift):
    context = await _discovery_context(auth_user, f"discovery-relation-{drift}")
    async with database.async_session_maker() as session:
        relation = await session.scalar(select(ResearchGenerationMaterialization))
        setattr(relation, drift, "unrelated-binding")
        await session.commit()
    remote = _Remote()

    with pytest.raises(ValueError, match="DISCOVERY_CANDIDATE_BINDING_DENIED"):
        await _service(context, remote).execute(context["discovery_context"])

    assert remote.commands == []


@pytest.mark.asyncio
async def test_discovery_unknown_remote_retains_quota_and_auditable_command(auth_user):
    context = await _discovery_context(auth_user, "discovery-unknown")
    remote = _Remote(fail=True)
    service = _service(context, remote)
    with pytest.raises(ValueError, match="DISCOVERY_REMOTE_OUTCOME_UNKNOWN"):
        await service.execute(context["discovery_context"])
    with pytest.raises(ValueError):
        await service.execute(context["discovery_context"])
    assert len(remote.commands) == 1
    async with database.async_session_maker() as session:
        from app.models.ai_research_v2 import ResearchDiscoveryExecution

        journal = await session.scalar(select(ResearchDiscoveryExecution))
        reservation = await session.scalar(select(ResearchQuotaReservation))
        assert journal.status == "UNKNOWN"
        assert "secret" not in str(journal.result_json)
        assert reservation.status == "IN_FLIGHT"


@pytest.mark.asyncio
async def test_discovery_records_late_result_but_does_not_publish_or_release_it(auth_user):
    context = await _discovery_context(auth_user, "discovery-late")

    async def cancel():
        async with database.async_session_maker() as session:
            task = await session.get(ResearchTask, context["task"].id)
            task.cancel_requested_at = datetime.now(timezone.utc)
            await session.commit()

    remote = _Remote(after_send=cancel)
    with pytest.raises(ValueError):
        await _service(context, remote).execute(context["discovery_context"])
    async with database.async_session_maker() as session:
        from app.models.ai_research_v2 import ResearchDiscoveryExecution

        journal = await session.scalar(select(ResearchDiscoveryExecution))
        reservation = await session.scalar(select(ResearchQuotaReservation))
        assert journal.status == "OBSERVED"
        assert reservation.status == "IN_FLIGHT"
    assert len(remote.commands) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["shared_identity", "storage", "network", "queue"])
async def test_discovery_requires_independent_runner_boundary_not_only_a_capability_bit(
    auth_user, boundary
):
    from app.models.ai_research_v2 import ResearchCapabilityProfile

    context = await _discovery_context(auth_user, f"discovery-boundary-{boundary}")
    async with database.async_session_maker() as session:
        profile = await session.scalar(select(ResearchCapabilityProfile))
        if boundary == "shared_identity":
            profile.service_identities = {
                "explorer": "discovery-runner",
                "evaluator": "evaluator",
                "runner": "discovery-runner",
            }
        elif boundary == "storage":
            profile.storage_boundaries = {"isolated": False}
        elif boundary == "network":
            profile.network_capabilities = {"isolated": False}
        else:
            profile.queue_capabilities = {"isolated": False}
        await session.commit()
    remote = _Remote()

    with pytest.raises(ValueError, match="DISCOVERY_RUNNER_CAPABILITY_DENIED"):
        await _service(context, remote).execute(context["discovery_context"])

    assert remote.commands == []


class _Remote:
    def __init__(self, *, fail=False, after_send=None):
        self.commands = []
        self.fail = fail
        self.after_send = after_send

    async def run(self, command):
        self.commands.append(command)
        if self.after_send:
            await self.after_send()
        if self.fail:
            raise RuntimeError("secret: do not expose remote diagnostic")
        snapshot = command.snapshot
        return DiscoveryExecutionResult.from_mapping(
            {
                "schema_version": "discovery-execution-result-v1",
                "operation_id": snapshot["operation_id"],
                "command_hash": command.request_hash,
                "runner_identity": snapshot["runner_identity"],
                "image_digest": snapshot["policy"]["image_digest"],
                "status": "SUCCEEDED",
                "exit_code": 0,
                "elapsed_milliseconds": 1501,
                "observed_market_performance": True,
                "returns": [0.01, -0.005, 0.002],
                "error_code": None,
            },
            command=command,
        )


def _policy():
    return SandboxPolicy(
        version="discovery-policy-v1",
        image_digest="sha256:" + "d" * 64,
        network_mode="none",
        input_read_only=True,
        output_path="/sandbox/output",
        cpu_limit=1,
        memory_limit_mb=256,
        pid_limit=16,
        wall_timeout_seconds=10,
        output_limit_bytes=10000,
    )


def _service(context, remote):
    return DiscoverySandboxService(
        executor=remote,
        dataset_registry=context["datasets"],
        policy=_policy(),
        runner_identity="discovery-runner",
        quota_policy_version="discovery-quota-v1",
        quota_lease_seconds=180,
    )


async def _discovery_context(auth_user, suffix):
    context = await _context(auth_user, suffix=suffix)
    request_hash = sha256(suffix.encode()).hexdigest()
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["run"].id)
        run.request_hash = request_hash
        run.status = "RUNNING"
        await session.commit()
    context["stage_context"] = replace(context["stage_context"], request_hash=request_hash)
    materialized = await _materializer(context).materialize(
        context=context["stage_context"],
        proposal=GenerationMaterializationProposal(
            model_invocation_id=context["invocation"].id,
            model_output=context["model_output"],
        ),
    )
    now = datetime.now(timezone.utc)
    profile = CapabilityProfile(
        profile_id="discovery-isolated",
        version="v1",
        service_identities={
            "explorer": "explorer",
            "evaluator": "evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        stage_image_digests={
            "evaluator": "evaluator-image@sha256:test",
            "scanner": f"sha256:{'5' * 64}",
        },
    )
    await CapabilityRegistry().register(profile)
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        run = await session.get(ResearchRun, context["run"].id)
        task.stage_cursor = "VALIDATE_DISCOVERY"
        run.stage_cursor = "VALIDATE_DISCOVERY"
        run.capability_profile_id = profile.profile_id
        run.capability_profile_version = profile.version
        previous = await session.get(ResearchStageAttempt, context["attempt"].id)
        previous.status = "SUCCEEDED"
        previous.output_artifact_id = materialized.output_artifact_id
        attempt = ResearchStageAttempt(
            run_id=run.id,
            task_id=task.id,
            stage="VALIDATE_DISCOVERY",
            attempt_no=1,
            idempotency_key=f"validation-{suffix}",
            status="RUNNING",
            lease_token=task.lease_token,
            input_hash=request_hash,
        )
        bucket = ResearchQuotaBucket(
            scope_type="user",
            scope_id=task.user_id,
            policy_version="discovery-quota-v1",
            resource_type="sandbox_seconds",
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=100,
            concurrency_limit=2,
        )
        session.add_all([attempt, bucket])
        await session.commit()
        await session.refresh(attempt)
    context["candidate_id"] = materialized.candidate_id
    context["discovery_context"] = StageExecutionContext(
        task_id=context["task"].id,
        run_id=context["run"].id,
        user_id=context["task"].user_id,
        stage_attempt_id=attempt.id,
        lease_token=context["task"].lease_token,
        stage="VALIDATE_DISCOVERY",
        request_hash=request_hash,
        trace_id=context["task"].trace_id,
    )
    return context
