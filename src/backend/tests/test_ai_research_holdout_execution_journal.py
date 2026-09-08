from __future__ import annotations

import asyncio
from hashlib import sha256
from importlib import import_module

import pytest
from sqlalchemy import inspect

from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import ResearchHoldoutEvaluationCommand
from tests import test_ai_research_holdout_claim as claim_tests
from tests import test_ai_research_holdout_request as request_tests
from tests.test_ai_research_holdout_execution_contract import _result_payload
from tests.test_ai_research_holdout_finalize import _claimed_context as _legacy_claimed_context


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


async def _claimed_context(client, auth_user, suffix: str):
    image_digest = f"sha256:{'5' * 64}"
    old_request_image = request_tests._EVALUATOR_IMAGE
    old_claim_image = claim_tests._EVALUATOR_IMAGE
    request_tests._EVALUATOR_IMAGE = image_digest
    claim_tests._EVALUATOR_IMAGE = image_digest
    try:
        return await _legacy_claimed_context(client, auth_user, suffix)
    finally:
        request_tests._EVALUATOR_IMAGE = old_request_image
        claim_tests._EVALUATOR_IMAGE = old_claim_image


def _modules():
    return (
        import_module("app.services.research.holdout_execution_contract"),
        import_module("app.services.research.holdout_execution_journal"),
    )


async def _execution_command(claimed):
    contract, _journal = _modules()
    promotion = import_module("app.services.research.promotion")
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert command is not None
    operation_id = sha256(f"holdout-operation:{command.id}".encode()).hexdigest()
    return contract.HoldoutExecutionCommand.from_mapping(
        {
            "schema_version": "holdout-execution-command-v2",
            "operation_id": operation_id,
            "command_id": command.id,
            "evaluation_id": command.evaluation_id,
            "authorization_id": command.authorization_id,
            "experiment_epoch_id": command.experiment_epoch_id,
            "request_hash": command.request_hash,
            "candidate_id": command.candidate_id,
            "candidate_hash": command.candidate_hash,
            "dataset_snapshot_id": command.dataset_snapshot_id,
            "sealed_dataset_hash": command.sealed_dataset_hash,
            "sealed_dataset_identity_hash": command.sealed_dataset_identity_hash,
            "freeze_receipt_fingerprint": command.freeze_receipt_fingerprint,
            "capability_evidence_hash": command.capability_evidence_hash,
            "policy_version": command.policy_version,
            "promotion_policy_hash": promotion.promotion_policy_material_hash(
                promotion.resolve_server_policy(command.policy_version)
            ),
            "evaluator_identity": command.evaluator_identity,
            "evaluator_image_digest": f"sha256:{'5' * 64}",
            "lease_generation": command.lease_generation,
        }
    )


@pytest.mark.asyncio
async def test_prepare_is_durable_exactly_idempotent_and_contains_no_authority_secret(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "journal-prepare")
    command = await _execution_command(claimed)
    _contract, journal_module = _modules()
    journal = journal_module.HoldoutExecutionJournal()

    first = await journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    replayed = await journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )

    assert replayed.id == first.id
    assert first.state == "PREPARED"
    assert first.lease_expires_at is not None
    serialized = str(first.command_json).lower()
    assert all(fragment not in serialized for fragment in ("token", "uri", "url", "path"))
    async with database.async_session_maker() as session:
        columns = await session.run_sync(
            lambda sync_session: {
                column["name"]
                for column in inspect(sync_session.connection()).get_columns(
                    "ai_research_holdout_executions"
                )
            }
        )
    assert not any("token" in name or "secret" in name or "uri" in name for name in columns)


@pytest.mark.asyncio
async def test_concurrent_begin_dispatch_has_exactly_one_winner(client, auth_user) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "journal-dispatch")
    command = await _execution_command(claimed)
    _contract, journal_module = _modules()
    journal = journal_module.HoldoutExecutionJournal()
    await journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )

    outcomes = await asyncio.gather(
        *(
            journal.begin_dispatch(
                user_id=context["candidate"].user_id,
                lease_owner=runtime.worker_identity,
                command=command,
            )
            for _ in range(20)
        )
    )

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 19
    record = await journal.read(command=command, user_id=context["candidate"].user_id)
    assert record.state == "IN_FLIGHT"
    assert record.dispatched_at is not None


@pytest.mark.asyncio
async def test_unknown_can_only_rearm_after_not_executed_inspection(client, auth_user) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "journal-unknown")
    command = await _execution_command(claimed)
    _contract, journal_module = _modules()
    journal = journal_module.HoldoutExecutionJournal()
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

    unknown = await journal.record_unknown(
        user_id=context["candidate"].user_id,
        command=command,
        error_code="HOLDOUT_HTTP_EXECUTOR_TIMEOUT",
    )
    assert unknown.state == "UNKNOWN"
    async with database.async_session_maker() as session:
        fenced = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
    assert fenced is not None and fenced.status == "RECONCILING"
    assert fenced.error_code == "HOLDOUT_EXECUTION_OUTCOME_UNKNOWN"
    assert all(
        value is None
        for value in (
            fenced.lease_owner,
            fenced.lease_token_hash,
            fenced.lease_expires_at,
            fenced.lease_heartbeat_at,
        )
    )
    assert not await journal.begin_dispatch(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )

    prepared = await journal.record_not_executed(
        user_id=context["candidate"].user_id,
        command=command,
        inspection=_not_executed_inspection(command),
    )
    assert prepared.state == "PREPARED"
    assert prepared.not_executed_at is not None
    assert await journal.begin_dispatch(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )


@pytest.mark.asyncio
async def test_not_executed_proof_is_bound_to_the_exact_operation(client, auth_user) -> None:
    context, claimed, runtime = await _claimed_context(
        client,
        auth_user,
        "journal-not-executed-proof",
    )
    command = await _execution_command(claimed)
    _contract, journal_module = _modules()
    journal = journal_module.HoldoutExecutionJournal()
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
    forged_payload = command.snapshot
    forged_payload["operation_id"] = "f" * 64
    contract, _journal_module = _modules()
    forged_command = contract.HoldoutExecutionCommand.from_mapping(forged_payload)

    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_TRANSITION_DENIED$"):
        await journal.record_not_executed(
            user_id=context["candidate"].user_id,
            command=command,
            inspection=_not_executed_inspection(forged_command),
        )


def _not_executed_inspection(command):
    contract, _journal = _modules()
    snapshot = command.snapshot
    return contract.HoldoutExecutionInspection.from_mapping(
        {
            "schema_version": "holdout-execution-inspection-v2",
            "operation_id": snapshot["operation_id"],
            "command_hash": command.command_hash,
            "evaluator_identity": snapshot["evaluator_identity"],
            "evaluator_image_digest": snapshot["evaluator_image_digest"],
            "status": "NOT_EXECUTED",
            "result": None,
            "error_code": None,
        },
        command=command,
    )


@pytest.mark.asyncio
async def test_observed_result_is_immutable_and_settlement_is_idempotent(client, auth_user) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "journal-observed")
    command = await _execution_command(claimed)
    contract, journal_module = _modules()
    journal = journal_module.HoldoutExecutionJournal()
    await journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    await journal.begin_dispatch(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    raw_canary = 0.9876543219876543
    result = contract.HoldoutExecutionResult.from_mapping(
        _result_payload(command, measurements={"returns": [raw_canary]}),
        command=command,
    )

    observed = await journal.record_result(
        user_id=context["candidate"].user_id,
        command=command,
        result=result,
    )
    replayed = await journal.record_result(
        user_id=context["candidate"].user_id,
        command=command,
        result=result,
    )

    assert replayed.id == observed.id
    assert observed.state == "OBSERVED"
    assert observed.result_hash == sha256(result.payload).hexdigest()
    serialized = str(observed.result_json)
    assert "returns" not in serialized
    assert str(raw_canary) not in serialized
    settled = await journal.settle(user_id=context["candidate"].user_id, command=command)
    assert settled.state == "SETTLED"
    assert (
        await journal.settle(user_id=context["candidate"].user_id, command=command)
    ).id == settled.id

    forged = contract.HoldoutExecutionResult.from_mapping(
        _result_payload(command, measurements={}),
        command=command,
    )
    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_RESULT_CONFLICT$"):
        await journal.record_result(
            user_id=context["candidate"].user_id,
            command=command,
            result=forged,
        )


@pytest.mark.asyncio
async def test_prepare_rejects_command_not_bound_to_the_live_claim(client, auth_user) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "journal-binding")
    command = await _execution_command(claimed)
    contract, journal_module = _modules()
    forged = command.snapshot
    forged["request_hash"] = "0" * 64
    forged_command = contract.HoldoutExecutionCommand.from_mapping(forged)

    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_PREPARE_DENIED$"):
        await journal_module.HoldoutExecutionJournal().prepare(
            user_id=context["candidate"].user_id,
            lease_owner=runtime.worker_identity,
            command=forged_command,
        )


@pytest.mark.asyncio
async def test_observed_result_may_be_recovered_from_unknown_without_redispatch(
    client,
    auth_user,
) -> None:
    context, claimed, runtime = await _claimed_context(client, auth_user, "journal-recover")
    command = await _execution_command(claimed)
    contract, journal_module = _modules()
    journal = journal_module.HoldoutExecutionJournal()
    await journal.prepare(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    await journal.begin_dispatch(
        user_id=context["candidate"].user_id,
        lease_owner=runtime.worker_identity,
        command=command,
    )
    await journal.record_unknown(
        user_id=context["candidate"].user_id,
        command=command,
        error_code="HOLDOUT_HTTP_EXECUTOR_TIMEOUT",
    )
    result = contract.HoldoutExecutionResult.from_mapping(
        _result_payload(command),
        command=command,
    )

    recovered = await journal.record_result(
        user_id=context["candidate"].user_id,
        command=command,
        result=result,
    )

    assert recovered.state == "OBSERVED"
    assert recovered.observed_at is not None
