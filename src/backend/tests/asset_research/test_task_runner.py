"""Durable lease contracts for interactive multi-asset research tasks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.database import async_session_maker
from app.models.asset_research import AssetAnalysisTask, AssetDataSourceRegistry, AssetSignalRun
from app.models.user import User
from app.schemas.asset_research import (
    AssetAnalysisCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research import orchestrator as orchestrator_module
from app.services.asset_research import task_runner as task_runner_module
from app.services.asset_research.data import DEFAULT_ASSET_RESEARCH_SOURCE_ID
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.services.asset_research.task_runner import AssetResearchTaskRunner


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="task-runner-fixture-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


async def _seed_pending_task() -> str:
    async with async_session_maker() as db:
        user = User(
            username="asset_task_runner_user",
            email="asset-task-runner@example.test",
            hashed_password="hash",
        )
        source = AssetDataSourceRegistry(
            source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
            asset_types=["futures"],
            jurisdictions=["GLOBAL"],
            license_status="RESEARCH_APPROVED",
            allowed_uses=["RESEARCH_ONLY"],
            redistribution_policy="NO_REDISTRIBUTION",
            derived_data_policy="ALLOWED",
            retention_policy="research-v1",
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
            freshness_sla={},
            enabled=True,
        )
        db.add_all([user, source])
        await db.flush()
        service = AssetResearchOrchestrator(db)
        await service.persist_identity(_identity())
        task = await service.create_pending(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures", canonical_id="futures:CFFEX:IF2609:CNY"
            ),
        )
        await db.commit()
        return task.id


@pytest.mark.asyncio
async def test_task_runner_claims_a_queued_task_with_a_durable_lease() -> None:
    task_id = await _seed_pending_task()
    now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )

    claims = await runner.claim_due(now=now)

    assert len(claims) == 1
    assert claims[0].task_id == task_id
    assert claims[0].lease_token
    async with async_session_maker() as db:
        task = await db.get(AssetAnalysisTask, task_id)
        assert task is not None
        assert task.status == "RUNNING"
        assert task.lease_token == claims[0].lease_token
        assert task.lease_expires_at is not None
        assert task.lease_expires_at.replace(tzinfo=timezone.utc) == now + timedelta(seconds=30)
        assert task.lease_heartbeat_at is not None
        assert task.lease_heartbeat_at.replace(tzinfo=timezone.utc) == now
    assert task.attempt_count == 1


@pytest.mark.asyncio
async def test_task_runner_publishes_queue_depth_before_claiming(monkeypatch) -> None:
    """Interactive queue depth is emitted before any task lease is created."""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        task_runner_module,
        "set_asset_research_queue_depth",
        lambda **event: events.append(event),
    )
    await _seed_pending_task()

    claims = await AssetResearchTaskRunner(
        session_maker=async_session_maker,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    ).claim_due(now=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc))

    assert len(claims) == 1
    assert events == [{"asset_type": "futures", "count": 1}]


@pytest.mark.asyncio
async def test_task_runner_turns_an_expired_running_lease_into_a_retryable_failure() -> None:
    task_id = await _seed_pending_task()
    now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )
    await runner.claim_due(now=now)

    recovered = await runner.recover_expired_leases(now=now + timedelta(seconds=31))

    assert recovered == 1
    async with async_session_maker() as db:
        task = await db.get(AssetAnalysisTask, task_id)
        assert task is not None
        assert task.status == "FAILED"
        assert task.error_code == "TASK_LEASE_EXPIRED"
        assert task.progress == 100
        assert task.lease_token is None
        assert task.lease_expires_at is None
        assert task.completed_at is not None
        assert task.completed_at.replace(tzinfo=timezone.utc) == now + timedelta(seconds=31)


@pytest.mark.asyncio
async def test_task_runner_executes_a_claimed_task_then_releases_its_terminal_lease() -> None:
    task_id = await _seed_pending_task()
    now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    executions: list[tuple[str, str]] = []

    class _FinishingService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def run_claimed_task(self, *, task_id: str, lease_token: str) -> None:
            task = await self.db.get(AssetAnalysisTask, task_id)  # type: ignore[union-attr]
            assert task is not None
            assert task.lease_token == lease_token
            executions.append((task_id, lease_token))
            task.status = "SUCCEEDED"
            task.progress = 100
            task.completed_at = now

    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        orchestrator_factory=_FinishingService,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )

    processed = await runner.run_due(now=now)

    assert processed == 1
    assert [execution[0] for execution in executions] == [task_id]
    async with async_session_maker() as db:
        task = await db.get(AssetAnalysisTask, task_id)
        assert task is not None
        assert task.status == "SUCCEEDED"
        assert task.lease_token is None
        assert task.lease_expires_at is None
        assert task.lease_heartbeat_at is None


@pytest.mark.asyncio
async def test_task_runner_executes_real_orchestration_from_a_matching_lease() -> None:
    task_id = await _seed_pending_task()

    class _FixtureData:
        async def collect(
            self, identity: InstrumentIdentity, *, cutoff_at: datetime
        ) -> RawAssetSnapshot:
            return RawAssetSnapshot(
                identity=identity,
                cutoff_at=cutoff_at,
                retrieved_at=cutoff_at,
                raw_schema_version="task-runner-fixture-v1",
                raw_fields={
                    "snapshot": {"price": 101, "bid": 100.9, "ask": 101.1},
                    "futures": {"contract_price": 101, "spot_price": 100},
                },
                history_rows=[{"date": "2026-08-01", "close": 101}],
                source_manifest={"source_id": DEFAULT_ASSET_RESEARCH_SOURCE_ID},
                license_tags=[],
                content_hash="a" * 64,
            )

    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        orchestrator_factory=lambda db: AssetResearchOrchestrator(db, data_adapter=_FixtureData()),
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )

    processed = await runner.run_due(now=datetime.now(timezone.utc))

    assert processed == 1
    async with async_session_maker() as db:
        task = await db.get(AssetAnalysisTask, task_id)
        assert task is not None
        assert task.status == "SUCCEEDED"
        assert task.lease_token is None
        runs = list((await db.execute(select(AssetSignalRun))).scalars())
        assert len(runs) == 1
        assert runs[0].status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_task_runner_renews_lease_while_claimed_work_is_still_running() -> None:
    task_id = await _seed_pending_task()
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def run_claimed_task(self, *, task_id: str, lease_token: str) -> None:
            task = await self.db.get(AssetAnalysisTask, task_id)  # type: ignore[union-attr]
            assert task is not None
            assert task.lease_token == lease_token
            started.set()
            await release.wait()
            task.status = "SUCCEEDED"
            task.progress = 100
            task.completed_at = datetime.now(timezone.utc)

    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        orchestrator_factory=_BlockingService,
        lease_seconds=1,
        max_batch=1,
        max_concurrency=1,
    )
    worker = asyncio.create_task(runner.run_due())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            initial_heartbeat = task.lease_heartbeat_at
            assert initial_heartbeat is not None

        await asyncio.sleep(1.1)

        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.lease_heartbeat_at is not None
            assert task.lease_heartbeat_at > initial_heartbeat
            assert task.lease_expires_at is not None
            assert task.lease_expires_at > task.lease_heartbeat_at
    finally:
        release.set()
        await worker


@pytest.mark.asyncio
async def test_task_runner_preserves_a_user_cancellation_over_a_late_worker_completion(
    monkeypatch,
) -> None:
    """A worker that finishes after cancellation must not revive the task."""
    task_id = await _seed_pending_task()
    started = asyncio.Event()
    release = asyncio.Event()
    lifecycle_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        task_runner_module,
        "record_asset_research_task",
        lambda **event: lifecycle_events.append(event),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "record_asset_research_task",
        lambda **event: lifecycle_events.append(event),
    )

    class _LateFinishingService:
        def __init__(self, db: object) -> None:
            self.db = db

        async def run_claimed_task(self, *, task_id: str, lease_token: str) -> None:
            task = await self.db.get(AssetAnalysisTask, task_id)  # type: ignore[union-attr]
            assert task is not None
            assert task.lease_token == lease_token
            started.set()
            await release.wait()
            task.status = "SUCCEEDED"
            task.progress = 100
            task.completed_at = datetime.now(timezone.utc)

    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        orchestrator_factory=_LateFinishingService,
        lease_seconds=30,
        max_batch=1,
        max_concurrency=1,
    )
    worker = asyncio.create_task(runner.run_due())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            response = await AssetResearchOrchestrator(db).cancel_task(
                user_id=task.user_id,
                task_id=task_id,
            )
            assert response is not None
            assert response.status == "CANCELLED"
            await db.commit()

        release.set()
        await asyncio.wait_for(worker, timeout=1)

        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.status == "CANCELLED"
            assert task.lease_token is None
            assert task.lease_expires_at is None
            assert task.lease_heartbeat_at is None
        assert [event["status"] for event in lifecycle_events] == ["RUNNING", "CANCELLED"]
    finally:
        release.set()
        if not worker.done():
            await worker


@pytest.mark.asyncio
async def test_task_runner_rolls_back_real_analysis_when_cancellation_wins_during_collection() -> None:
    """A cancelled real task must not leave a run or published result behind."""
    task_id = await _seed_pending_task()
    collection_started = asyncio.Event()
    release_collection = asyncio.Event()

    class _BlockingFixtureData:
        async def collect(
            self, identity: InstrumentIdentity, *, cutoff_at: datetime
        ) -> RawAssetSnapshot:
            collection_started.set()
            await release_collection.wait()
            return RawAssetSnapshot(
                identity=identity,
                cutoff_at=cutoff_at,
                retrieved_at=cutoff_at,
                raw_schema_version="task-runner-cancellation-v1",
                raw_fields={
                    "snapshot": {"price": 101, "bid": 100.9, "ask": 101.1},
                    "futures": {"contract_price": 101, "spot_price": 100},
                },
                history_rows=[{"date": "2026-08-01", "close": 101}],
                source_manifest={"source_id": DEFAULT_ASSET_RESEARCH_SOURCE_ID},
                license_tags=[],
                content_hash="c" * 64,
            )

    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        orchestrator_factory=lambda db: AssetResearchOrchestrator(
            db,
            data_adapter=_BlockingFixtureData(),
        ),
        lease_seconds=30,
        max_batch=1,
        max_concurrency=1,
    )
    worker = asyncio.create_task(runner.run_due())
    try:
        await asyncio.wait_for(collection_started.wait(), timeout=1)
        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            response = await AssetResearchOrchestrator(db).cancel_task(
                user_id=task.user_id,
                task_id=task_id,
            )
            assert response is not None
            await db.commit()

        release_collection.set()
        await asyncio.wait_for(worker, timeout=1)

        async with async_session_maker() as db:
            task = await db.get(AssetAnalysisTask, task_id)
            assert task is not None
            assert task.status == "CANCELLED"
            assert task.lease_token is None
            assert task.lease_expires_at is None
            assert task.lease_heartbeat_at is None
            assert list((await db.execute(select(AssetSignalRun))).scalars()) == []
    finally:
        release_collection.set()
        if not worker.done():
            await worker


@pytest.mark.asyncio
async def test_task_runner_wake_coalesces_repeated_request_triggers(monkeypatch) -> None:
    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    runs = 0

    async def blocked_run_due() -> int:
        nonlocal runs
        runs += 1
        started.set()
        await release.wait()
        return 0

    monkeypatch.setattr(runner, "run_due", blocked_run_due)

    assert runner.wake() is True
    await asyncio.wait_for(started.wait(), timeout=1)
    assert runner.wake() is False
    assert runs == 1

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert runner.wake() is True
    await asyncio.sleep(0)
    assert runs == 2
    await runner.shutdown()


def test_task_runner_uses_validated_interactive_worker_defaults() -> None:
    runner = AssetResearchTaskRunner(session_maker=async_session_maker)
    settings = get_settings()

    assert runner._lease_seconds == settings.ASSET_RESEARCH_TASK_LEASE_SECONDS
    assert runner._max_batch == settings.ASSET_RESEARCH_TASK_MAX_BATCH
    assert runner._max_concurrency == settings.ASSET_RESEARCH_TASK_WORKER_CONCURRENCY


@pytest.mark.asyncio
async def test_task_runner_does_not_wake_when_the_interactive_worker_is_disabled(
    monkeypatch,
) -> None:
    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )
    monkeypatch.setattr(
        task_runner_module,
        "get_settings",
        lambda: SimpleNamespace(ASSET_RESEARCH_TASK_RUNNER_ENABLED=False),
    )

    assert runner.wake() is False


@pytest.mark.asyncio
async def test_task_runner_start_relies_on_the_poller_without_an_implicit_wake(
    monkeypatch,
) -> None:
    runner = AssetResearchTaskRunner(
        session_maker=async_session_maker,
        lease_seconds=30,
        max_batch=10,
        max_concurrency=1,
    )
    calls: list[str] = []

    class _Scheduler:
        running = False

        def start(self) -> None:
            calls.append("scheduler.start")
            self.running = True

    monkeypatch.setattr(
        task_runner_module,
        "get_settings",
        lambda: SimpleNamespace(ASSET_RESEARCH_TASK_RUNNER_ENABLED=True),
    )
    monkeypatch.setattr(runner, "_ensure_scheduler", lambda: _Scheduler())
    monkeypatch.setattr(runner, "wake", lambda: calls.append("wake") or True)

    assert await runner.start() is True
    assert calls == ["scheduler.start"]
