from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchGateDecision,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchRun,
)
from app.services.research import holdout_finalize as holdout_finalize_module
from app.services.research.candidate_registry import require_strict_freeze_receipt
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.holdout_finalize import HoldoutFinalizeService
from app.services.research.promotion import (
    CommandPromotionAuthority,
    CommandPromotionMode,
    PromotionGateEngine,
    PromotionResult,
    _authoritative_trial_sharpes,
    resolve_server_policy,
)
from tests.conftest import app
from tests.test_ai_research_holdout_claim import _claim_service, _queued_command


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@pytest.fixture(autouse=True)
def clear_holdout_overrides() -> None:
    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


@pytest.mark.asyncio
async def test_production_finalizer_rejects_inline_sealed_measurements() -> None:
    runtime = holdout_finalize_module.HoldoutEvaluatorRuntimeIdentity(
        worker_identity="test-worker",
        evaluator_identity="test-evaluator",
        evaluator_image_digest=f"sha256:{'5' * 64}",
    )

    with pytest.raises(
        ValueError,
        match="^HOLDOUT_FINALIZE_INLINE_MEASUREMENTS_DISABLED$",
    ):
        await HoldoutFinalizeService().checkpoint_claimed_evidence(
            command_id="untrusted-command",
            runtime=runtime,
            lease_token="untrusted-token",
            lease_generation=1,
            measurements={"returns": [0.01]},
        )


@pytest.mark.asyncio
async def test_checkpoint_builds_one_server_bound_canonical_artifact_and_replays_exactly(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "finalize-checkpoint")
    service = HoldoutFinalizeService._for_test_only_inline_measurements()

    first = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements={},
    )
    replayed = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements={},
    )

    assert replayed == first
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        artifact = await session.get(ResearchArtifact, first.artifact_id)
        retained = await session.get(ResearchArtifactContent, first.artifact_id)
        bindings = tuple((await session.scalars(select(ResearchHoldoutArtifactBinding))).all())
        audits = tuple(
            (
                await session.scalars(
                    select(ResearchHoldoutAccessAudit).where(
                        ResearchHoldoutAccessAudit.action == "CHECKPOINT_RECORDED"
                    )
                )
            ).all()
        )

    assert command is not None and command.status == "RUNNING"
    assert command.lease_token_hash == sha256(claimed.lease_token.encode()).hexdigest()
    assert evaluation is not None and evaluation.status == "RUNNING"
    assert evaluation.returns_artifact_id == first.artifact_id
    assert artifact is not None and retained is not None
    payload = json.loads(bytes(retained.content))
    assert bytes(retained.content) == canonical_json(payload).encode("utf-8")
    assert payload == {
        "schema_version": "sealed-holdout-evidence-v1",
        "authorization_id": command.authorization_id,
        "candidate_id": context["candidate"].id,
        "candidate_hash": context["candidate"].candidate_hash,
        "experiment_epoch_id": context["candidate"].experiment_epoch_id,
        "dataset_snapshot_id": context["sealed"].id,
        "sealed_dataset_hash": context["sealed"].content_hash,
        "policy_version": command.policy_version,
        "evaluator_identity": runtime.evaluator_identity,
        "evaluator_version": runtime.evaluator_image_digest,
        "measurements": {},
    }
    assert artifact.content_hash == sha256(bytes(retained.content)).hexdigest()
    assert artifact.storage_uri == f"controlled://sealed-holdout-evidence/{artifact.content_hash}"
    assert len(bindings) == 1
    binding = bindings[0]
    assert binding.command_id == claimed.command_id
    assert binding.authorization_id == command.authorization_id
    assert binding.evaluation_id == claimed.evaluation_id
    assert binding.artifact_id == artifact.id
    assert binding.lease_owner == runtime.worker_identity
    assert binding.lease_generation == claimed.lease_generation
    assert binding.binding_schema_version == "holdout-artifact-binding-v1"
    assert binding.authority_binding_hash == content_hash(
        {
            "schema_version": "holdout-artifact-binding-v1",
            "user_id": command.user_id,
            "run_id": command.run_id,
            "command_id": command.id,
            "authorization_id": command.authorization_id,
            "evaluation_id": command.evaluation_id,
            "experiment_epoch_id": command.experiment_epoch_id,
            "candidate_id": command.candidate_id,
            "candidate_hash": command.candidate_hash,
            "freeze_receipt_id": command.freeze_receipt_id,
            "freeze_receipt_fingerprint": command.freeze_receipt_fingerprint,
            "dataset_snapshot_id": command.dataset_snapshot_id,
            "sealed_dataset_hash": command.sealed_dataset_hash,
            "sealed_dataset_identity_hash": command.sealed_dataset_identity_hash,
            "policy_version": command.policy_version,
            "evaluator_identity": command.evaluator_identity,
            "evaluator_version": command.evaluator_version,
            "capability_profile_id": command.capability_profile_id,
            "capability_profile_version": command.capability_profile_version,
            "capability_evidence_hash": command.capability_evidence_hash,
            "artifact_id": artifact.id,
            "artifact_hash": artifact.content_hash,
            "claim_access_audit_id": binding.claim_access_audit_id,
            "request_hash": command.request_hash,
            "lease_owner": runtime.worker_identity,
            "lease_generation": claimed.lease_generation,
            "lease_expires_at": _as_utc(binding.lease_expires_at),
        }
    )
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_checkpoint_rejects_stale_lease_without_creating_evidence(
    client,
    auth_user,
) -> None:
    _context, claimed, runtime = await _claimed_context(client, auth_user, "finalize-stale")
    service = HoldoutFinalizeService._for_test_only_inline_measurements()

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_LEASE_STALE$"):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token="wrong-lease-token",
            lease_generation=claimed.lease_generation,
            measurements={},
        )

    assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
    assert await _count(ResearchHoldoutArtifactBinding) == 0


@pytest.mark.asyncio
async def test_malformed_checkpoint_and_finalize_inputs_append_rejected_audits(
    client,
    auth_user,
) -> None:
    _context, claimed, runtime = await _claimed_context(client, auth_user, "finalize-malformed")
    service = HoldoutFinalizeService._for_test_only_inline_measurements()

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_MEASUREMENTS_INVALID$"):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements={"caller_policy": "relaxed"},
        )
    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_LEASE_STALE$"):
        await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token="",
            lease_generation=0,
        )

    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_REJECTED") == 1
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_REJECTED") == 1


@pytest.mark.asyncio
async def test_checkpoint_second_fence_rolls_back_every_provisional_write(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-checkpoint-second-fence",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    original_fence = holdout_finalize_module._second_authority_fence

    async def expire_before_second_fence(
        session: AsyncSession,
        command: ResearchHoldoutEvaluationCommand,
        **kwargs: Any,
    ) -> None:
        command.lease_token_hash = "0" * 64
        await session.flush()
        await original_fence(session, command, **kwargs)

    monkeypatch.setattr(
        holdout_finalize_module,
        "_second_authority_fence",
        expire_before_second_fence,
    )

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_LEASE_STALE$"):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements={},
        )

    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
    assert command is not None
    assert command.status == "RUNNING"
    assert command.lease_token_hash == sha256(claimed.lease_token.encode()).hexdigest()
    assert evaluation is not None and evaluation.returns_artifact_id is None
    assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
    assert await _count(ResearchHoldoutArtifactBinding) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_RECORDED") == 0
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_REJECTED") == 1


@pytest.mark.asyncio
async def test_checkpoint_rejects_evidence_above_retention_limit(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-size-limit",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    monkeypatch.setattr(holdout_finalize_module, "_MAX_EVIDENCE_BYTES", 1)

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_ARTIFACT_SIZE_EXCEEDED$"):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements={},
        )

    assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
    assert await _count(ResearchHoldoutArtifactBinding) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_REJECTED") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size_delta", [0, 1])
async def test_checkpoint_enforces_real_utf8_retention_boundary_exactly(
    client,
    auth_user,
    size_delta: int,
) -> None:
    _context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-real-size-boundary-{size_delta}",
    )
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert command is not None and command.authorization_id is not None
        authorization = await session.get(
            ResearchHoldoutAuthorization,
            command.authorization_id,
        )
        assert authorization is not None
        measurements = _measurements_for_exact_evidence_size(
            command,
            authorization,
            target_size=holdout_finalize_module._MAX_EVIDENCE_BYTES + size_delta,
        )
        retained = canonical_json(
            holdout_finalize_module._evidence_payload(
                command,
                authorization=authorization,
                measurements=measurements,
            )
        ).encode("utf-8")

    assert "界" in measurements["returns"][0]
    assert len(retained) == 10_000_000 + size_delta
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    if size_delta == 0:
        receipt = await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements=measurements,
        )
        async with database.async_session_maker() as session:
            artifact = await session.get(ResearchArtifact, receipt.artifact_id)
            content = await session.get(ResearchArtifactContent, receipt.artifact_id)
        assert artifact is not None and artifact.size_bytes == 10_000_000
        assert content is not None and len(bytes(content.content)) == 10_000_000
        assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_RECORDED") == 1
    else:
        with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_ARTIFACT_SIZE_EXCEEDED$"):
            await service.checkpoint_claimed_evidence(
                command_id=claimed.command_id,
                runtime=runtime,
                lease_token=claimed.lease_token,
                lease_generation=claimed.lease_generation,
                measurements=measurements,
            )
        assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
        assert await _count(ResearchHoldoutArtifactBinding) == 0
        assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_REJECTED") == 1


@pytest.mark.asyncio
async def test_checkpoint_rejects_started_authority_profile_tamper(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-started-authority-tamper",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    original_load = holdout_finalize_module._load_started_authority

    async def tampered_load(session: AsyncSession, graph: Any):
        authorization, evaluation, audit = await original_load(session, graph)
        assert authorization is not None
        authorization.capability_evidence_hash = "0" * 64
        return authorization, evaluation, audit

    monkeypatch.setattr(
        holdout_finalize_module,
        "_load_started_authority",
        tampered_load,
    )

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_AUTHORITY_INCONSISTENT$"):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements={},
        )

    assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
    assert await _count(ResearchHoldoutArtifactBinding) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_REJECTED") == 1


@pytest.mark.asyncio
async def test_checkpoint_conflicting_replay_fails_closed(client, auth_user) -> None:
    _context, claimed, runtime = await _claimed_context(client, auth_user, "finalize-conflict")
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements={},
    )

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_CHECKPOINT_CONFLICT$"):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements={"returns": [0.01]},
        )

    assert await _count(ResearchHoldoutArtifactBinding) == 1
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_RECORDED") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_was_applied", [True, False])
async def test_checkpoint_commit_ack_loss_uses_exact_readback_or_fences_unknown(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    commit_was_applied: bool,
) -> None:
    _context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-checkpoint-ack-{commit_was_applied}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    original_commit = AsyncSession.commit
    calls = 0

    async def uncertain_commit(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            if commit_was_applied:
                await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("ack lost"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", uncertain_commit)
    if commit_was_applied:
        receipt = await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements={},
        )
        assert receipt.evaluation_id == claimed.evaluation_id
        assert await _count(ResearchHoldoutArtifactBinding) == 1
        assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_UNKNOWN") == 0
    else:
        with pytest.raises(
            ValueError,
            match="^HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN$",
        ):
            await service.checkpoint_claimed_evidence(
                command_id=claimed.command_id,
                runtime=runtime,
                lease_token=claimed.lease_token,
                lease_generation=claimed.lease_generation,
                measurements={},
            )
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
            evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        assert command is not None and command.status == "RECONCILING"
        assert command.lease_owner is None and command.lease_token_hash is None
        assert evaluation is not None and evaluation.returns_artifact_id is None
        assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
        assert await _count(ResearchHoldoutArtifactBinding) == 0
        assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_UNKNOWN") == 1


@pytest.mark.asyncio
async def test_applied_checkpoint_with_failed_ack_query_reconciles_from_retained_authority(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-checkpoint-applied-query-failure-reconcile",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    original_commit = AsyncSession.commit
    original_lock = service._claims._lock_claim_graph
    commit_calls = 0
    ack_lost = False
    readback_failed = False

    async def uncertain_commit(session: AsyncSession) -> None:
        nonlocal ack_lost, commit_calls
        commit_calls += 1
        if commit_calls == 1:
            await original_commit(session)
            ack_lost = True
            raise OperationalError("COMMIT", {}, RuntimeError("ack lost after apply"))
        await original_commit(session)

    async def fail_only_ack_readback(
        session: AsyncSession,
        *,
        command_id: str,
    ) -> Any:
        nonlocal readback_failed
        if ack_lost and not readback_failed:
            readback_failed = True
            raise OperationalError("SELECT", {}, RuntimeError("ack readback failed"))
        return await original_lock(session, command_id=command_id)

    monkeypatch.setattr(AsyncSession, "commit", uncertain_commit)
    monkeypatch.setattr(service._claims, "_lock_claim_graph", fail_only_ack_readback)

    with pytest.raises(
        ValueError,
        match="^HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN$",
    ):
        await service.checkpoint_claimed_evidence(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
            measurements=await _trusted_rejecting_measurements(context),
        )

    assert ack_lost is True and readback_failed is True
    before = {
        "authorization": await _count(ResearchHoldoutAuthorization),
        "evaluation": await _count(ResearchEvaluation),
        "artifact": await _count(ResearchArtifact, kind="sealed_holdout_evidence"),
        "binding": await _count(ResearchHoldoutArtifactBinding),
    }
    assert before == {
        "authorization": 1,
        "evaluation": 1,
        "artifact": 1,
        "binding": 1,
    }
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
    assert command is not None and command.status == "RECONCILING"
    assert command.error_code == "HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN"
    assert evaluation is not None and evaluation.returns_artifact_id is not None
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_RECORDED") == 1
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_UNKNOWN") == 1

    resolver_reads = 0

    async def reject_sealed_reread(**kwargs: Any) -> None:
        nonlocal resolver_reads
        resolver_reads += 1
        raise AssertionError("sealed object resolver must not be called during reconciliation")

    monkeypatch.setattr(context["resolver"], "resolve_receipt", reject_sealed_reread)
    monkeypatch.setattr(context["resolver"], "resolve_current", reject_sealed_reread)
    reconciliation_runtime = replace(runtime, worker_identity="checkpoint-unknown-reconciler")

    reconciled = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciliation_runtime,
    )

    after = {
        "authorization": await _count(ResearchHoldoutAuthorization),
        "evaluation": await _count(ResearchEvaluation),
        "artifact": await _count(ResearchArtifact, kind="sealed_holdout_evidence"),
        "binding": await _count(ResearchHoldoutArtifactBinding),
    }
    assert reconciled.command_status == "SUCCEEDED"
    assert resolver_reads == 0
    assert after == before
    assert await _count(ResearchGateDecision) == 13
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_COMPLETED") == 0
    assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 1

    replayed = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciliation_runtime,
    )
    assert replayed == reconciled
    assert await _count(ResearchGateDecision) == 13
    assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("advanced_status", ["RECONCILING", "SUCCEEDED"])
async def test_checkpoint_ack_readback_accepts_exact_artifact_after_legal_state_advance(
    client,
    auth_user,
    advanced_status: str,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-checkpoint-advanced-{advanced_status.lower()}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    receipt = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    async with database.async_session_maker() as session:
        retained = await session.get(ResearchArtifactContent, receipt.artifact_id)
    assert retained is not None
    probe = holdout_finalize_module._CheckpointProbe(
        receipt=receipt,
        retained_content=bytes(retained.content),
        runtime=runtime,
        lease_token_hash=sha256(claimed.lease_token.encode()).hexdigest(),
    )

    if advanced_status == "RECONCILING":
        await _recover_expired_checkpoint(context, claimed, runtime)
    else:
        finalized = await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )
        assert finalized.command_status == "SUCCEEDED"

    assert await service._read_committed_checkpoint(probe) == receipt
    assert await _count(ResearchHoldoutAccessAudit, action="CHECKPOINT_UNKNOWN") == 0


@pytest.mark.asyncio
async def test_finalize_records_thirteen_gates_and_terminal_graph_atomically(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "finalize-terminal")
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    measurements = await _trusted_rejecting_measurements(context)
    checkpoint = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )

    result = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )

    assert result.command_id == claimed.command_id
    assert result.evaluation_id == claimed.evaluation_id
    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == "REJECTED"
    assert result.eligible is False
    assert len(result.gate_statuses) == 13
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        decisions = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == claimed.evaluation_id
                    )
                )
            ).all()
        )
        final_audits = tuple(
            (
                await session.scalars(
                    select(ResearchHoldoutAccessAudit).where(
                        ResearchHoldoutAccessAudit.action == "FINALIZE_COMPLETED"
                    )
                )
            ).all()
        )

    assert command is not None and command.status == "SUCCEEDED"
    assert command.error_code is None
    assert command.lease_owner is None
    assert command.lease_token_hash is None
    assert command.lease_expires_at is None
    assert command.lease_heartbeat_at is None
    assert evaluation is not None and evaluation.status == "REJECTED"
    assert evaluation.returns_artifact_id == checkpoint.artifact_id
    assert evaluation.completed_at is not None
    assert evaluation.metrics == {"promotion_eligible": False}
    assert evaluation.gate_inputs["input_evidence_hash"] == result.input_evidence_hash
    assert epoch is not None and epoch.status == "CLOSED" and epoch.closed_at is not None
    assert len(decisions) == 13
    assert len(final_audits) == 1

    replayed = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )
    assert replayed == result
    assert await _count(ResearchGateDecision) == 13
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_COMPLETED") == 1


@pytest.mark.asyncio
async def test_finalize_complete_trusted_evidence_passes_all_thirteen_gates(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-all-gates-pass",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    measurements = await _trusted_passing_measurements(context, runtime=runtime)
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )

    result = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )

    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == "PASSED"
    assert result.eligible is True
    assert len(result.gate_statuses) == 13
    assert set(result.gate_statuses.values()) == {"PASS"}
    async with database.async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        decisions = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == claimed.evaluation_id
                    )
                )
            ).all()
        )
    assert evaluation is not None and evaluation.status == "PASSED"
    assert evaluation.metrics == {"promotion_eligible": True}
    assert len(decisions) == 13
    assert {decision.status for decision in decisions} == {"PASS"}


@pytest.mark.asyncio
async def test_finalize_complete_trusted_evidence_preserves_one_hard_gate_failure(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-one-hard-gate-fail",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    measurements = await _trusted_passing_measurements(context, runtime=runtime)
    measurements["max_drawdown"] = 0.21
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )

    result = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )

    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == "REJECTED"
    assert result.eligible is False
    assert result.gate_statuses["MAX_DRAWDOWN"] == "FAIL"
    assert {
        code: status for code, status in result.gate_statuses.items() if code != "MAX_DRAWDOWN"
    } == {code: "PASS" for code in result.gate_statuses if code != "MAX_DRAWDOWN"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["construct", "add", "flush"])
async def test_terminal_accepted_audit_failure_rolls_back_terminal_graph(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-terminal-audit-{failure_point}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    original_audit_factory = holdout_finalize_module._accepted_access_audit
    original_add = AsyncSession.add
    original_flush = AsyncSession.flush

    if failure_point == "construct":

        def fail_terminal_audit_construction(*args: Any, **kwargs: Any) -> Any:
            if kwargs.get("action") == "FINALIZE_COMPLETED":
                raise ValueError("HOLDOUT_FINALIZE_TERMINAL_AUDIT_CONSTRUCTION_FAILED")
            return original_audit_factory(*args, **kwargs)

        monkeypatch.setattr(
            holdout_finalize_module,
            "_accepted_access_audit",
            fail_terminal_audit_construction,
        )
    elif failure_point == "add":

        def fail_terminal_audit_add(session: AsyncSession, instance: object) -> None:
            if (
                isinstance(instance, ResearchHoldoutAccessAudit)
                and instance.action == "FINALIZE_COMPLETED"
            ):
                raise OperationalError("ADD", {}, RuntimeError("forced terminal audit add"))
            original_add(session, instance)

        monkeypatch.setattr(AsyncSession, "add", fail_terminal_audit_add)
    else:

        async def fail_terminal_audit_flush(
            session: AsyncSession,
            objects: object | None = None,
        ) -> None:
            if any(
                isinstance(instance, ResearchHoldoutAccessAudit)
                and instance.action == "FINALIZE_COMPLETED"
                for instance in session.new
            ):
                raise OperationalError("FLUSH", {}, RuntimeError("forced terminal audit flush"))
            await original_flush(session, objects)

        monkeypatch.setattr(AsyncSession, "flush", fail_terminal_audit_flush)

    expected_error = (
        "HOLDOUT_FINALIZE_TERMINAL_AUDIT_CONSTRUCTION_FAILED"
        if failure_point == "construct"
        else "HOLDOUT_FINALIZE_PERSISTENCE_FAILED"
    )
    with pytest.raises(ValueError, match=f"^{expected_error}$"):
        await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )

    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        rejected = tuple(
            (
                await session.scalars(
                    select(ResearchHoldoutAccessAudit).where(
                        ResearchHoldoutAccessAudit.action == "FINALIZE_REJECTED"
                    )
                )
            ).all()
        )
    assert command is not None and command.status == "RUNNING"
    assert command.error_code is None and command.lease_token_hash is not None
    assert evaluation is not None and evaluation.status == "RUNNING"
    assert evaluation.metrics == {} and evaluation.gate_inputs == {}
    assert epoch is not None and epoch.status == "DISCLOSED" and epoch.closed_at is None
    assert await _count(ResearchGateDecision) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_COMPLETED") == 0
    assert len(rejected) == 1
    assert rejected[0].command_id is None
    assert rejected[0].requested_command_id == claimed.command_id


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_was_applied", [True, False])
async def test_finalize_commit_ack_loss_uses_exact_readback_or_reconciliation(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    commit_was_applied: bool,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-terminal-ack-{commit_was_applied}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    original_commit = AsyncSession.commit
    calls = 0

    async def uncertain_commit(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            if commit_was_applied:
                await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("ack lost"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", uncertain_commit)
    if commit_was_applied:
        result = await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )
        assert result.command_status == "SUCCEEDED"
        assert await _count(ResearchGateDecision) == 13
        assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_UNKNOWN") == 0
    else:
        with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN$"):
            await service.finalize_claimed_evaluation(
                command_id=claimed.command_id,
                runtime=runtime,
                lease_token=claimed.lease_token,
                lease_generation=claimed.lease_generation,
            )
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
            evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
            epoch = await session.get(
                ResearchExperimentEpoch,
                context["candidate"].experiment_epoch_id,
            )
        assert command is not None and command.status == "RECONCILING"
        assert command.lease_owner is None and command.lease_token_hash is None
        assert evaluation is not None and evaluation.status == "RUNNING"
        assert epoch is not None and epoch.status == "DISCLOSED"
        assert await _count(ResearchGateDecision) == 0
        assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_UNKNOWN") == 1

        reconciled = await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
        )
        assert reconciled.command_status == "SUCCEEDED"
        assert await _count(ResearchGateDecision) == 13


@pytest.mark.asyncio
async def test_heartbeat_after_checkpoint_keeps_binding_valid_for_finalize(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "finalize-after-heartbeat",
    )
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )

    heartbeat = await claim_service.heartbeat(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )
    result = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )

    assert heartbeat.lease_expires_at >= claimed.lease_expires_at
    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == "REJECTED"


@pytest.mark.asyncio
async def test_tampered_promotion_receipt_rolls_back_gate_and_terminal_writes(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-tampered-promotion",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    original_evaluate = service._promotion.evaluate_command_and_record_in_session

    async def tampered_receipt(*args: Any, **kwargs: Any) -> PromotionResult:
        result = await original_evaluate(*args, **kwargs)
        return replace(result, strict_freeze_receipt_fingerprint="0" * 64)

    monkeypatch.setattr(
        service._promotion,
        "evaluate_command_and_record_in_session",
        tampered_receipt,
    )

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_PROMOTION_INCOMPLETE$"):
        await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )

    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert command is not None and command.status == "RUNNING"
    assert evaluation is not None and evaluation.status == "RUNNING"
    assert epoch is not None and epoch.status == "DISCLOSED"
    assert await _count(ResearchGateDecision) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_REJECTED") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    ["error_code", "lease_heartbeat_at", "lease_token_hash", "lease_expires_at"],
)
async def test_finalize_second_fence_rejects_active_state_drift_after_promotion(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-active-second-fence-{drift}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    original_fence = holdout_finalize_module._second_authority_fence

    async def drift_before_fence(
        session: AsyncSession,
        command: ResearchHoldoutEvaluationCommand,
        **kwargs: Any,
    ) -> None:
        values = {
            "error_code": {"error_code": "FORGED_ACTIVE_ERROR"},
            "lease_heartbeat_at": {"lease_heartbeat_at": None},
            "lease_token_hash": {"lease_token_hash": "0" * 64},
            "lease_expires_at": {
                "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)
            },
        }[drift]
        await _write_constraint_bypassing_drift(
            session,
            command_id=command.id,
            values=values,
        )
        try:
            await original_fence(session, command, **kwargs)
        finally:
            await session.execute(text("PRAGMA ignore_check_constraints = OFF"))

    monkeypatch.setattr(holdout_finalize_module, "_second_authority_fence", drift_before_fence)

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_LEASE_STALE$"):
        await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )

    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert command is not None and command.status == "RUNNING" and command.error_code is None
    assert command.lease_token_hash == sha256(claimed.lease_token.encode()).hexdigest()
    assert _as_utc(command.lease_expires_at) == _as_utc(claimed.lease_expires_at)
    assert command.lease_heartbeat_at is not None
    assert evaluation is not None and evaluation.status == "RUNNING"
    assert epoch is not None and epoch.status == "DISCLOSED"
    assert await _count(ResearchGateDecision) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_COMPLETED") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("drifted_error", [None, "HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN"])
async def test_reconcile_second_fence_rejects_error_drift_after_promotion(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    drifted_error: str | None,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-reconcile-second-fence-error-{drifted_error}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    await _recover_expired_checkpoint(context, claimed, runtime)
    original_fence = holdout_finalize_module._second_authority_fence

    async def clear_error_before_fence(
        session: AsyncSession,
        command: ResearchHoldoutEvaluationCommand,
        **kwargs: Any,
    ) -> None:
        await _write_constraint_bypassing_drift(
            session,
            command_id=command.id,
            values={"error_code": drifted_error},
        )
        try:
            await original_fence(session, command, **kwargs)
        finally:
            await session.execute(text("PRAGMA ignore_check_constraints = OFF"))

    monkeypatch.setattr(
        holdout_finalize_module, "_second_authority_fence", clear_error_before_fence
    )

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_LEASE_STALE$"):
        await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
        )

    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert command is not None and command.status == "RECONCILING"
    assert command.error_code == "HOLDOUT_CLAIM_LEASE_EXPIRED"
    assert evaluation is not None and evaluation.status == "RUNNING"
    assert epoch is not None and epoch.status == "DISCLOSED"
    assert await _count(ResearchGateDecision) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 0


@pytest.mark.asyncio
async def test_reconcile_uses_only_persisted_checkpoint_and_creates_no_new_authority(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "finalize-reconcile")
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    measurements = await _trusted_rejecting_measurements(context)
    checkpoint = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=measurements,
    )
    await _recover_expired_checkpoint(context, claimed, runtime)

    before = {
        "authorization": await _count(ResearchHoldoutAuthorization),
        "evaluation": await _count(ResearchEvaluation),
        "artifact": await _count(ResearchArtifact, kind="sealed_holdout_evidence"),
        "binding": await _count(ResearchHoldoutArtifactBinding),
    }
    result = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
    )
    after = {
        "authorization": await _count(ResearchHoldoutAuthorization),
        "evaluation": await _count(ResearchEvaluation),
        "artifact": await _count(ResearchArtifact, kind="sealed_holdout_evidence"),
        "binding": await _count(ResearchHoldoutArtifactBinding),
    }

    assert result.command_status == "SUCCEEDED"
    assert result.evaluation_status == "REJECTED"
    assert (
        before
        == after
        == {
            "authorization": 1,
            "evaluation": 1,
            "artifact": 1,
            "binding": 1,
        }
    )
    assert checkpoint.artifact_id
    assert await _count(ResearchGateDecision) == 13
    assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 1


@pytest.mark.asyncio
async def test_reconcile_allows_new_worker_with_same_evaluator_identity_and_image(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-reconcile-new-worker",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    await _recover_expired_checkpoint(context, claimed, runtime)

    reconciliation_runtime = replace(runtime, worker_identity="holdout-reconciler-new-worker")
    result = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciliation_runtime,
    )

    assert result.command_status == "SUCCEEDED"
    assert (
        await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=reconciliation_runtime,
        )
        == result
    )
    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT$"):
        await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=replace(
                reconciliation_runtime,
                worker_identity="holdout-reconciler-wrong-worker",
            ),
        )
    async with database.async_session_maker() as session:
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == claimed.command_id
            )
        )
        audit = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "RECONCILE_COMPLETED",
            )
        )
    assert binding is not None and binding.lease_owner == runtime.worker_identity
    assert audit is not None and audit.actor_identity == reconciliation_runtime.worker_identity


@pytest.mark.asyncio
async def test_reconcile_accepts_expiry_recovered_by_new_same_evaluator_workers(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-reconcile-new-recovery-worker",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    recovery_runtime = replace(runtime, worker_identity="holdout-recovery-new-worker")
    reconciliation_runtime = replace(runtime, worker_identity="holdout-reconciler-third-worker")
    await _recover_expired_checkpoint(
        context,
        claimed,
        runtime,
        recovery_runtime=recovery_runtime,
    )

    result = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciliation_runtime,
    )

    assert result.command_status == "SUCCEEDED"
    async with database.async_session_maker() as session:
        recovery_audit = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "LEASE_EXPIRED_RECONCILING",
            )
        )
        terminal_audit = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "RECONCILE_COMPLETED",
            )
        )
    assert recovery_audit is not None
    assert recovery_audit.actor_identity == recovery_runtime.worker_identity
    assert terminal_audit is not None
    assert terminal_audit.actor_identity == reconciliation_runtime.worker_identity


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_was_applied", [True, False])
async def test_reconcile_commit_ack_loss_is_exactly_read_back_or_safely_retried(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    commit_was_applied: bool,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-reconcile-ack-{commit_was_applied}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    await _recover_expired_checkpoint(context, claimed, runtime)
    reconciliation_runtime = replace(runtime, worker_identity="holdout-reconcile-ack-worker")
    original_commit = AsyncSession.commit
    calls = 0

    async def uncertain_commit(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            if commit_was_applied:
                await original_commit(session)
            raise OperationalError("COMMIT", {}, RuntimeError("ack lost"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", uncertain_commit)
    if commit_was_applied:
        result = await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=reconciliation_runtime,
        )
        assert result.command_status == "SUCCEEDED"
        assert await _count(ResearchGateDecision) == 13
        assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 1
        assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_REJECTED") == 0
    else:
        with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN$"):
            await service.reconcile_checkpointed_evaluation(
                command_id=claimed.command_id,
                runtime=reconciliation_runtime,
            )
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
            evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
        assert command is not None and command.status == "RECONCILING"
        assert command.error_code == "HOLDOUT_CLAIM_LEASE_EXPIRED"
        assert evaluation is not None and evaluation.status == "RUNNING"
        assert await _count(ResearchGateDecision) == 0
        assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 0
        assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_REJECTED") == 1

        result = await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=reconciliation_runtime,
        )
        assert result.command_status == "SUCCEEDED"
        assert await _count(ResearchGateDecision) == 13
        assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 1

    replayed = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=reconciliation_runtime,
    )
    assert replayed == result
    assert await _count(ResearchGateDecision) == 13
    assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 1


@pytest.mark.asyncio
async def test_finalize_ack_readback_rejects_cross_action_reconcile_completion(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-cross-action-ack",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    await _recover_expired_checkpoint(context, claimed, runtime)
    reconciled = await service.reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
    )
    finalize_probe = holdout_finalize_module._FinalizeProbe(
        receipt=reconciled,
        runtime=runtime,
        lease_generation=claimed.lease_generation,
        terminal_action="FINALIZE_COMPLETED",
    )

    assert await service._read_committed_finalization(finalize_probe) is None


@pytest.mark.asyncio
async def test_finalize_ack_readback_query_failure_is_fail_closed(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-ack-query-failure",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    finalized = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )
    probe = holdout_finalize_module._FinalizeProbe(
        receipt=finalized,
        runtime=runtime,
        lease_generation=claimed.lease_generation,
        terminal_action="FINALIZE_COMPLETED",
    )

    async def fail_readback_query(*args: Any, **kwargs: Any) -> None:
        raise OperationalError("SELECT", {}, RuntimeError("forced readback failure"))

    monkeypatch.setattr(service._claims, "_lock_claim_graph", fail_readback_query)

    assert await service._read_committed_finalization(probe) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "binding_hash",
        "claim_audit",
        "checkpoint_audit",
        "artifact",
        "binding_owner",
        "authorization",
    ],
)
async def test_promotion_rejects_forged_checkpoint_graph_before_any_gate(
    client,
    auth_user,
    tamper: str,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"promotion-forged-checkpoint-{tamper}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    checkpoint = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert command is not None and command.authorization_id is not None
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == claimed.command_id
            )
        )
        authorization = await session.get(
            ResearchHoldoutAuthorization,
            command.authorization_id,
        )
        claim_audit = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "CLAIM_STARTED",
            )
        )
        checkpoint_audit = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "CHECKPOINT_RECORDED",
            )
        )
        artifact = await session.get(ResearchArtifact, checkpoint.artifact_id)
        assert all(
            value is not None
            for value in (
                binding,
                authorization,
                claim_audit,
                checkpoint_audit,
                artifact,
            )
        )
        if tamper == "binding_hash":
            binding.authority_binding_hash = "0" * 64
        elif tamper == "claim_audit":
            claim_audit.reason_code = "FORGED_CLAIM_STARTED"
        elif tamper == "checkpoint_audit":
            checkpoint_audit.actor_identity = "forged-checkpoint-writer"
        elif tamper == "artifact":
            artifact.size_bytes += 1
        elif tamper == "binding_owner":
            binding.lease_owner = "forged-checkpoint-owner"
        else:
            authorization.capability_evidence_hash = "0" * 64
        await session.commit()

    authority = CommandPromotionAuthority(
        command_id=claimed.command_id,
        candidate_id=claimed.candidate_id,
        evaluation_id=claimed.evaluation_id,
        actor_identity=runtime.worker_identity,
        evaluator_identity=runtime.evaluator_identity,
        evaluator_version=runtime.evaluator_image_digest,
        lease_generation=claimed.lease_generation,
        mode=CommandPromotionMode.ACTIVE,
        lease_token_hash=sha256(claimed.lease_token.encode()).hexdigest(),
    )
    async with database.async_session_maker() as session:
        with pytest.raises(ValueError, match="^PROMOTION_CLAIM_AUTHORITY_INVALID$"):
            await PromotionGateEngine().evaluate_command_and_record_in_session(
                session,
                authority=authority,
                policy=resolve_server_policy("promotion-v1"),
            )
        await session.rollback()
    assert await _count(ResearchGateDecision) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    ["retained_bytes", "content_hash", "size", "schema", "payload_schema"],
)
async def test_finalize_rejects_every_checkpoint_artifact_tamper_before_any_gate(
    client,
    auth_user,
    tamper: str,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-artifact-tamper-{tamper}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    checkpoint = await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        artifact = await session.get(ResearchArtifact, checkpoint.artifact_id)
        retained = await session.get(ResearchArtifactContent, checkpoint.artifact_id)
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == claimed.command_id
            )
        )
        claim_audit = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "CLAIM_STARTED",
            )
        )
        assert command is not None
        assert artifact is not None and retained is not None
        assert binding is not None and claim_audit is not None
        if tamper == "retained_bytes":
            retained.content = bytes(retained.content) + b" "
        elif tamper == "content_hash":
            artifact.content_hash = "0" * 64
        elif tamper == "size":
            artifact.size_bytes += 1
        elif tamper == "schema":
            artifact.schema_version = "forged-sealed-holdout-schema"
        else:
            payload = json.loads(bytes(retained.content))
            payload["schema_version"] = "forged-sealed-holdout-schema"
            forged_content = canonical_json(payload).encode("utf-8")
            forged_digest = sha256(forged_content).hexdigest()
            retained.content = forged_content
            artifact.content_hash = forged_digest
            artifact.size_bytes = len(forged_content)
            artifact.storage_uri = f"controlled://sealed-holdout-evidence/{forged_digest}"
            binding.authority_binding_hash = holdout_finalize_module._authority_binding_hash(
                command,
                artifact=artifact,
                claim_audit=claim_audit,
                lease_owner=binding.lease_owner,
                lease_generation=binding.lease_generation,
                lease_expires_at=_as_utc(binding.lease_expires_at),
            )
        await session.commit()

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_CHECKPOINT_INVALID$"):
        await service.finalize_claimed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )

    assert await _count(ResearchGateDecision) == 0
    assert await _count(ResearchHoldoutAccessAudit, action="FINALIZE_COMPLETED") == 0
    assert await _count(ResearchHoldoutAccessAudit, action="RECONCILE_COMPLETED") == 0


@pytest.mark.asyncio
async def test_terminal_readback_rejects_dual_terminal_audit_ambiguity(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "finalize-dual-terminal-audit",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    finalized = await service.finalize_claimed_evaluation(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )
    async with database.async_session_maker() as session:
        terminal = await session.scalar(
            select(ResearchHoldoutAccessAudit).where(
                ResearchHoldoutAccessAudit.command_id == claimed.command_id,
                ResearchHoldoutAccessAudit.action == "FINALIZE_COMPLETED",
            )
        )
        assert terminal is not None
        session.add(
            ResearchHoldoutAccessAudit(
                actor_identity=terminal.actor_identity,
                evaluator_version=terminal.evaluator_version,
                requested_command_id=terminal.requested_command_id,
                action="RECONCILE_COMPLETED",
                result="ACCEPTED",
                reason_code="HOLDOUT_FINALIZE_RECONCILED",
                command_id=terminal.command_id,
                authorization_id=terminal.authorization_id,
                evaluation_id=terminal.evaluation_id,
                experiment_epoch_id=terminal.experiment_epoch_id,
                candidate_id=terminal.candidate_id,
                dataset_snapshot_id=terminal.dataset_snapshot_id,
                lease_generation=terminal.lease_generation,
                trace_id=terminal.trace_id,
                created_at=terminal.created_at,
            )
        )
        await session.commit()
    probe = holdout_finalize_module._FinalizeProbe(
        receipt=finalized,
        runtime=runtime,
        lease_generation=claimed.lease_generation,
        terminal_action="FINALIZE_COMPLETED",
    )

    assert await service._read_committed_finalization(probe) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("transition_case", ["missing", "conflicting"])
async def test_reconcile_rejects_missing_or_conflicting_transition_audit_before_gates(
    client,
    auth_user,
    transition_case: str,
) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        f"finalize-reconcile-transition-{transition_case}",
    )
    service = HoldoutFinalizeService._for_test_only_inline_measurements()
    await service.checkpoint_claimed_evidence(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
        measurements=await _trusted_rejecting_measurements(context),
    )
    if transition_case == "missing":
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
            assert command is not None
            command.status = "RECONCILING"
            command.error_code = "HOLDOUT_CLAIM_LEASE_EXPIRED"
            command.lease_owner = None
            command.lease_token_hash = None
            command.lease_expires_at = None
            command.lease_heartbeat_at = None
            await session.commit()
    else:
        await _recover_expired_checkpoint(context, claimed, runtime)
        async with database.async_session_maker() as session:
            command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
            assert command is not None
            session.add(
                ResearchHoldoutAccessAudit(
                    actor_identity=runtime.worker_identity,
                    evaluator_version=runtime.evaluator_image_digest,
                    requested_command_id=claimed.command_id,
                    action="FINALIZE_UNKNOWN",
                    result="UNKNOWN",
                    reason_code="HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN",
                    command_id=None,
                    authorization_id=None,
                    evaluation_id=None,
                    experiment_epoch_id=None,
                    candidate_id=None,
                    dataset_snapshot_id=None,
                    lease_generation=None,
                    trace_id=None,
                    created_at=command.updated_at,
                )
            )
            await session.commit()

    with pytest.raises(ValueError, match="^PROMOTION_CLAIM_AUTHORITY_INVALID$"):
        await service.reconcile_checkpointed_evaluation(
            command_id=claimed.command_id,
            runtime=runtime,
        )
    assert await _count(ResearchGateDecision) == 0


async def _claimed_context(client, auth_user, suffix: str):
    context, _headers, command = await _queued_command(client, auth_user, suffix)
    claim_service, runtime = _claim_service(context)
    claimed = await claim_service.claim(command_id=command["id"], runtime=runtime)
    return context, claimed, runtime


async def _recover_expired_checkpoint(
    context,
    claimed,
    runtime,
    *,
    recovery_runtime=None,
) -> None:
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert command is not None
        command.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    claim_service, _runtime = _claim_service(context)
    recovered = await claim_service.recover_expired(
        command_id=claimed.command_id,
        runtime=recovery_runtime or runtime,
    )
    assert recovered.status == "RECONCILING"


async def _write_constraint_bypassing_drift(
    session: AsyncSession,
    *,
    command_id: str,
    values: dict[str, Any],
) -> None:
    await session.execute(text("PRAGMA ignore_check_constraints = ON"))
    await session.execute(
        update(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.id == command_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def _trusted_rejecting_measurements(context: dict[str, Any]) -> dict[str, Any]:
    async with database.async_session_maker() as session:
        candidate = await session.get(
            type(context["candidate"]),
            context["candidate"].id,
            with_for_update=True,
        )
        assert candidate is not None
        receipt = await require_strict_freeze_receipt(session, candidate)
        trial_sharpes, error = await _authoritative_trial_sharpes(
            session,
            candidate=candidate,
            receipt=receipt,
            policy=resolve_server_policy("promotion-v1"),
        )
    assert error is None
    return {"trial_sharpes": trial_sharpes}


async def _trusted_passing_measurements(
    context: dict[str, Any],
    *,
    runtime: Any,
) -> dict[str, Any]:
    measurements = await _trusted_rejecting_measurements(context)
    candidate = context["candidate"]
    scanner_image = f"sha256:{'5' * 64}"
    async with database.async_session_maker() as session:
        discovery = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
        run = await session.get(ResearchRun, candidate.run_id)
        code = await session.get(ResearchArtifact, candidate.code_artifact_id)
        dependency = await session.get(ResearchArtifact, candidate.dependency_artifact_id)
        assert discovery is not None and run is not None
        assert code is not None and dependency is not None
        scan_payload = {
            "schema_version": "security-scan-evidence-v1",
            "candidate_id": candidate.id,
            "candidate_hash": candidate.candidate_hash,
            "code_artifact_id": code.id,
            "code_hash": code.content_hash,
            "dependency_artifact_id": dependency.id,
            "dependency_hash": dependency.content_hash,
            "evaluator_identity": runtime.evaluator_identity,
            "evaluator_version": runtime.evaluator_image_digest,
            "scan_policy_version": "security-scan-policy-v1",
            "scanner_identity": "research-security-scanner",
            "scanner_image_digest": scanner_image,
            "critical_findings": 0,
        }
        retained = canonical_json(scan_payload).encode("utf-8")
        digest = sha256(retained).hexdigest()
        scan_artifact = ResearchArtifact(
            kind="security_scan_evidence",
            content_hash=digest,
            storage_uri=f"controlled://security-scan-evidence/{digest}",
            size_bytes=len(retained),
            media_type="application/json",
            schema_version="security-scan-evidence-v1",
            producer_identity="research-security-scanner",
            container_image_digest=scanner_image,
        )
        session.add(scan_artifact)
        await session.flush()
        session.add(
            ResearchArtifactContent(
                artifact_id=scan_artifact.id,
                content=retained,
            )
        )
        await session.commit()

    measurements.update(
        {
            "returns": [0.01, 0.005, 0.015, 0.002, 0.003, 0.008],
            "discovery_dataset_snapshot_hash": discovery.content_hash,
            "cost_model_hash": candidate.cost_model_hash,
            "environment_hash": candidate.environment_hash,
            "capability_evidence_hash": run.capability_evidence_hash,
            "max_drawdown": 0.10,
            "robustness_score": 0.90,
            "cost_bps": 4.0,
            "slippage_bps": 1.0,
            "turnover": 2.0,
            "capacity_notional": 1_000_000.0,
            "extreme_path_loss": 0.18,
            "execution_semantics_match": True,
            "security_critical_findings": 0,
            "security_scan_hash": digest,
        }
    )
    return measurements


def _measurements_for_exact_evidence_size(
    command: ResearchHoldoutEvaluationCommand,
    authorization: ResearchHoldoutAuthorization,
    *,
    target_size: int,
) -> dict[str, Any]:
    empty_measurements = {"returns": [""]}
    empty_size = len(
        canonical_json(
            holdout_finalize_module._evidence_payload(
                command,
                authorization=authorization,
                measurements=empty_measurements,
            )
        ).encode("utf-8")
    )
    remaining = target_size - empty_size
    assert remaining > 3
    padding = "界" * (remaining // 3) + "x" * (remaining % 3)
    measurements = {"returns": [padding]}
    actual_size = len(
        canonical_json(
            holdout_finalize_module._evidence_payload(
                command,
                authorization=authorization,
                measurements=measurements,
            )
        ).encode("utf-8")
    )
    assert actual_size == target_size
    return measurements


async def _count(model: Any, **filters: object) -> int:
    statement = select(func.count()).select_from(model)
    for key, value in filters.items():
        statement = statement.where(getattr(model, key) == value)
    async with database.async_session_maker() as session:
        return int(await session.scalar(statement) or 0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
