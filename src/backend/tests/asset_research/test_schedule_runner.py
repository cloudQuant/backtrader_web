"""Lease, retry and recovery contracts for the multi-asset schedule worker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.asset_research import (
    AssetAnalysisReport,
    AssetAnalysisTask,
    AssetDataSourceRegistry,
    AssetSignalPrediction,
    AssetSignalRun,
    AssetSignalSchedule,
)
from app.models.user import User
from app.schemas.asset_research import (
    ApprovedScheduleManifestCreateRequest,
    ApprovedScheduleManifestEntry,
    AssetSignalScheduleCreateRequest,
    AssetSignalScheduleUpdateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research import scheduler as scheduler_module
from app.services.asset_research.concurrency import AssetResearchSourceConcurrencyLimiter
from app.services.asset_research.orchestrator import (
    AssetResearchOrchestrationError,
    AssetResearchOrchestrator,
)
from app.services.asset_research.scheduler import (
    AssetResearchScheduleRunner,
    ClaimedSchedule,
    _as_utc,
)


class _FuturesData:
    def __init__(self) -> None:
        self.fail = False

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        if self.fail:
            raise RuntimeError("fixture source temporarily unavailable")
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={"snapshot": {"price": 101, "bid": 100.9, "ask": 101.1}},
            history_rows=[{"date": "2026-08-01", "close": 101}],
            source_manifest={
                "provider": "schedule-runner-fixture",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=[],
            content_hash="e" * 64,
        )


def _identity(index: int | None = None) -> InstrumentIdentity:
    contract_code = "IF2609" if index is None else f"IF{2700 + index:04d}"
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id=f"futures:CFFEX:{contract_code}:CNY",
        display_symbol=contract_code,
        name=f"沪深300期货{contract_code}",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value=contract_code,
        product_type="FUTURE",
        metadata_version="fixture-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month=contract_code[-4:],
            expiry_at=(
                "2026-09-18T07:15:00+00:00" if index is None else "2031-09-18T07:15:00+00:00"
            ),
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


# Iteration 193 Task J (T1): defuse the 2026-08-03 time bomb. The suite seeded
# due schedules with a fixed past fire_at; once the real clock moved past it,
# internal now()-relative logic (persist_identity / lease timestamps) made the
# suite fail -- the same root cause as iter 192's 4 expired tests. These
# module-level references keep the relative spacing (fire -> claim = 4d+50m)
# while anchoring to the current clock so the suite is reproducible on any
# system date.
_FIRE_AT = datetime.now(timezone.utc).replace(
    hour=11, minute=10, second=0, microsecond=0
) - timedelta(days=1)
_CLAIM_AT = _FIRE_AT + timedelta(days=4, minutes=50)  # 12:00 on day 4
_AS_OF_AT = _FIRE_AT + timedelta(days=4)  # claim date + fire time (11:10)


async def _seed_due_schedule(
    *,
    fire_at: datetime,
) -> tuple[str, str]:
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_runner_user",
            email="asset-schedule-runner@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-runner-fixture",
                asset_types=["futures"],
                jurisdictions=["GLOBAL"],
                license_status="APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="research-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                freshness_sla={},
                enabled=True,
            )
        )
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_FuturesData())
        await service.persist_identity(
            _identity(),
            valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        schedule = await service.create_schedule(
            user_id=user.id,
            request=AssetSignalScheduleCreateRequest(
                asset_type="futures",
                canonical_id="futures:CFFEX:IF2609:CNY",
                cron_expression="10 19 * * 1-5",
                timezone="Asia/Shanghai",
                cutoff_policy="futures-complete-session-v1",
            ),
            idempotency_key="schedule-runner-1",
        )
        schedule.next_run_at = fire_at
        await db.commit()
        return user.id, schedule.id


async def _seed_due_system_schedule(
    *,
    fire_at: datetime,
    owner_scope: str,
) -> str:
    """Seed one exact system-owned schedule without a runtime universe selector."""
    async with async_session_maker() as db:
        if await db.get(AssetDataSourceRegistry, "schedule-runner-fixture") is None:
            db.add(
                AssetDataSourceRegistry(
                    source_id="schedule-runner-fixture",
                    asset_types=["futures"],
                    jurisdictions=["GLOBAL"],
                    license_status="APPROVED",
                    allowed_uses=["RESEARCH_ONLY"],
                    redistribution_policy="NO_REDISTRIBUTION",
                    derived_data_policy="ALLOWED",
                    retention_policy="research-v1",
                    effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                    freshness_sla={},
                    enabled=True,
                )
            )
        service = AssetResearchOrchestrator(db, data_adapter=_FuturesData())
        instrument = await service.persist_identity(
            _identity(),
            valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        manifest = await service.create_approved_schedule_manifest(
            actor_id="fixture-admin",
            request=ApprovedScheduleManifestCreateRequest(
                manifest_key=f"runner-{owner_scope.lower()}",
                manifest_version="fixture-v1",
                owner_scope=owner_scope,  # type: ignore[arg-type]
                approval_reference="TEST-ONLY",
                evidence_uri=f"evidence://test/{owner_scope.lower()}",
                evidence_content_hash="f" * 64,
                entries=[
                    ApprovedScheduleManifestEntry(
                        entry_key="if2609",
                        schedule=AssetSignalScheduleCreateRequest(
                            asset_type="futures",
                            canonical_id=instrument.canonical_id,
                            cron_expression="10 19 * * 1-5",
                            timezone="Asia/Shanghai",
                            cutoff_policy="futures-complete-session-v1",
                        ),
                    )
                ],
            ),
        )
        schedule = (
            await db.execute(
                select(AssetSignalSchedule).where(
                    AssetSignalSchedule.approved_manifest_id == manifest.id
                )
            )
        ).scalar_one()
        schedule.next_run_at = fire_at
        await db.commit()
        return schedule.id


class _CapacityFuturesData(_FuturesData):
    """Fixed provider fixture that records the real source-concurrency peak."""

    declared_source_ids = ("schedule-runner-fixture",)

    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            # Keep a collection in flight long enough for the worker pool and
            # the shared source limiter to contend deterministically.
            await asyncio.sleep(0.002)
            return await super().collect(identity, cutoff_at=cutoff_at)
        finally:
            self.active -= 1


async def _seed_due_system_schedule_batch(
    *,
    fire_at: datetime,
    count: int,
) -> list[str]:
    """Create an exact, bounded public-shadow manifest for capacity coverage."""
    async with async_session_maker() as db:
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-runner-fixture",
                asset_types=["futures"],
                jurisdictions=["GLOBAL"],
                license_status="APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="research-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                freshness_sla={},
                enabled=True,
            )
        )
        service = AssetResearchOrchestrator(db, data_adapter=_CapacityFuturesData())
        entries: list[ApprovedScheduleManifestEntry] = []
        for index in range(count):
            instrument = await service.persist_identity(
                _identity(index),
                valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
            entries.append(
                ApprovedScheduleManifestEntry(
                    entry_key=f"capacity-{index:03d}",
                    schedule=AssetSignalScheduleCreateRequest(
                        asset_type="futures",
                        canonical_id=instrument.canonical_id,
                        cron_expression="10 19 * * 1-5",
                        timezone="Asia/Shanghai",
                        cutoff_policy="futures-complete-session-v1",
                    ),
                )
            )
        manifest = await service.create_approved_schedule_manifest(
            actor_id="capacity-fixture-admin",
            request=ApprovedScheduleManifestCreateRequest(
                manifest_key="capacity-public-shadow",
                manifest_version="fixture-v1",
                owner_scope="PUBLIC_SHADOW",
                approval_reference="CAPACITY-FIXTURE-ONLY",
                evidence_uri="evidence://test/capacity-public-shadow",
                evidence_content_hash="c" * 64,
                entries=entries,
            ),
        )
        schedules = list(
            (
                await db.execute(
                    select(AssetSignalSchedule)
                    .where(AssetSignalSchedule.approved_manifest_id == manifest.id)
                    .order_by(AssetSignalSchedule.manifest_entry_key)
                )
            ).scalars()
        )
        for schedule in schedules:
            schedule.next_run_at = fire_at
        await db.commit()
        return [str(schedule.id) for schedule in schedules]


def _runner(
    data: _FuturesData,
    *,
    misfire_grace_seconds: int | None = None,
) -> AssetResearchScheduleRunner:
    return AssetResearchScheduleRunner(
        session_maker=async_session_maker,
        orchestrator_factory=lambda db: AssetResearchOrchestrator(db, data_adapter=data),
        lease_seconds=120,
        max_retries=2,
        misfire_grace_seconds=misfire_grace_seconds,
        retry_base_seconds=30,
        retry_max_seconds=60,
        max_batch=10,
        max_concurrency=1,
    )


def test_default_schedule_runner_matches_approved_capacity_configuration() -> None:
    """The runtime defaults must drain the documented approved cycle in one poll."""
    runner = AssetResearchScheduleRunner(session_maker=async_session_maker)

    assert runner._max_batch == 100
    assert runner._max_concurrency == 4


@pytest.mark.asyncio
async def test_runner_limits_parallel_claim_execution_to_configured_worker_concurrency() -> None:
    """A bounded batch must use workers without exceeding the configured pool size."""
    runner = AssetResearchScheduleRunner(
        session_maker=async_session_maker,
        max_batch=4,
        max_concurrency=2,
    )
    claims = [
        ClaimedSchedule(schedule_id=f"schedule-{index}", lease_token=f"lease-{index}")
        for index in range(4)
    ]
    active = 0
    max_active = 0

    async def fake_claim_due(*, now: datetime | None = None) -> list[ClaimedSchedule]:
        del now
        return claims

    async def fake_run_claim(claim: ClaimedSchedule, *, claim_time: datetime) -> None:
        nonlocal active, max_active
        del claim, claim_time
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1

    runner.claim_due = fake_claim_due  # type: ignore[method-assign]
    runner._run_claim = fake_run_claim  # type: ignore[method-assign]

    assert await runner.run_due(now=_FIRE_AT) == 4
    assert max_active == 2


@pytest.mark.asyncio
async def test_capacity_fixture_persists_one_approved_100_instrument_cycle_without_reports() -> (
    None
):
    """One bounded static manifest persists only terminal schedule artifacts."""
    fire_at = datetime(2030, 1, 2, 11, 10, tzinfo=timezone.utc)
    schedule_ids = await _seed_due_system_schedule_batch(fire_at=fire_at, count=100)
    data = _CapacityFuturesData()
    source_limiter = AssetResearchSourceConcurrencyLimiter(max_per_source=2)
    runner = AssetResearchScheduleRunner(
        session_maker=async_session_maker,
        orchestrator_factory=lambda db: AssetResearchOrchestrator(
            db,
            data_adapter=data,
            source_limiter=source_limiter,
        ),
        max_batch=100,
        # The repository-wide unit fixture is a single-connection in-memory
        # SQLite database.  Dedicated disposable-MySQL acceptance covers the
        # real four-worker persistence path.
        max_concurrency=1,
    )

    started_at = perf_counter()
    claimed_count = await runner.run_due(now=fire_at + timedelta(minutes=1))
    elapsed_seconds = perf_counter() - started_at

    assert claimed_count == 100
    assert elapsed_seconds < 30 * 60
    assert data.max_active <= 2
    async with async_session_maker() as db:
        schedules = list(
            (
                await db.execute(
                    select(AssetSignalSchedule).where(AssetSignalSchedule.id.in_(schedule_ids))
                )
            ).scalars()
        )
        runs = list(
            (
                await db.execute(
                    select(AssetSignalRun).where(AssetSignalRun.schedule_id.in_(schedule_ids))
                )
            ).scalars()
        )
        task_count = await db.scalar(select(func.count()).select_from(AssetAnalysisTask))
        report_count = await db.scalar(select(func.count()).select_from(AssetAnalysisReport))

    assert len(schedules) == 100
    assert all(schedule.lease_token is None for schedule in schedules)
    assert all(schedule.retry_of_run_id is None for schedule in schedules)
    assert len(runs) == 100
    assert all(run.status == "SUCCEEDED" for run in runs)
    assert all(run.prediction_id is not None for run in runs)
    assert task_count == 0
    assert report_count == 0


@pytest.mark.asyncio
async def test_two_workers_can_claim_one_due_schedule_only_once() -> None:
    fire_at = _FIRE_AT
    await _seed_due_schedule(fire_at=fire_at)
    first = _runner(_FuturesData())
    second = _runner(_FuturesData())

    first_claim, second_claim = await asyncio.gather(
        first.claim_due(now=fire_at + timedelta(minutes=1)),
        second.claim_due(now=fire_at + timedelta(minutes=1)),
    )

    assert len(first_claim) + len(second_claim) == 1


@pytest.mark.asyncio
async def test_schedule_runner_publishes_queue_depth_before_claiming(monkeypatch) -> None:
    """Queue depth is observable even before a due schedule is leased."""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        scheduler_module,
        "set_asset_research_queue_depth",
        lambda **event: events.append(event),
    )
    fire_at = _FIRE_AT
    await _seed_due_schedule(fire_at=fire_at)

    claims = await _runner(_FuturesData()).claim_due(now=fire_at + timedelta(minutes=1))

    assert len(claims) == 1
    assert events == [{"asset_type": "futures", "count": 1}]


@pytest.mark.asyncio
async def test_runner_executes_public_shadow_schedule_without_a_user() -> None:
    """Approved static public schedules are system-owned, never converted to a user run."""
    fire_at = _FIRE_AT
    schedule_id = await _seed_due_system_schedule(
        fire_at=fire_at,
        owner_scope="PUBLIC_SHADOW",
    )

    assert await _runner(_FuturesData()).run_due(now=fire_at + timedelta(minutes=1)) == 1
    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        run = (
            await db.execute(
                select(AssetSignalRun).where(AssetSignalRun.schedule_id == schedule_id)
            )
        ).scalar_one()
        assert run.prediction_id is not None
        prediction = await db.get(AssetSignalPrediction, run.prediction_id)

    assert schedule is not None
    assert schedule.owner_scope == "PUBLIC_SHADOW"
    assert schedule.user_id is None
    assert run.status == "SUCCEEDED"
    assert run.owner_scope == "PUBLIC_SHADOW"
    assert run.user_id is None
    assert prediction is not None
    assert prediction.owner_scope == "PUBLIC_SHADOW"
    assert prediction.user_id is None


@pytest.mark.asyncio
async def test_visible_history_includes_public_shadow_but_excludes_admin_evaluation() -> None:
    """A normal user sees published public shadow facts but never admin candidates."""
    fire_at = _FIRE_AT
    public_schedule_id = await _seed_due_system_schedule(
        fire_at=fire_at,
        owner_scope="PUBLIC_SHADOW",
    )
    admin_schedule_id = await _seed_due_system_schedule(
        fire_at=fire_at,
        owner_scope="ADMIN_EVAL",
    )
    runner = _runner(_FuturesData())

    assert await runner.run_due(now=fire_at + timedelta(minutes=1)) == 2
    async with async_session_maker() as db:
        user = User(
            username="asset_public_history_user",
            email="asset-public-history@example.test",
            hashed_password="hash",
        )
        db.add(user)
        await db.flush()
        service = AssetResearchOrchestrator(db, data_adapter=_FuturesData())
        history = await service.get_signal_history(
            user_id=user.id,
            asset_type="futures",
            canonical_id="futures:CFFEX:IF2609:CNY",
        )
        runs = list(
            (
                await db.execute(
                    select(AssetSignalRun).where(
                        AssetSignalRun.schedule_id.in_([public_schedule_id, admin_schedule_id])
                    )
                )
            ).scalars()
        )

    public_run = next(run for run in runs if run.schedule_id == public_schedule_id)
    admin_run = next(run for run in runs if run.schedule_id == admin_schedule_id)
    assert public_run.prediction_id is not None
    assert admin_run.prediction_id is not None
    async with async_session_maker() as db:
        public_prediction = await db.get(AssetSignalPrediction, public_run.prediction_id)
        admin_prediction = await db.get(AssetSignalPrediction, admin_run.prediction_id)

    assert public_run.owner_scope == "PUBLIC_SHADOW"
    assert public_run.user_id is None
    assert admin_run.owner_scope == "ADMIN_EVAL"
    assert admin_run.user_id is None
    assert public_prediction is not None
    assert public_prediction.owner_scope == "PUBLIC_SHADOW"
    assert public_prediction.user_id is None
    assert admin_prediction is not None
    assert admin_prediction.owner_scope == "ADMIN_EVAL"
    assert admin_prediction.user_id is None
    assert [item.prediction_id for item in history.items] == [public_run.prediction_id]
    assert [item.owner_scope for item in history.items] == ["PUBLIC_SHADOW"]


@pytest.mark.asyncio
async def test_runner_retries_with_original_cutoff_and_preserves_failed_run() -> None:
    fire_at = _FIRE_AT
    user_id, schedule_id = await _seed_due_schedule(fire_at=fire_at)
    data = _FuturesData()
    data.fail = True
    runner = _runner(data)

    assert await runner.run_due(now=fire_at + timedelta(minutes=1)) == 1
    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        failed_run = (
            await db.execute(
                select(AssetSignalRun).where(AssetSignalRun.schedule_id == schedule_id)
            )
        ).scalar_one()
        assert schedule is not None
        assert failed_run.status == "FAILED"
        assert schedule.retry_of_run_id == failed_run.id
        assert schedule.retry_attempt == 1
        assert schedule.retry_scheduled_fire_at == failed_run.as_of_at
        assert schedule.retry_cutoff_at == failed_run.cutoff_at
        assert schedule.lease_token is None
        assert schedule.lease_expires_at is None
        retry_at = _as_utc(schedule.retry_not_before_at)
        service = AssetResearchOrchestrator(db, data_adapter=data)
        with pytest.raises(AssetResearchOrchestrationError, match="SCHEDULE_RETRY_PENDING"):
            await service.update_schedule(
                user_id=user_id,
                schedule_id=schedule_id,
                request=AssetSignalScheduleUpdateRequest(enabled=False),
            )

    data.fail = False
    assert await runner.run_due(now=retry_at) == 1
    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        runs = list(
            (
                await db.execute(
                    select(AssetSignalRun)
                    .where(AssetSignalRun.schedule_id == schedule_id)
                    .order_by(AssetSignalRun.attempt_number)
                )
            ).scalars()
        )

    assert [run.status for run in runs] == ["FAILED", "SUCCEEDED"], schedule.last_error_code
    assert runs[1].retry_of_run_id == runs[0].id
    assert runs[1].as_of_at == runs[0].as_of_at
    assert runs[1].cutoff_at == runs[0].cutoff_at
    assert runs[1].schedule_config_json == runs[0].schedule_config_json
    assert schedule is not None
    assert schedule.retry_of_run_id is None
    assert schedule.retry_attempt == 0
    assert schedule.lease_token is None
    assert schedule.next_run_at is not None
    assert _as_utc(schedule.next_run_at) > fire_at


@pytest.mark.asyncio
async def test_skip_misfire_advances_schedule_without_creating_a_prediction() -> None:
    fire_at = _FIRE_AT
    _, schedule_id = await _seed_due_schedule(fire_at=fire_at)
    runner = _runner(_FuturesData(), misfire_grace_seconds=30)
    claim_time = fire_at + timedelta(days=2)

    assert await runner.run_due(now=claim_time) == 1
    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        runs = list(
            (
                await db.execute(
                    select(AssetSignalRun).where(AssetSignalRun.schedule_id == schedule_id)
                )
            ).scalars()
        )

    assert schedule is not None
    assert runs == []
    assert schedule.last_error_code == "SCHEDULE_MISFIRE_SKIPPED"
    assert schedule.lease_token is None
    assert schedule.next_run_at is not None
    assert _as_utc(schedule.next_run_at) > claim_time


@pytest.mark.asyncio
async def test_run_once_misfire_uses_the_latest_completed_fire_only() -> None:
    fire_at = _FIRE_AT
    _, schedule_id = await _seed_due_schedule(fire_at=fire_at)
    runner = _runner(_FuturesData(), misfire_grace_seconds=30)
    claim_time = _CLAIM_AT

    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        assert schedule is not None
        schedule.misfire_policy = "RUN_ONCE"
        await db.commit()

    assert await runner.run_due(now=claim_time) == 1
    async with async_session_maker() as db:
        runs = list(
            (
                await db.execute(
                    select(AssetSignalRun).where(AssetSignalRun.schedule_id == schedule_id)
                )
            ).scalars()
        )

    assert len(runs) == 1
    assert runs[0].status == "SUCCEEDED"
    assert _as_utc(runs[0].as_of_at) == _AS_OF_AT


@pytest.mark.asyncio
async def test_backfill_misfire_keeps_the_original_fire_for_the_next_bounded_poll() -> None:
    fire_at = _FIRE_AT
    _, schedule_id = await _seed_due_schedule(fire_at=fire_at)
    runner = _runner(_FuturesData(), misfire_grace_seconds=30)
    claim_time = _CLAIM_AT

    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        assert schedule is not None
        schedule.misfire_policy = "BACKFILL"
        await db.commit()

    assert await runner.run_due(now=claim_time) == 1
    async with async_session_maker() as db:
        schedule = await db.get(AssetSignalSchedule, schedule_id)
        runs = list(
            (
                await db.execute(
                    select(AssetSignalRun).where(AssetSignalRun.schedule_id == schedule_id)
                )
            ).scalars()
        )

    assert schedule is not None
    assert len(runs) == 1
    assert _as_utc(runs[0].as_of_at) == fire_at
    assert schedule.next_run_at is not None
    assert _as_utc(schedule.next_run_at) <= claim_time
