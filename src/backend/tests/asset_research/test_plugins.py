"""Asset-specific quality gates must not be flattened into a stock-like score."""

from datetime import datetime, timezone

from app.schemas.asset_research import (
    BondIdentityDetails,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _raw(identity: InstrumentIdentity, *, capabilities: list[str]) -> RawAssetSnapshot:
    return RawAssetSnapshot(
        identity=identity,
        cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_schema_version="test-v1",
        raw_fields={"snapshot": {"price": 100}},
        history_rows=[{"date": "2026-07-31", "close": 99}, {"date": "2026-08-01", "close": 100}],
        source_manifest={"license_status": "APPROVED", "capabilities": capabilities},
        license_tags=["APPROVED"],
        content_hash="a" * 64,
    )


def test_bond_plugin_rejects_a_price_only_source_without_valuation_capabilities() -> None:
    identity = InstrumentIdentity(
        asset_type="bond",
        identity_level="PRODUCT",
        canonical_id="bond:listing:XSHG:019547:CNY",
        display_symbol="019547",
        name="测试债券",
        venue="XSHG",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="LISTING_CODE",
        identifier_value="019547",
        product_type="BOND",
        metadata_version="test-v1",
        details=BondIdentityDetails(bond_identity_kind="LISTING", issuer_id="issuer-1"),
    )

    quality = DEFAULT_ASSET_RESEARCH_REGISTRY.get("bond").assess_quality(
        _raw(identity, capabilities=["price"])
    )

    assert quality.status == "REJECTED"
    assert "BOND.REQUIRED_SOURCE_CAPABILITY_MISSING" in quality.reason_codes


def test_futures_plugin_rejects_a_continuous_series_for_contract_level_research() -> None:
    identity = InstrumentIdentity(
        asset_type="futures",
        identity_level="SERIES",
        canonical_id="futures:CFFEX:IF0:CNY",
        display_symbol="IF0",
        name="沪深300连续",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="SERIES_CODE",
        identifier_value="IF0",
        product_type="FUTURE",
        metadata_version="test-v1",
        details=FuturesIdentityDetails(product_code="IF", trading_calendar_id="CFFEX"),
    )

    quality = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures").assess_quality(
        _raw(identity, capabilities=["price", "contract_calendar"])
    )

    assert quality.status == "REJECTED"
    assert "FUTURES.CONTINUOUS_PRICE_NOT_TRADABLE" in quality.reason_codes
