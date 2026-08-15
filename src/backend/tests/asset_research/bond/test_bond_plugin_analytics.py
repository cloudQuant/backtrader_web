"""Bond plugin integration contracts for frozen cashflow analytics."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import BondIdentityDetails, InstrumentIdentity, RawAssetSnapshot
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="bond",
        identity_level="PRODUCT",
        canonical_id="bond:listing:fixture:fixed-rate:usd",
        display_symbol="FIXED-2027",
        name="Fixture fixed-rate bond",
        venue="FIXTURE",
        currency="USD",
        timezone="UTC",
        identifier_type="LISTING_CODE",
        identifier_value="fixed-2027",
        product_type="BOND",
        metadata_version="fixture-v1",
        details=BondIdentityDetails(bond_identity_kind="LISTING", issuer_id="fixture-issuer"),
    )


def _snapshot(*, cashflow_date: str = "2027-01-01") -> RawAssetSnapshot:
    return RawAssetSnapshot(
        identity=_identity(),
        cutoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={
            "snapshot": {
                "price": 100.0,
                "official_valuation": 100.0,
                "bid": 99.9,
                "ask": 100.1,
            },
            "bond": {
                "maturity_date": "2027-01-01",
                "curve": "USD_GOVT",
                "benchmark": "USD_AGG",
                "settlement_date": "2026-01-01",
                "clean_price": 100.0,
                "accrued_interest": 0.0,
                "face_value": 100.0,
                "coupon_frequency": 1,
                "day_count": "ACT_365F",
                "cashflows": [{"payment_date": cashflow_date, "amount": 105.0}],
            },
        },
        history_rows=[
            {"date": "2025-12-31", "close": 99.0},
            {"date": "2026-01-01", "close": 100.0},
        ],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": ["price", "official_valuation", "curve", "cashflows"],
        },
        license_tags=["APPROVED"],
        content_hash="b" * 64,
    )


def test_bond_plugin_derives_ytm_duration_and_dv01_from_frozen_cashflows() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("bond")
    raw_snapshot = _snapshot()
    eligible = plugin.promote_snapshot(raw_snapshot, plugin.assess_quality(raw_snapshot))

    assert eligible is not None
    features = plugin.compute_features(eligible)

    assert float(Decimal(str(features.values["yield_to_maturity"]))) == pytest.approx(0.05)
    assert float(Decimal(str(features.values["modified_duration"]))) == pytest.approx(1 / 1.05)
    assert float(Decimal(str(features.values["dv01"]))) == pytest.approx((100 / 1.05) * 0.0001)
    assert features.values["bond_analytics_reason_code"] is None


def test_bond_report_details_expose_the_derived_price_identity_and_convexity() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("bond")
    raw_snapshot = _snapshot()
    quality = plugin.assess_quality(raw_snapshot)
    eligible = plugin.promote_snapshot(raw_snapshot, quality)

    assert eligible is not None
    decision = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="20D",
        snapshot=raw_snapshot,
    )
    details = decision.asset_details

    assert float(details.clean_price or 0) == pytest.approx(100.0)
    assert float(details.accrued_interest or 0) == pytest.approx(0.0)
    assert float(details.dirty_price or 0) == pytest.approx(100.0)
    assert details.convexity is not None
    assert details.valuation_reason_code is None


def test_bond_plugin_keeps_failed_cashflow_analytics_null_with_its_reason() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("bond")
    raw_snapshot = _snapshot(cashflow_date="2026-01-01")
    eligible = plugin.promote_snapshot(raw_snapshot, plugin.assess_quality(raw_snapshot))

    assert eligible is not None
    features = plugin.compute_features(eligible)

    assert features.values["yield_to_maturity"] is None
    assert features.values["modified_duration"] is None
    assert features.values["dv01"] is None
    assert features.values["bond_analytics_reason_code"] == "BOND.NO_FUTURE_CASHFLOWS"
