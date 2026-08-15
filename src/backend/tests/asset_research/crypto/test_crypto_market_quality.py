"""Golden contracts for crypto composite-price and stablecoin quality gates."""

from decimal import Decimal

import pytest

from app.services.asset_research.plugins.crypto.market_quality import (
    CryptoMarketQualityInput,
    CryptoVenueQuote,
    calculate_crypto_market_quality,
)


def test_crypto_market_quality_uses_multiple_independent_venues_for_composite_price() -> None:
    result = calculate_crypto_market_quality(
        CryptoMarketQualityInput(
            quote_asset="USD",
            venue_quotes=(
                CryptoVenueQuote(
                    venue="VENUE_A",
                    bid=Decimal("99.9"),
                    ask=Decimal("100.1"),
                    depth_1pct=Decimal("1000000"),
                ),
                CryptoVenueQuote(
                    venue="VENUE_B",
                    bid=Decimal("100.1"),
                    ask=Decimal("100.3"),
                    depth_1pct=Decimal("3000000"),
                ),
            ),
            stablecoin_usd_rate=None,
            max_stablecoin_depeg_bps=100,
        )
    )

    assert result.reason_code is None
    assert result.venue_count == 2
    assert result.total_depth_1pct == Decimal("4000000")
    assert float(result.composite_mid or 0) == pytest.approx(100.15)
    assert result.stablecoin_depeg_bps is None


def test_crypto_market_quality_blocks_stablecoin_quote_after_a_material_depeg() -> None:
    result = calculate_crypto_market_quality(
        CryptoMarketQualityInput(
            quote_asset="USDT",
            venue_quotes=(
                CryptoVenueQuote(
                    venue="VENUE_A",
                    bid=Decimal("99.9"),
                    ask=Decimal("100.1"),
                    depth_1pct=Decimal("1000000"),
                ),
                CryptoVenueQuote(
                    venue="VENUE_B",
                    bid=Decimal("100.1"),
                    ask=Decimal("100.3"),
                    depth_1pct=Decimal("3000000"),
                ),
            ),
            stablecoin_usd_rate=Decimal("0.97"),
            max_stablecoin_depeg_bps=100,
        )
    )

    assert result.reason_code == "CRYPTO.STABLECOIN_DEPEG"
    assert float(result.stablecoin_depeg_bps or 0) == pytest.approx(300.0)


def test_crypto_market_quality_marks_a_single_venue_as_research_only_evidence() -> None:
    result = calculate_crypto_market_quality(
        CryptoMarketQualityInput(
            quote_asset="USD",
            venue_quotes=(
                CryptoVenueQuote(
                    venue="VENUE_A",
                    bid=Decimal("99.9"),
                    ask=Decimal("100.1"),
                    depth_1pct=Decimal("1000000"),
                ),
            ),
            stablecoin_usd_rate=None,
            max_stablecoin_depeg_bps=100,
        )
    )

    assert result.reason_code == "CRYPTO.SINGLE_VENUE_REFERENCE"
    assert result.composite_mid == Decimal("100.0")
