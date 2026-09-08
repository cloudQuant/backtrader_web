from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
)
from app.services.research.canonical import canonical_json
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.holdout_execution_contract import HoldoutExecutionResult
from app.services.research.holdout_execution_journal import HoldoutExecutionJournal
from app.services.research.holdout_finalize import HoldoutFinalizeService
from tests.test_ai_research_holdout_authorization import _dataset_registry
from tests.test_ai_research_holdout_execution_contract import _result_payload
from tests.test_ai_research_holdout_execution_journal import (
    _claimed_context,
    _execution_command,
)
from tests.test_ai_research_holdout_finalize import _trusted_passing_measurements


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


async def _observed_execution(client, auth_user, suffix: str):
    context, claimed, runtime = await _claimed_context(client, auth_user, suffix)
    command = await _execution_command(claimed)
    measurements = await _trusted_passing_measurements(context, runtime=runtime)
    measurements = json.loads(canonical_json(measurements))
    result_payload = _result_payload(command, measurements=measurements)
    result = HoldoutExecutionResult.from_mapping(
        result_payload,
        command=command,
    )
    journal = HoldoutExecutionJournal()
    await journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    assert await journal.begin_dispatch(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    execution = await journal.record_result(
        user_id=context["candidate"].user_id,
        command=command,
        result=result,
    )
    return context, claimed, runtime, command, execution


async def _expire(command_id: str) -> None:
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, command_id)
        assert command is not None
        execution = await session.scalar(
            select(ResearchHoldoutExecution).where(
                ResearchHoldoutExecution.command_id == command_id
            )
        )
        assert execution is not None
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        command.lease_expires_at = expired_at
        execution.lease_expires_at = expired_at
        await session.commit()


@pytest.mark.asyncio
async def test_expired_observed_operation_checkpoints_without_token_or_redispatch(
    client,
    auth_user,
) -> None:
    context, claimed, runtime, _command, execution = await _observed_execution(
        client,
        auth_user,
        "pipeline-expired-observed",
    )
    await _expire(claimed.command_id)
    recovery_runtime = replace(runtime, worker_identity="holdout-recovery-worker-2")

    checkpoint = await HoldoutFinalizeService().checkpoint_observed_execution(
        command_id=claimed.command_id,
        operation_id=execution.operation_id,
        runtime=recovery_runtime,
    )

    assert checkpoint.command_id == claimed.command_id
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        binding = await session.scalar(
            select(ResearchHoldoutArtifactBinding).where(
                ResearchHoldoutArtifactBinding.command_id == claimed.command_id
            )
        )
        stored_execution = await session.scalar(
            select(ResearchHoldoutExecution).where(
                ResearchHoldoutExecution.command_id == claimed.command_id
            )
        )
        audits = list(
            (
                await session.scalars(
                    select(ResearchHoldoutAccessAudit).where(
                        ResearchHoldoutAccessAudit.command_id == claimed.command_id
                    )
                )
            ).all()
        )
    assert command is not None and command.status == "RECONCILING"
    assert command.error_code == "HOLDOUT_EXECUTION_OBSERVED_RECOVERY"
    assert all(
        value is None
        for value in (
            command.lease_owner,
            command.lease_token_hash,
            command.lease_expires_at,
            command.lease_heartbeat_at,
        )
    )
    assert binding is not None and binding.lease_owner == runtime.worker_identity
    assert stored_execution is not None
    assert _as_utc(binding.lease_expires_at) == _as_utc(stored_execution.lease_expires_at)
    by_action = {audit.action: audit for audit in audits}
    assert by_action["CLAIM_STARTED"].actor_identity == runtime.worker_identity
    assert (
        by_action["EXECUTION_OBSERVED_RECONCILING"].actor_identity
        == recovery_runtime.worker_identity
    )
    assert _as_utc(by_action["EXECUTION_OBSERVED_RECONCILING"].created_at) >= _as_utc(
        stored_execution.lease_expires_at
    )
    assert by_action["CHECKPOINT_RECORDED"].actor_identity == recovery_runtime.worker_identity

    finalized = await HoldoutFinalizeService().reconcile_checkpointed_evaluation(
        command_id=claimed.command_id,
        runtime=recovery_runtime,
    )
    assert finalized.evaluation_status == "PASSED"
    package = await EvidencePackageService(
        dataset_registry=_dataset_registry(context)
    ).build_for_terminal_command(
        user_id=context["candidate"].user_id,
        command_id=claimed.command_id,
    )
    assert package.command_id == claimed.command_id


@pytest.mark.asyncio
async def test_observed_recovery_rejects_tampered_result_hash_atomically(
    client,
    auth_user,
) -> None:
    _context, claimed, runtime, _command, execution = await _observed_execution(
        client,
        auth_user,
        "pipeline-tampered-observed",
    )
    await _expire(claimed.command_id)
    async with database.async_session_maker() as session:
        stored = await session.get(type(execution), execution.id)
        assert stored is not None
        stored.result_hash = "0" * 64
        await session.commit()

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_EXECUTION_INVALID$"):
        await HoldoutFinalizeService().checkpoint_observed_execution(
            command_id=claimed.command_id,
            operation_id=execution.operation_id,
            runtime=replace(runtime, worker_identity="recovery-tamper-worker"),
        )

    assert await _count(ResearchArtifact, kind="sealed_holdout_evidence") == 0
    assert await _count(ResearchHoldoutArtifactBinding) == 0


@pytest.mark.asyncio
async def test_observed_recovery_rejects_same_version_policy_material_drift(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, claimed, runtime, _command, execution = await _observed_execution(
        client,
        auth_user,
        "pipeline-policy-drift",
    )
    await _expire(claimed.command_id)
    from app.services.research import promotion

    current = dict(promotion._SERVER_POLICY_CATALOG["promotion-v1"])
    monkeypatch.setitem(
        promotion._SERVER_POLICY_CATALOG,
        "promotion-v1",
        {**current, "max_drawdown": 0.19},
    )

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_EXECUTION_INVALID$"):
        await HoldoutFinalizeService().checkpoint_observed_execution(
            command_id=claimed.command_id,
            operation_id=execution.operation_id,
            runtime=replace(runtime, worker_identity="recovery-policy-drift-worker"),
        )

    assert await _count(ResearchHoldoutArtifactBinding) == 0


@pytest.mark.asyncio
async def test_observed_recovery_requires_expired_lease_and_exact_operation(
    client,
    auth_user,
) -> None:
    _context, claimed, runtime, _command, execution = await _observed_execution(
        client,
        auth_user,
        "pipeline-live-observed",
    )
    service = HoldoutFinalizeService()
    recovery_runtime = replace(runtime, worker_identity="recovery-live-worker")

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_EXECUTION_LEASE_ACTIVE$"):
        await service.checkpoint_observed_execution(
            command_id=claimed.command_id,
            operation_id=execution.operation_id,
            runtime=recovery_runtime,
        )
    await _expire(claimed.command_id)
    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_EXECUTION_INVALID$"):
        await service.checkpoint_observed_execution(
            command_id=claimed.command_id,
            operation_id="0" * 64,
            runtime=recovery_runtime,
        )


@pytest.mark.asyncio
async def test_observed_recovery_rejects_backdated_command_before_journal_lease_expiry(
    client,
    auth_user,
) -> None:
    _context, claimed, runtime, _command, execution = await _observed_execution(
        client,
        auth_user,
        "pipeline-backdated-command-expiry",
    )
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert command is not None
        command.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    with pytest.raises(ValueError, match="^HOLDOUT_FINALIZE_EXECUTION_LEASE_ACTIVE$"):
        await HoldoutFinalizeService().checkpoint_observed_execution(
            command_id=claimed.command_id,
            operation_id=execution.operation_id,
            runtime=replace(runtime, worker_identity="recovery-backdated-expiry-worker"),
        )

    assert await _count(ResearchHoldoutArtifactBinding) == 0


@pytest.mark.asyncio
async def test_observed_recovery_is_exactly_replayable(client, auth_user) -> None:
    _context, claimed, runtime, _command, execution = await _observed_execution(
        client,
        auth_user,
        "pipeline-replay",
    )
    await _expire(claimed.command_id)
    recovery_runtime = replace(runtime, worker_identity="recovery-replay-worker")
    service = HoldoutFinalizeService()

    first = await service.checkpoint_observed_execution(
        command_id=claimed.command_id,
        operation_id=execution.operation_id,
        runtime=recovery_runtime,
    )
    replayed = await service.checkpoint_observed_execution(
        command_id=claimed.command_id,
        operation_id=execution.operation_id,
        runtime=recovery_runtime,
    )

    assert replayed == first
    assert await _count(ResearchHoldoutArtifactBinding) == 1
    assert (
        await _count(
            ResearchHoldoutAccessAudit,
            action="EXECUTION_OBSERVED_RECONCILING",
        )
        == 1
    )


async def _count(model, **filters: object) -> int:
    async with database.async_session_maker() as session:
        statement = select(func.count()).select_from(model)
        for name, value in filters.items():
            statement = statement.where(getattr(model, name) == value)
        return int(await session.scalar(statement) or 0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
