"""Durable, idempotent journal around the external sealed-evaluator side effect."""

from __future__ import annotations

import asyncio
import re
import weakref
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db import database
from app.models.ai_research_v2 import (
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
)
from app.services.research.database_clock import DatabaseUtcNow, database_utc_now
from app.services.research.holdout_execution_contract import (
    HoldoutExecutionCommand,
    HoldoutExecutionInspection,
    HoldoutExecutionResult,
)
from app.services.research.promotion import (
    promotion_policy_material_hash,
    resolve_server_policy,
)

_LOCK_SHARDS = 64
_LOCKS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    tuple[asyncio.Lock, ...],
] = weakref.WeakKeyDictionary()
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")


class HoldoutExecutionJournal:
    """Persist one pre-dispatch command and one immutable observed result."""

    async def prepare(
        self,
        *,
        user_id: str,
        lease_owner: str,
        command: HoldoutExecutionCommand,
    ) -> ResearchHoldoutExecution:
        verified = _verified_command(command, "HOLDOUT_EXECUTION_PREPARE_DENIED")
        snapshot = verified.snapshot
        async with _lock(str(snapshot["command_id"])):
            async with database.async_session_maker() as session:
                existing = await _by_command(session, str(snapshot["command_id"]), lock=True)
                if existing is not None:
                    return _require_exact(
                        existing,
                        user_id=user_id,
                        lease_owner=lease_owner,
                        command=verified,
                        conflict_code="HOLDOUT_EXECUTION_PREPARE_CONFLICT",
                    )
                binding = await _require_live_binding(
                    session,
                    user_id=user_id,
                    lease_owner=lease_owner,
                    command=verified,
                )
                now = await database_utc_now(session)
                model = ResearchHoldoutExecution(
                    operation_id=str(snapshot["operation_id"]),
                    user_id=user_id,
                    command_id=str(snapshot["command_id"]),
                    evaluation_id=str(snapshot["evaluation_id"]),
                    command_hash=verified.command_hash,
                    lease_owner=lease_owner,
                    lease_generation=int(snapshot["lease_generation"]),
                    lease_expires_at=_as_utc(binding.lease_expires_at),
                    state="PREPARED",
                    command_json=snapshot,
                    prepared_at=now,
                    updated_at=now,
                )
                session.add(model)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                except SQLAlchemyError:
                    await session.rollback()
                    raise ValueError("HOLDOUT_EXECUTION_PREPARE_FAILED") from None
                else:
                    await session.refresh(model)
                    return model

            async with database.async_session_maker() as session:
                existing = await _by_command(session, str(snapshot["command_id"]), lock=False)
                if existing is None:
                    raise ValueError("HOLDOUT_EXECUTION_PREPARE_FAILED")
                return _require_exact(
                    existing,
                    user_id=user_id,
                    lease_owner=lease_owner,
                    command=verified,
                    conflict_code="HOLDOUT_EXECUTION_PREPARE_CONFLICT",
                )

    async def begin_dispatch(
        self,
        *,
        user_id: str,
        lease_owner: str,
        command: HoldoutExecutionCommand,
        actor_identity: str | None = None,
    ) -> bool:
        verified = _verified_command(command, "HOLDOUT_EXECUTION_DISPATCH_DENIED")
        snapshot = verified.snapshot
        async with _lock(str(snapshot["command_id"])):
            async with database.async_session_maker() as session:
                record = await _by_command(session, str(snapshot["command_id"]), lock=True)
                _require_exact(
                    record,
                    user_id=user_id,
                    lease_owner=lease_owner,
                    command=verified,
                    conflict_code="HOLDOUT_EXECUTION_DISPATCH_DENIED",
                )
                if record is None or record.state != "PREPARED":
                    await session.rollback()
                    return False
                await _require_dispatch_binding(
                    session,
                    user_id=user_id,
                    lease_owner=lease_owner,
                    command=verified,
                    actor_identity=actor_identity or lease_owner,
                    not_executed_proved=record.not_executed_at is not None,
                )
                write = await session.execute(
                    update(ResearchHoldoutExecution)
                    .where(
                        ResearchHoldoutExecution.id == record.id,
                        ResearchHoldoutExecution.state == "PREPARED",
                        ResearchHoldoutExecution.command_hash == verified.command_hash,
                    )
                    .values(
                        state="IN_FLIGHT",
                        error_code=None,
                        dispatched_at=record.dispatched_at or DatabaseUtcNow(),
                        updated_at=DatabaseUtcNow(),
                    )
                    .execution_options(synchronize_session=False)
                )
                if write.rowcount != 1:
                    await session.rollback()
                    return False
                await session.commit()
                return True

    async def record_unknown(
        self,
        *,
        user_id: str,
        command: HoldoutExecutionCommand,
        error_code: str,
    ) -> ResearchHoldoutExecution:
        if (
            type(error_code) is not str
            or len(error_code) > 128
            or _ERROR_CODE.fullmatch(error_code) is None
        ):
            raise ValueError("HOLDOUT_EXECUTION_UNKNOWN_INVALID")
        verified = _verified_command(command, "HOLDOUT_EXECUTION_TRANSITION_DENIED")
        snapshot = verified.snapshot
        command_id = str(snapshot["command_id"])
        async with _lock(command_id):
            async with database.async_session_maker() as session:
                record = await _by_command(session, command_id, lock=True)
                _require_owner_command(
                    record,
                    user_id=user_id,
                    command=verified,
                    code="HOLDOUT_EXECUTION_TRANSITION_DENIED",
                )
                assert record is not None
                bound_command = await _require_unknown_binding(
                    session,
                    user_id=user_id,
                    lease_owner=record.lease_owner,
                    command=verified,
                )
                if record.state == "UNKNOWN" and record.error_code == error_code:
                    if bound_command.status != "RECONCILING":
                        raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
                    await session.rollback()
                    return record
                if record.state not in {"PREPARED", "IN_FLIGHT"} or record.result_hash is not None:
                    raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
                now = await database_utc_now(session)
                if bound_command.status == "RUNNING":
                    command_write = await session.execute(
                        update(ResearchHoldoutEvaluationCommand)
                        .where(
                            ResearchHoldoutEvaluationCommand.id == command_id,
                            ResearchHoldoutEvaluationCommand.status == "RUNNING",
                            ResearchHoldoutEvaluationCommand.stage == "HOLDOUT_PENDING",
                            ResearchHoldoutEvaluationCommand.error_code.is_(None),
                            ResearchHoldoutEvaluationCommand.lease_owner == record.lease_owner,
                            ResearchHoldoutEvaluationCommand.lease_token_hash.is_not(None),
                            ResearchHoldoutEvaluationCommand.lease_generation
                            == record.lease_generation,
                            ResearchHoldoutEvaluationCommand.lease_expires_at.is_not(None),
                            ResearchHoldoutEvaluationCommand.lease_heartbeat_at.is_not(None),
                        )
                        .values(
                            status="RECONCILING",
                            error_code="HOLDOUT_EXECUTION_OUTCOME_UNKNOWN",
                            lease_owner=None,
                            lease_token_hash=None,
                            lease_expires_at=None,
                            lease_heartbeat_at=None,
                            updated_at=now,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    if command_write.rowcount != 1:
                        await session.rollback()
                        raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
                execution_write = await session.execute(
                    update(ResearchHoldoutExecution)
                    .where(
                        ResearchHoldoutExecution.id == record.id,
                        ResearchHoldoutExecution.state.in_(("PREPARED", "IN_FLIGHT")),
                        ResearchHoldoutExecution.result_hash.is_(None),
                    )
                    .values(
                        state="UNKNOWN",
                        error_code=error_code,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
                if execution_write.rowcount != 1:
                    await session.rollback()
                    raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
                await session.commit()
            return await self.read(command=verified, user_id=user_id)

    async def record_not_executed(
        self,
        *,
        user_id: str,
        command: HoldoutExecutionCommand,
        inspection: HoldoutExecutionInspection,
    ) -> ResearchHoldoutExecution:
        """Re-arm only after the deployment executor proved no operation exists."""

        verified = _verified_command(command, "HOLDOUT_EXECUTION_TRANSITION_DENIED")
        if type(inspection) is not HoldoutExecutionInspection or not inspection.proves_not_executed(
            verified
        ):
            raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
        snapshot = verified.snapshot
        async with _lock(str(snapshot["command_id"])):
            async with database.async_session_maker() as session:
                record = await _by_command(session, str(snapshot["command_id"]), lock=True)
                _require_owner_command(
                    record,
                    user_id=user_id,
                    command=verified,
                    code="HOLDOUT_EXECUTION_TRANSITION_DENIED",
                )
                assert record is not None
                if record.state == "PREPARED" and record.not_executed_at is not None:
                    return record
                if (
                    record.state not in {"PREPARED", "IN_FLIGHT", "UNKNOWN"}
                    or record.result_hash is not None
                ):
                    raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
                write = await session.execute(
                    update(ResearchHoldoutExecution)
                    .where(
                        ResearchHoldoutExecution.id == record.id,
                        ResearchHoldoutExecution.state.in_(("PREPARED", "IN_FLIGHT", "UNKNOWN")),
                        ResearchHoldoutExecution.result_hash.is_(None),
                    )
                    .values(
                        state="PREPARED",
                        error_code=None,
                        not_executed_at=DatabaseUtcNow(),
                        updated_at=DatabaseUtcNow(),
                    )
                    .execution_options(synchronize_session=False)
                )
                if write.rowcount != 1:
                    await session.rollback()
                else:
                    await session.commit()
            return await self.read(command=verified, user_id=user_id)

    async def record_result(
        self,
        *,
        user_id: str,
        command: HoldoutExecutionCommand,
        result: HoldoutExecutionResult,
    ) -> ResearchHoldoutExecution:
        verified = _verified_command(command, "HOLDOUT_EXECUTION_RESULT_DENIED")
        try:
            if type(result) is not HoldoutExecutionResult:
                raise ValueError
            verified_result = HoldoutExecutionResult(payload=result.payload, _command=verified)
        except Exception:
            raise ValueError("HOLDOUT_EXECUTION_RESULT_DENIED") from None
        snapshot = verified.snapshot
        result_snapshot = verified_result.snapshot
        result_hash = sha256(verified_result.payload).hexdigest()
        async with _lock(str(snapshot["command_id"])):
            async with database.async_session_maker() as session:
                record = await _by_command(session, str(snapshot["command_id"]), lock=True)
                _require_owner_command(
                    record,
                    user_id=user_id,
                    command=verified,
                    code="HOLDOUT_EXECUTION_RESULT_DENIED",
                )
                assert record is not None
                if record.state in {"OBSERVED", "SETTLED"}:
                    if record.result_hash == result_hash and record.result_json == result_snapshot:
                        return record
                    raise ValueError("HOLDOUT_EXECUTION_RESULT_CONFLICT")
                if record.state not in {"PREPARED", "IN_FLIGHT", "UNKNOWN"}:
                    raise ValueError("HOLDOUT_EXECUTION_RESULT_DENIED")
                now = await database_utc_now(session)
                write = await session.execute(
                    update(ResearchHoldoutExecution)
                    .where(
                        ResearchHoldoutExecution.id == record.id,
                        ResearchHoldoutExecution.state.in_(("PREPARED", "IN_FLIGHT", "UNKNOWN")),
                        ResearchHoldoutExecution.result_hash.is_(None),
                    )
                    .values(
                        state="OBSERVED",
                        result_hash=result_hash,
                        result_json=result_snapshot,
                        error_code=None,
                        dispatched_at=record.dispatched_at or now,
                        observed_at=now,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
                if write.rowcount != 1:
                    await session.rollback()
                else:
                    await session.commit()
            return await self.read(command=verified, user_id=user_id)

    async def settle(
        self,
        *,
        user_id: str,
        command: HoldoutExecutionCommand,
    ) -> ResearchHoldoutExecution:
        verified = _verified_command(command, "HOLDOUT_EXECUTION_SETTLEMENT_DENIED")
        snapshot = verified.snapshot
        async with _lock(str(snapshot["command_id"])):
            async with database.async_session_maker() as session:
                record = await _by_command(session, str(snapshot["command_id"]), lock=True)
                _require_owner_command(
                    record,
                    user_id=user_id,
                    command=verified,
                    code="HOLDOUT_EXECUTION_SETTLEMENT_DENIED",
                )
                assert record is not None
                if record.state == "SETTLED":
                    return record
                if record.state != "OBSERVED" or record.result_hash is None:
                    raise ValueError("HOLDOUT_EXECUTION_SETTLEMENT_DENIED")
                write = await session.execute(
                    update(ResearchHoldoutExecution)
                    .where(
                        ResearchHoldoutExecution.id == record.id,
                        ResearchHoldoutExecution.state == "OBSERVED",
                        ResearchHoldoutExecution.result_hash == record.result_hash,
                    )
                    .values(
                        state="SETTLED",
                        settled_at=DatabaseUtcNow(),
                        updated_at=DatabaseUtcNow(),
                    )
                    .execution_options(synchronize_session=False)
                )
                if write.rowcount != 1:
                    await session.rollback()
                else:
                    await session.commit()
            return await self.read(command=verified, user_id=user_id)

    async def read(
        self,
        *,
        command: HoldoutExecutionCommand,
        user_id: str,
    ) -> ResearchHoldoutExecution:
        verified = _verified_command(command, "HOLDOUT_EXECUTION_NOT_FOUND")
        async with database.async_session_maker() as session:
            record = await _by_command(session, str(verified.snapshot["command_id"]), lock=False)
            _require_owner_command(
                record,
                user_id=user_id,
                command=verified,
                code="HOLDOUT_EXECUTION_NOT_FOUND",
            )
            assert record is not None
            return record

    async def _transition(
        self,
        *,
        user_id: str,
        command: HoldoutExecutionCommand,
        from_states: tuple[str, ...],
        to_state: str,
        error_code: str | None,
    ) -> ResearchHoldoutExecution:
        verified = _verified_command(command, "HOLDOUT_EXECUTION_TRANSITION_DENIED")
        snapshot = verified.snapshot
        async with _lock(str(snapshot["command_id"])):
            async with database.async_session_maker() as session:
                record = await _by_command(session, str(snapshot["command_id"]), lock=True)
                _require_owner_command(
                    record,
                    user_id=user_id,
                    command=verified,
                    code="HOLDOUT_EXECUTION_TRANSITION_DENIED",
                )
                assert record is not None
                if record.state == to_state and record.error_code == error_code:
                    return record
                if record.state not in from_states or record.result_hash is not None:
                    raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
                write = await session.execute(
                    update(ResearchHoldoutExecution)
                    .where(
                        ResearchHoldoutExecution.id == record.id,
                        ResearchHoldoutExecution.state.in_(from_states),
                        ResearchHoldoutExecution.result_hash.is_(None),
                    )
                    .values(
                        state=to_state,
                        error_code=error_code,
                        updated_at=DatabaseUtcNow(),
                    )
                    .execution_options(synchronize_session=False)
                )
                if write.rowcount != 1:
                    await session.rollback()
                else:
                    await session.commit()
            return await self.read(command=verified, user_id=user_id)


async def _require_live_binding(
    session,
    *,
    user_id: str,
    lease_owner: str,
    command: HoldoutExecutionCommand,
) -> ResearchHoldoutEvaluationCommand:
    snapshot = command.snapshot
    model = await session.scalar(
        select(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.id == snapshot["command_id"])
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = await database_utc_now(session)
    if (
        model is None
        or model.user_id != user_id
        or model.status != "RUNNING"
        or model.stage != "HOLDOUT_PENDING"
        or model.error_code is not None
        or model.evaluation_id != snapshot["evaluation_id"]
        or model.authorization_id != snapshot["authorization_id"]
        or model.experiment_epoch_id != snapshot["experiment_epoch_id"]
        or model.request_hash != snapshot["request_hash"]
        or model.candidate_id != snapshot["candidate_id"]
        or model.candidate_hash != snapshot["candidate_hash"]
        or model.dataset_snapshot_id != snapshot["dataset_snapshot_id"]
        or model.sealed_dataset_hash != snapshot["sealed_dataset_hash"]
        or model.sealed_dataset_identity_hash != snapshot["sealed_dataset_identity_hash"]
        or model.freeze_receipt_fingerprint != snapshot["freeze_receipt_fingerprint"]
        or model.capability_evidence_hash != snapshot["capability_evidence_hash"]
        or model.policy_version != snapshot["policy_version"]
        or snapshot["promotion_policy_hash"]
        != promotion_policy_material_hash(resolve_server_policy(model.policy_version))
        or model.evaluator_identity != snapshot["evaluator_identity"]
        or model.evaluator_version != snapshot["evaluator_image_digest"]
        or model.lease_owner != lease_owner
        or model.lease_generation != snapshot["lease_generation"]
        or model.lease_token_hash is None
        or model.lease_expires_at is None
        or _as_utc(model.lease_expires_at) <= now
    ):
        raise ValueError("HOLDOUT_EXECUTION_PREPARE_DENIED")
    return model


async def _require_dispatch_binding(
    session,
    *,
    user_id: str,
    lease_owner: str,
    command: HoldoutExecutionCommand,
    actor_identity: str,
    not_executed_proved: bool,
) -> ResearchHoldoutEvaluationCommand:
    """Authorize either the live claimant or a proved same-operation recovery.

    A replacement worker never receives or reconstructs the original bearer.
    It may enter the dispatch CAS only after an authoritative inspection was
    durably recorded as NOT_EXECUTED and the original lease expired.
    """

    snapshot = command.snapshot
    model = await session.scalar(
        select(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.id == snapshot["command_id"])
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        model is None
        or model.user_id != user_id
        or model.stage != "HOLDOUT_PENDING"
        or model.evaluation_id != snapshot["evaluation_id"]
        or model.authorization_id != snapshot["authorization_id"]
        or model.experiment_epoch_id != snapshot["experiment_epoch_id"]
        or model.request_hash != snapshot["request_hash"]
        or model.candidate_id != snapshot["candidate_id"]
        or model.candidate_hash != snapshot["candidate_hash"]
        or model.dataset_snapshot_id != snapshot["dataset_snapshot_id"]
        or model.sealed_dataset_hash != snapshot["sealed_dataset_hash"]
        or model.sealed_dataset_identity_hash != snapshot["sealed_dataset_identity_hash"]
        or model.freeze_receipt_fingerprint != snapshot["freeze_receipt_fingerprint"]
        or model.capability_evidence_hash != snapshot["capability_evidence_hash"]
        or model.policy_version != snapshot["policy_version"]
        or snapshot["promotion_policy_hash"]
        != promotion_policy_material_hash(resolve_server_policy(model.policy_version))
        or model.evaluator_identity != snapshot["evaluator_identity"]
        or model.evaluator_version != snapshot["evaluator_image_digest"]
        or model.lease_generation != snapshot["lease_generation"]
        or type(actor_identity) is not str
        or not actor_identity
        or len(actor_identity) > 128
    ):
        raise ValueError("HOLDOUT_EXECUTION_DISPATCH_DENIED")
    if model.status == "RUNNING":
        if (
            model.error_code is not None
            or model.lease_owner != lease_owner
            or model.lease_token_hash is None
            or model.lease_expires_at is None
            or model.lease_heartbeat_at is None
        ):
            raise ValueError("HOLDOUT_EXECUTION_DISPATCH_DENIED")
        now = await database_utc_now(session)
        lease_is_live = _as_utc(model.lease_expires_at) > now
        if lease_is_live:
            if actor_identity != lease_owner:
                raise ValueError("HOLDOUT_EXECUTION_DISPATCH_DENIED")
        elif not not_executed_proved:
            raise ValueError("HOLDOUT_EXECUTION_DISPATCH_DENIED")
    elif (
        model.status != "RECONCILING"
        or model.error_code != "HOLDOUT_EXECUTION_OUTCOME_UNKNOWN"
        or model.lease_owner is not None
        or model.lease_token_hash is not None
        or model.lease_expires_at is not None
        or model.lease_heartbeat_at is not None
        or not not_executed_proved
    ):
        raise ValueError("HOLDOUT_EXECUTION_DISPATCH_DENIED")
    return model


async def _require_unknown_binding(
    session,
    *,
    user_id: str,
    lease_owner: str,
    command: HoldoutExecutionCommand,
) -> ResearchHoldoutEvaluationCommand:
    """Lock the command and validate either the live or already-fenced graph."""

    snapshot = command.snapshot
    model = await session.scalar(
        select(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.id == snapshot["command_id"])
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    common_invalid = bool(
        model is None
        or model.user_id != user_id
        or model.stage != "HOLDOUT_PENDING"
        or model.evaluation_id != snapshot["evaluation_id"]
        or model.authorization_id != snapshot["authorization_id"]
        or model.experiment_epoch_id != snapshot["experiment_epoch_id"]
        or model.request_hash != snapshot["request_hash"]
        or model.candidate_id != snapshot["candidate_id"]
        or model.candidate_hash != snapshot["candidate_hash"]
        or model.dataset_snapshot_id != snapshot["dataset_snapshot_id"]
        or model.sealed_dataset_hash != snapshot["sealed_dataset_hash"]
        or model.sealed_dataset_identity_hash != snapshot["sealed_dataset_identity_hash"]
        or model.freeze_receipt_fingerprint != snapshot["freeze_receipt_fingerprint"]
        or model.capability_evidence_hash != snapshot["capability_evidence_hash"]
        or model.policy_version != snapshot["policy_version"]
        or snapshot["promotion_policy_hash"]
        != promotion_policy_material_hash(resolve_server_policy(model.policy_version))
        or model.evaluator_identity != snapshot["evaluator_identity"]
        or model.evaluator_version != snapshot["evaluator_image_digest"]
        or model.lease_generation != snapshot["lease_generation"]
    )
    if common_invalid or model is None:
        raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
    live = bool(
        model.status == "RUNNING"
        and model.error_code is None
        and model.lease_owner == lease_owner
        and model.lease_token_hash is not None
        and model.lease_expires_at is not None
        and model.lease_heartbeat_at is not None
    )
    fenced = bool(
        model.status == "RECONCILING"
        and model.error_code == "HOLDOUT_EXECUTION_OUTCOME_UNKNOWN"
        and model.lease_owner is None
        and model.lease_token_hash is None
        and model.lease_expires_at is None
        and model.lease_heartbeat_at is None
    )
    if not live and not fenced:
        raise ValueError("HOLDOUT_EXECUTION_TRANSITION_DENIED")
    return model


async def _by_command(session, command_id: str, *, lock: bool) -> ResearchHoldoutExecution | None:
    statement = select(ResearchHoldoutExecution).where(
        ResearchHoldoutExecution.command_id == command_id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


def _require_exact(
    record: ResearchHoldoutExecution | None,
    *,
    user_id: str,
    lease_owner: str,
    command: HoldoutExecutionCommand,
    conflict_code: str,
) -> ResearchHoldoutExecution:
    _require_owner_command(record, user_id=user_id, command=command, code=conflict_code)
    snapshot = command.snapshot
    assert record is not None
    if (
        record.operation_id != snapshot["operation_id"]
        or record.evaluation_id != snapshot["evaluation_id"]
        or record.lease_owner != lease_owner
        or record.lease_generation != snapshot["lease_generation"]
        or record.lease_expires_at is None
        or record.command_json != snapshot
        or record.prepared_at is None
    ):
        raise ValueError(conflict_code)
    return record


def _require_owner_command(
    record: ResearchHoldoutExecution | None,
    *,
    user_id: str,
    command: HoldoutExecutionCommand,
    code: str,
) -> None:
    snapshot = command.snapshot
    if (
        record is None
        or record.user_id != user_id
        or record.command_id != snapshot["command_id"]
        or record.command_hash != command.command_hash
    ):
        raise ValueError(code)


def _verified_command(command: object, code: str) -> HoldoutExecutionCommand:
    try:
        if type(command) is not HoldoutExecutionCommand:
            raise ValueError
        return HoldoutExecutionCommand(payload=command.payload, command_hash=command.command_hash)
    except Exception:
        raise ValueError(code) from None


def _lock(command_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    locks = _LOCKS_BY_LOOP.get(loop)
    if locks is None:
        locks = tuple(asyncio.Lock() for _ in range(_LOCK_SHARDS))
        _LOCKS_BY_LOOP[loop] = locks
    return locks[int(sha256(command_id.encode()).hexdigest(), 16) % _LOCK_SHARDS]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
