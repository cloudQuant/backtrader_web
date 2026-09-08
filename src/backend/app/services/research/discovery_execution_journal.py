"""Durable pre-dispatch commands and post-dispatch discovery-runner receipts.

The journal is deliberately a receipt boundary.  It does not publish a stage,
record a trial, settle quota, or decide whether a result is statistically good.
Those later actions must revalidate this durable evidence through their own
fenced aggregates.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchDiscoveryExecution,
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.database_clock import database_utc_now
from app.services.research.discovery_execution_contract import (
    DiscoveryExecutionCommand,
    DiscoveryExecutionResult,
)
from app.services.research.discovery_search_budget import lock_search_epoch, next_search_slot

_INTENT_SCHEMA_VERSION = "discovery-execution-intent-v1"
_DISCOVERY_STAGE = "VALIDATE_DISCOVERY"
_SANDBOX_RESOURCE_TYPE = "sandbox_seconds"
_SANDBOX_UNIT = "seconds"
_OBSERVABLE_DISPATCH_STATUSES = frozenset({"IN_FLIGHT", "RECONCILING", "SETTLED"})
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")


class DiscoveryExecutionJournal:
    """Persist exactly one command/receipt pair for one discovery side effect."""

    async def prepare(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
    ) -> ResearchDiscoveryExecution:
        """Persist a live, mutable-candidate command before HTTP dispatch.

        The table's primary and unique constraints are the cross-process
        idempotency boundary.  A duplicate insert is re-read narrowly after
        ``IntegrityError`` and can only return the exact original command.
        """

        snapshot = _command_snapshot(command, error_code="DISCOVERY_EXECUTION_PREPARE_DENIED")
        operation_id = snapshot["operation_id"]
        execution_id = _execution_id(operation_id)
        async with database.async_session_maker() as session:
            existing = await _find_by_operation(session, execution_id, lock=False)
            if existing is not None:
                return _same_or_prepare_conflict(existing, user_id=user_id, command=command)

            epoch = await lock_search_epoch(session, user_id=user_id, run_id=snapshot["run_id"])
            # Another connection may have committed the exact command while
            # we waited for the epoch write lock. Replay does not take a slot.
            existing = await _find_by_operation(session, execution_id, lock=True)
            if existing is not None:
                return _same_or_prepare_conflict(existing, user_id=user_id, command=command)

            conflicting = await _find_by_attempt_or_reservation(
                session,
                stage_attempt_id=snapshot["stage_attempt_id"],
                quota_reservation_id=snapshot["quota"]["reservation_id"],
                lock=True,
            )
            if conflicting is not None:
                raise ValueError("DISCOVERY_EXECUTION_PREPARE_CONFLICT")

            await _require_prepare_binding(
                session, user_id=user_id, command=command, expected_epoch_id=epoch.id
            )
            slot = await next_search_slot(session, epoch=epoch)
            model = ResearchDiscoveryExecution(
                id=execution_id,
                operation_id=operation_id,
                user_id=user_id,
                run_id=snapshot["run_id"],
                task_id=snapshot["task_id"],
                stage_attempt_id=snapshot["stage_attempt_id"],
                candidate_id=snapshot["candidate_id"],
                quota_reservation_id=snapshot["quota"]["reservation_id"],
                command_hash=command.request_hash,
                search_epoch_id=slot.epoch_id,
                search_ordinal=slot.ordinal,
                search_budget_hash=slot.budget_hash,
                command_json=_json_copy(snapshot),
                status="PREPARED",
            )
            session.add(model)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            else:
                await session.refresh(model)
                return model

        return await self._resolve_prepare_integrity_conflict(
            user_id=user_id,
            command=command,
            execution_id=execution_id,
        )

    async def record_result(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
        result: DiscoveryExecutionResult,
    ) -> ResearchDiscoveryExecution:
        """Persist an independently revalidated result after actual dispatch.

        A late task lease cannot authorize downstream publication, but it also
        must not discard evidence of a provider operation already in flight.
        """

        snapshot = _command_snapshot(command, error_code="DISCOVERY_EXECUTION_RESULT_DENIED")
        if type(result) is not DiscoveryExecutionResult:
            raise ValueError("DISCOVERY_EXECUTION_RESULT_DENIED")
        expected_result = await self._verified_result(
            user_id=user_id,
            command=command,
            result=result,
        )
        expected_snapshot = expected_result.snapshot
        execution_id = _execution_id(snapshot["operation_id"])

        async with database.async_session_maker() as session:
            record = await _find_by_operation(session, execution_id, lock=True)
            _require_owner_command(
                record,
                user_id=user_id,
                command=command,
                denied_code="DISCOVERY_EXECUTION_RESULT_DENIED",
                conflict_code="DISCOVERY_EXECUTION_RESULT_CONFLICT",
            )
            assert record is not None
            if record.status == "OBSERVED":
                if _canonical_equal(record.result_json, expected_snapshot):
                    return record
                raise ValueError("DISCOVERY_EXECUTION_RESULT_CONFLICT")
            if record.status not in {"PREPARED", "UNKNOWN"}:
                raise ValueError("DISCOVERY_EXECUTION_RESULT_CONFLICT")
            await _require_recorded_dispatch(
                session,
                record=record,
                command=command,
                denied_code="DISCOVERY_EXECUTION_RESULT_DISPATCH_REQUIRED",
            )
            write = await session.execute(
                update(ResearchDiscoveryExecution)
                .where(
                    ResearchDiscoveryExecution.id == record.id,
                    ResearchDiscoveryExecution.command_hash == command.request_hash,
                    ResearchDiscoveryExecution.status.in_(("PREPARED", "UNKNOWN")),
                )
                .values(
                    result_json=_json_copy(expected_snapshot),
                    status="OBSERVED",
                    error_code=expected_snapshot["error_code"],
                    updated_at=_utc_now(),
                )
                .execution_options(synchronize_session=False)
            )
            if write.rowcount == 1:
                await session.commit()
                await session.refresh(record)
                return record
            await session.rollback()

        return await self._resolve_result_race(
            user_id=user_id,
            command=command,
            expected_result=expected_snapshot,
            execution_id=execution_id,
        )

    async def record_unknown(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
        error_code: str,
    ) -> ResearchDiscoveryExecution:
        """Record an ambiguous post-dispatch outcome without releasing quota."""

        _stable_error_code(error_code, denied_code="DISCOVERY_EXECUTION_UNKNOWN_DENIED")
        snapshot = _command_snapshot(command, error_code="DISCOVERY_EXECUTION_UNKNOWN_DENIED")
        execution_id = _execution_id(snapshot["operation_id"])
        async with database.async_session_maker() as session:
            record = await _find_by_operation(session, execution_id, lock=True)
            _require_owner_command(
                record,
                user_id=user_id,
                command=command,
                denied_code="DISCOVERY_EXECUTION_UNKNOWN_DENIED",
                conflict_code="DISCOVERY_EXECUTION_UNKNOWN_CONFLICT",
            )
            assert record is not None
            await _require_recorded_dispatch(
                session,
                record=record,
                command=command,
                denied_code="DISCOVERY_EXECUTION_UNKNOWN_DISPATCH_REQUIRED",
            )
            if record.status == "OBSERVED":
                return record
            if record.status == "UNKNOWN":
                if record.error_code == error_code:
                    return record
                raise ValueError("DISCOVERY_EXECUTION_UNKNOWN_CONFLICT")
            if record.status != "PREPARED":
                raise ValueError("DISCOVERY_EXECUTION_UNKNOWN_CONFLICT")
            write = await session.execute(
                update(ResearchDiscoveryExecution)
                .where(
                    ResearchDiscoveryExecution.id == record.id,
                    ResearchDiscoveryExecution.command_hash == command.request_hash,
                    ResearchDiscoveryExecution.status == "PREPARED",
                )
                .values(
                    status="UNKNOWN",
                    error_code=error_code,
                    updated_at=_utc_now(),
                )
                .execution_options(synchronize_session=False)
            )
            if write.rowcount == 1:
                await session.commit()
                await session.refresh(record)
                return record
            await session.rollback()

        return await self._resolve_unknown_race(
            user_id=user_id,
            command=command,
            error_code=error_code,
            execution_id=execution_id,
        )

    async def _resolve_prepare_integrity_conflict(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
        execution_id: str,
    ) -> ResearchDiscoveryExecution:
        async with database.async_session_maker() as session:
            record = await _find_by_operation(session, execution_id, lock=False)
            if record is None:
                snapshot = command.snapshot
                record = await _find_by_attempt_or_reservation(
                    session,
                    stage_attempt_id=snapshot["stage_attempt_id"],
                    quota_reservation_id=snapshot["quota"]["reservation_id"],
                    lock=False,
                )
            if record is not None:
                return _same_or_prepare_conflict(record, user_id=user_id, command=command)
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_CONFLICT")

    async def _verified_result(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
        result: DiscoveryExecutionResult,
    ) -> DiscoveryExecutionResult:
        """Reconstruct the stored command before trusting a result payload."""

        snapshot = _command_snapshot(command, error_code="DISCOVERY_EXECUTION_RESULT_DENIED")
        execution_id = _execution_id(snapshot["operation_id"])
        async with database.async_session_maker() as session:
            record = await _find_by_operation(session, execution_id, lock=False)
            _require_owner_command(
                record,
                user_id=user_id,
                command=command,
                denied_code="DISCOVERY_EXECUTION_RESULT_DENIED",
                conflict_code="DISCOVERY_EXECUTION_RESULT_CONFLICT",
            )
            assert record is not None
            try:
                stored_command = DiscoveryExecutionCommand.from_mapping(
                    _json_copy(record.command_json)
                )
            except ValueError:
                raise ValueError("DISCOVERY_EXECUTION_RESULT_DENIED") from None
            if stored_command.request_hash != record.command_hash:
                raise ValueError("DISCOVERY_EXECUTION_RESULT_DENIED")
            try:
                return DiscoveryExecutionResult.from_mapping(
                    result.snapshot, command=stored_command
                )
            except ValueError:
                raise ValueError("DISCOVERY_EXECUTION_RESULT_DENIED") from None

    async def _resolve_result_race(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
        expected_result: dict[str, Any],
        execution_id: str,
    ) -> ResearchDiscoveryExecution:
        async with database.async_session_maker() as session:
            record = await _find_by_operation(session, execution_id, lock=False)
            _require_owner_command(
                record,
                user_id=user_id,
                command=command,
                denied_code="DISCOVERY_EXECUTION_RESULT_DENIED",
                conflict_code="DISCOVERY_EXECUTION_RESULT_CONFLICT",
            )
            assert record is not None
            if record.status == "OBSERVED" and _canonical_equal(
                record.result_json, expected_result
            ):
                return record
        raise ValueError("DISCOVERY_EXECUTION_RESULT_CONFLICT")

    async def _resolve_unknown_race(
        self,
        *,
        user_id: str,
        command: DiscoveryExecutionCommand,
        error_code: str,
        execution_id: str,
    ) -> ResearchDiscoveryExecution:
        async with database.async_session_maker() as session:
            record = await _find_by_operation(session, execution_id, lock=False)
            _require_owner_command(
                record,
                user_id=user_id,
                command=command,
                denied_code="DISCOVERY_EXECUTION_UNKNOWN_DENIED",
                conflict_code="DISCOVERY_EXECUTION_UNKNOWN_CONFLICT",
            )
            assert record is not None
            if record.status == "OBSERVED":
                return record
            if record.status == "UNKNOWN" and record.error_code == error_code:
                return record
        raise ValueError("DISCOVERY_EXECUTION_UNKNOWN_CONFLICT")


async def _require_prepare_binding(
    session: AsyncSession,
    *,
    user_id: str,
    command: DiscoveryExecutionCommand,
    expected_epoch_id: str,
) -> None:
    snapshot = command.snapshot
    now = await database_utc_now(session)
    # Existing stage/broker writers take task before run. The family lock
    # precedes both, but must not reverse this shared pair's order.
    task = await session.scalar(
        select(ResearchTask)
        .where(ResearchTask.id == snapshot["task_id"], ResearchTask.user_id == user_id)
        .with_for_update()
    )
    run = await session.scalar(
        select(ResearchRun)
        .where(ResearchRun.id == snapshot["run_id"], ResearchRun.user_id == user_id)
        .with_for_update()
    )
    attempt = await session.scalar(
        select(ResearchStageAttempt)
        .where(ResearchStageAttempt.id == snapshot["stage_attempt_id"])
        .with_for_update()
    )
    candidate = await session.scalar(
        select(ResearchCandidate)
        .where(
            ResearchCandidate.id == snapshot["candidate_id"], ResearchCandidate.user_id == user_id
        )
        .with_for_update()
    )
    reservation = await session.scalar(
        select(ResearchQuotaReservation)
        .where(ResearchQuotaReservation.id == snapshot["quota"]["reservation_id"])
        .with_for_update()
    )
    if run is None or task is None or attempt is None or candidate is None or reservation is None:
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if (
        run.status != "RUNNING"
        or run.experiment_epoch_id != expected_epoch_id
        or task.run_id != run.id
        or task.status != "RUNNING"
        or task.stage_cursor != _DISCOVERY_STAGE
        or task.cancel_requested_at is not None
        or task.lease_token is None
        or task.lease_expires_at is None
        or _as_utc(task.lease_expires_at) <= now
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if sha256(task.lease_token.encode("utf-8")).hexdigest() != snapshot["lease_token_hash"]:
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if (
        attempt.run_id != run.id
        or attempt.task_id != task.id
        or attempt.stage != _DISCOVERY_STAGE
        or attempt.status != "RUNNING"
        or attempt.lease_token != task.lease_token
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if (
        candidate.run_id != run.id
        or candidate.experiment_epoch_id != run.experiment_epoch_id
        or candidate.dataset_snapshot_id != run.dataset_snapshot_id
        or candidate.freeze_status != "MUTABLE"
        or candidate.candidate_hash != snapshot["candidate_hash"]
        or candidate.environment_hash != snapshot["environment_hash"]
        or candidate.cost_model_hash != snapshot["cost_model_hash"]
        or not _canonical_equal(candidate.params, snapshot["params"])
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if (
        run.request_hash != snapshot["run_request_hash"]
        or run.capability_profile_id != snapshot["profile"]["id"]
        or run.capability_profile_version != snapshot["profile"]["version"]
        or run.capability_evidence_hash != snapshot["profile"]["evidence_hash"]
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")

    await _require_candidate_inputs(
        session, candidate=candidate, snapshot=snapshot, user_id=user_id
    )
    await _require_live_single_reservation(
        session,
        reservation=reservation,
        task=task,
        attempt=attempt,
        command=command,
        now=now,
    )


async def _require_candidate_inputs(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    snapshot: dict[str, Any],
    user_id: str,
) -> None:
    code = await session.get(ResearchArtifact, candidate.code_artifact_id)
    dependencies = await session.get(ResearchArtifact, candidate.dependency_artifact_id)
    dataset = await session.scalar(
        select(ResearchDatasetSnapshot)
        .where(
            ResearchDatasetSnapshot.id == candidate.dataset_snapshot_id,
            ResearchDatasetSnapshot.user_id == user_id,
        )
        .with_for_update()
    )
    if code is None or dependencies is None or dataset is None:
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if (
        snapshot["code"]["artifact_id"] != code.id
        or snapshot["code"]["content_hash"] != code.content_hash
        or snapshot["code"]["size_bytes"] != code.size_bytes
        or snapshot["dependencies"]["artifact_id"] != dependencies.id
        or snapshot["dependencies"]["content_hash"] != dependencies.content_hash
        or snapshot["dependencies"]["size_bytes"] != dependencies.size_bytes
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    if (
        snapshot["dataset"]["snapshot_id"] != dataset.id
        or snapshot["dataset"]["snapshot_identity_hash"] != dataset.snapshot_identity_hash
        or snapshot["dataset"]["object_receipt_id"] != dataset.object_receipt_id
        or snapshot["dataset"]["object_digest"] != dataset.object_digest
        or snapshot["dataset"]["object_size_bytes"] != dataset.object_size_bytes
        or snapshot["dataset"]["partition_kind"] != dataset.partition_kind
        or dataset.partition_kind not in {"DISCOVERY", "ITERATION_VALIDATION"}
        or not _canonical_equal(dataset.execution_policy, snapshot["execution_policy"])
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")


async def _require_live_single_reservation(
    session: AsyncSession,
    *,
    reservation: ResearchQuotaReservation,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    command: DiscoveryExecutionCommand,
    now: datetime,
) -> None:
    snapshot = command.snapshot
    bucket = await session.scalar(
        select(ResearchQuotaBucket)
        .where(ResearchQuotaBucket.id == reservation.bucket_id)
        .with_for_update()
    )
    if bucket is None:
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    wall_timeout = snapshot["policy"]["wall_timeout_seconds"]
    minimum_reservation_expiry = now + timedelta(seconds=wall_timeout + 90)
    if (
        reservation.task_id != task.id
        or reservation.stage_attempt_id != attempt.id
        or reservation.fencing_token != snapshot["quota"]["fencing_token"]
        or reservation.status != "RESERVED"
        or reservation.provider_operation_id is not None
        or reservation.resource_type != _SANDBOX_RESOURCE_TYPE
        or reservation.unit != _SANDBOX_UNIT
        or reservation.reserved_amount < wall_timeout
        or reservation.lease_expires_at is None
        or _as_utc(reservation.lease_expires_at) < minimum_reservation_expiry
        or bucket.status != "ACTIVE"
        or _as_utc(bucket.window_start) > now
        or _as_utc(bucket.window_end) <= now
    ):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    intent = _intent(command)
    if not _canonical_equal(
        reservation.reservation_context, intent
    ) or reservation.request_hash != content_hash(intent):
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")


async def _require_recorded_dispatch(
    session: AsyncSession,
    *,
    record: ResearchDiscoveryExecution,
    command: DiscoveryExecutionCommand,
    denied_code: str,
) -> None:
    reservation = await session.scalar(
        select(ResearchQuotaReservation)
        .where(ResearchQuotaReservation.id == record.quota_reservation_id)
        .with_for_update()
    )
    if reservation is None or reservation.id != command.snapshot["quota"]["reservation_id"]:
        raise ValueError(denied_code)
    if (
        reservation.provider_operation_id != record.operation_id
        or reservation.status not in _OBSERVABLE_DISPATCH_STATUSES
    ):
        raise ValueError(denied_code)


async def _find_by_operation(
    session: AsyncSession,
    execution_id: str,
    *,
    lock: bool,
) -> ResearchDiscoveryExecution | None:
    statement = select(ResearchDiscoveryExecution).where(
        ResearchDiscoveryExecution.id == execution_id
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _find_by_attempt_or_reservation(
    session: AsyncSession,
    *,
    stage_attempt_id: str,
    quota_reservation_id: str,
    lock: bool,
) -> ResearchDiscoveryExecution | None:
    statement = select(ResearchDiscoveryExecution).where(
        or_(
            ResearchDiscoveryExecution.stage_attempt_id == stage_attempt_id,
            ResearchDiscoveryExecution.quota_reservation_id == quota_reservation_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalars().first()


def _same_or_prepare_conflict(
    record: ResearchDiscoveryExecution,
    *,
    user_id: str,
    command: DiscoveryExecutionCommand,
) -> ResearchDiscoveryExecution:
    if _same_command_record(record, user_id=user_id, command=command):
        if (
            record.search_epoch_id is None
            or record.search_budget_hash is None
            or type(record.search_ordinal) is not int
            or record.search_ordinal < 1
        ):
            # Old receipts remain readable/recordable for reconciliation, but
            # cannot become fresh dispatch authority by taking the replay path.
            raise ValueError("DISCOVERY_SEARCH_ALLOCATION_REQUIRED")
        return record
    raise ValueError("DISCOVERY_EXECUTION_PREPARE_CONFLICT")


def _require_owner_command(
    record: ResearchDiscoveryExecution | None,
    *,
    user_id: str,
    command: DiscoveryExecutionCommand,
    denied_code: str,
    conflict_code: str,
) -> None:
    if record is None or record.user_id != user_id:
        raise ValueError(denied_code)
    if not _same_command_record(record, user_id=user_id, command=command):
        raise ValueError(conflict_code)


def _same_command_record(
    record: ResearchDiscoveryExecution,
    *,
    user_id: str,
    command: DiscoveryExecutionCommand,
) -> bool:
    snapshot = command.snapshot
    return (
        record.operation_id == snapshot["operation_id"]
        and record.user_id == user_id
        and record.run_id == snapshot["run_id"]
        and record.task_id == snapshot["task_id"]
        and record.stage_attempt_id == snapshot["stage_attempt_id"]
        and record.candidate_id == snapshot["candidate_id"]
        and record.quota_reservation_id == snapshot["quota"]["reservation_id"]
        and record.command_hash == command.request_hash
        and _canonical_equal(record.command_json, snapshot)
    )


def _command_snapshot(command: object, *, error_code: str) -> dict[str, Any]:
    if type(command) is not DiscoveryExecutionCommand:
        raise ValueError(error_code)
    return command.snapshot


def _execution_id(operation_id: object) -> str:
    if type(operation_id) is not str:
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    return sha256(operation_id.encode("utf-8")).hexdigest()


def _intent(command: DiscoveryExecutionCommand) -> dict[str, Any]:
    snapshot = command.snapshot
    return {
        "schema_version": _INTENT_SCHEMA_VERSION,
        "inputs": {
            key: value for key, value in snapshot.items() if key not in {"operation_id", "quota"}
        },
    }


def _json_copy(value: object) -> dict[str, Any]:
    try:
        copied = json.loads(canonical_json(value))
    except Exception as exc:
        raise ValueError("DISCOVERY_EXECUTION_JSON_INVALID") from exc
    if type(copied) is not dict:
        raise ValueError("DISCOVERY_EXECUTION_JSON_INVALID")
    return copied


def _canonical_equal(left: object, right: object) -> bool:
    try:
        return canonical_json(left) == canonical_json(right)
    except Exception:
        return False


def _stable_error_code(value: object, *, denied_code: str) -> None:
    if (
        type(value) is not str
        or len(value.encode("utf-8")) > 128
        or _ERROR_CODE.fullmatch(value) is None
    ):
        raise ValueError(denied_code)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
