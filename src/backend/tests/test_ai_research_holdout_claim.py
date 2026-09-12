from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import pytest
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
)
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_authorization import (
    IssuedHoldoutAuthorization,
)
from tests.conftest import app
from tests.test_ai_research_holdout_authorization import (
    _create_additional_sealed_snapshot,
    _dataset_registry,
    _drift_sealed_object,
)
from tests.test_ai_research_holdout_request import (
    _request_context,
    _request_payload,
    _request_url,
)

_ACCESS_AUDIT_TABLE = "ai_research_holdout_access_audits"
_AUTHORIZATION_TABLE = "ai_research_holdout_authorizations"
_COMMAND_TABLE = "ai_research_holdout_evaluation_commands"
_EVALUATION_TABLE = "ai_research_evaluations"
_EVALUATOR_IDENTITY = "ai_research_evaluator"
_EVALUATOR_IMAGE = "evaluator-image@sha256:test"


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


@pytest.fixture(autouse=True)
def clear_holdout_claim_overrides() -> None:
    yield
    app.dependency_overrides.pop(research_api.get_dataset_object_resolver, None)
    app.dependency_overrides.pop(research_api.get_holdout_request_service, None)


@pytest.mark.asyncio
async def test_internal_claim_starts_one_consumed_authorization_and_running_evaluation(
    client,
    auth_user,
) -> None:
    context, headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-happy",
    )
    service, runtime = _claim_service(context)
    candidate_hash = context["candidate"].candidate_hash

    claimed = await service.claim(command_id=command["id"], runtime=runtime)

    assert claimed.command_id == command["id"]
    assert claimed.candidate_id == context["candidate"].id
    assert claimed.lease_generation == 1
    assert claimed.lease_token not in repr(claimed)
    assert "lease_token" not in repr(claimed)
    assert not hasattr(claimed, "authorization_token")

    async with database.async_session_maker() as session:
        stored_command = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
        authorizations = list((await session.scalars(select(ResearchHoldoutAuthorization))).all())
        evaluations = list((await session.scalars(select(ResearchEvaluation))).all())
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        candidate = await session.get(ResearchCandidate, context["candidate"].id)
        audits = (
            (
                await session.execute(
                    text(
                        f"SELECT action, result, reason_code, command_id, authorization_id, "
                        f"evaluation_id, experiment_epoch_id, candidate_id, "
                        f"dataset_snapshot_id, lease_generation FROM {_ACCESS_AUDIT_TABLE}"
                    )
                )
            )
            .mappings()
            .all()
        )
        audit_columns = {
            column[1]
            for column in (await session.execute(text(f"PRAGMA table_info({_ACCESS_AUDIT_TABLE})")))
        }

    assert stored_command is not None
    assert stored_command.status == "RUNNING"
    assert stored_command.stage == "HOLDOUT_PENDING"
    assert stored_command.authorization_id == authorizations[0].id
    assert stored_command.evaluation_id == evaluations[0].id
    assert stored_command.lease_owner == runtime.worker_identity
    assert stored_command.lease_token_hash == sha256(claimed.lease_token.encode()).hexdigest()
    assert stored_command.lease_generation == 1
    assert stored_command.attempt_count == 1
    assert stored_command.started_at is not None
    assert stored_command.lease_heartbeat_at is not None
    assert stored_command.lease_expires_at is not None
    assert len(authorizations) == 1
    assert authorizations[0].status == "CONSUMED"
    assert authorizations[0].consumed_at is not None
    assert len(evaluations) == 1
    assert evaluations[0].status == "RUNNING"
    assert evaluations[0].authorization_id == authorizations[0].id
    assert epoch is not None and epoch.status == "DISCLOSED"
    assert candidate is not None and candidate.candidate_hash == candidate_hash
    assert [dict(row) for row in audits] == [
        {
            "action": "CLAIM_STARTED",
            "result": "ACCEPTED",
            "reason_code": "HOLDOUT_CLAIM_STARTED",
            "command_id": command["id"],
            "authorization_id": authorizations[0].id,
            "evaluation_id": evaluations[0].id,
            "experiment_epoch_id": context["candidate"].experiment_epoch_id,
            "candidate_id": context["candidate"].id,
            "dataset_snapshot_id": context["sealed"].id,
            "lease_generation": 1,
        }
    ]
    assert not any(
        fragment in column
        for fragment in ("token", "hash", "uri", "metric", "evidence")
        for column in audit_columns
    )

    recovered = await client.get(
        f"/api/v1/strategy/ai-research/v2/holdout-evaluations/{command['id']}",
        headers=headers,
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["status"] == "RUNNING"
    assert recovered.json()["stage"] == "HOLDOUT_PENDING"
    assert all(
        fragment not in recovered.text.lower()
        for fragment in ("authorization_id", "evaluation_id", "lease", "token")
    )


def test_authorization_issue_result_hides_raw_token_from_repr() -> None:
    issued = IssuedHoldoutAuthorization(authorization=object(), token="raw-secret-token")  # type: ignore[arg-type]

    assert "raw-secret-token" not in repr(issued)
    assert "token=" not in repr(issued)


@pytest.mark.asyncio
async def test_twenty_concurrent_local_claims_start_exactly_once(client, auth_user) -> None:
    """This proves only same-process SQLite behavior; DB constraints remain authoritative."""

    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-concurrent",
    )
    service, runtime = _claim_service(context)

    outcomes = await asyncio.gather(
        *(service.claim(command_id=command["id"], runtime=runtime) for _ in range(20)),
        return_exceptions=True,
    )

    successes = [result for result in outcomes if not isinstance(result, BaseException)]
    failures = [result for result in outcomes if isinstance(result, BaseException)]
    assert len(successes) == 1
    assert len(failures) == 19
    assert {str(result) for result in failures} == {"HOLDOUT_CLAIM_ALREADY_STARTED"}
    assert await _model_count(ResearchHoldoutAuthorization) == 1
    assert await _model_count(ResearchEvaluation) == 1
    assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'ACCEPTED'") == 1
    assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'REJECTED'") == 19


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("needle", "expected_code"),
    [
        (f"insert into {_AUTHORIZATION_TABLE}", "HOLDOUT_CLAIM_PERSISTENCE_FAILED"),
        (f"insert into {_EVALUATION_TABLE}", "HOLDOUT_CLAIM_PERSISTENCE_FAILED"),
        (f"insert into {_ACCESS_AUDIT_TABLE}", "HOLDOUT_CLAIM_AUDIT_UNAVAILABLE"),
        (f"update {_COMMAND_TABLE}", "HOLDOUT_CLAIM_PERSISTENCE_FAILED"),
    ],
)
async def test_claim_child_write_failure_rolls_back_every_authority_mutation(
    client,
    auth_user,
    needle: str,
    expected_code: str,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-atomic-{expected_code}-{needle.split()[0]}",
    )
    service, runtime = _claim_service(context)

    def fail_write(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if needle in statement.lower():
            raise OperationalError(
                statement, parameters, RuntimeError("forced claim write failure")
            )

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", fail_write)
    try:
        with pytest.raises(ValueError, match=expected_code):
            await service.claim(command_id=command["id"], runtime=runtime)
    finally:
        event.remove(sync_engine, "before_cursor_execute", fail_write)

    await _assert_unclaimed(command["id"], context["candidate"].experiment_epoch_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["identity", "profile", "freeze", "request_hash"])
async def test_claim_revalidates_runtime_profile_freeze_and_request_bindings(
    client,
    auth_user,
    drift: str,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-drift-{drift}",
    )
    service, runtime = _claim_service(context)
    if drift == "identity":
        runtime = _runtime(worker_identity="worker-other", evaluator_identity="wrong-evaluator")
    else:
        async with database.async_session_maker() as session:
            if drift == "profile":
                profile = await session.scalar(select(ResearchCapabilityProfile))
                assert profile is not None
                profile.evidence_hash = "f" * 64
            elif drift == "freeze":
                receipt = await session.get(
                    ResearchCandidateFreezeReceipt,
                    command["freeze_receipt_id"],
                )
                assert receipt is not None
                receipt.ledger_hash = "f" * 64
            else:
                stored = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
                assert stored is not None
                stored.request_hash = "f" * 64
            await session.commit()

    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_"):
        await service.claim(command_id=command["id"], runtime=runtime)

    await _assert_unclaimed(command["id"], context["candidate"].experiment_epoch_id)
    assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'REJECTED'") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("partition", ["discovery", "sealed"])
async def test_claim_revalidation_failure_quarantines_exact_bound_snapshot(
    client,
    auth_user,
    partition: str,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-snapshot-drift-{partition}",
    )
    service, runtime = _claim_service(context)
    if partition == "sealed":
        _drift_sealed_object(context)
        expected_snapshot_id = context["sealed"].id
    else:
        expected_snapshot_id = context["candidate"].dataset_snapshot_id
        await _drift_discovery_object(context)

    with pytest.raises(
        ValueError,
        match="DATASET_OBJECT_ATTESTATION_MISMATCH",
    ):
        await service.claim(command_id=command["id"], runtime=runtime)

    await _assert_unclaimed(command["id"], context["candidate"].experiment_epoch_id)
    async with database.async_session_maker() as session:
        snapshot = await session.get(ResearchDatasetSnapshot, expected_snapshot_id)
    assert snapshot is not None
    assert snapshot.integrity_status == "FAILED"
    assert snapshot.integrity_checked_at is not None


@pytest.mark.asyncio
async def test_claim_uses_snapshot_bound_at_queue_time_even_if_same_policy_is_added(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-bound-snapshot",
    )
    added = await _create_additional_sealed_snapshot(context, suffix="post-queue")
    assert added.id != command["dataset_snapshot_id"]
    service, runtime = _claim_service(context)

    claimed = await service.claim(command_id=command["id"], runtime=runtime)

    async with database.async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, claimed.evaluation_id)
    assert evaluation is not None
    assert evaluation.dataset_snapshot_id == command["dataset_snapshot_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("residue", ["authorization", "evaluation"])
async def test_claim_refuses_existing_authority_residue_without_creating_a_second(
    client,
    auth_user,
    residue: str,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-residue-{residue}",
    )
    if residue == "authorization":
        # Public issue now rejects any command-owned epoch.  Insert an
        # otherwise binding-consistent historical/corrupt residue directly so
        # claim still proves it fails closed if such a row already exists.
        authorization = ResearchHoldoutAuthorization(
            experiment_epoch_id=context["candidate"].experiment_epoch_id,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="promotion-v1",
            token_hash=sha256(f"holdout-claim-residue-{residue}".encode()).hexdigest(),
            status="ISSUED",
            evaluator_identity=_EVALUATOR_IDENTITY,
            capability_profile_id=f"holdout-claim-residue-{residue}-profile",
            capability_profile_version="v1",
            capability_evidence_hash="e" * 64,
            issued_by=context["user_id"],
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        async with database.async_session_maker() as session:
            session.add(authorization)
            await session.commit()
            await session.refresh(authorization)
        assert authorization.status == "ISSUED"
    else:
        async with database.async_session_maker() as session:
            session.add(
                ResearchEvaluation(
                    experiment_epoch_id=context["candidate"].experiment_epoch_id,
                    candidate_id=context["candidate"].id,
                    dataset_snapshot_id=context["sealed"].id,
                    evaluation_type="SEALED_HOLDOUT",
                    evaluator_identity=_EVALUATOR_IDENTITY,
                    evaluator_version=_EVALUATOR_IMAGE,
                    authorization_id=None,
                    returns_artifact_id=None,
                    metrics={},
                    gate_inputs={},
                    policy_version="promotion-v1",
                    status="RUNNING",
                    started_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    service, runtime = _claim_service(context)

    with pytest.raises(ValueError, match="HOLDOUT_"):
        await service.claim(command_id=command["id"], runtime=runtime)

    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
        epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
        authorizations = list((await session.scalars(select(ResearchHoldoutAuthorization))).all())
        evaluations = list((await session.scalars(select(ResearchEvaluation))).all())
    assert stored is not None and stored.status == "QUEUED"
    assert stored.authorization_id is None and stored.evaluation_id is None
    assert epoch is not None and epoch.status == "SELECTED"
    assert len(authorizations) == (1 if residue == "authorization" else 0)
    assert len(evaluations) == (1 if residue == "evaluation" else 0)


@pytest.mark.asyncio
async def test_heartbeat_is_fenced_by_owner_token_generation_status_and_database_expiry(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-heartbeat",
    )
    service, runtime = _claim_service(context)
    claimed = await service.claim(command_id=command["id"], runtime=runtime)

    renewed = await service.heartbeat(
        command_id=claimed.command_id,
        runtime=runtime,
        lease_token=claimed.lease_token,
        lease_generation=claimed.lease_generation,
    )
    assert renewed.lease_generation == claimed.lease_generation
    assert renewed.lease_expires_at >= claimed.lease_expires_at

    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_LEASE_STALE"):
        await service.heartbeat(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token="wrong-token",
            lease_generation=claimed.lease_generation,
        )
    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_LEASE_STALE"):
        await service.heartbeat(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation + 1,
        )
    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_LEASE_STALE"):
        await service.heartbeat(
            command_id=claimed.command_id,
            runtime=_runtime(worker_identity="other-worker"),
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )

    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_LEASE_EXPIRED"):
        await service.heartbeat(
            command_id=claimed.command_id,
            runtime=runtime,
            lease_token=claimed.lease_token,
            lease_generation=claimed.lease_generation,
        )


@pytest.mark.asyncio
async def test_expired_running_claim_moves_to_reconciling_without_resigning(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-reconcile",
    )
    service, runtime = _claim_service(context)
    claimed = await service.claim(command_id=command["id"], runtime=runtime)
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        authorization_id = stored.authorization_id
        evaluation_id = stored.evaluation_id
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    recovered = await service.recover_expired(
        command_id=claimed.command_id,
        runtime=runtime,
    )

    assert recovered.status == "RECONCILING"
    assert recovered.stage == "HOLDOUT_PENDING"
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
    assert stored is not None
    assert stored.authorization_id == authorization_id
    assert stored.evaluation_id == evaluation_id
    assert stored.lease_owner is None
    assert stored.lease_token_hash is None
    assert stored.lease_generation == 1
    assert stored.lease_expires_at is None
    assert stored.lease_heartbeat_at is None
    assert (
        await _table_count(
            _ACCESS_AUDIT_TABLE,
            where="action = 'LEASE_EXPIRED_RECONCILING' AND result = 'ACCEPTED'",
        )
        == 1
    )
    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_ALREADY_STARTED"):
        await service.claim(command_id=command["id"], runtime=runtime)
    assert await _model_count(ResearchHoldoutAuthorization) == 1
    assert await _model_count(ResearchEvaluation) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_was_applied", [True, False])
async def test_claim_reconciles_commit_ack_loss_without_blind_second_authorization(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    commit_was_applied: bool,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-commit-unknown-{commit_was_applied}",
    )
    service, runtime = _claim_service(context)
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
        claimed = await service.claim(command_id=command["id"], runtime=runtime)
        assert claimed.command_id == command["id"]
        assert await _model_count(ResearchHoldoutAuthorization) == 1
        assert await _model_count(ResearchEvaluation) == 1
        assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'ACCEPTED'") == 1
        assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'UNKNOWN'") == 0
    else:
        with pytest.raises(ValueError, match="HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN"):
            await service.claim(command_id=command["id"], runtime=runtime)
        async with database.async_session_maker() as session:
            stored = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
            epoch = await session.get(
                ResearchExperimentEpoch,
                context["candidate"].experiment_epoch_id,
            )
        assert stored is not None
        assert stored.status == "RECONCILING"
        assert stored.stage == "REQUEST_HOLDOUT"
        assert stored.error_code == "HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN"
        assert stored.authorization_id is None and stored.evaluation_id is None
        assert stored.lease_generation == 0
        assert stored.lease_owner is None and stored.lease_token_hash is None
        assert epoch is not None and epoch.status == "SELECTED"
        with pytest.raises(ValueError, match="HOLDOUT_CLAIM_ALREADY_STARTED"):
            await service.claim(command_id=command["id"], runtime=runtime)
        assert await _model_count(ResearchHoldoutAuthorization) == 0
        assert await _model_count(ResearchEvaluation) == 0
        assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'UNKNOWN'") == 1


@pytest.mark.asyncio
async def test_unknown_readback_fences_before_a_cross_process_claim_can_escape(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-unknown-fence-race",
    )
    service, runtime = _claim_service(context)
    competing_service, _ = _claim_service(context)
    original_commit = AsyncSession.commit
    calls = 0

    async def unapplied_commit_with_lost_ack(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("COMMIT", {}, RuntimeError("ack lost"))
        await original_commit(session)

    original_readback = service._read_committed_claim
    competing_outcomes: list[str] = []

    async def readback_then_compete(probe: Any):
        result = await original_readback(probe)
        if result is None:
            try:
                await competing_service._claim_once(command_id=command["id"], runtime=runtime)
            except ValueError as exc:
                competing_outcomes.append(str(exc))
            else:
                competing_outcomes.append("LEASE_ESCAPED")
        return result

    monkeypatch.setattr(AsyncSession, "commit", unapplied_commit_with_lost_ack)
    monkeypatch.setattr(service, "_read_committed_claim", readback_then_compete)

    with pytest.raises(ValueError, match="^HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN$"):
        await service.claim(command_id=command["id"], runtime=runtime)

    assert competing_outcomes == ["HOLDOUT_CLAIM_ALREADY_STARTED"]
    assert await _model_count(ResearchHoldoutAuthorization) == 0
    assert await _model_count(ResearchEvaluation) == 0
    assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'UNKNOWN'") == 1


@pytest.mark.asyncio
async def test_running_command_rejects_attempt_generation_drift(client, auth_user) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-attempt-fsm",
    )
    service, runtime = _claim_service(context)
    await service.claim(command_id=command["id"], runtime=runtime)

    async with database.async_session_maker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "UPDATE ai_research_holdout_evaluation_commands "
                    "SET attempt_count = 0 WHERE id = :command_id"
                ),
                {"command_id": command["id"]},
            )
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_unknown_fence_clears_legacy_lease_despite_attempt_counter_drift(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-legacy-attempt-fence",
    )
    service, runtime = _claim_service(context)
    claimed = await service.claim(command_id=command["id"], runtime=runtime)
    module = _claim_contract()
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.attempt_count = 0
        module._fence_unknown_command(stored, occurred_at=datetime.now(timezone.utc))
        assert stored.status == "RECONCILING"
        assert stored.stage == "HOLDOUT_PENDING"
        assert stored.attempt_count == stored.lease_generation == 1
        assert stored.lease_owner is None
        assert stored.lease_token_hash is None
        assert stored.lease_expires_at is None
        assert stored.lease_heartbeat_at is None
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("layer", "tamper_statement"),
    [
        (
            "command",
            "UPDATE ai_research_holdout_evaluation_commands SET trace_id = 'tampered'",
        ),
        (
            "authorization",
            "UPDATE ai_research_holdout_authorizations SET issued_by = 'tampered'",
        ),
        (
            "evaluation",
            "UPDATE ai_research_evaluations SET metrics = '{\"tampered\": true}'",
        ),
        (
            "epoch",
            "UPDATE ai_research_experiment_epochs SET disclosed_at = '2020-01-01 00:00:00'",
        ),
        (
            "audit",
            "UPDATE ai_research_holdout_access_audits SET reason_code = 'TAMPERED' "
            "WHERE action = 'CLAIM_STARTED'",
        ),
    ],
)
async def test_commit_ack_readback_returns_no_lease_when_any_authority_layer_drifted(
    client,
    auth_user,
    monkeypatch: pytest.MonkeyPatch,
    layer: str,
    tamper_statement: str,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-ack-tamper-{layer}",
    )
    service, runtime = _claim_service(context)
    original_commit = AsyncSession.commit
    calls = 0

    async def commit_tamper_then_lose_ack(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            await original_commit(session)
            async with database.async_session_maker() as tamper_session:
                await tamper_session.execute(text(tamper_statement))
                await original_commit(tamper_session)
            raise OperationalError("COMMIT", {}, RuntimeError("ack lost"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", commit_tamper_then_lose_ack)

    with pytest.raises(ValueError, match="^HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN$") as exc_info:
        await service.claim(command_id=command["id"], runtime=runtime)

    assert "token" not in str(exc_info.value).lower()
    assert await _table_count(_ACCESS_AUDIT_TABLE, where="result = 'UNKNOWN'") == 1
    assert await _model_count(ResearchHoldoutAuthorization) == 1
    assert await _model_count(ResearchEvaluation) == 1
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, command["id"])
    assert stored is not None
    assert stored.status == "RECONCILING"
    assert stored.stage == "HOLDOUT_PENDING"
    assert stored.error_code == "HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN"
    assert stored.authorization_id is not None and stored.evaluation_id is not None
    assert stored.lease_generation == 1
    assert stored.lease_owner is None and stored.lease_token_hash is None
    assert stored.lease_expires_at is None and stored.lease_heartbeat_at is None


@pytest.mark.asyncio
async def test_recovery_audit_failure_restores_the_complete_active_lease(
    client,
    auth_user,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-recovery-audit-failure",
    )
    service, runtime = _claim_service(context)
    claimed = await service.claim(command_id=command["id"], runtime=runtime)
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.lease_expires_at = expired_at
        await session.commit()
        expected = {
            "status": stored.status,
            "stage": stored.stage,
            "lease_owner": stored.lease_owner,
            "lease_token_hash": stored.lease_token_hash,
            "lease_generation": stored.lease_generation,
            "lease_expires_at": _utc_time(stored.lease_expires_at),
            "lease_heartbeat_at": _utc_time(stored.lease_heartbeat_at),
            "authorization_id": stored.authorization_id,
            "evaluation_id": stored.evaluation_id,
        }

    def fail_recovery_audit(
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if f"insert into {_ACCESS_AUDIT_TABLE}" in statement.lower():
            raise OperationalError(statement, parameters, RuntimeError("forced audit failure"))

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", fail_recovery_audit)
    try:
        with pytest.raises(ValueError, match="^HOLDOUT_CLAIM_AUDIT_UNAVAILABLE$"):
            await service.recover_expired(command_id=claimed.command_id, runtime=runtime)
    finally:
        event.remove(sync_engine, "before_cursor_execute", fail_recovery_audit)

    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        actual = {
            "status": stored.status,
            "stage": stored.stage,
            "lease_owner": stored.lease_owner,
            "lease_token_hash": stored.lease_token_hash,
            "lease_generation": stored.lease_generation,
            "lease_expires_at": _utc_time(stored.lease_expires_at),
            "lease_heartbeat_at": _utc_time(stored.lease_heartbeat_at),
            "authorization_id": stored.authorization_id,
            "evaluation_id": stored.evaluation_id,
        }
    assert actual == expected
    assert actual["status"] == "RUNNING"
    assert (
        await _table_count(
            _ACCESS_AUDIT_TABLE,
            where="action = 'LEASE_EXPIRED_RECONCILING'",
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transient_condition", ["expired_profile", "resolver_unavailable"])
async def test_expired_lease_static_recovery_does_not_require_live_capability_or_object_probe(
    client,
    auth_user,
    transient_condition: str,
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        f"holdout-claim-static-recovery-{transient_condition}",
    )
    service, runtime = _claim_service(context)
    claimed = await service.claim(command_id=command["id"], runtime=runtime)
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        if transient_condition == "expired_profile":
            profile = await session.scalar(select(ResearchCapabilityProfile))
            assert profile is not None
            profile.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()
    if transient_condition == "resolver_unavailable":
        module = _claim_contract()
        service = module.HoldoutClaimService(
            dataset_registry=DatasetRegistry(),
            lease_seconds=60,
        )

    recovered = await service.recover_expired(
        command_id=claimed.command_id,
        runtime=runtime,
    )

    assert recovered.status == "RECONCILING"
    assert await _model_count(ResearchHoldoutAuthorization) == 1
    assert await _model_count(ResearchEvaluation) == 1


@pytest.mark.asyncio
async def test_expired_lease_recovery_still_requires_bound_runtime_identity(
    client, auth_user
) -> None:
    context, _headers, command = await _queued_command(
        client,
        auth_user,
        "holdout-claim-recovery-runtime",
    )
    service, runtime = _claim_service(context)
    claimed = await service.claim(command_id=command["id"], runtime=runtime)
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
        assert stored is not None
        stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    with pytest.raises(ValueError, match="HOLDOUT_CLAIM_RUNTIME_IDENTITY_MISMATCH"):
        await service.recover_expired(
            command_id=claimed.command_id,
            runtime=_runtime(evaluator_identity="wrong-evaluator"),
        )

    async with database.async_session_maker() as session:
        stored = await session.get(ResearchHoldoutEvaluationCommand, claimed.command_id)
    assert stored is not None and stored.status == "RUNNING"
    assert stored.authorization_id is not None and stored.evaluation_id is not None


@pytest.mark.asyncio
async def test_holdout_claim_schema_has_fenced_state_constraints_and_safe_audit_table() -> None:
    async with database.engine.begin() as connection:
        schema = await connection.run_sync(_claim_schema)

    assert {
        "lease_owner",
        "lease_token_hash",
        "lease_generation",
        "lease_expires_at",
        "lease_heartbeat_at",
        "attempt_count",
        "started_at",
    } <= schema["command_columns"]
    assert _ACCESS_AUDIT_TABLE in schema["tables"]
    assert "uq_ai_research_evaluation_authorization" in schema["evaluation_uniques"]
    assert "ix_ai_research_holdout_command_claim" in schema["command_indexes"]
    assert {
        "ck_ai_research_holdout_command_binding_pair",
        "ck_ai_research_holdout_command_lease_group",
        "ck_ai_research_holdout_command_state_bindings",
        "ck_ai_research_holdout_command_attempt_count",
        "ck_ai_research_holdout_command_lease_generation",
    } <= schema["command_checks"]


async def _queued_command(
    client,
    auth_user,
    suffix: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    context, headers = await _request_context(auth_user, suffix)
    response = await client.post(
        _request_url(context),
        headers={**headers, "Idempotency-Key": suffix},
        json=_request_payload(context),
    )
    assert response.status_code == 202, response.text
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, response.json()["id"])
        assert command is not None
        detached = {
            "id": command.id,
            "freeze_receipt_id": command.freeze_receipt_id,
            "dataset_snapshot_id": command.dataset_snapshot_id,
        }
    return context, headers, detached


def _claim_contract():
    return importlib.import_module("app.services.research.holdout_claim")


def _runtime(
    *,
    worker_identity: str = "holdout-evaluator-worker-1",
    evaluator_identity: str = _EVALUATOR_IDENTITY,
):
    module = _claim_contract()
    return module.HoldoutEvaluatorRuntimeIdentity(
        worker_identity=worker_identity,
        evaluator_identity=evaluator_identity,
        evaluator_image_digest=_EVALUATOR_IMAGE,
    )


def _claim_service(context: dict[str, Any]):
    module = _claim_contract()
    return (
        module.HoldoutClaimService(
            dataset_registry=_dataset_registry(context),
            lease_seconds=60,
        ),
        _runtime(),
    )


async def _assert_unclaimed(command_id: str, epoch_id: str) -> None:
    async with database.async_session_maker() as session:
        command = await session.get(ResearchHoldoutEvaluationCommand, command_id)
        epoch = await session.get(ResearchExperimentEpoch, epoch_id)
        authorizations = await session.scalar(
            select(func.count()).select_from(ResearchHoldoutAuthorization)
        )
        evaluations = await session.scalar(select(func.count()).select_from(ResearchEvaluation))
    assert command is not None
    assert command.status == "QUEUED"
    assert command.stage == "REQUEST_HOLDOUT"
    assert command.authorization_id is None
    assert command.evaluation_id is None
    assert epoch is not None and epoch.status == "SELECTED"
    assert epoch.disclosed_at is None
    assert authorizations == 0
    assert evaluations == 0


async def _model_count(model: Any) -> int:
    async with database.async_session_maker() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _table_count(table_name: str, *, where: str | None = None) -> int:
    clause = f" WHERE {where}" if where is not None else ""
    async with database.async_session_maker() as session:
        return int(await session.scalar(text(f"SELECT COUNT(*) FROM {table_name}{clause}")) or 0)


async def _drift_discovery_object(context: dict[str, Any]) -> None:
    resolver = context["resolver"]
    candidate = context["candidate"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    async with database.async_session_maker() as session:
        snapshot = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
    assert snapshot is not None
    assert snapshot.object_logical_id is not None
    assert snapshot.storage_uri is not None
    resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"{snapshot.object_receipt_id}-claim-drift",
            user_id=context["user_id"],
            logical_object_id=snapshot.object_logical_id,
            object_version="version-drift",
            object_digest="d" * 64,
            object_size_bytes=snapshot.object_size_bytes or 1,
            storage_uri=snapshot.storage_uri,
            attested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        )
    )


def _claim_schema(sync_connection: Any) -> dict[str, set[str]]:
    inspector = inspect(sync_connection)
    return {
        "tables": set(inspector.get_table_names()),
        "command_columns": {column["name"] for column in inspector.get_columns(_COMMAND_TABLE)},
        "command_checks": {
            constraint["name"]
            for constraint in inspector.get_check_constraints(_COMMAND_TABLE)
            if constraint["name"]
        },
        "command_indexes": {
            index["name"] for index in inspector.get_indexes(_COMMAND_TABLE) if index["name"]
        },
        "evaluation_uniques": {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(_EVALUATION_TABLE)
            if constraint["name"]
        },
    }


def _utc_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
