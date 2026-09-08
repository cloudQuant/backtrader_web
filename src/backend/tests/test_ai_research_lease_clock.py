"""Lease expiry must be measured in the same database clock domain as dispatch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchQuotaBucket,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchTask,
)
from app.services.research import quota as quota_module
from app.services.research import task_runner as task_runner_module
from app.services.research.quota import QuotaReservationRequest, QuotaService
from app.services.research.task_runner import DurableResearchTaskRunner

_LEASE_SECONDS = 90
_SKEW_CASES = (
    pytest.param(timedelta(minutes=10), id="application-clock-fast-by-ten-minutes"),
    pytest.param(timedelta(minutes=-10), id="application-clock-slow-by-ten-minutes"),
)


@pytest.mark.parametrize("seconds", [True, -1, 7201, 1.5, "10"])
def test_statement_deadline_rejects_invalid_seconds(seconds):
    from app.services.research.database_clock import DatabaseUtcAfter

    with pytest.raises(ValueError, match="RESEARCH_DATABASE_CLOCK_OFFSET_INVALID"):
        DatabaseUtcAfter(seconds)


@pytest.mark.parametrize("dialect_name", ["sqlite", "postgresql", "mysql"])
def test_statement_deadline_compiles_with_bound_seconds_and_live_clock(dialect_name):
    from sqlalchemy.dialects import mysql, postgresql, sqlite

    from app.services.research.database_clock import DatabaseUtcAfter

    dialects = {
        "sqlite": sqlite.dialect(),
        "postgresql": postgresql.dialect(),
        "mysql": mysql.dialect(),
    }
    compiled = select(DatabaseUtcAfter(123)).compile(dialect=dialects[dialect_name])
    assert list(compiled.params.values()) == [123]
    expected = {
        "sqlite": "strftime(",
        "postgresql": "clock_timestamp()",
        "mysql": "UTC_TIMESTAMP(6)",
    }
    assert expected[dialect_name] in str(compiled)


@pytest.mark.asyncio
async def test_statement_deadline_round_trips_sqlite_database_seconds():
    from app.services.research.database_clock import DatabaseUtcAfter

    before = await _sqlite_utc_now()
    async with async_session_maker() as session:
        deadline = await session.scalar(select(DatabaseUtcAfter(123)))
    after = await _sqlite_utc_now()
    assert before + timedelta(seconds=123) <= _as_utc(deadline) <= after + timedelta(seconds=123)


@pytest.mark.asyncio
@pytest.mark.parametrize("application_skew", _SKEW_CASES)
async def test_reservation_lease_uses_database_clock_despite_application_skew(
    monkeypatch: pytest.MonkeyPatch, application_skew: timedelta
) -> None:
    bucket, task = await _quota_context("reservation")
    database_before = await _sqlite_utc_now()
    monkeypatch.setattr(quota_module, "_now", lambda: database_before + application_skew)

    (receipt,) = await QuotaService().reserve(
        task_id=task.id,
        policy_version="quota-v1",
        idempotency_key=f"reservation-{application_skew}",
        request_hash="a" * 64,
        requests=(QuotaReservationRequest(bucket.id, "model_tokens", 1, "tokens"),),
        lease_seconds=_LEASE_SECONDS,
    )

    _assert_duration_from_database_clock(
        receipt.lease_expires_at,
        database_before,
        await _sqlite_utc_now(),
        _LEASE_SECONDS,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("application_skew", "expiry_from_database", "expected"),
    (
        pytest.param(timedelta(minutes=10), timedelta(minutes=5), True, id="fast-clock"),
        pytest.param(timedelta(minutes=-10), timedelta(minutes=-1), False, id="slow-clock"),
    ),
)
async def test_quota_fencing_validation_uses_database_clock_despite_application_skew(
    monkeypatch: pytest.MonkeyPatch,
    application_skew: timedelta,
    expiry_from_database: timedelta,
    expected: bool,
) -> None:
    bucket, task = await _quota_context("fencing")
    service = QuotaService()
    (receipt,) = await service.reserve(
        task_id=task.id,
        policy_version="quota-v1",
        idempotency_key="fencing",
        request_hash="b" * 64,
        requests=(QuotaReservationRequest(bucket.id, "model_tokens", 1, "tokens"),),
    )
    database_now = await _sqlite_utc_now()
    async with async_session_maker() as session:
        reservation = await session.get(ResearchQuotaReservation, receipt.reservation_id)
        assert reservation is not None
        reservation.lease_expires_at = database_now + expiry_from_database
        await session.commit()
    monkeypatch.setattr(quota_module, "_now", lambda: database_now + application_skew)

    assert await service.validate_fencing(receipt.reservation_id, receipt.fencing_token) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("application_skew", _SKEW_CASES)
async def test_task_claim_lease_uses_database_clock_despite_application_skew(
    monkeypatch: pytest.MonkeyPatch, application_skew: timedelta
) -> None:
    task = await _task("claim", status="QUEUED")
    runner = DurableResearchTaskRunner(lease_seconds=_LEASE_SECONDS)
    database_before = await _sqlite_utc_now()
    monkeypatch.setattr(task_runner_module, "_now", lambda: database_before + application_skew)

    (claim,) = await runner.claim_due()
    assert claim.task_id == task.id
    async with async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
    assert stored is not None and stored.lease_expires_at is not None
    _assert_duration_from_database_clock(
        stored.lease_expires_at,
        database_before,
        await _sqlite_utc_now(),
        _LEASE_SECONDS,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("application_skew", _SKEW_CASES)
async def test_task_heartbeat_lease_uses_database_clock_despite_application_skew(
    monkeypatch: pytest.MonkeyPatch, application_skew: timedelta
) -> None:
    task = await _task("heartbeat", status="RUNNING")
    runner = DurableResearchTaskRunner(lease_seconds=_LEASE_SECONDS)
    database_before = await _sqlite_utc_now()
    monkeypatch.setattr(task_runner_module, "_now", lambda: database_before + application_skew)

    assert task.lease_token is not None
    assert await runner.heartbeat(task.id, task.lease_token)
    async with async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
    assert stored is not None and stored.lease_expires_at is not None
    _assert_duration_from_database_clock(
        stored.lease_expires_at,
        database_before,
        await _sqlite_utc_now(),
        _LEASE_SECONDS,
    )


@pytest.mark.asyncio
async def test_task_heartbeat_cannot_revive_a_lease_expired_after_clock_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = await _task("expired-heartbeat", status="RUNNING")
    database_now = await _sqlite_utc_now()
    async with async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
        assert stored is not None
        stored.lease_expires_at = database_now - timedelta(seconds=1)
        await session.commit()

    async def stale_database_clock(_session: object) -> datetime:
        return database_now - timedelta(minutes=10)

    monkeypatch.setattr(task_runner_module, "database_utc_now", stale_database_clock)
    assert task.lease_token is not None
    assert not await DurableResearchTaskRunner(lease_seconds=_LEASE_SECONDS).heartbeat(
        task.id, task.lease_token
    )


@pytest.mark.asyncio
async def test_task_heartbeat_retains_explicit_deterministic_clock_override() -> None:
    task = await _task("heartbeat-explicit-clock", status="RUNNING")
    test_now = datetime(2000, 1, 1, tzinfo=timezone.utc)
    async with async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
        assert stored is not None
        stored.lease_expires_at = test_now + timedelta(seconds=1)
        await session.commit()

    assert task.lease_token is not None
    assert await DurableResearchTaskRunner(lease_seconds=_LEASE_SECONDS).heartbeat(
        task.id, task.lease_token, now=test_now
    )
    async with async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
    assert stored is not None
    assert _as_utc(stored.lease_heartbeat_at) == test_now
    assert _as_utc(stored.lease_expires_at) == test_now + timedelta(seconds=_LEASE_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("application_skew", "expiry_from_database", "expected_recovered"),
    (
        pytest.param(timedelta(minutes=10), timedelta(minutes=5), 0, id="fast-clock"),
        pytest.param(timedelta(minutes=-10), timedelta(minutes=-1), 1, id="slow-clock"),
    ),
)
async def test_task_lease_recovery_uses_database_clock_despite_application_skew(
    monkeypatch: pytest.MonkeyPatch,
    application_skew: timedelta,
    expiry_from_database: timedelta,
    expected_recovered: int,
) -> None:
    task = await _task("recovery", status="RUNNING")
    database_now = await _sqlite_utc_now()
    async with async_session_maker() as session:
        stored = await session.get(ResearchTask, task.id)
        assert stored is not None
        stored.lease_expires_at = database_now + expiry_from_database
        await session.commit()
    monkeypatch.setattr(task_runner_module, "_now", lambda: database_now + application_skew)

    assert await DurableResearchTaskRunner().recover_expired_leases() == expected_recovered


async def _quota_context(label: str) -> tuple[ResearchQuotaBucket, ResearchTask]:
    database_now = await _sqlite_utc_now()
    bucket = ResearchQuotaBucket(
        scope_type="user",
        scope_id=f"lease-clock-{label}",
        policy_version="quota-v1",
        resource_type="model_tokens",
        # Keep quota admission valid for the intentionally injected +/-10m
        # application skew; this test isolates lease clock behavior.
        window_start=database_now - timedelta(hours=1),
        window_end=database_now + timedelta(hours=1),
        hard_limit=100,
        concurrency_limit=10,
    )
    task = ResearchTask(
        user_id=f"lease-clock-{label}",
        run_id=f"lease-clock-run-{label}",
        status="QUEUED",
        stage_cursor="GENERATE",
        request_json={},
        idempotency_key=f"lease-clock-quota-{label}",
        idempotency_request_hash="c" * 64,
    )
    async with async_session_maker() as session:
        session.add_all([bucket, task])
        await session.commit()
        await session.refresh(bucket)
        await session.refresh(task)
    return bucket, task


async def _task(label: str, *, status: str) -> ResearchTask:
    database_now = await _sqlite_utc_now()
    run = ResearchRun(
        user_id=f"lease-clock-{label}",
        hypothesis_version_id=f"lease-clock-hypothesis-{label}",
        promotion_policy_version="promotion-v1",
        request_hash="d" * 64,
        capability_profile_id="lease-clock-profile",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id=f"lease-clock-trace-{label}",
    )
    task = ResearchTask(
        user_id=run.user_id,
        run_id="",
        status=status,
        stage_cursor="GENERATE",
        request_json={},
        idempotency_key=f"lease-clock-task-{label}",
        idempotency_request_hash="f" * 64,
        lease_token=f"lease-clock-token-{label}" if status == "RUNNING" else None,
        lease_expires_at=(database_now + timedelta(minutes=5)) if status == "RUNNING" else None,
        lease_heartbeat_at=database_now if status == "RUNNING" else None,
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task.run_id = run.id
        session.add(task)
        await session.commit()
        await session.refresh(task)
    return task


async def _sqlite_utc_now() -> datetime:
    """Read the test database's own UTC wall clock, independent of app patches."""

    async with async_session_maker() as session:
        value = await session.scalar(select(func.strftime("%Y-%m-%d %H:%M:%f000", "now")))
    assert isinstance(value, str)
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _assert_duration_from_database_clock(
    expires_at: datetime,
    database_before: datetime,
    database_after: datetime,
    lease_seconds: int,
) -> None:
    normalized = _as_utc(expires_at)
    tolerance = timedelta(seconds=2)
    assert database_before + timedelta(seconds=lease_seconds) - tolerance <= normalized
    assert normalized <= database_after + timedelta(seconds=lease_seconds) + tolerance


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
