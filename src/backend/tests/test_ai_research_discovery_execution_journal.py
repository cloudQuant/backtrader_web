from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchDiscoveryExecution,
    ResearchExperimentEpoch,
    ResearchHypothesisVersion,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.models.user import User
from app.services.research import discovery_execution_journal as journal_module
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.discovery_execution_contract import (
    DiscoveryExecutionCommand,
    DiscoveryExecutionResult,
)
from app.services.research.discovery_execution_journal import DiscoveryExecutionJournal


@pytest_asyncio.fixture
async def independent_journal_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """Use independent SQLite connections for the receipt uniqueness race."""

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'discovery-journal.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            await connection.run_sync(database.Base.metadata.create_all)
        with monkeypatch.context() as local_patch:
            local_patch.setattr(database, "async_session_maker", sessions)
            yield
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prepare_persists_a_canonical_command_and_is_idempotent() -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    journal = DiscoveryExecutionJournal()

    prepared = await journal.prepare(user_id=_user_id(context), command=command)
    repeated = await journal.prepare(user_id=_user_id(context), command=command)

    assert prepared.id == sha256(command.snapshot["operation_id"].encode("utf-8")).hexdigest()
    assert repeated.id == prepared.id
    assert prepared.status == "PREPARED"
    assert prepared.command_hash == command.request_hash
    assert prepared.result_json is None
    assert canonical_json(prepared.command_json).encode("utf-8") == command.payload

    detached = command.snapshot
    detached["params"]["lookback"] = 999
    async with database.async_session_maker() as session:
        stored = await session.get(ResearchDiscoveryExecution, prepared.id)
    assert stored is not None
    assert stored.command_json["params"] == {"lookback": 20, "symbols": ["RB0"]}


@pytest.mark.asyncio
async def test_prepare_rejects_a_different_command_for_the_same_stage_or_receipt() -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    journal = DiscoveryExecutionJournal()
    await journal.prepare(user_id=_user_id(context), command=command)

    different_operation = _command(context, operation_id="discovery-operation-2")
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_PREPARE_CONFLICT"):
        await journal.prepare(user_id=_user_id(context), command=different_operation)

    same_operation_different_payload = _command(
        context,
        mutate=lambda payload: payload["params"].update({"lookback": 30}),
    )
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_PREPARE_CONFLICT"):
        await journal.prepare(user_id=_user_id(context), command=same_operation_different_payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation",
    (
        "expired_task_lease",
        "frozen_candidate",
        "reservation_window",
        "intent",
        "short_lease",
        "run_epoch_group",
        "run_dataset_group",
    ),
)
async def test_prepare_requires_a_live_mutable_single_receipt_intent(revocation: str) -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    now = datetime.now(timezone.utc)
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, _task_id(context))
        candidate = await session.get(ResearchCandidate, _candidate_id(context))
        reservation = await session.get(ResearchQuotaReservation, _reservation_id(context))
        bucket = await session.get(ResearchQuotaBucket, _bucket_id(context))
        assert task is not None
        assert candidate is not None
        assert reservation is not None
        assert bucket is not None
        if revocation == "expired_task_lease":
            task.lease_expires_at = now - timedelta(seconds=1)
        elif revocation == "frozen_candidate":
            candidate.freeze_status = "FROZEN"
        elif revocation == "reservation_window":
            bucket.window_end = now - timedelta(seconds=1)
        elif revocation == "intent":
            reservation.reservation_context = {
                "schema_version": "discovery-execution-intent-v1",
                "inputs": {"not": "the command"},
            }
            reservation.request_hash = content_hash(reservation.reservation_context)
        elif revocation == "short_lease":
            reservation.lease_expires_at = now + timedelta(seconds=100)
        elif revocation == "run_epoch_group":
            run = await session.get(ResearchRun, _run(context).id)
            assert run is not None
            run.experiment_epoch_id = None
        else:
            run = await session.get(ResearchRun, _run(context).id)
            assert run is not None
            run.dataset_snapshot_id = None
        await session.commit()

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_PREPARE_DENIED"):
        await DiscoveryExecutionJournal().prepare(user_id=_user_id(context), command=command)


@pytest.mark.asyncio
async def test_record_result_needs_a_claimed_dispatch_but_survives_a_late_task_lease() -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    journal = DiscoveryExecutionJournal()
    prepared = await journal.prepare(user_id=_user_id(context), command=command)
    result = _result(command)

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_DISPATCH_REQUIRED"):
        await journal.record_result(user_id=_user_id(context), command=command, result=result)

    await _mark_dispatched(context, command)
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, _task_id(context))
        assert task is not None
        task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    observed = await journal.record_result(
        user_id=_user_id(context), command=command, result=result
    )
    repeated = await journal.record_result(
        user_id=_user_id(context), command=command, result=result
    )

    assert observed.id == prepared.id
    assert repeated.id == prepared.id
    assert observed.status == "OBSERVED"
    assert observed.result_json == result.snapshot

    conflicting = _result(
        command,
        mutate=lambda payload: payload.update(
            {
                "status": "FAILED",
                "exit_code": 2,
                "error_code": "EXECUTION_FAILED",
            }
        ),
    )
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_CONFLICT"):
        await journal.record_result(user_id=_user_id(context), command=command, result=conflicting)


@pytest.mark.asyncio
@pytest.mark.parametrize("reservation_status", ("IN_FLIGHT", "RECONCILING", "SETTLED"))
async def test_record_result_accepts_only_a_persisted_dispatched_receipt(
    reservation_status: str,
) -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    journal = DiscoveryExecutionJournal()
    await journal.prepare(user_id=_user_id(context), command=command)
    await _mark_dispatched(context, command, status=reservation_status)

    observed = await journal.record_result(
        user_id=_user_id(context), command=command, result=_result(command)
    )

    assert observed.status == "OBSERVED"


@pytest.mark.asyncio
async def test_unknown_requires_dispatch_is_idempotent_and_never_downgrades_observed() -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    journal = DiscoveryExecutionJournal()
    await journal.prepare(user_id=_user_id(context), command=command)

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_UNKNOWN_DISPATCH_REQUIRED"):
        await journal.record_unknown(
            user_id=_user_id(context), command=command, error_code="RUNNER_TIMEOUT"
        )

    await _mark_dispatched(context, command)
    unknown = await journal.record_unknown(
        user_id=_user_id(context), command=command, error_code="RUNNER_TIMEOUT"
    )
    repeated = await journal.record_unknown(
        user_id=_user_id(context), command=command, error_code="RUNNER_TIMEOUT"
    )
    assert unknown.status == repeated.status == "UNKNOWN"
    assert unknown.error_code == "RUNNER_TIMEOUT"

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_UNKNOWN_CONFLICT"):
        await journal.record_unknown(
            user_id=_user_id(context), command=command, error_code="NETWORK_TIMEOUT"
        )

    observed = await journal.record_result(
        user_id=_user_id(context), command=command, result=_result(command)
    )
    preserved = await journal.record_unknown(
        user_id=_user_id(context), command=command, error_code="RUNNER_TIMEOUT"
    )
    assert observed.status == preserved.status == "OBSERVED"

    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, _reservation_id(context))
    assert reservation is not None
    assert reservation.status == "IN_FLIGHT"


@pytest.mark.asyncio
async def test_prepare_concurrent_independent_connections_return_one_receipt(
    independent_journal_database: None,
) -> None:
    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)

    first, second = await asyncio.gather(
        DiscoveryExecutionJournal().prepare(user_id=_user_id(context), command=command),
        DiscoveryExecutionJournal().prepare(user_id=_user_id(context), command=command),
    )

    assert first.id == second.id
    async with database.async_session_maker() as session:
        count = await session.scalar(select(func.count(ResearchDiscoveryExecution.id)))
    assert count == 1


@pytest.mark.asyncio
async def test_known_result_promotes_a_concurrent_unknown_receipt_on_sqlite(
    independent_journal_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the real SQLite result/unknown race preserves known evidence.

    This is a behavior proof, not a regression fix: the result path reads the
    pre-existing ``PREPARED`` receipt, a concurrent timeout records ``UNKNOWN``,
    and the delayed known result must promote that receipt to ``OBSERVED``.
    """

    context = await _context()
    command = _command(context)
    await _bind_reservation_intent(context, command)
    journal = DiscoveryExecutionJournal()
    await journal.prepare(user_id=_user_id(context), command=command)
    await _mark_dispatched(context, command)

    result_checked_dispatch = asyncio.Event()
    resume_result = asyncio.Event()
    original_require_dispatch = journal_module._require_recorded_dispatch

    async def pause_result_after_dispatch_check(*args, **kwargs):
        await original_require_dispatch(*args, **kwargs)
        if kwargs["denied_code"] == "DISCOVERY_EXECUTION_RESULT_DISPATCH_REQUIRED":
            result_checked_dispatch.set()
            await resume_result.wait()

    monkeypatch.setattr(
        journal_module, "_require_recorded_dispatch", pause_result_after_dispatch_check
    )
    result_task = asyncio.create_task(
        journal.record_result(user_id=_user_id(context), command=command, result=_result(command))
    )
    await asyncio.wait_for(result_checked_dispatch.wait(), timeout=5)

    unknown = await journal.record_unknown(
        user_id=_user_id(context), command=command, error_code="RUNNER_TIMEOUT"
    )
    resume_result.set()
    observed = await asyncio.wait_for(result_task, timeout=5)

    assert unknown.status == "UNKNOWN"
    assert observed.status == "OBSERVED"
    assert observed.result_json == _result(command).snapshot


async def _context() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    async with database.async_session_maker() as session:
        user = User(
            username="discovery-journal-user",
            email="discovery-journal-user@example.test",
            hashed_password="fixture",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        hypothesis = ResearchHypothesisVersion(
            user_id=user.id,
            hypothesis_id="discovery-journal-hypothesis",
            version_no=1,
            status="CONFIRMED",
            canonical_payload={"question": "does discovery validation preserve receipts"},
            content_hash="a" * 64,
        )
        session.add(hypothesis)
        await session.flush()
        epoch = ResearchExperimentEpoch(
            user_id=user.id,
            hypothesis_version_id=hypothesis.id,
            family_hash="b" * 64,
            search_budget={"max_trials": 5},
            dataset_policy_version="dataset-policy-v1",
            status="OPEN",
        )
        dataset = ResearchDatasetSnapshot(
            user_id=user.id,
            dataset_policy_version="dataset-policy-v1",
            partition_kind="DISCOVERY",
            instrument_manifest={"symbols": ["RB0"]},
            split_manifest={"train": "2024", "validation": "2025"},
            source_manifest={"provider": "fixture"},
            execution_policy={"engine": "backtrader", "seed": 7},
            point_in_time_cutoff=now - timedelta(days=1),
            content_hash="c" * 64,
            storage_uri="controlled://fixture/discovery.parquet",
            storage_reference_hash="d" * 64,
            object_receipt_id="dataset-receipt-1",
            object_logical_id="dataset-object-1",
            object_version="v1",
            object_digest="e" * 64,
            object_size_bytes=2_048,
            integrity_status="VERIFIED",
            integrity_checked_at=now,
            integrity_receipt_hash="f" * 64,
            snapshot_identity_hash="1" * 64,
            license_tags=["fixture"],
        )
        code = ResearchArtifact(
            kind="strategy_code",
            content_hash="2" * 64,
            storage_uri="controlled://fixture/strategy.py",
            size_bytes=512,
            media_type="text/x-python",
            schema_version="v1",
            producer_identity="fixture",
        )
        dependencies = ResearchArtifact(
            kind="dependency_lock",
            content_hash="3" * 64,
            storage_uri="controlled://fixture/requirements.lock",
            size_bytes=128,
            media_type="text/plain",
            schema_version="v1",
            producer_identity="fixture",
        )
        session.add_all([epoch, dataset, code, dependencies])
        await session.flush()
        run = ResearchRun(
            user_id=user.id,
            hypothesis_version_id=hypothesis.id,
            dataset_snapshot_id=dataset.id,
            experiment_epoch_id=epoch.id,
            status="RUNNING",
            stage_cursor="VALIDATE_DISCOVERY",
            promotion_policy_version="promotion-v1",
            request_hash="4" * 64,
            capability_profile_id="discovery-profile",
            capability_profile_version="v1",
            capability_evidence_hash="5" * 64,
            trace_id="trace-discovery-journal",
        )
        session.add(run)
        await session.flush()
        candidate = ResearchCandidate(
            user_id=user.id,
            run_id=run.id,
            experiment_epoch_id=epoch.id,
            dataset_snapshot_id=dataset.id,
            code_artifact_id=code.id,
            dependency_artifact_id=dependencies.id,
            candidate_hash="6" * 64,
            environment_hash="7" * 64,
            cost_model_hash="8" * 64,
            params={"lookback": 20, "symbols": ["RB0"]},
            freeze_status="MUTABLE",
        )
        task = ResearchTask(
            user_id=user.id,
            run_id=run.id,
            status="RUNNING",
            stage_cursor="VALIDATE_DISCOVERY",
            request_json={},
            idempotency_key="discovery-journal-task",
            idempotency_request_hash="9" * 64,
            lease_token="discovery-lease-token",
            lease_expires_at=now + timedelta(minutes=15),
            lease_heartbeat_at=now,
        )
        session.add_all([candidate, task])
        await session.flush()
        attempt = ResearchStageAttempt(
            run_id=run.id,
            task_id=task.id,
            stage="VALIDATE_DISCOVERY",
            attempt_no=1,
            idempotency_key="discovery-journal-attempt",
            status="RUNNING",
            lease_token=task.lease_token,
            input_hash="a" * 64,
        )
        bucket = ResearchQuotaBucket(
            scope_type="user",
            scope_id=user.id,
            policy_version="quota-v1",
            resource_type="sandbox_seconds",
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=1_000,
            concurrency_limit=5,
            status="ACTIVE",
        )
        session.add_all([attempt, bucket])
        await session.flush()
        reservation = ResearchQuotaReservation(
            bucket_id=bucket.id,
            task_id=task.id,
            stage_attempt_id=attempt.id,
            idempotency_key="discovery-journal-reservation",
            resource_type="sandbox_seconds",
            reserved_amount=120,
            unit="seconds",
            status="RESERVED",
            lease_expires_at=now + timedelta(minutes=15),
            fencing_token=1,
            policy_version="quota-v1",
            request_hash="b" * 64,
            reason="discovery validation",
        )
        session.add(reservation)
        await session.commit()
        return {
            "user": user,
            "run": run,
            "task": task,
            "attempt": attempt,
            "candidate": candidate,
            "dataset": dataset,
            "code": code,
            "dependencies": dependencies,
            "bucket": bucket,
            "reservation": reservation,
        }


async def _bind_reservation_intent(
    context: dict[str, object], command: DiscoveryExecutionCommand
) -> None:
    intent = _intent(command)
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, _reservation_id(context))
        assert reservation is not None
        reservation.reservation_context = deepcopy(intent)
        reservation.request_hash = content_hash(intent)
        await session.commit()


async def _mark_dispatched(
    context: dict[str, object],
    command: DiscoveryExecutionCommand,
    *,
    status: str = "IN_FLIGHT",
) -> None:
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, _reservation_id(context))
        assert reservation is not None
        reservation.status = status
        reservation.provider_operation_id = command.snapshot["operation_id"]
        await session.commit()


def _command(
    context: dict[str, object],
    *,
    operation_id: str = "discovery-operation-1",
    mutate=None,
) -> DiscoveryExecutionCommand:
    task = _task(context)
    run = _run(context)
    attempt = _attempt(context)
    candidate = _candidate(context)
    dataset = _dataset(context)
    code = _code(context)
    dependencies = _dependencies(context)
    reservation = _reservation(context)
    assert task.lease_token is not None
    payload: dict[str, object] = {
        "schema_version": "discovery-execution-command-v1",
        "operation_id": operation_id,
        "task_id": task.id,
        "run_id": run.id,
        "stage_attempt_id": attempt.id,
        "candidate_id": candidate.id,
        "stage": "VALIDATE_DISCOVERY",
        "candidate_hash": candidate.candidate_hash,
        "run_request_hash": run.request_hash,
        "lease_token_hash": sha256(task.lease_token.encode("utf-8")).hexdigest(),
        "environment_hash": candidate.environment_hash,
        "cost_model_hash": candidate.cost_model_hash,
        "runner_identity": "discovery-runner-v1",
        "profile": {
            "id": run.capability_profile_id,
            "version": run.capability_profile_version,
            "evidence_hash": run.capability_evidence_hash,
        },
        "quota": {"reservation_id": reservation.id, "fencing_token": reservation.fencing_token},
        "code": {
            "artifact_id": code.id,
            "content_hash": code.content_hash,
            "size_bytes": code.size_bytes,
        },
        "dependencies": {
            "artifact_id": dependencies.id,
            "content_hash": dependencies.content_hash,
            "size_bytes": dependencies.size_bytes,
        },
        "dataset": {
            "snapshot_id": dataset.id,
            "snapshot_identity_hash": dataset.snapshot_identity_hash,
            "object_receipt_id": dataset.object_receipt_id,
            "object_digest": dataset.object_digest,
            "object_size_bytes": dataset.object_size_bytes,
            "partition_kind": dataset.partition_kind,
        },
        "params": deepcopy(candidate.params),
        "execution_policy": deepcopy(dataset.execution_policy),
        "policy": {
            "version": "discovery-policy-v1",
            "image_digest": f"sha256:{'9' * 64}",
            "network_mode": "none",
            "input_read_only": True,
            "output_path": "/sandbox/output",
            "cpu_limit": 1,
            "memory_limit_mb": 256,
            "pid_limit": 64,
            "wall_timeout_seconds": 30,
            "output_limit_bytes": 1_000_000,
        },
    }
    if mutate is not None:
        mutate(payload)
    return DiscoveryExecutionCommand.from_mapping(payload)


def _result(
    command: DiscoveryExecutionCommand,
    *,
    mutate=None,
) -> DiscoveryExecutionResult:
    snapshot = command.snapshot
    payload: dict[str, object] = {
        "schema_version": "discovery-execution-result-v1",
        "operation_id": snapshot["operation_id"],
        "command_hash": command.request_hash,
        "runner_identity": snapshot["runner_identity"],
        "image_digest": snapshot["policy"]["image_digest"],
        "status": "SUCCEEDED",
        "exit_code": 0,
        "elapsed_milliseconds": 500,
        "observed_market_performance": True,
        "returns": [0.01, -0.005],
        "error_code": None,
    }
    if mutate is not None:
        mutate(payload)
    return DiscoveryExecutionResult.from_mapping(payload, command=command)


def _intent(command: DiscoveryExecutionCommand) -> dict[str, object]:
    snapshot = command.snapshot
    return {
        "schema_version": "discovery-execution-intent-v1",
        "inputs": {
            key: value for key, value in snapshot.items() if key not in {"operation_id", "quota"}
        },
    }


def _user_id(context: dict[str, object]) -> str:
    return _user(context).id


def _task_id(context: dict[str, object]) -> str:
    return _task(context).id


def _candidate_id(context: dict[str, object]) -> str:
    return _candidate(context).id


def _reservation_id(context: dict[str, object]) -> str:
    return _reservation(context).id


def _bucket_id(context: dict[str, object]) -> str:
    return _bucket(context).id


def _user(context: dict[str, object]) -> User:
    value = context["user"]
    assert isinstance(value, User)
    return value


def _run(context: dict[str, object]) -> ResearchRun:
    value = context["run"]
    assert isinstance(value, ResearchRun)
    return value


def _task(context: dict[str, object]) -> ResearchTask:
    value = context["task"]
    assert isinstance(value, ResearchTask)
    return value


def _attempt(context: dict[str, object]) -> ResearchStageAttempt:
    value = context["attempt"]
    assert isinstance(value, ResearchStageAttempt)
    return value


def _candidate(context: dict[str, object]) -> ResearchCandidate:
    value = context["candidate"]
    assert isinstance(value, ResearchCandidate)
    return value


def _dataset(context: dict[str, object]) -> ResearchDatasetSnapshot:
    value = context["dataset"]
    assert isinstance(value, ResearchDatasetSnapshot)
    return value


def _code(context: dict[str, object]) -> ResearchArtifact:
    value = context["code"]
    assert isinstance(value, ResearchArtifact)
    return value


def _dependencies(context: dict[str, object]) -> ResearchArtifact:
    value = context["dependencies"]
    assert isinstance(value, ResearchArtifact)
    return value


def _bucket(context: dict[str, object]) -> ResearchQuotaBucket:
    value = context["bucket"]
    assert isinstance(value, ResearchQuotaBucket)
    return value


def _reservation(context: dict[str, object]) -> ResearchQuotaReservation:
    value = context["reservation"]
    assert isinstance(value, ResearchQuotaReservation)
    return value
