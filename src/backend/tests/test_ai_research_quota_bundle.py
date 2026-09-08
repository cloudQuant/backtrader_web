"""Independent-connection coverage for atomic multi-resource quota dispatches."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
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
from app.services.research import quota as quota_module
from app.services.research.canonical import content_hash
from app.services.research.quota import (
    QuotaConflictError,
    QuotaDispatchRequirement,
    QuotaReservationReceipt,
    QuotaReservationRequest,
    QuotaService,
    QuotaSettlementRequest,
)


@pytest_asyncio.fixture
async def independent_bundle_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """Back bundle races with independent SQLite connections, not StaticPool."""

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'quota-bundle.db'}",
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
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reservation_context_schema", None),
        ("reservation_context_schema", {}),
        ("reservation_context_schema", "unknown-schema"),
        ("minimum_remaining_seconds", True),
        ("minimum_remaining_seconds", -1),
        ("minimum_remaining_seconds", 7201),
    ],
)
async def test_dispatch_rejects_invalid_schema_or_remaining_lease_before_io(field, value):
    requirement = QuotaDispatchRequirement(
        "reservation", 1, "sandbox_seconds", "seconds", 10, "a" * 64
    )
    requirement = replace(requirement, **{field: value})

    with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_BUNDLE_INVALID"):
        await QuotaService().claim_external_dispatch_bundle(
            (requirement,),
            provider_operation_id="operation",
            task_id="task",
            run_id="run",
            stage_attempt_id="attempt",
            lease_token="lease",
            stage="VALIDATE_DISCOVERY",
        )


@pytest.mark.asyncio
async def test_claim_bundle_transitions_the_complete_group_exactly_once(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="claim")
    requirements = _requirements(receipts, request_hash)
    service = QuotaService()

    assert await service.claim_external_dispatch_bundle(
        requirements,
        provider_operation_id="provider-bundle-claim",
        **_dispatch_binding(context),
    )
    assert not await service.claim_external_dispatch_bundle(
        requirements,
        provider_operation_id="provider-bundle-claim",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"IN_FLIGHT"}
    assert {item.provider_operation_id for item in reservations.values()} == {
        "provider-bundle-claim"
    }


@pytest.mark.asyncio
async def test_claim_bundle_requires_persisted_context_for_strict_dispatch(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="strict-context-missing")

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash, require_reservation_context=True),
        provider_operation_id="provider-strict-context-missing",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_requires_model_budget_context_schema_for_strict_dispatch(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    generic_context = _reservation_context(context)
    request_hash, receipts = await _reserve_bundle(
        context,
        suffix="strict-generic-context",
        reservation_context=generic_context,
    )

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash, require_reservation_context=True),
        provider_operation_id="provider-strict-generic-context",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_accepts_matching_model_budget_context_for_strict_dispatch(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    model_budget_context = _model_budget_context(context)
    request_hash, receipts = await _reserve_bundle(
        context,
        suffix="strict-model-budget-context",
        reservation_context=model_budget_context,
    )

    assert await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash, require_reservation_context=True),
        provider_operation_id="provider-strict-model-budget-context",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"IN_FLIGHT"}


@pytest.mark.asyncio
async def test_claim_bundle_rejects_model_budget_context_with_drifted_canonical_hash(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    model_budget_context = _model_budget_context(context)
    _, receipts = await _reserve_bundle(
        context,
        suffix="strict-model-budget-hash-drift",
        reservation_context=model_budget_context,
    )
    drifted_hash = "d" * 64
    async with database.async_session_maker() as session:
        reservations = await session.execute(
            select(ResearchQuotaReservation).where(
                ResearchQuotaReservation.id.in_([item.reservation_id for item in receipts])
            )
        )
        for reservation in reservations.scalars():
            reservation.request_hash = drifted_hash
        await session.commit()

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, drifted_hash, require_reservation_context=True),
        provider_operation_id="provider-strict-model-budget-hash-drift",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_flag", (1, "true", None))
async def test_claim_bundle_rejects_non_boolean_context_requirement_flag(
    independent_bundle_database: None, invalid_flag: object
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="strict-flag-type")

    with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_BUNDLE_INVALID"):
        await QuotaService().claim_external_dispatch_bundle(
            _requirements(receipts, request_hash, require_reservation_context=invalid_flag),
            provider_operation_id="provider-strict-flag-type",
            **_dispatch_binding(context),
        )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_rejects_mixed_context_requirement_flags(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="strict-mixed-flags")
    requirements = _requirements(receipts, request_hash)
    mixed_requirements = (
        replace(requirements[0], require_reservation_context=True),
        requirements[1],
    )

    with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_BUNDLE_INVALID"):
        await QuotaService().claim_external_dispatch_bundle(
            mixed_requirements,
            provider_operation_id="provider-strict-mixed-flags",
            **_dispatch_binding(context),
        )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_rejects_a_partial_group_without_claiming_any_receipt(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="partial")

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash)[:1],
        provider_operation_id="provider-bundle-partial",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_rolls_back_when_its_second_receipt_is_revoked(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="revoked")
    revoked = _receipt_for(receipts, "model_cost_microusd")
    async with database.async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, revoked.reservation_id)
        assert reservation is not None
        reservation.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id="provider-bundle-revoked",
        **_dispatch_binding(context),
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation",
    ("bucket_window", "bucket_policy", "bucket_resource", "task_cancel", "stage_cursor"),
)
async def test_claim_bundle_requires_a_current_bucket_and_task_stage(
    independent_bundle_database: None, revocation: str
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix=f"current-{revocation}")
    cost = _receipt_for(receipts, "model_cost_microusd")
    async with database.async_session_maker() as session:
        if revocation == "bucket_window":
            bucket = await session.get(ResearchQuotaBucket, cost.bucket_id)
            assert bucket is not None
            bucket.window_end = datetime.now(timezone.utc) - timedelta(minutes=1)
        elif revocation == "bucket_policy":
            bucket = await session.get(ResearchQuotaBucket, cost.bucket_id)
            assert bucket is not None
            bucket.policy_version = "quota-revoked"
        elif revocation == "bucket_resource":
            bucket = await session.get(ResearchQuotaBucket, cost.bucket_id)
            assert bucket is not None
            bucket.resource_type = "other_resource"
        else:
            task = await session.get(ResearchTask, _task(context).id)
            assert task is not None
            if revocation == "task_cancel":
                task.cancel_requested_at = datetime.now(timezone.utc)
            else:
                task.stage_cursor = "CLARIFY"
        await session.commit()

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id=f"provider-bundle-current-{revocation}",
        **_dispatch_binding(context),
    )
    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_rolls_back_when_its_second_cas_is_rejected_by_database(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="cas-rollback")
    second_requirement = sorted(
        _requirements(receipts, request_hash), key=lambda item: item.reservation_id
    )[1]
    async with database.async_session_maker() as session:
        await session.execute(
            text(
                "CREATE TRIGGER reject_second_bundle_claim "
                "BEFORE UPDATE OF status ON ai_research_quota_reservations "
                f"WHEN OLD.id = '{second_requirement.reservation_id}' "
                "AND NEW.status = 'IN_FLIGHT' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
        )
        await session.commit()

    assert not await QuotaService().claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id="provider-bundle-cas-rollback",
        **_dispatch_binding(context),
    )
    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


@pytest.mark.asyncio
async def test_claim_bundle_allows_only_one_independent_connection_to_dispatch(
    independent_bundle_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="race")
    requirements = _requirements(receipts, request_hash)
    barrier = asyncio.Barrier(2)
    original_locked_group = quota_module._locked_complete_bundle_group

    async def synchronize_after_group_read(
        session: Any, reservation_ids: tuple[str, ...]
    ) -> tuple[ResearchQuotaReservation, ...] | None:
        result = await original_locked_group(session, reservation_ids)
        await barrier.wait()
        return result

    monkeypatch.setattr(quota_module, "_locked_complete_bundle_group", synchronize_after_group_read)

    results = await asyncio.gather(
        *(
            QuotaService().claim_external_dispatch_bundle(
                requirements,
                provider_operation_id="provider-bundle-race",
                **_dispatch_binding(context),
            )
            for _ in range(2)
        )
    )

    assert sum(results) == 1
    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"IN_FLIGHT"}


@pytest.mark.asyncio
async def test_settle_bundle_rolls_back_when_its_second_bucket_update_is_rejected_by_database(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="bucket-cas-rollback")
    service = QuotaService()
    operation_id = "provider-bundle-bucket-cas-rollback"
    assert await service.claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id=operation_id,
        **_dispatch_binding(context),
    )
    ordered_reservations = sorted(
        (await _reservations(receipts)).values(), key=lambda item: item.id
    )
    blocked_bucket_id = ordered_reservations[1].bucket_id
    async with database.async_session_maker() as session:
        await session.execute(
            text(
                "CREATE TRIGGER reject_second_bundle_bucket_update "
                "BEFORE UPDATE ON ai_research_quota_buckets "
                f"WHEN OLD.id = '{blocked_bucket_id}' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
        )
        await session.commit()

    assert not await service.settle_bundle(
        tuple(
            QuotaSettlementRequest(
                item.reservation_id, item.fencing_token, item.reserved_amount - 1
            )
            for item in receipts
        ),
        provider_operation_id=operation_id,
    )
    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"IN_FLIGHT"}
    buckets = await _buckets_for(receipts)
    assert {bucket.reserved_amount for bucket in buckets.values()} == {32, 41}
    assert {bucket.settled_amount for bucket in buckets.values()} == {0}
    assert {bucket.active_reservations for bucket in buckets.values()} == {1}


@pytest.mark.asyncio
async def test_settle_bundle_rolls_back_when_its_second_item_exceeds_reservation(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="settle-rollback")
    requirements = _requirements(receipts, request_hash)
    service = QuotaService()
    assert await service.claim_external_dispatch_bundle(
        requirements,
        provider_operation_id="provider-bundle-settle-rollback",
        **_dispatch_binding(context),
    )
    token = _receipt_for(receipts, "model_tokens")
    cost = _receipt_for(receipts, "model_cost_microusd")

    assert not await service.settle_bundle(
        (
            QuotaSettlementRequest(token.reservation_id, token.fencing_token, 31),
            QuotaSettlementRequest(
                cost.reservation_id, cost.fencing_token, cost.reserved_amount + 1
            ),
        ),
        provider_operation_id="provider-bundle-settle-rollback",
    )

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"IN_FLIGHT"}
    buckets = await _buckets_for(receipts)
    assert {bucket.reserved_amount for bucket in buckets.values()} == {32, 41}
    assert {bucket.settled_amount for bucket in buckets.values()} == {0}
    assert {bucket.active_reservations for bucket in buckets.values()} == {1}


@pytest.mark.asyncio
async def test_settle_bundle_rejects_stale_or_unknown_receipt_without_settling_others(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="settle-stale")
    service = QuotaService()
    operation_id = "provider-bundle-settle-stale"
    assert await service.claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id=operation_id,
        **_dispatch_binding(context),
    )
    token = _receipt_for(receipts, "model_tokens")
    cost = _receipt_for(receipts, "model_cost_microusd")

    assert not await service.settle_bundle(
        (
            QuotaSettlementRequest(token.reservation_id, token.fencing_token, 20),
            QuotaSettlementRequest(cost.reservation_id, cost.fencing_token + 1, 30),
        ),
        provider_operation_id=operation_id,
    )
    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"IN_FLIGHT"}

    async with database.async_session_maker() as session:
        unknown = await session.get(ResearchQuotaReservation, cost.reservation_id)
        assert unknown is not None
        unknown.status = "RECONCILING"
        await session.commit()
    assert not await service.settle_bundle(
        (
            QuotaSettlementRequest(token.reservation_id, token.fencing_token, 20),
            QuotaSettlementRequest(cost.reservation_id, cost.fencing_token, 30),
        ),
        provider_operation_id=operation_id,
    )
    reservations = await _reservations(receipts)
    assert reservations[token.reservation_id].status == "IN_FLIGHT"
    assert reservations[cost.reservation_id].status == "RECONCILING"


@pytest.mark.asyncio
async def test_settle_bundle_is_exactly_once_for_the_complete_in_flight_group(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    request_hash, receipts = await _reserve_bundle(context, suffix="settle-once")
    service = QuotaService()
    operation_id = "provider-bundle-settle-once"
    assert await service.claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id=operation_id,
        **_dispatch_binding(context),
    )
    requests = tuple(
        QuotaSettlementRequest(item.reservation_id, item.fencing_token, item.reserved_amount - 1)
        for item in receipts
    )

    assert await service.settle_bundle(requests, provider_operation_id=operation_id)
    assert not await service.settle_bundle(requests, provider_operation_id=operation_id)

    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"SETTLED"}
    buckets = await _buckets_for(receipts)
    assert {bucket.reserved_amount for bucket in buckets.values()} == {0}
    assert {bucket.active_reservations for bucket in buckets.values()} == {0}


@pytest.mark.asyncio
async def test_reserve_rejects_invalid_integer_amounts_and_wrong_microusd_unit(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    token_bucket = _bucket_for(context, "model_tokens")
    cost_bucket = _bucket_for(context, "model_cost_microusd")
    service = QuotaService()
    invalid_requests = (
        (QuotaReservationRequest(token_bucket.id, "model_tokens", True, "tokens"),),
        (QuotaReservationRequest(token_bucket.id, "model_tokens", 1.5, "tokens"),),
        (QuotaReservationRequest(token_bucket.id, "model_tokens", 2_147_483_648, "tokens"),),
        (QuotaReservationRequest(cost_bucket.id, "model_cost_microusd", 1, "usd"),),
    )

    for index, requests in enumerate(invalid_requests):
        with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_REQUEST_INVALID"):
            await service.reserve(
                task_id=_task(context).id,
                policy_version="quota-v1",
                idempotency_key=f"invalid-{index}",
                request_hash=f"{index + 1:064x}",
                requests=requests,
                stage_attempt_id=_attempt(context).id,
            )


@pytest.mark.asyncio
async def test_reserve_persists_immutable_context_and_claim_rejects_context_hash_mismatch(
    independent_bundle_database: None,
) -> None:
    context = await _context()
    reservation_context = _reservation_context(context)
    request_hash = content_hash(reservation_context)
    service = QuotaService()
    requests = _bundle_requests(context)
    receipts = await service.reserve(
        task_id=_task(context).id,
        policy_version="quota-v1",
        idempotency_key="context-bound",
        request_hash=request_hash,
        requests=requests,
        stage_attempt_id=_attempt(context).id,
        reservation_context=reservation_context,
    )
    reservation_context["tariff"]["max_microusd"] = 999

    equivalent_context = _reservation_context(context)
    repeated = await service.reserve(
        task_id=_task(context).id,
        policy_version="quota-v1",
        idempotency_key="context-bound",
        request_hash=content_hash(equivalent_context),
        requests=requests,
        stage_attempt_id=_attempt(context).id,
        reservation_context={key: equivalent_context[key] for key in reversed(equivalent_context)},
    )
    assert [item.reservation_id for item in repeated] == [item.reservation_id for item in receipts]

    reservations = await _reservations(receipts)
    assert {
        item.reservation_context["tariff"]["max_microusd"] for item in reservations.values()
    } == {41}
    cost = _receipt_for(receipts, "model_cost_microusd")
    async with database.async_session_maker() as session:
        changed = await session.get(ResearchQuotaReservation, cost.reservation_id)
        assert changed is not None
        changed.reservation_context = {"different": "context"}
        await session.commit()

    with pytest.raises(QuotaConflictError, match="RESEARCH_QUOTA_IDEMPOTENCY_CONFLICT"):
        await service.reserve(
            task_id=_task(context).id,
            policy_version="quota-v1",
            idempotency_key="context-bound",
            request_hash=request_hash,
            requests=requests,
            stage_attempt_id=_attempt(context).id,
            reservation_context=_reservation_context(context),
        )

    assert not await service.claim_external_dispatch_bundle(
        _requirements(receipts, request_hash),
        provider_operation_id="provider-context-mismatch",
        **_dispatch_binding(context),
    )
    reservations = await _reservations(receipts)
    assert {item.status for item in reservations.values()} == {"RESERVED"}


async def _context() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id="quota-bundle-user",
        hypothesis_version_id="hypothesis-bundle",
        dataset_snapshot_id="dataset-bundle",
        experiment_epoch_id="epoch-bundle",
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="profile-bundle",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id="trace-bundle",
    )
    buckets = (
        ResearchQuotaBucket(
            scope_type="user",
            scope_id="quota-bundle-user",
            policy_version="quota-v1",
            resource_type="model_tokens",
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=1_000,
            concurrency_limit=10,
        ),
        ResearchQuotaBucket(
            scope_type="user",
            scope_id="quota-bundle-user",
            policy_version="quota-v1",
            resource_type="model_cost_microusd",
            window_start=now - timedelta(minutes=1),
            window_end=now + timedelta(hours=1),
            hard_limit=1_000,
            concurrency_limit=10,
        ),
    )
    lease_token = "bundle-lease"
    async with database.async_session_maker() as session:
        session.add_all((run, *buckets))
        await session.commit()
        await session.refresh(run)
        for bucket in buckets:
            await session.refresh(bucket)
        task = ResearchTask(
            user_id="quota-bundle-user",
            run_id=run.id,
            status="RUNNING",
            stage_cursor="GENERATE",
            request_json={},
            idempotency_key="quota-bundle-task",
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
            idempotency_key="quota-bundle-stage",
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


async def _reserve_bundle(
    context: dict[str, object], *, suffix: str, reservation_context: dict[str, Any] | None = None
) -> tuple[str, tuple[QuotaReservationReceipt, ...]]:
    request_hash = content_hash(reservation_context or {"bundle": suffix})
    receipts = await QuotaService().reserve(
        task_id=_task(context).id,
        policy_version="quota-v1",
        idempotency_key=f"bundle-{suffix}",
        request_hash=request_hash,
        requests=_bundle_requests(context),
        stage_attempt_id=_attempt(context).id,
        reservation_context=reservation_context,
    )
    return request_hash, receipts


def _bundle_requests(context: dict[str, object]) -> tuple[QuotaReservationRequest, ...]:
    return (
        QuotaReservationRequest(
            _bucket_for(context, "model_tokens").id, "model_tokens", 32, "tokens"
        ),
        QuotaReservationRequest(
            _bucket_for(context, "model_cost_microusd").id,
            "model_cost_microusd",
            41,
            "microusd",
        ),
    )


def _requirements(
    receipts: tuple[QuotaReservationReceipt, ...],
    request_hash: str,
    *,
    require_reservation_context: object = False,
) -> tuple[QuotaDispatchRequirement, ...]:
    return tuple(
        QuotaDispatchRequirement(
            reservation_id=item.reservation_id,
            fencing_token=item.fencing_token,
            resource_type=item.resource_type,
            unit=item.unit,
            reserved_amount=item.reserved_amount,
            request_hash=request_hash,
            require_reservation_context=require_reservation_context,
        )
        for item in receipts
    )


def _dispatch_binding(context: dict[str, object]) -> dict[str, str]:
    return {
        "task_id": _task(context).id,
        "run_id": _run(context).id,
        "stage_attempt_id": _attempt(context).id,
        "lease_token": _lease_token(context),
        "stage": "GENERATE",
    }


async def _reservations(
    receipts: tuple[QuotaReservationReceipt, ...],
) -> dict[str, ResearchQuotaReservation]:
    async with database.async_session_maker() as session:
        result = await session.execute(
            select(ResearchQuotaReservation).where(
                ResearchQuotaReservation.id.in_([item.reservation_id for item in receipts])
            )
        )
        return {item.id: item for item in result.scalars()}


async def _buckets_for(
    receipts: tuple[QuotaReservationReceipt, ...],
) -> dict[str, ResearchQuotaBucket]:
    async with database.async_session_maker() as session:
        result = await session.execute(
            select(ResearchQuotaBucket).where(
                ResearchQuotaBucket.id.in_([item.bucket_id for item in receipts])
            )
        )
        return {item.id: item for item in result.scalars()}


def _receipt_for(
    receipts: tuple[QuotaReservationReceipt, ...], resource_type: str
) -> QuotaReservationReceipt:
    return next(item for item in receipts if item.resource_type == resource_type)


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


def _reservation_context(context: dict[str, object]) -> dict[str, Any]:
    return {
        "run_request_hash": _run(context).request_hash,
        "task_id": _task(context).id,
        "stage": "GENERATE",
        "body_sha256": "b" * 64,
        "policy": {"version": "quota-v1"},
        "tariff": {"version": "tariff-v1", "max_microusd": 41},
    }


def _model_budget_context(context: dict[str, object]) -> dict[str, Any]:
    """Minimal persisted quote shape accepted by strict quota dispatch."""

    return {
        "schema_version": "model-budget-quote-v1",
        "run_request_hash": _run(context).request_hash,
        "task_id": _task(context).id,
        "stage_attempt_id": _attempt(context).id,
        "quota_policy_version": "quota-v1",
        "provider_id": "provider-test",
        "model_id": "model-test",
        "endpoint_hash": "a" * 64,
        "body_hash": "b" * 64,
        "policy_content_hash": "c" * 64,
        "input_token_ceiling": 20,
        "output_token_ceiling": 12,
        "reserved_tokens": 32,
        "reserved_microusd": 41,
    }
