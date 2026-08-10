"""Single-instrument shadow schedules freeze config and never infer a position."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import (
    AssetDataSourceRegistry,
    AssetInstrument,
    AssetSignalOutcome,
    AssetSignalRun,
)
from app.models.user import User
from app.schemas.asset_research import (
    AssetSignalScheduleCreateRequest,
    AssetSignalScheduleUpdateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research.orchestrator import (
    AssetResearchOrchestrationError,
    AssetResearchOrchestrator,
)


class _Data:
    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={"snapshot": {"price": 101, "bid": 100.9, "ask": 101.1}},
            history_rows=[{"date": "2026-08-01", "close": 101}],
            source_manifest={
                "provider": "schedule-fixture",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=[],
            content_hash="d" * 64,
        )


@pytest.mark.asyncio
async def test_failed_schedule_never_keeps_a_prediction_link_or_outcomes() -> None:
    """A failed run is not allowed to retain a run-to-prediction association."""
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_failure_user",
            email="asset-schedule-failure@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-fixture",
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
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
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
            idempotency_key="schedule-failure-1",
        )
        original_next_run = schedule.next_run_at
        plugin = service.registry.get("futures")

        with patch.object(
            type(plugin), "score_outcome", side_effect=RuntimeError("outcome failed")
        ):
            run = await service.run_schedule(
                user_id=user.id,
                schedule_id=schedule.id,
                scheduled_fire_at=datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc),
            )
        runs = list((await db.execute(select(AssetSignalRun))).scalars())
        outcomes = list((await db.execute(select(AssetSignalOutcome))).scalars())

    assert run.status == "FAILED"
    assert runs == [run]
    assert run.prediction_id is None
    assert run.prediction_link_role is None
    assert outcomes == []
    assert schedule.next_run_at == original_next_run


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
        metadata_version="fixture-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


@pytest.mark.asyncio
async def test_schedule_freezes_one_identity_version_and_creates_a_schedule_sourced_run() -> None:
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_user",
            email="asset-schedule@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-fixture",
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
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
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
            idempotency_key="schedule-1",
        )
        initial_next_run = schedule.next_run_at
        updated = await service.update_schedule(
            user_id=user.id,
            schedule_id=schedule.id,
            request=AssetSignalScheduleUpdateRequest(enabled=False),
        )
        run = await service.run_schedule(
            user_id=user.id,
            schedule_id=updated.id,
            scheduled_fire_at=datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc),
        )
        persisted = (
            await db.execute(select(AssetSignalRun).where(AssetSignalRun.id == run.id))
        ).scalar_one()

    assert schedule.position_context == "UNKNOWN"
    assert schedule.position_context_snapshot_id is None
    assert initial_next_run is not None
    assert updated.next_run_at is None
    assert updated.schedule_version == 2
    assert persisted.schedule_id == schedule.id
    assert persisted.task_id is None
    assert persisted.status == "SUCCEEDED"
    assert persisted.cutoff_at == datetime(2026, 8, 3, 11, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_reenabling_a_schedule_rejects_a_delisted_instrument() -> None:
    """A stale schedule cannot be re-enabled after its confirmed identity is retired."""
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_delisted_user",
            email="asset-schedule-delisted@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-delisted-fixture",
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
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
        instrument = await service.persist_identity(
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
        )
        await service.update_schedule(
            user_id=user.id,
            schedule_id=schedule.id,
            request=AssetSignalScheduleUpdateRequest(enabled=False),
        )
        instrument.lifecycle_status = "DELISTED"
        await db.flush()

        with pytest.raises(AssetResearchOrchestrationError, match="INSTRUMENT_VERSION_STALE"):
            await service.update_schedule(
                user_id=user.id,
                schedule_id=schedule.id,
                request=AssetSignalScheduleUpdateRequest(enabled=True),
            )


@pytest.mark.asyncio
async def test_schedule_run_fails_when_its_identity_expires_before_cutoff() -> None:
    """A queued schedule must not collect from an identity expired at its frozen cutoff."""
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_runtime_expired_user",
            email="asset-schedule-runtime-expired@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-fixture",
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
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
        instrument = await service.persist_identity(
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
        )
        instrument.valid_to = datetime(2026, 8, 2, 23, 59, tzinfo=timezone.utc)
        await db.flush()

        run = await service.run_schedule(
            user_id=user.id,
            schedule_id=schedule.id,
            scheduled_fire_at=datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc),
        )

    assert run.status == "FAILED"
    assert run.counts_json == {"error_code": "INSTRUMENT_VERSION_STALE"}


@pytest.mark.asyncio
async def test_schedule_run_fails_when_a_newer_identity_version_supersedes_its_binding() -> None:
    """A future schedule fire cannot silently retain an older overlapping version."""
    first_identity = _identity()
    second_identity = first_identity.model_copy(update={"metadata_version": "fixture-v2"})
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_runtime_superseded_user",
            email="asset-schedule-runtime-superseded@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-fixture",
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
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
        first = await service.persist_identity(
            first_identity,
            valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        first.valid_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
        schedule = await service.create_schedule(
            user_id=user.id,
            request=AssetSignalScheduleCreateRequest(
                asset_type="futures",
                canonical_id=first_identity.canonical_id,
                cron_expression="10 19 * * 1-5",
                timezone="Asia/Shanghai",
                cutoff_policy="futures-complete-session-v1",
            ),
        )
        db.add(
            AssetInstrument(
                canonical_id=second_identity.canonical_id,
                asset_type=second_identity.asset_type,
                identity_level=second_identity.identity_level,
                venue=second_identity.venue,
                currency=second_identity.currency,
                product_type=second_identity.product_type,
                identity_json=second_identity.model_dump(mode="json"),
                metadata_version=second_identity.metadata_version,
                lifecycle_status="ACTIVE",
                valid_from=datetime(2026, 8, 2, tzinfo=timezone.utc),
            )
        )
        await db.flush()

        run = await service.run_schedule(
            user_id=user.id,
            schedule_id=schedule.id,
            scheduled_fire_at=datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc),
        )

    assert run.status == "FAILED"
    assert run.counts_json == {"error_code": "INSTRUMENT_VERSION_STALE"}


@pytest.mark.asyncio
async def test_schedule_retry_reuses_the_historical_identity_version_at_its_frozen_cutoff() -> None:
    """A retry must replay its original point in time, not today's master version."""
    first_identity = _identity()
    second_identity = first_identity.model_copy(update={"metadata_version": "fixture-v2"})
    async with async_session_maker() as db:
        user = User(
            username="asset_schedule_retry_historical_identity_user",
            email="asset-schedule-retry-historical-identity@example.test",
            hashed_password="hash",
        )
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="schedule-fixture",
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
        service = AssetResearchOrchestrator(db, data_adapter=_Data())
        first = await service.persist_identity(
            first_identity,
            valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        first.valid_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
        schedule = await service.create_schedule(
            user_id=user.id,
            request=AssetSignalScheduleCreateRequest(
                asset_type="futures",
                canonical_id=first_identity.canonical_id,
                cron_expression="10 19 * * 1-5",
                timezone="Asia/Shanghai",
                cutoff_policy="futures-complete-session-v1",
            ),
        )
        plugin = service.registry.get("futures")
        fire_at = datetime(2026, 8, 1, 11, 10, tzinfo=timezone.utc)
        with patch.object(
            type(plugin), "score_outcome", side_effect=RuntimeError("fixture scoring failure")
        ):
            failed_run = await service.run_schedule(
                user_id=user.id,
                schedule_id=schedule.id,
                scheduled_fire_at=fire_at,
            )
        assert failed_run.status == "FAILED"

        first.valid_to = datetime(2026, 8, 1, 23, 59, tzinfo=timezone.utc)
        db.add(
            AssetInstrument(
                canonical_id=second_identity.canonical_id,
                asset_type=second_identity.asset_type,
                identity_level=second_identity.identity_level,
                venue=second_identity.venue,
                currency=second_identity.currency,
                product_type=second_identity.product_type,
                identity_json=second_identity.model_dump(mode="json"),
                metadata_version=second_identity.metadata_version,
                lifecycle_status="ACTIVE",
                valid_from=datetime(2026, 8, 2, tzinfo=timezone.utc),
            )
        )
        await db.flush()

        retried_run = await service.retry_schedule_run(
            user_id=user.id,
            schedule_id=schedule.id,
            failed_run_id=failed_run.id,
        )

    assert retried_run.status == "SUCCEEDED"
    assert retried_run.retry_of_run_id == failed_run.id
    assert retried_run.cutoff_at == failed_run.cutoff_at
    assert retried_run.schedule_config_json == failed_run.schedule_config_json
