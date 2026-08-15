"""Crypto plugin contracts for derived cross-venue market quality."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import (
    CryptoProductIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _snapshot(*, stablecoin_usd_rate: float) -> RawAssetSnapshot:
    return RawAssetSnapshot(
        identity=InstrumentIdentity(
            asset_type="crypto",
            identity_level="PRODUCT",
            canonical_id="crypto:fixture:btc-usdt:spot",
            display_symbol="BTC/USDT",
            name="Fixture BTC/USDT",
            venue="VENUE_A",
            currency="USDT",
            timezone="UTC",
            identifier_type="MARKET",
            identifier_value="BTC/USDT",
            product_type="SPOT",
            metadata_version="fixture-v1",
            details=CryptoProductIdentityDetails(
                base_asset_id="btc",
                quote_asset_id="usdt",
                market_type="SPOT",
                linear_or_inverse="NOT_APPLICABLE",
            ),
        ),
        cutoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={
            "snapshot": {"price": 100.0, "bid": 99.9, "ask": 100.1},
            "crypto": {
                "venue_verified": True,
                "depth_1pct": 1000000.0,
                "quote_asset": "USDT",
                "stablecoin_usd_rate": stablecoin_usd_rate,
                "max_stablecoin_depeg_bps": 100,
                "venue_quotes": [
                    {"venue": "VENUE_A", "bid": 99.9, "ask": 100.1, "depth_1pct": 1000000.0},
                    {"venue": "VENUE_B", "bid": 100.1, "ask": 100.3, "depth_1pct": 3000000.0},
                ],
            },
        },
        history_rows=[
            {"date": "2025-12-31", "close": 99.0},
            {"date": "2026-01-01", "close": 100.0},
        ],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": ["price", "venue"],
        },
        license_tags=["APPROVED"],
        content_hash="e" * 64,
    )


def test_crypto_plugin_derives_composite_price_and_depth_from_frozen_venue_quotes() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("crypto")
    raw_snapshot = _snapshot(stablecoin_usd_rate=1.0)
    eligible = plugin.promote_snapshot(raw_snapshot, plugin.assess_quality(raw_snapshot))

    assert eligible is not None
    features = plugin.compute_features(eligible)

    assert float(Decimal(str(features.values["composite_mid"]))) == pytest.approx(100.15)
    assert features.values["composite_price_venue_count"] == 2.0
    assert float(Decimal(str(features.values["depth_1pct"]))) == pytest.approx(4000000.0)
    assert features.values["crypto_market_quality_reason_code"] is None


def test_crypto_report_details_expose_composite_depth_and_depeg_facts_without_trade_controls() -> (
    None
):
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("crypto")
    raw_snapshot = _snapshot(stablecoin_usd_rate=1.0)
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

    assert float(details.composite_mid or 0) == pytest.approx(100.15)
    assert float(details.depth_1pct or 0) == pytest.approx(4000000.0)
    assert details.composite_price_venue_count == 2
    assert details.market_quality_reason_code is None


def test_crypto_plugin_rejects_a_material_quote_stablecoin_depeg() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("crypto")

    quality = plugin.assess_quality(_snapshot(stablecoin_usd_rate=0.97))

    assert quality.status == "REJECTED"
    assert "CRYPTO.STABLECOIN_DEPEG" in quality.reason_codes
