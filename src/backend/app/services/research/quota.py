"""Fenced, all-or-nothing quota reservations for protocol-v2 side effects.

The service deliberately treats an expired lease as an *unknown external
operation*.  A reservation is never silently returned to a bucket after a
worker dies: an explicit provider readback must settle or release it.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.database_clock import DatabaseUtcAfter, DatabaseUtcNow, database_utc_now

_MAX_QUOTA_AMOUNT = 2_147_483_647
_MODEL_COST_RESOURCE_TYPE = "model_cost_microusd"
_MODEL_COST_UNIT = "microusd"
_MODEL_BUDGET_CONTEXT_SCHEMA = "model-budget-quote-v1"
_BUNDLE_MUTATION_REQUIRED = "RESEARCH_QUOTA_BUNDLE_OPERATION_REQUIRED"


class QuotaError(ValueError):
    """Base class for stable quota error codes."""


class QuotaConflictError(QuotaError):
    """The request conflicts with a prior reservation or fencing state."""


class QuotaUnavailableError(QuotaError):
    """The bucket cannot admit the requested work now."""


@dataclass(frozen=True, slots=True)
class QuotaReservationRequest:
    """One resource requirement in a single atomic reservation operation."""

    bucket_id: str
    resource_type: str
    amount: int
    unit: str


@dataclass(frozen=True, slots=True)
class QuotaReservationReceipt:
    """Fencing receipt that downstream LLM/sandbox/evaluator calls must carry."""

    reservation_id: str
    bucket_id: str
    resource_type: str
    reserved_amount: int
    unit: str
    fencing_token: int
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class QuotaDispatchRequirement:
    """One immutable reservation receipt required for a bundle dispatch.

    ``require_reservation_context`` is set only by strict, deployment-owned
    dispatchers that need a persisted, schema-bound intent before provider I/O.
    The default schema keeps existing model-budget dispatchers unchanged.
    Generic legacy bundles retain the default ``False`` behavior.
    """

    reservation_id: str
    fencing_token: int
    resource_type: str
    unit: str
    reserved_amount: int
    request_hash: str
    require_reservation_context: bool = False
    reservation_context_schema: str = "model-budget-quote-v1"
    minimum_remaining_seconds: int = 0


@dataclass(frozen=True, slots=True)
class QuotaSettlementRequest:
    """One confirmed amount in an all-or-nothing bundle settlement."""

    reservation_id: str
    fencing_token: int
    settled_amount: int


class QuotaService:
    """Reserve multiple quota resources without partial debit.

    Row-version compare-and-swap protects distinct service instances.  The
    instance lock additionally gives SQLite's single-process development mode
    deterministic short-write semantics; it is not treated as deployment
    isolation evidence.
    """

    def __init__(self) -> None:
        self._reservation_lock = asyncio.Lock()

    async def reserve(
        self,
        *,
        task_id: str,
        policy_version: str,
        idempotency_key: str,
        request_hash: str,
        requests: tuple[QuotaReservationRequest, ...],
        lease_seconds: int = 900,
        stage_attempt_id: str | None = None,
        trace_id: str | None = None,
        reservation_context: dict[str, Any] | None = None,
    ) -> tuple[QuotaReservationReceipt, ...]:
        """Atomically reserve every requested resource or reserve none.

        Repeating an identical task/idempotency key returns the original
        fencing receipts.  Any payload change is a conflict rather than a
        second debit.
        """

        normalized_context = _normalize_reservation_context(reservation_context)
        _validate_reservation_request(
            task_id=task_id,
            policy_version=policy_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            requests=requests,
            lease_seconds=lease_seconds,
            reservation_context=normalized_context,
        )
        ordered = tuple(sorted(requests, key=lambda item: (item.bucket_id, item.resource_type)))
        async with self._reservation_lock:
            async with database.async_session_maker() as session:
                try:
                    await _validate_task_binding(session, task_id, stage_attempt_id)
                    existing = await _existing_reservations(session, task_id, idempotency_key)
                    if existing:
                        return _existing_receipts(
                            existing,
                            request_hash=request_hash,
                            policy_version=policy_version,
                            requests=ordered,
                            reservation_context=normalized_context,
                        )

                    buckets = await _locked_buckets(
                        session, tuple(item.bucket_id for item in ordered)
                    )
                    now = await database_utc_now(session)
                    expires_at = now + timedelta(seconds=lease_seconds)
                    _validate_buckets(buckets, ordered, policy_version=policy_version, now=now)

                    created: dict[str, ResearchQuotaReservation] = {}
                    for item in ordered:
                        bucket = buckets[item.bucket_id]
                        fencing_token = bucket.next_fencing_token
                        result = await session.execute(
                            update(ResearchQuotaBucket)
                            .where(
                                ResearchQuotaBucket.id == bucket.id,
                                ResearchQuotaBucket.version == bucket.version,
                                ResearchQuotaBucket.status == "ACTIVE",
                                ResearchQuotaBucket.reserved_amount == bucket.reserved_amount,
                                ResearchQuotaBucket.active_reservations
                                == bucket.active_reservations,
                            )
                            .values(
                                reserved_amount=bucket.reserved_amount + item.amount,
                                active_reservations=bucket.active_reservations + 1,
                                next_fencing_token=fencing_token + 1,
                                version=bucket.version + 1,
                                updated_at=now,
                            )
                        )
                        if result.rowcount != 1:
                            raise QuotaUnavailableError("RESEARCH_QUOTA_CONCURRENT_UPDATE_RETRY")
                        reservation = ResearchQuotaReservation(
                            bucket_id=bucket.id,
                            task_id=task_id,
                            stage_attempt_id=stage_attempt_id,
                            idempotency_key=idempotency_key,
                            resource_type=item.resource_type,
                            reserved_amount=item.amount,
                            unit=item.unit,
                            status="RESERVED",
                            lease_expires_at=expires_at,
                            fencing_token=fencing_token,
                            policy_version=policy_version,
                            request_hash=request_hash,
                            trace_id=trace_id,
                            reservation_context=_copy_context(normalized_context),
                        )
                        session.add(reservation)
                        created[item.bucket_id] = reservation
                    await session.commit()
                    for reservation in created.values():
                        await session.refresh(reservation)
                    return tuple(_receipt(created[item.bucket_id]) for item in ordered)
                except Exception:
                    await session.rollback()
                    raise

    async def validate_fencing(self, reservation_id: str, fencing_token: int) -> bool:
        """Return whether a downstream command may still use a reservation."""

        async with database.async_session_maker() as session:
            reservation = await session.get(ResearchQuotaReservation, reservation_id)
            if reservation is None or reservation.fencing_token != fencing_token:
                return False
            if reservation.status not in {"RESERVED", "IN_FLIGHT"}:
                return False
            now = await database_utc_now(session)
            if reservation.lease_expires_at is None or _as_utc(reservation.lease_expires_at) <= now:
                return False
            bucket = await session.get(ResearchQuotaBucket, reservation.bucket_id)
            return bucket is not None and bucket.status == "ACTIVE"

    async def validate_stage_attempt_fencing(
        self,
        reservation_id: str,
        fencing_token: int,
        *,
        task_id: str,
        run_id: str,
        stage_attempt_id: str,
        lease_token: str,
        stage: str,
    ) -> bool:
        """Require a live, leased stage checkpoint for an external side effect.

        A quota receipt alone deliberately does not authorize a provider or
        sandbox call.  The receipt must be tied to the exact durable task and
        its still-running stage attempt; this prevents a recovered, cancelled,
        or stale worker from turning an old reservation into new external work.
        """

        if not all(
            value.strip() for value in (task_id, run_id, stage_attempt_id, lease_token, stage)
        ):
            return False
        async with database.async_session_maker() as session:
            reservation = await session.get(ResearchQuotaReservation, reservation_id)
            if reservation is None or reservation.fencing_token != fencing_token:
                return False
            if reservation.stage_attempt_id != stage_attempt_id:
                return False
            if reservation.task_id != task_id or reservation.status not in {
                "RESERVED",
                "IN_FLIGHT",
            }:
                return False
            now = await database_utc_now(session)
            if reservation.lease_expires_at is None or _as_utc(reservation.lease_expires_at) <= now:
                return False
            bucket = await session.get(ResearchQuotaBucket, reservation.bucket_id)
            if bucket is None or bucket.status != "ACTIVE":
                return False
            task = await session.get(ResearchTask, task_id)
            if (
                task is None
                or task.run_id != run_id
                or task.status != "RUNNING"
                or task.lease_token != lease_token
                or task.cancel_requested_at is not None
                or task.lease_expires_at is None
                or _as_utc(task.lease_expires_at) <= now
            ):
                return False
            attempt = await session.get(ResearchStageAttempt, stage_attempt_id)
            return bool(
                attempt is not None
                and attempt.run_id == run_id
                and attempt.task_id == task_id
                and attempt.stage == stage
                and attempt.status == "RUNNING"
                and attempt.lease_token == lease_token
            )

    async def claim_external_dispatch(
        self,
        reservation_id: str,
        fencing_token: int,
        *,
        provider_operation_id: str,
        task_id: str,
        run_id: str,
        stage_attempt_id: str,
        lease_token: str,
        stage: str,
        resource_type: str,
        unit: str,
    ) -> bool:
        """Claim one external dispatch with a conditional durable transition.

        Unlike ``mark_in_flight``, this method is not idempotent permission to
        dispatch. Only the caller changing RESERVED to IN_FLIGHT may contact
        the provider. An already claimed or ambiguous operation must instead
        be reconciled, even when the operation id is identical.

        All live-stage predicates are checked in the UPDATE, not reused from
        a previous read. A cancellation committed before this claim denies it;
        a cancellation after a successful claim cannot undo external work.
        """

        if not provider_operation_id.strip():
            raise QuotaConflictError("RESEARCH_QUOTA_PROVIDER_OPERATION_ID_REQUIRED")
        if not all(
            value.strip()
            for value in (
                task_id,
                run_id,
                stage_attempt_id,
                lease_token,
                stage,
                resource_type,
                unit,
            )
        ):
            return False
        # Database evaluation time avoids an application timestamp becoming
        # stale while waiting for a connection. Unknown dialects fail closed.
        now = DatabaseUtcNow()
        live_bucket = (
            select(ResearchQuotaBucket.id)
            .where(
                ResearchQuotaBucket.id == ResearchQuotaReservation.bucket_id,
                ResearchQuotaBucket.status == "ACTIVE",
            )
            .exists()
        )
        live_task = (
            select(ResearchTask.id)
            .where(
                ResearchTask.id == task_id,
                ResearchTask.run_id == run_id,
                ResearchTask.status == "RUNNING",
                ResearchTask.lease_token == lease_token,
                ResearchTask.cancel_requested_at.is_(None),
                ResearchTask.lease_expires_at > now,
            )
            .exists()
        )
        live_attempt = (
            select(ResearchStageAttempt.id)
            .where(
                ResearchStageAttempt.id == stage_attempt_id,
                ResearchStageAttempt.run_id == run_id,
                ResearchStageAttempt.task_id == task_id,
                ResearchStageAttempt.stage == stage,
                ResearchStageAttempt.status == "RUNNING",
                ResearchStageAttempt.lease_token == lease_token,
            )
            .exists()
        )
        async with database.async_session_maker() as session:
            reservation = await session.scalar(
                select(ResearchQuotaReservation)
                .where(ResearchQuotaReservation.id == reservation_id)
                .with_for_update()
            )
            # Preserve the legacy method's boolean stale/unknown receipt
            # contract while refusing to turn one member of a quote bundle
            # into an external side effect.
            if reservation is None or reservation.fencing_token != fencing_token:
                await session.rollback()
                return False
            await _require_legacy_single_mutation_allowed(session, reservation)
            result = await session.execute(
                update(ResearchQuotaReservation)
                .where(
                    ResearchQuotaReservation.id == reservation_id,
                    ResearchQuotaReservation.fencing_token == fencing_token,
                    ResearchQuotaReservation.task_id == task_id,
                    ResearchQuotaReservation.stage_attempt_id == stage_attempt_id,
                    ResearchQuotaReservation.status == "RESERVED",
                    ResearchQuotaReservation.resource_type == resource_type,
                    ResearchQuotaReservation.unit == unit,
                    ResearchQuotaReservation.lease_expires_at > now,
                    live_bucket,
                    live_task,
                    live_attempt,
                )
                .values(status="IN_FLIGHT", provider_operation_id=provider_operation_id)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            return result.rowcount == 1

    async def claim_external_dispatch_bundle(
        self,
        requirements: tuple[QuotaDispatchRequirement, ...],
        *,
        provider_operation_id: str,
        task_id: str,
        run_id: str,
        stage_attempt_id: str,
        lease_token: str,
        stage: str,
    ) -> bool:
        """Atomically claim every receipt in one provider dispatch group.

        No external call is authorized unless every receipt in the durable
        idempotency group makes the same ``RESERVED -> IN_FLIGHT`` transition.
        A stale, incomplete, cancelled, or concurrently-claimed group returns
        ``False`` without changing any receipt.
        """

        ordered = _validate_dispatch_requirements(requirements)
        if not _valid_provider_operation_id(provider_operation_id):
            raise QuotaConflictError("RESEARCH_QUOTA_PROVIDER_OPERATION_ID_REQUIRED")
        if not _valid_dispatch_binding(
            task_id=task_id,
            run_id=run_id,
            stage_attempt_id=stage_attempt_id,
            lease_token=lease_token,
            stage=stage,
        ):
            return False

        # This expression is deliberately embedded in every CAS predicate so
        # connection wait time and application-host clock skew cannot renew a
        # dispatch right.
        now = DatabaseUtcNow()
        live_bucket = (
            select(ResearchQuotaBucket.id)
            .where(
                ResearchQuotaBucket.id == ResearchQuotaReservation.bucket_id,
                ResearchQuotaBucket.status == "ACTIVE",
                ResearchQuotaBucket.resource_type == ResearchQuotaReservation.resource_type,
                ResearchQuotaBucket.policy_version == ResearchQuotaReservation.policy_version,
                ResearchQuotaBucket.window_start <= now,
                ResearchQuotaBucket.window_end > now,
            )
            .exists()
        )
        live_task = (
            select(ResearchTask.id)
            .where(
                ResearchTask.id == task_id,
                ResearchTask.run_id == run_id,
                ResearchTask.status == "RUNNING",
                ResearchTask.stage_cursor == stage,
                ResearchTask.lease_token == lease_token,
                ResearchTask.cancel_requested_at.is_(None),
                ResearchTask.lease_expires_at > now,
            )
            .exists()
        )
        live_attempt = (
            select(ResearchStageAttempt.id)
            .where(
                ResearchStageAttempt.id == stage_attempt_id,
                ResearchStageAttempt.run_id == run_id,
                ResearchStageAttempt.task_id == task_id,
                ResearchStageAttempt.stage == stage,
                ResearchStageAttempt.status == "RUNNING",
                ResearchStageAttempt.lease_token == lease_token,
            )
            .exists()
        )
        async with database.async_session_maker() as session:
            try:
                reservations = await _locked_complete_bundle_group(
                    session, tuple(item.reservation_id for item in ordered)
                )
                if not _dispatch_group_matches(
                    reservations,
                    ordered,
                    task_id=task_id,
                    stage_attempt_id=stage_attempt_id,
                ):
                    await session.rollback()
                    return False

                by_id = {reservation.id: reservation for reservation in reservations}
                for requirement in ordered:
                    reservation = by_id[requirement.reservation_id]
                    claimed = await session.execute(
                        update(ResearchQuotaReservation)
                        .where(
                            ResearchQuotaReservation.id == reservation.id,
                            ResearchQuotaReservation.fencing_token == requirement.fencing_token,
                            ResearchQuotaReservation.task_id == task_id,
                            ResearchQuotaReservation.stage_attempt_id == stage_attempt_id,
                            ResearchQuotaReservation.status == "RESERVED",
                            ResearchQuotaReservation.provider_operation_id.is_(None),
                            ResearchQuotaReservation.resource_type == requirement.resource_type,
                            ResearchQuotaReservation.unit == requirement.unit,
                            ResearchQuotaReservation.reserved_amount == requirement.reserved_amount,
                            ResearchQuotaReservation.request_hash == requirement.request_hash,
                            ResearchQuotaReservation.lease_expires_at
                            > DatabaseUtcAfter(requirement.minimum_remaining_seconds),
                            live_bucket,
                            live_task,
                            live_attempt,
                        )
                        .values(status="IN_FLIGHT", provider_operation_id=provider_operation_id)
                        .execution_options(synchronize_session=False)
                    )
                    if claimed.rowcount != 1:
                        await session.rollback()
                        return False
                await session.commit()
                return True
            except OperationalError:
                # SQLite can surface a write collision rather than waiting for
                # the competing transaction. It is a denied dispatch, never a
                # reason to contact the provider optimistically.
                await session.rollback()
                return False

    async def settle_bundle(
        self,
        requests: tuple[QuotaSettlementRequest, ...],
        *,
        provider_operation_id: str,
    ) -> bool:
        """Atomically settle every receipt previously claimed as one bundle.

        Settlement does not re-authorize an expired worker: it only records a
        provider result already durably claimed.  Every requested receipt must
        be the complete, same-operation ``IN_FLIGHT`` group; any failed CAS or
        bucket arithmetic check rolls the entire transaction back.
        """

        ordered = _validate_settlement_requests(requests)
        if not _valid_provider_operation_id(provider_operation_id):
            raise QuotaConflictError("RESEARCH_QUOTA_PROVIDER_OPERATION_ID_REQUIRED")

        async with database.async_session_maker() as session:
            try:
                reservations = await _locked_complete_bundle_group(
                    session, tuple(item.reservation_id for item in ordered)
                )
                if not _settlement_group_matches(
                    reservations,
                    ordered,
                    provider_operation_id=provider_operation_id,
                ):
                    await session.rollback()
                    return False
                if len({reservation.bucket_id for reservation in reservations}) != len(
                    reservations
                ):
                    await session.rollback()
                    return False

                by_id = {reservation.id: reservation for reservation in reservations}
                if any(
                    item.settled_amount > by_id[item.reservation_id].reserved_amount
                    for item in ordered
                ):
                    await session.rollback()
                    return False

                settled_at = await database_utc_now(session)
                for request in ordered:
                    reservation = by_id[request.reservation_id]
                    settled = await session.execute(
                        update(ResearchQuotaReservation)
                        .where(
                            ResearchQuotaReservation.id == reservation.id,
                            ResearchQuotaReservation.fencing_token == request.fencing_token,
                            ResearchQuotaReservation.status == "IN_FLIGHT",
                            ResearchQuotaReservation.provider_operation_id == provider_operation_id,
                        )
                        .values(
                            status="SETTLED",
                            settled_amount=request.settled_amount,
                            settled_at=settled_at,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    if settled.rowcount != 1:
                        await session.rollback()
                        return False

                for reservation in reservations:
                    request = next(
                        item for item in ordered if item.reservation_id == reservation.id
                    )
                    adjusted = await session.execute(
                        update(ResearchQuotaBucket)
                        .where(
                            ResearchQuotaBucket.id == reservation.bucket_id,
                            ResearchQuotaBucket.reserved_amount >= reservation.reserved_amount,
                            ResearchQuotaBucket.active_reservations >= 1,
                        )
                        .values(
                            reserved_amount=(
                                ResearchQuotaBucket.reserved_amount - reservation.reserved_amount
                            ),
                            settled_amount=ResearchQuotaBucket.settled_amount
                            + request.settled_amount,
                            active_reservations=ResearchQuotaBucket.active_reservations - 1,
                            version=ResearchQuotaBucket.version + 1,
                            updated_at=settled_at,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    if adjusted.rowcount != 1:
                        await session.rollback()
                        return False
                await session.commit()
                return True
            except OperationalError:
                await session.rollback()
                return False

    async def mark_in_flight(
        self,
        reservation_id: str,
        fencing_token: int,
        *,
        provider_operation_id: str,
    ) -> bool:
        """Record an operation id idempotently; do not use as dispatch permission.

        External callers must use ``claim_external_dispatch`` to prevent
        duplicate execution. This method retains its reconciliation-compatible
        behavior for existing callers already tracking an operation.
        """

        if not provider_operation_id.strip():
            raise QuotaConflictError("RESEARCH_QUOTA_PROVIDER_OPERATION_ID_REQUIRED")
        async with database.async_session_maker() as session:
            reservation = await _locked_reservation(session, reservation_id)
            _require_fencing(reservation, fencing_token)
            await _require_legacy_single_mutation_allowed(session, reservation)
            if reservation.status == "IN_FLIGHT":
                if reservation.provider_operation_id != provider_operation_id:
                    raise QuotaConflictError("RESEARCH_QUOTA_PROVIDER_OPERATION_CONFLICT")
                return True
            if reservation.status != "RESERVED":
                return False
            now = await database_utc_now(session)
            if reservation.lease_expires_at is None or _as_utc(reservation.lease_expires_at) <= now:
                return False
            reservation.status = "IN_FLIGHT"
            reservation.provider_operation_id = provider_operation_id
            await session.commit()
            return True

    async def settle(
        self,
        reservation_id: str,
        fencing_token: int,
        *,
        settled_amount: int,
    ) -> bool:
        """Settle a confirmed external result exactly once."""

        if type(settled_amount) is not int or settled_amount < 0:
            raise QuotaConflictError("RESEARCH_QUOTA_SETTLED_AMOUNT_INVALID")
        async with database.async_session_maker() as session:
            reservation = await _locked_reservation(session, reservation_id)
            _require_fencing(reservation, fencing_token)
            await _require_legacy_single_mutation_allowed(session, reservation)
            if reservation.status in {"SETTLED", "RELEASED"}:
                return False
            if reservation.status == "RECONCILING":
                raise QuotaConflictError("RESEARCH_QUOTA_RECONCILIATION_REQUIRED")
            if reservation.status not in {"RESERVED", "IN_FLIGHT"}:
                raise QuotaConflictError("RESEARCH_QUOTA_SETTLEMENT_NOT_ALLOWED")
            if settled_amount > reservation.reserved_amount:
                raise QuotaConflictError("RESEARCH_QUOTA_SETTLED_AMOUNT_EXCEEDS_RESERVATION")
            now = _now()
            claimed = await session.execute(
                update(ResearchQuotaReservation)
                .where(
                    ResearchQuotaReservation.id == reservation.id,
                    ResearchQuotaReservation.fencing_token == fencing_token,
                    ResearchQuotaReservation.status.in_(("RESERVED", "IN_FLIGHT")),
                )
                .values(status="SETTLED", settled_amount=settled_amount, settled_at=now)
                .execution_options(synchronize_session=False)
            )
            if claimed.rowcount != 1:
                return False
            # Arithmetic UPDATE avoids overwriting another receipt's completed
            # settlement with an older ORM snapshot (notably SQLite, which
            # ignores SELECT FOR UPDATE). The reservation transition and this
            # aggregate change commit or roll back together.
            adjusted = await session.execute(
                update(ResearchQuotaBucket)
                .where(
                    ResearchQuotaBucket.id == reservation.bucket_id,
                    ResearchQuotaBucket.reserved_amount >= reservation.reserved_amount,
                    ResearchQuotaBucket.active_reservations >= 1,
                )
                .values(
                    reserved_amount=(
                        ResearchQuotaBucket.reserved_amount - reservation.reserved_amount
                    ),
                    settled_amount=ResearchQuotaBucket.settled_amount + settled_amount,
                    active_reservations=ResearchQuotaBucket.active_reservations - 1,
                    version=ResearchQuotaBucket.version + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if adjusted.rowcount != 1:
                raise QuotaConflictError("RESEARCH_QUOTA_BUCKET_ACCOUNTING_CORRUPT")
            await session.commit()
            return True

    async def release(self, reservation_id: str, fencing_token: int) -> bool:
        """Release only a reservation proved not to have dispatched work."""

        async with database.async_session_maker() as session:
            reservation = await _locked_reservation(session, reservation_id)
            _require_fencing(reservation, fencing_token)
            await _require_legacy_single_mutation_allowed(session, reservation)
            if reservation.status == "RELEASED":
                return False
            if reservation.status != "RESERVED":
                raise QuotaConflictError("RESEARCH_QUOTA_RELEASE_REQUIRES_NOOP_PROOF")
            bucket = await _locked_bucket(session, reservation.bucket_id)
            _release_bucket(bucket, reservation.reserved_amount)
            reservation.status = "RELEASED"
            reservation.released_at = _now()
            await session.commit()
            return True

    async def reconcile_expired(self, *, now: datetime | None = None) -> int:
        """Block expired work for explicit provider reconciliation, never release it."""

        changed = 0
        async with database.async_session_maker() as session:
            reference_time = _as_utc(now) if now is not None else await database_utc_now(session)
            result = await session.execute(
                select(ResearchQuotaReservation)
                .where(ResearchQuotaReservation.status.in_(("RESERVED", "IN_FLIGHT")))
                .with_for_update()
            )
            reservations = list(result.scalars())
            for reservation in reservations:
                if (
                    reservation.lease_expires_at is None
                    or _as_utc(reservation.lease_expires_at) > reference_time
                ):
                    continue
                bucket = await _locked_bucket(session, reservation.bucket_id)
                reservation.status = "RECONCILING"
                reservation.reason = "lease_expired_external_operation_unknown"
                bucket.status = "BLOCKED_UNKNOWN"
                bucket.reconcile_reason = "expired_reservation_requires_provider_readback"
                bucket.version += 1
                bucket.updated_at = reference_time
                changed += 1
            await session.commit()
        return changed

    async def resolve_reconciliation(
        self,
        reservation_id: str,
        fencing_token: int,
        *,
        outcome: str,
        settled_amount: int = 0,
    ) -> bool:
        """Apply an explicit, auditable provider readback outcome."""

        if outcome not in {"NO_OPERATION", "SETTLED"}:
            raise QuotaConflictError("RESEARCH_QUOTA_RECONCILIATION_OUTCOME_INVALID")
        async with database.async_session_maker() as session:
            reservation = await _locked_reservation(session, reservation_id)
            _require_fencing(reservation, fencing_token)
            await _require_legacy_single_mutation_allowed(session, reservation)
            if reservation.status != "RECONCILING":
                raise QuotaConflictError("RESEARCH_QUOTA_RECONCILIATION_NOT_REQUIRED")
            bucket = await _locked_bucket(session, reservation.bucket_id)
            if outcome == "NO_OPERATION":
                _release_bucket(bucket, reservation.reserved_amount)
                reservation.status = "RELEASED"
                reservation.released_at = _now()
            else:
                if settled_amount < 0 or settled_amount > reservation.reserved_amount:
                    raise QuotaConflictError("RESEARCH_QUOTA_SETTLED_AMOUNT_INVALID")
                _settle_bucket(bucket, reservation.reserved_amount, settled_amount)
                reservation.status = "SETTLED"
                reservation.settled_amount = settled_amount
                reservation.settled_at = _now()
            bucket.status = "ACTIVE"
            bucket.reconcile_reason = None
            bucket.version += 1
            bucket.updated_at = _now()
            await session.commit()
            return True


def _validate_reservation_request(
    *,
    task_id: str,
    policy_version: str,
    idempotency_key: str,
    request_hash: str,
    requests: tuple[QuotaReservationRequest, ...],
    lease_seconds: int,
    reservation_context: dict[str, Any] | None,
) -> None:
    if not all(
        _valid_nonempty_string(value) for value in (task_id, policy_version, idempotency_key)
    ):
        raise QuotaConflictError("RESEARCH_QUOTA_IDENTITY_REQUIRED")
    if not isinstance(request_hash, str) or len(request_hash) != 64:
        raise QuotaConflictError("RESEARCH_QUOTA_REQUEST_HASH_INVALID")
    if reservation_context is not None and content_hash(reservation_context) != request_hash:
        raise QuotaConflictError("RESEARCH_QUOTA_REQUEST_HASH_INVALID")
    if not requests or lease_seconds < 1:
        raise QuotaConflictError("RESEARCH_QUOTA_REQUEST_INVALID")
    bucket_ids = [item.bucket_id for item in requests]
    if len(bucket_ids) != len(set(bucket_ids)):
        raise QuotaConflictError("RESEARCH_QUOTA_DUPLICATE_BUCKET")
    for item in requests:
        if (
            not isinstance(item, QuotaReservationRequest)
            or not all(
                _valid_nonempty_string(value)
                for value in (item.bucket_id, item.resource_type, item.unit)
            )
            or type(item.amount) is not int
            or not 0 < item.amount <= _MAX_QUOTA_AMOUNT
            or (item.resource_type == _MODEL_COST_RESOURCE_TYPE and item.unit != _MODEL_COST_UNIT)
        ):
            raise QuotaConflictError("RESEARCH_QUOTA_REQUEST_INVALID")


def _validate_dispatch_requirements(
    requirements: tuple[QuotaDispatchRequirement, ...],
) -> tuple[QuotaDispatchRequirement, ...]:
    """Reject malformed bundle inputs before any durable transition."""

    if not isinstance(requirements, tuple) or not requirements:
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if any(not isinstance(item, QuotaDispatchRequirement) for item in requirements):
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if len({item.reservation_id for item in requirements}) != len(requirements):
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if len({item.request_hash for item in requirements}) != 1:
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if any(type(item.require_reservation_context) is not bool for item in requirements):
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if len({item.require_reservation_context for item in requirements}) != 1:
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if any(
        type(item.reservation_context_schema) is not str
        or item.reservation_context_schema
        not in {_MODEL_BUDGET_CONTEXT_SCHEMA, "discovery-execution-intent-v1"}
        for item in requirements
    ):
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if len({item.reservation_context_schema for item in requirements}) != 1:
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    for item in requirements:
        if (
            not all(
                _valid_nonempty_string(value)
                for value in (item.reservation_id, item.resource_type, item.unit, item.request_hash)
            )
            or type(item.fencing_token) is not int
            or item.fencing_token < 1
            or type(item.reserved_amount) is not int
            or not 0 < item.reserved_amount <= _MAX_QUOTA_AMOUNT
            or len(item.request_hash) != 64
            or type(item.minimum_remaining_seconds) is not int
            or not 0 <= item.minimum_remaining_seconds <= 7200
            or (item.resource_type == _MODEL_COST_RESOURCE_TYPE and item.unit != _MODEL_COST_UNIT)
        ):
            raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    return tuple(sorted(requirements, key=lambda item: item.reservation_id))


def _validate_settlement_requests(
    requests: tuple[QuotaSettlementRequest, ...],
) -> tuple[QuotaSettlementRequest, ...]:
    """Reject malformed settlement payloads before a group read."""

    if not isinstance(requests, tuple) or not requests:
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if any(not isinstance(item, QuotaSettlementRequest) for item in requests):
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    if len({item.reservation_id for item in requests}) != len(requests):
        raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    for item in requests:
        if (
            not _valid_nonempty_string(item.reservation_id)
            or type(item.fencing_token) is not int
            or item.fencing_token < 1
            or type(item.settled_amount) is not int
            or not 0 <= item.settled_amount <= _MAX_QUOTA_AMOUNT
        ):
            raise QuotaConflictError("RESEARCH_QUOTA_BUNDLE_INVALID")
    return tuple(sorted(requests, key=lambda item: item.reservation_id))


async def _locked_complete_bundle_group(
    session: AsyncSession,
    reservation_ids: tuple[str, ...],
) -> tuple[ResearchQuotaReservation, ...] | None:
    """Lock exactly one durable idempotency group, or fail closed."""

    requested_result = await session.execute(
        select(ResearchQuotaReservation)
        .where(ResearchQuotaReservation.id.in_(reservation_ids))
        .order_by(ResearchQuotaReservation.id)
        .with_for_update()
    )
    requested = tuple(requested_result.scalars())
    if len(requested) != len(reservation_ids):
        return None
    reference = requested[0]
    if reference.stage_attempt_id is None:
        return None
    group_result = await session.execute(
        select(ResearchQuotaReservation)
        .where(
            ResearchQuotaReservation.task_id == reference.task_id,
            ResearchQuotaReservation.stage_attempt_id == reference.stage_attempt_id,
            ResearchQuotaReservation.idempotency_key == reference.idempotency_key,
        )
        .order_by(ResearchQuotaReservation.id)
        .with_for_update()
    )
    group = tuple(group_result.scalars())
    if {item.id for item in group} != set(reservation_ids):
        return None
    if any(
        item.task_id != reference.task_id
        or item.stage_attempt_id != reference.stage_attempt_id
        or item.idempotency_key != reference.idempotency_key
        or item.policy_version != reference.policy_version
        or item.request_hash != reference.request_hash
        for item in group
    ):
        return None
    return group


def _dispatch_group_matches(
    reservations: tuple[ResearchQuotaReservation, ...] | None,
    requirements: tuple[QuotaDispatchRequirement, ...],
    *,
    task_id: str,
    stage_attempt_id: str,
) -> bool:
    if reservations is None or len(reservations) != len(requirements):
        return False
    if not _bundle_context_is_consistent(
        reservations,
        require_reservation_context=requirements[0].require_reservation_context,
        reservation_context_schema=requirements[0].reservation_context_schema,
    ):
        return False
    by_id = {reservation.id: reservation for reservation in reservations}
    for requirement in requirements:
        reservation = by_id.get(requirement.reservation_id)
        if (
            reservation is None
            or reservation.task_id != task_id
            or reservation.stage_attempt_id != stage_attempt_id
            or reservation.status != "RESERVED"
            or reservation.provider_operation_id is not None
            or reservation.fencing_token != requirement.fencing_token
            or reservation.resource_type != requirement.resource_type
            or reservation.unit != requirement.unit
            or reservation.reserved_amount != requirement.reserved_amount
            or reservation.request_hash != requirement.request_hash
        ):
            return False
    return True


def _settlement_group_matches(
    reservations: tuple[ResearchQuotaReservation, ...] | None,
    requests: tuple[QuotaSettlementRequest, ...],
    *,
    provider_operation_id: str,
) -> bool:
    if reservations is None or len(reservations) != len(requests):
        return False
    if not _bundle_context_is_consistent(reservations):
        return False
    by_id = {reservation.id: reservation for reservation in reservations}
    for request in requests:
        reservation = by_id.get(request.reservation_id)
        if (
            reservation is None
            or reservation.status != "IN_FLIGHT"
            or reservation.provider_operation_id != provider_operation_id
            or reservation.fencing_token != request.fencing_token
        ):
            return False
    return True


def _bundle_context_is_consistent(
    reservations: tuple[ResearchQuotaReservation, ...],
    *,
    require_reservation_context: bool = False,
    reservation_context_schema: str = _MODEL_BUDGET_CONTEXT_SCHEMA,
) -> bool:
    """Require a coherent persisted quote, optionally of the strict budget kind."""

    normalized_contexts: list[dict[str, Any] | None] = []
    for reservation in reservations:
        try:
            normalized_contexts.append(
                _normalize_reservation_context(reservation.reservation_context)
            )
        except QuotaConflictError:
            return False
    if all(context is None for context in normalized_contexts):
        return not require_reservation_context
    if any(context is None for context in normalized_contexts):
        return False
    first = normalized_contexts[0]
    assert first is not None
    if require_reservation_context and first.get("schema_version") != reservation_context_schema:
        return False
    context_hash = content_hash(first)
    return all(
        context is not None
        and canonical_json(context) == canonical_json(first)
        and reservation.request_hash == context_hash
        for context, reservation in zip(normalized_contexts, reservations, strict=True)
    )


def _normalize_reservation_context(
    reservation_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Canonicalize and detach a JSON context before storing or comparing it."""

    if reservation_context is None:
        return None
    if not isinstance(reservation_context, dict):
        raise QuotaConflictError("RESEARCH_QUOTA_RESERVATION_CONTEXT_INVALID")
    try:
        normalized = json.loads(canonical_json(reservation_context))
    except (TypeError, ValueError) as exc:
        raise QuotaConflictError("RESEARCH_QUOTA_RESERVATION_CONTEXT_INVALID") from exc
    if not isinstance(normalized, dict):
        raise QuotaConflictError("RESEARCH_QUOTA_RESERVATION_CONTEXT_INVALID")
    return normalized


def _copy_context(reservation_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if reservation_context is None:
        return None
    return json.loads(canonical_json(reservation_context))


def _contexts_match(
    stored_context: dict[str, Any] | None,
    requested_context: dict[str, Any] | None,
) -> bool:
    try:
        return _normalize_reservation_context(stored_context) == requested_context
    except QuotaConflictError:
        return False


def _valid_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_provider_operation_id(value: object) -> bool:
    return _valid_nonempty_string(value)


def _valid_dispatch_binding(
    *,
    task_id: str,
    run_id: str,
    stage_attempt_id: str,
    lease_token: str,
    stage: str,
) -> bool:
    return all(
        _valid_nonempty_string(value)
        for value in (task_id, run_id, stage_attempt_id, lease_token, stage)
    )


async def _existing_reservations(
    session: AsyncSession,
    task_id: str,
    idempotency_key: str,
) -> list[ResearchQuotaReservation]:
    result = await session.execute(
        select(ResearchQuotaReservation)
        .where(
            ResearchQuotaReservation.task_id == task_id,
            ResearchQuotaReservation.idempotency_key == idempotency_key,
        )
        .order_by(ResearchQuotaReservation.bucket_id)
        .with_for_update()
    )
    return list(result.scalars())


async def _validate_task_binding(
    session: AsyncSession,
    task_id: str,
    stage_attempt_id: str | None,
) -> None:
    task = await session.get(ResearchTask, task_id)
    if task is None:
        raise QuotaConflictError("RESEARCH_QUOTA_TASK_NOT_FOUND")
    if stage_attempt_id is None:
        return
    stage_attempt = await session.get(ResearchStageAttempt, stage_attempt_id)
    if stage_attempt is None or stage_attempt.task_id != task.id:
        raise QuotaConflictError("RESEARCH_QUOTA_STAGE_ATTEMPT_MISMATCH")


async def _require_legacy_single_mutation_allowed(
    session: AsyncSession,
    reservation: ResearchQuotaReservation,
) -> None:
    """Reject old single-receipt mutations for a durable dispatch bundle.

    Bundle claim/settle has all-or-nothing primitives.  There is intentionally
    no equivalent reconciliation primitive yet, so a stale operator cannot use
    the older one-receipt APIs to release or settle only tokens or only money.
    A malformed stored context is also denied: it cannot prove that a legacy
    single-resource compatibility path is safe.
    """

    try:
        context = _normalize_reservation_context(reservation.reservation_context)
    except QuotaConflictError:
        raise QuotaConflictError(_BUNDLE_MUTATION_REQUIRED) from None
    if context is not None and context.get("schema_version") == _MODEL_BUDGET_CONTEXT_SCHEMA:
        raise QuotaConflictError(_BUNDLE_MUTATION_REQUIRED)

    # Idempotency groups are immutable through ``reserve``.  Reading the group
    # is enough for this deny gate; bundle mutations acquire and CAS every
    # member themselves.  Do not lock the complete group here after first
    # locking one member, which could create opposing lock order for two stale
    # legacy callers.
    result = await session.execute(
        select(ResearchQuotaReservation.id).where(
            ResearchQuotaReservation.task_id == reservation.task_id,
            ResearchQuotaReservation.stage_attempt_id == reservation.stage_attempt_id,
            ResearchQuotaReservation.idempotency_key == reservation.idempotency_key,
        )
    )
    if len(tuple(result.scalars())) != 1:
        raise QuotaConflictError(_BUNDLE_MUTATION_REQUIRED)


def _existing_receipts(
    existing: list[ResearchQuotaReservation],
    *,
    request_hash: str,
    policy_version: str,
    requests: tuple[QuotaReservationRequest, ...],
    reservation_context: dict[str, Any] | None,
) -> tuple[QuotaReservationReceipt, ...]:
    if any(
        reservation.request_hash != request_hash
        or reservation.policy_version != policy_version
        or not _contexts_match(reservation.reservation_context, reservation_context)
        for reservation in existing
    ):
        raise QuotaConflictError("RESEARCH_QUOTA_IDEMPOTENCY_CONFLICT")
    by_bucket = {reservation.bucket_id: reservation for reservation in existing}
    if len(by_bucket) != len(requests):
        raise QuotaConflictError("RESEARCH_QUOTA_IDEMPOTENCY_CONFLICT")
    receipts: list[QuotaReservationReceipt] = []
    for item in requests:
        reservation = by_bucket.get(item.bucket_id)
        if (
            reservation is None
            or reservation.resource_type != item.resource_type
            or reservation.reserved_amount != item.amount
            or reservation.unit != item.unit
        ):
            raise QuotaConflictError("RESEARCH_QUOTA_IDEMPOTENCY_CONFLICT")
        receipts.append(_receipt(reservation))
    return tuple(receipts)


async def _locked_buckets(
    session: AsyncSession,
    bucket_ids: tuple[str, ...],
) -> dict[str, ResearchQuotaBucket]:
    result = await session.execute(
        select(ResearchQuotaBucket)
        .where(ResearchQuotaBucket.id.in_(bucket_ids))
        .order_by(ResearchQuotaBucket.id)
        .with_for_update()
    )
    buckets = {bucket.id: bucket for bucket in result.scalars()}
    if len(buckets) != len(bucket_ids):
        raise QuotaUnavailableError("RESEARCH_QUOTA_BUCKET_NOT_FOUND")
    return buckets


def _validate_buckets(
    buckets: dict[str, ResearchQuotaBucket],
    requests: tuple[QuotaReservationRequest, ...],
    *,
    policy_version: str,
    now: datetime,
) -> None:
    for item in requests:
        bucket = buckets[item.bucket_id]
        if bucket.policy_version != policy_version:
            raise QuotaConflictError("RESEARCH_QUOTA_POLICY_MISMATCH")
        if bucket.resource_type != item.resource_type:
            raise QuotaConflictError("RESEARCH_QUOTA_RESOURCE_MISMATCH")
        if bucket.status != "ACTIVE":
            raise QuotaUnavailableError("RESEARCH_QUOTA_BUCKET_BLOCKED_UNKNOWN")
        if _as_utc(bucket.window_start) > now or _as_utc(bucket.window_end) <= now:
            raise QuotaUnavailableError("RESEARCH_QUOTA_WINDOW_INACTIVE")
        if bucket.reserved_amount + bucket.settled_amount + item.amount > bucket.hard_limit:
            raise QuotaUnavailableError("RESEARCH_QUOTA_HARD_LIMIT_EXCEEDED")
        if bucket.active_reservations + 1 > bucket.concurrency_limit:
            raise QuotaUnavailableError("RESEARCH_QUOTA_CONCURRENCY_LIMIT_EXCEEDED")


async def _locked_reservation(
    session: AsyncSession,
    reservation_id: str,
) -> ResearchQuotaReservation:
    result = await session.execute(
        select(ResearchQuotaReservation)
        .where(ResearchQuotaReservation.id == reservation_id)
        .with_for_update()
    )
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise QuotaConflictError("RESEARCH_QUOTA_RESERVATION_NOT_FOUND")
    return reservation


async def _locked_bucket(session: AsyncSession, bucket_id: str) -> ResearchQuotaBucket:
    result = await session.execute(
        select(ResearchQuotaBucket).where(ResearchQuotaBucket.id == bucket_id).with_for_update()
    )
    bucket = result.scalar_one_or_none()
    if bucket is None:
        raise QuotaConflictError("RESEARCH_QUOTA_BUCKET_NOT_FOUND")
    return bucket


def _require_fencing(reservation: ResearchQuotaReservation, fencing_token: int) -> None:
    if reservation.fencing_token != fencing_token:
        raise QuotaConflictError("RESEARCH_QUOTA_FENCING_TOKEN_STALE")


def _settle_bucket(bucket: ResearchQuotaBucket, reserved_amount: int, settled_amount: int) -> None:
    if bucket.reserved_amount < reserved_amount or bucket.active_reservations < 1:
        raise QuotaConflictError("RESEARCH_QUOTA_BUCKET_ACCOUNTING_CORRUPT")
    bucket.reserved_amount -= reserved_amount
    bucket.settled_amount += settled_amount
    bucket.active_reservations -= 1
    bucket.version += 1
    bucket.updated_at = _now()


def _release_bucket(bucket: ResearchQuotaBucket, reserved_amount: int) -> None:
    if bucket.reserved_amount < reserved_amount or bucket.active_reservations < 1:
        raise QuotaConflictError("RESEARCH_QUOTA_BUCKET_ACCOUNTING_CORRUPT")
    bucket.reserved_amount -= reserved_amount
    bucket.active_reservations -= 1
    bucket.version += 1
    bucket.updated_at = _now()


def _receipt(reservation: ResearchQuotaReservation) -> QuotaReservationReceipt:
    if reservation.lease_expires_at is None:
        raise QuotaConflictError("RESEARCH_QUOTA_LEASE_MISSING")
    return QuotaReservationReceipt(
        reservation_id=reservation.id,
        bucket_id=reservation.bucket_id,
        resource_type=reservation.resource_type,
        reserved_amount=reservation.reserved_amount,
        unit=reservation.unit,
        fencing_token=reservation.fencing_token,
        lease_expires_at=_as_utc(reservation.lease_expires_at),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
