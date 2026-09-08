from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchQuotaBucket, ResearchQuotaReservation, ResearchTask
from app.services.research.quota import (
    QuotaConflictError,
    QuotaReservationRequest,
    QuotaService,
    QuotaUnavailableError,
)


@pytest.mark.asyncio
async def test_multi_resource_reservation_is_all_or_none_and_idempotent() -> None:
    first, second = await _buckets(hard_limit=10, concurrency_limit=2)
    task_one, task_two = await _tasks("task-1", "task-2")
    service = QuotaService()
    requests = (
        QuotaReservationRequest(first.id, "model_tokens", 3, "tokens"),
        QuotaReservationRequest(second.id, "sandbox_seconds", 4, "seconds"),
    )

    receipts = await service.reserve(
        task_id=task_one.id,
        policy_version="quota-v1",
        idempotency_key="stage-1",
        request_hash="a" * 64,
        requests=requests,
    )
    repeated = await service.reserve(
        task_id=task_one.id,
        policy_version="quota-v1",
        idempotency_key="stage-1",
        request_hash="a" * 64,
        requests=requests,
    )

    assert [receipt.reservation_id for receipt in repeated] == [
        receipt.reservation_id for receipt in receipts
    ]
    with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_IDEMPOTENCY_CONFLICT"):
        await service.reserve(
            task_id=task_one.id,
            policy_version="quota-v1",
            idempotency_key="stage-1",
            request_hash="b" * 64,
            requests=requests,
        )

    with pytest.raises(QuotaUnavailableError, match="RESEARCH_QUOTA_HARD_LIMIT_EXCEEDED"):
        await service.reserve(
            task_id=task_two.id,
            policy_version="quota-v1",
            idempotency_key="stage-2",
            request_hash="c" * 64,
            requests=(
                QuotaReservationRequest(first.id, "model_tokens", 8, "tokens"),
                QuotaReservationRequest(second.id, "sandbox_seconds", 1, "seconds"),
            ),
        )

    refreshed_first, refreshed_second = await _read_buckets(first.id, second.id)
    assert (refreshed_first.reserved_amount, refreshed_first.active_reservations) == (3, 1)
    assert (refreshed_second.reserved_amount, refreshed_second.active_reservations) == (4, 1)


@pytest.mark.asyncio
async def test_concurrent_reservations_never_exceed_hard_or_concurrency_limit() -> None:
    (bucket,) = await _buckets(hard_limit=10, concurrency_limit=10)
    tasks = await _tasks(*(f"task-{index}" for index in range(20)))
    service = QuotaService()

    async def reserve(index: int) -> bool:
        try:
            await service.reserve(
                task_id=tasks[index].id,
                policy_version="quota-v1",
                idempotency_key=f"stage-{index}",
                request_hash=f"{index:064x}",
                requests=(QuotaReservationRequest(bucket.id, "model_tokens", 1, "tokens"),),
            )
        except QuotaUnavailableError:
            return False
        return True

    outcomes = await asyncio.gather(*(reserve(index) for index in range(20)))

    assert sum(outcomes) == 10
    (refreshed_bucket,) = await _read_buckets(bucket.id)
    assert (refreshed_bucket.reserved_amount, refreshed_bucket.active_reservations) == (10, 10)


@pytest.mark.asyncio
async def test_expired_external_work_is_blocked_until_explicit_reconciliation() -> None:
    _unused, bucket = await _buckets(hard_limit=10, concurrency_limit=2)
    (task,) = await _tasks("task-unknown")
    service = QuotaService()
    (receipt,) = await service.reserve(
        task_id=task.id,
        policy_version="quota-v1",
        idempotency_key="stage-unknown",
        request_hash="d" * 64,
        requests=(QuotaReservationRequest(bucket.id, "sandbox_seconds", 3, "seconds"),),
        lease_seconds=1,
    )
    assert await service.mark_in_flight(
        receipt.reservation_id,
        receipt.fencing_token,
        provider_operation_id="runner-op-1",
    )

    changed = await service.reconcile_expired(now=datetime.now(timezone.utc) + timedelta(seconds=2))
    assert changed == 1
    with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_RELEASE_REQUIRES_NOOP_PROOF"):
        await service.release(receipt.reservation_id, receipt.fencing_token)
    assert not await service.validate_fencing(receipt.reservation_id, receipt.fencing_token)

    assert await service.resolve_reconciliation(
        receipt.reservation_id,
        receipt.fencing_token,
        outcome="NO_OPERATION",
    )
    async with async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        refreshed_bucket = await session.get(ResearchQuotaBucket, bucket.id)
    assert reservation is not None and reservation.status == "RELEASED"
    assert refreshed_bucket is not None and refreshed_bucket.status == "ACTIVE"
    assert refreshed_bucket.reserved_amount == 0


async def _buckets(*, hard_limit: int, concurrency_limit: int) -> tuple[ResearchQuotaBucket, ...]:
    now = datetime.now(timezone.utc)
    bucket_specs = (("model_tokens", "tokens"), ("sandbox_seconds", "seconds"))
    if hard_limit == 10 and concurrency_limit == 10:
        bucket_specs = (("model_tokens", "tokens"),)
    models = [
        ResearchQuotaBucket(
            scope_type="user",
            scope_id="quota-test-user",
            policy_version="quota-v1",
            resource_type=resource_type,
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=hard_limit,
            concurrency_limit=concurrency_limit,
        )
        for resource_type, _unit in bucket_specs
    ]
    async with async_session_maker() as session:
        session.add_all(models)
        await session.commit()
        for model in models:
            await session.refresh(model)
    return tuple(models)


async def _read_buckets(*bucket_ids: str) -> tuple[ResearchQuotaBucket, ...]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(ResearchQuotaBucket)
            .where(ResearchQuotaBucket.id.in_(bucket_ids))
            .order_by(ResearchQuotaBucket.resource_type)
        )
        models = tuple(result.scalars())
    return models


async def _tasks(*labels: str) -> tuple[ResearchTask, ...]:
    models = [
        ResearchTask(
            user_id="quota-test-user",
            run_id=f"run-{label}",
            status="QUEUED",
            stage_cursor="CLARIFY",
            request_json={},
            idempotency_key=f"submission-{label}",
            idempotency_request_hash="a" * 64,
        )
        for label in labels
    ]
    async with async_session_maker() as session:
        session.add_all(models)
        await session.commit()
        for model in models:
            await session.refresh(model)
    return tuple(models)
