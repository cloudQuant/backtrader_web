"""Source-level collection limits protect approved upstream providers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity, RawAssetSnapshot
from app.services.asset_research.concurrency import AssetResearchSourceConcurrencyLimiter
from app.services.asset_research.orchestrator import AssetResearchOrchestrator


class _BlockingFuturesData:
    """A deterministic adapter whose active collections can be counted."""

    declared_source_ids = ("source-concurrency-fixture",)

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.first_collection_started = asyncio.Event()
        self.release = asyncio.Event()

    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.first_collection_started.set()
        try:
            await self.release.wait()
        finally:
            self.active -= 1
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={"snapshot": {"price": 101}},
            history_rows=[],
            source_manifest={"source_id": "source-concurrency-fixture"},
            license_tags=[],
            content_hash="a" * 64,
        )


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
async def test_orchestrator_shares_a_bounded_limiter_for_one_declared_source() -> None:
    """Independent request services must not bypass the same provider cap."""
    cutoff_at = datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc)
    data = _BlockingFuturesData()
    limiter = AssetResearchSourceConcurrencyLimiter(max_per_source=1)
    async with async_session_maker() as setup_db:
        setup_db.add(
            AssetDataSourceRegistry(
                source_id="source-concurrency-fixture",
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
        await setup_db.commit()

    async with async_session_maker() as first_db, async_session_maker() as second_db:
        first = AssetResearchOrchestrator(
            first_db,
            data_adapter=data,
            source_limiter=limiter,
        )
        second = AssetResearchOrchestrator(
            second_db,
            data_adapter=data,
            source_limiter=limiter,
        )
        first_task = asyncio.create_task(
            first._collect_authorized_snapshot(_identity(), cutoff_at=cutoff_at)
        )
        await asyncio.wait_for(data.first_collection_started.wait(), timeout=1)
        second_task = asyncio.create_task(
            second._collect_authorized_snapshot(_identity(), cutoff_at=cutoff_at)
        )
        await asyncio.sleep(0.02)
        assert data.max_active == 1
        data.release.set()
        first_snapshot, second_snapshot = await asyncio.gather(first_task, second_task)

    assert first_snapshot.source_manifest["source_registry_status"] == "ACTIVE"
    assert second_snapshot.source_manifest["source_registry_status"] == "ACTIVE"
    assert data.max_active == 1
