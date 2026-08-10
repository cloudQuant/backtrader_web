"""Source registry controls license assertions before a plugin sees a snapshot."""

from datetime import datetime, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity, RawAssetSnapshot
from app.services.asset_research.source_registry import AssetSourceRegistryPolicy


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


def _snapshot(provider: str = "fixture-provider") -> RawAssetSnapshot:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return RawAssetSnapshot(
        identity=_identity(),
        cutoff_at=now,
        retrieved_at=now,
        raw_schema_version="fixture-v1",
        raw_fields={"snapshot": {"price": 101}},
        history_rows=[{"date": "2026-08-01", "close": 101}],
        source_manifest={
            "provider": provider,
            "capabilities": ["price", "contract_calendar"],
        },
        license_tags=[],
        content_hash="a" * 64,
    )


@pytest.mark.asyncio
async def test_source_registry_only_grants_active_research_approved_sources() -> None:
    async with async_session_maker() as db:
        db.add(
            AssetDataSourceRegistry(
                source_id="fixture-provider",
                asset_types=["futures"],
                jurisdictions=["GLOBAL"],
                license_status="RESEARCH_APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="research-v1",
                effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                freshness_sla={"max_age_seconds": 86400},
                enabled=True,
            )
        )
        policy = AssetSourceRegistryPolicy(db)
        approved = await policy.authorize(_snapshot())
        missing = await policy.authorize(_snapshot("unregistered-provider"))

    assert approved.source_manifest["license_status"] == "RESEARCH_APPROVED"
    assert approved.source_manifest["source_registry_status"] == "ACTIVE"
    assert approved.source_manifest["capabilities"] == ["price", "contract_calendar"]
    assert missing.source_manifest["license_status"] == "UNKNOWN"
    assert missing.source_manifest["source_registry_status"] == "UNREGISTERED"


@pytest.mark.asyncio
async def test_source_registry_capability_can_be_limited_to_bound_adapter_sources() -> None:
    """An approval for one provider must not authorize a different adapter."""
    async with async_session_maker() as db:
        db.add_all(
            [
                AssetDataSourceRegistry(
                    source_id="bound-futures-source",
                    asset_types=["futures"],
                    jurisdictions=["GLOBAL"],
                    license_status="RESEARCH_APPROVED",
                    allowed_uses=["RESEARCH_ONLY"],
                    redistribution_policy="NO_REDISTRIBUTION",
                    derived_data_policy="ALLOWED",
                    retention_policy="research-v1",
                    effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    freshness_sla={},
                    enabled=True,
                ),
                AssetDataSourceRegistry(
                    source_id="other-fund-source",
                    asset_types=["fund"],
                    jurisdictions=["GLOBAL"],
                    license_status="RESEARCH_APPROVED",
                    allowed_uses=["RESEARCH_ONLY"],
                    redistribution_policy="NO_REDISTRIBUTION",
                    derived_data_policy="ALLOWED",
                    retention_policy="research-v1",
                    effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    freshness_sla={},
                    enabled=True,
                ),
            ]
        )
        policy = AssetSourceRegistryPolicy(db)
        all_enabled = await policy.enabled_asset_types()
        bound_enabled = await policy.enabled_asset_types(source_ids=("bound-futures-source",))

    assert all_enabled == {"futures", "fund"}
    assert bound_enabled == {"futures"}
