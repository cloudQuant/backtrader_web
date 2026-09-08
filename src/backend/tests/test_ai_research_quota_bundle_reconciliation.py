"""Fail-closed guards for legacy single-receipt quota mutations.

A model-budget quote reserves token and micro-USD receipts as one durable
external-operation group.  Until an explicit bundle reconciliation API exists,
old single-receipt mutation methods must not split that group.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import database
from app.models.ai_research_v2 import (
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
)
from app.services.research.canonical import content_hash
from app.services.research.quota import (
    QuotaConflictError,
    QuotaDispatchRequirement,
    QuotaReservationReceipt,
    QuotaReservationRequest,
    QuotaService,
)

_BUNDLE_MUTATION_REQUIRED = "RESEARCH_QUOTA_BUNDLE_OPERATION_REQUIRED"


@pytest_asyncio.fixture
async def quota_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Run the mutation gate against a real independent SQLite database."""

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'quota-bundle-reconciliation.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(database.Base.metadata.create_all)
        with monkeypatch.context() as local_patch:
            local_patch.setattr(database, "async_session_maker", sessions)
            yield
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ("NO_OPERATION", "SETTLED"))
async def test_single_reconciliation_cannot_split_an_expired_budget_bundle(
    quota_database: None, outcome: str
) -> None:
    context = await _context()
    receipts, request_hash = await _reserve_budget_bundle(context)
    service = QuotaService()
    assert await service.claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id="provider-budget-operation",
        **_dispatch_binding(context),
    )
    await _expire(receipts)
    assert await service.reconcile_expired(now=datetime.now(timezone.utc)) == 2

    before = await _state(receipts)
    token = _receipt_for(receipts, "model_tokens")
    with pytest.raises(QuotaConflictError, match=f"^{_BUNDLE_MUTATION_REQUIRED}$"):
        await service.resolve_reconciliation(
            token.reservation_id,
            token.fencing_token,
            outcome=outcome,
            settled_amount=1,
        )

    assert await _state(receipts) == before
    assert {item["status"] for item in before["reservations"].values()} == {"RECONCILING"}
    assert {item["status"] for item in before["buckets"].values()} == {"BLOCKED_UNKNOWN"}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("claim", "mark", "settle", "release"))
async def test_legacy_single_mutators_cannot_change_a_budget_bundle(
    quota_database: None, operation: str
) -> None:
    context = await _context()
    receipts, request_hash = await _reserve_budget_bundle(context)
    token = _receipt_for(receipts, "model_tokens")
    service = QuotaService()
    before = await _state(receipts)

    with pytest.raises(QuotaConflictError, match=f"^{_BUNDLE_MUTATION_REQUIRED}$"):
        if operation == "claim":
            await service.claim_external_dispatch(
                token.reservation_id,
                token.fencing_token,
                provider_operation_id="legacy-single-claim",
                resource_type=token.resource_type,
                unit=token.unit,
                **_dispatch_binding(context),
            )
        elif operation == "mark":
            await service.mark_in_flight(
                token.reservation_id,
                token.fencing_token,
                provider_operation_id="legacy-single-mark",
            )
        elif operation == "settle":
            await service.settle(token.reservation_id, token.fencing_token, settled_amount=1)
        else:
            await service.release(token.reservation_id, token.fencing_token)

    assert await _state(receipts) == before
    assert request_hash == content_hash(_budget_context(context))


@pytest.mark.asyncio
async def test_model_budget_context_denies_legacy_mutation_even_without_a_second_receipt(
    quota_database: None,
) -> None:
    context = await _context()
    receipt = await _reserve_single(context, reservation_context=_budget_context(context))
    before = await _state((receipt,))

    with pytest.raises(QuotaConflictError, match=f"^{_BUNDLE_MUTATION_REQUIRED}$"):
        await QuotaService().release(receipt.reservation_id, receipt.fencing_token)

    assert await _state((receipt,)) == before


@pytest.mark.asyncio
async def test_legacy_single_resource_reconciliation_remains_compatible(
    quota_database: None,
) -> None:
    context = await _context()
    receipt = await _reserve_single(context)
    service = QuotaService()
    assert await service.mark_in_flight(
        receipt.reservation_id,
        receipt.fencing_token,
        provider_operation_id="legacy-single-operation",
    )
    await _expire((receipt,))
    assert await service.reconcile_expired(now=datetime.now(timezone.utc)) == 1

    assert await service.resolve_reconciliation(
        receipt.reservation_id,
        receipt.fencing_token,
        outcome="SETTLED",
        settled_amount=3,
    )
    state = await _state((receipt,))
    reservation = state["reservations"][receipt.reservation_id]
    bucket = state["buckets"][receipt.bucket_id]
    assert reservation["status"] == "SETTLED"
    assert reservation["settled_amount"] == 3
    assert bucket == {
        "status": "ACTIVE",
        "reserved_amount": 0,
        "settled_amount": 3,
        "active_reservations": 0,
        "reconcile_reason": None,
    }


async def _context() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id="bundle-reconciliation-user",
        hypothesis_version_id="hypothesis-bundle-reconciliation",
        dataset_snapshot_id="dataset-bundle-reconciliation",
        experiment_epoch_id="epoch-bundle-reconciliation",
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="profile-bundle-reconciliation",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id="trace-bundle-reconciliation",
    )
    buckets = (
        ResearchQuotaBucket(
            scope_type="user",
            scope_id="bundle-reconciliation-user",
            policy_version="quota-v1",
            resource_type="model_tokens",
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=1_000,
            concurrency_limit=10,
        ),
        ResearchQuotaBucket(
            scope_type="user",
            scope_id="bundle-reconciliation-user",
            policy_version="quota-v1",
            resource_type="model_cost_microusd",
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=1_000,
            concurrency_limit=10,
        ),
    )
    lease_token = "bundle-reconciliation-lease"
    async with database.async_session_maker() as session:
        session.add_all((run, *buckets))
        await session.commit()
        await session.refresh(run)
        for bucket in buckets:
            await session.refresh(bucket)
        task = ResearchTask(
            user_id=run.user_id,
            run_id=run.id,
            status="RUNNING",
            stage_cursor="GENERATE",
            request_json={},
            idempotency_key="bundle-reconciliation-task",
            idempotency_request_hash="t" * 64,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(hours=1),
            lease_heartbeat_at=now,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        attempt = ResearchStageAttempt(
            run_id=run.id,
            task_id=task.id,
            stage="GENERATE",
            attempt_no=1,
            idempotency_key="bundle-reconciliation-attempt",
            status="RUNNING",
            lease_token=lease_token,
            input_hash="i" * 64,
        )
        session.add(attempt)
        await session.commit()
        await session.refresh(attempt)
    return {
        "run": run,
        "task": task,
        "attempt": attempt,
        "buckets": buckets,
        "lease_token": lease_token,
    }


async def _reserve_budget_bundle(
    context: dict[str, object],
) -> tuple[tuple[QuotaReservationReceipt, ...], str]:
    reservation_context = _budget_context(context)
    request_hash = content_hash(reservation_context)
    receipts = await QuotaService().reserve(
        task_id=_task(context).id,
        policy_version="quota-v1",
        idempotency_key="budget-bundle",
        request_hash=request_hash,
        reservation_context=reservation_context,
        requests=(
            QuotaReservationRequest(
                _bucket_for(context, "model_tokens").id, "model_tokens", 32, "tokens"
            ),
            QuotaReservationRequest(
                _bucket_for(context, "model_cost_microusd").id,
                "model_cost_microusd",
                41,
                "microusd",
            ),
        ),
        stage_attempt_id=_attempt(context).id,
    )
    return receipts, request_hash


async def _reserve_single(
    context: dict[str, object], *, reservation_context: dict[str, Any] | None = None
) -> QuotaReservationReceipt:
    request_hash = (
        content_hash(reservation_context) if reservation_context is not None else "s" * 64
    )
    return (
        await QuotaService().reserve(
            task_id=_task(context).id,
            policy_version="quota-v1",
            idempotency_key="legacy-single",
            request_hash=request_hash,
            reservation_context=reservation_context,
            requests=(
                QuotaReservationRequest(
                    _bucket_for(context, "model_tokens").id, "model_tokens", 32, "tokens"
                ),
            ),
            stage_attempt_id=_attempt(context).id,
        )
    )[0]


def _budget_context(context: dict[str, object]) -> dict[str, Any]:
    return {
        "schema_version": "model-budget-quote-v1",
        "run_request_hash": _run(context).request_hash,
        "task_id": _task(context).id,
        "stage_attempt_id": _attempt(context).id,
        "quota_policy_version": "quota-v1",
        "provider_id": "provider-v1",
        "model_id": "model-v1",
        "endpoint_hash": "a" * 64,
        "body_hash": "b" * 64,
        "policy": {"version": "model-accounting-v1"},
        "policy_content_hash": "c" * 64,
        "input_token_ceiling": 20,
        "output_token_ceiling": 12,
        "reserved_tokens": 32,
        "reserved_microusd": 41,
    }


def _requirements(
    receipts: tuple[QuotaReservationReceipt, ...], request_hash: str
) -> tuple[QuotaDispatchRequirement, ...]:
    return tuple(
        QuotaDispatchRequirement(
            reservation_id=receipt.reservation_id,
            fencing_token=receipt.fencing_token,
            resource_type=receipt.resource_type,
            unit=receipt.unit,
            reserved_amount=receipt.reserved_amount,
            request_hash=request_hash,
        )
        for receipt in receipts
    )


async def _expire(receipts: tuple[QuotaReservationReceipt, ...]) -> None:
    async with database.async_session_maker() as session:
        for receipt in receipts:
            reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
            assert reservation is not None
            reservation.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()


async def _state(
    receipts: tuple[QuotaReservationReceipt, ...],
) -> dict[str, dict[str, dict[str, Any]]]:
    async with database.async_session_maker() as session:
        reservations = {
            item.id: item
            for item in (
                await session.scalars(
                    select(ResearchQuotaReservation).where(
                        ResearchQuotaReservation.id.in_(
                            [receipt.reservation_id for receipt in receipts]
                        )
                    )
                )
            )
        }
        buckets = {
            item.id: item
            for item in (
                await session.scalars(
                    select(ResearchQuotaBucket).where(
                        ResearchQuotaBucket.id.in_([receipt.bucket_id for receipt in receipts])
                    )
                )
            )
        }
    return {
        "reservations": {
            reservation_id: {
                "status": item.status,
                "provider_operation_id": item.provider_operation_id,
                "reserved_amount": item.reserved_amount,
                "settled_amount": item.settled_amount,
                "reason": item.reason,
            }
            for reservation_id, item in reservations.items()
        },
        "buckets": {
            bucket_id: {
                "status": item.status,
                "reserved_amount": item.reserved_amount,
                "settled_amount": item.settled_amount,
                "active_reservations": item.active_reservations,
                "reconcile_reason": item.reconcile_reason,
            }
            for bucket_id, item in buckets.items()
        },
    }


def _receipt_for(
    receipts: tuple[QuotaReservationReceipt, ...], resource_type: str
) -> QuotaReservationReceipt:
    return next(item for item in receipts if item.resource_type == resource_type)


def _dispatch_binding(context: dict[str, object]) -> dict[str, str]:
    return {
        "task_id": _task(context).id,
        "run_id": _run(context).id,
        "stage_attempt_id": _attempt(context).id,
        "lease_token": _lease_token(context),
        "stage": "GENERATE",
    }


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


def _bucket_for(context: dict[str, object], resource_type: str) -> ResearchQuotaBucket:
    value = context["buckets"]
    assert isinstance(value, tuple)
    return next(
        item
        for item in value
        if isinstance(item, ResearchQuotaBucket) and item.resource_type == resource_type
    )


def _lease_token(context: dict[str, object]) -> str:
    value = context["lease_token"]
    assert isinstance(value, str)
    return value
