"""Fund plugin integration contracts for NAV-derived research metrics."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import FundIdentityDetails, InstrumentIdentity, RawAssetSnapshot
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _snapshot() -> RawAssetSnapshot:
    return RawAssetSnapshot(
        identity=InstrumentIdentity(
            asset_type="fund",
            identity_level="PRODUCT",
            canonical_id="fund:listing:fixture:etf:usd",
            display_symbol="FIXETF",
            name="Fixture ETF",
            venue="FIXTURE",
            currency="USD",
            timezone="UTC",
            identifier_type="LISTING_CODE",
            identifier_value="FIXETF",
            product_type="ETF",
            metadata_version="fixture-v1",
            details=FundIdentityDetails(
                fund_identity_kind="LISTING",
                fund_id="fixture-fund",
                share_class_id="fixture-share-class",
                official_benchmark_id="fixture-benchmark",
            ),
        ),
        cutoff_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={
            "snapshot": {"price": 104.03},
            "fund": {
                "fund_type": "ETF",
                "official_nav": 103.0,
                "benchmark": "FIXTURE_BENCHMARK",
                "fee_schedule": "fixture-fees",
                "holdings_as_of": "2026-01-02",
                "market_mid": 104.03,
                "periods_per_year": 252,
                "nav_series": [
                    {"date": "2026-01-01", "nav": 100.0},
                    {"date": "2026-01-02", "nav": 101.0, "distribution": 1.0},
                    {"date": "2026-01-03", "nav": 103.0},
                ],
                "benchmark_series": [
                    {"date": "2026-01-01", "level": 100.0},
                    {"date": "2026-01-02", "level": 101.0},
                    {"date": "2026-01-03", "level": 102.0},
                ],
            },
        },
        history_rows=[
            {"date": "2026-01-02", "close": 103.0},
            {"date": "2026-01-03", "close": 104.03},
        ],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": ["official_nav", "benchmark"],
        },
        license_tags=["APPROVED"],
        content_hash="c" * 64,
    )


def test_fund_plugin_uses_frozen_nav_and_benchmark_series_instead_of_price_momentum() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("fund")
    raw_snapshot = _snapshot()
    eligible = plugin.promote_snapshot(raw_snapshot, plugin.assess_quality(raw_snapshot))

    assert eligible is not None
    features = plugin.compute_features(eligible)

    expected_total_return = (102 / 100) * (103 / 101) - 1
    assert float(Decimal(str(features.values["fund_return_20"]))) == pytest.approx(
        expected_total_return
    )
    assert float(Decimal(str(features.values["benchmark_return_20"]))) == pytest.approx(0.02)
    assert float(Decimal(str(features.values["excess_return_20"]))) == pytest.approx(
        expected_total_return - 0.02
    )
    assert float(Decimal(str(features.values["nav_premium_discount"]))) == pytest.approx(0.01)
    assert features.values["fund_metrics_reason_code"] is None


def test_fund_report_details_expose_nav_and_benchmark_metrics_without_an_action_alias() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("fund")
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

    assert details.nav_total_return is not None
    assert float(details.benchmark_total_return or 0) == pytest.approx(0.02)
    assert details.excess_return is not None
    assert float(details.nav_premium_discount or 0) == pytest.approx(0.01)
    assert details.metrics_reason_code is None
