"""Pure cross-venue price, depth and stablecoin-reference checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_STABLECOIN_QUOTES = {"USDT", "USDC"}


@dataclass(frozen=True, slots=True)
class CryptoVenueQuote:
    """A frozen, executable two-sided quote from one named venue."""

    venue: str
    bid: Decimal
    ask: Decimal
    depth_1pct: Decimal


@dataclass(frozen=True, slots=True)
class CryptoMarketQualityInput:
    """All facts needed to form a composite reference without assuming a peg."""

    quote_asset: str
    venue_quotes: tuple[CryptoVenueQuote, ...]
    stablecoin_usd_rate: Decimal | None
    max_stablecoin_depeg_bps: int


@dataclass(frozen=True, slots=True)
class CryptoMarketQuality:
    """Composite metrics and the first blocking/degrading quality reason, if any."""

    composite_mid: Decimal | None
    venue_count: int | None
    total_depth_1pct: Decimal | None
    stablecoin_depeg_bps: Decimal | None
    reason_code: str | None


def calculate_crypto_market_quality(
    quality_input: CryptoMarketQualityInput,
) -> CryptoMarketQuality:
    """Calculate a depth-weighted composite and identify unsafe quote conditions."""
    if quality_input.max_stablecoin_depeg_bps < 0:
        return _empty_market_quality("CRYPTO.DEPEG_THRESHOLD_INVALID")
    if not quality_input.venue_quotes:
        return _empty_market_quality("CRYPTO.VENUE_QUOTES_MISSING")

    venues: set[str] = set()
    weighted_mid_sum = Decimal("0")
    total_depth = Decimal("0")
    for venue_quote in quality_input.venue_quotes:
        venue = venue_quote.venue.strip().upper()
        if not venue:
            return _empty_market_quality("CRYPTO.VENUE_UNVERIFIED")
        if venue in venues:
            return _empty_market_quality("CRYPTO.VENUE_DUPLICATE")
        venues.add(venue)
        if (
            venue_quote.bid <= 0
            or venue_quote.ask <= 0
            or venue_quote.bid > venue_quote.ask
            or venue_quote.depth_1pct <= 0
        ):
            return _empty_market_quality("CRYPTO.VENUE_QUOTE_INVALID")
        midpoint = (venue_quote.bid + venue_quote.ask) / Decimal("2")
        weighted_mid_sum += midpoint * venue_quote.depth_1pct
        total_depth += venue_quote.depth_1pct

    composite_mid = weighted_mid_sum / total_depth
    quote_asset = quality_input.quote_asset.strip().upper()
    depeg_bps: Decimal | None = None
    if quote_asset in _STABLECOIN_QUOTES:
        if quality_input.stablecoin_usd_rate is None or quality_input.stablecoin_usd_rate <= 0:
            return CryptoMarketQuality(
                composite_mid=composite_mid,
                venue_count=len(venues),
                total_depth_1pct=total_depth,
                stablecoin_depeg_bps=None,
                reason_code="CRYPTO.STABLECOIN_REFERENCE_MISSING",
            )
        depeg_bps = abs(quality_input.stablecoin_usd_rate - Decimal("1")) * Decimal("10000")
        if depeg_bps > Decimal(quality_input.max_stablecoin_depeg_bps):
            return CryptoMarketQuality(
                composite_mid=composite_mid,
                venue_count=len(venues),
                total_depth_1pct=total_depth,
                stablecoin_depeg_bps=depeg_bps,
                reason_code="CRYPTO.STABLECOIN_DEPEG",
            )
    if len(venues) < 2:
        return CryptoMarketQuality(
            composite_mid=composite_mid,
            venue_count=len(venues),
            total_depth_1pct=total_depth,
            stablecoin_depeg_bps=depeg_bps,
            reason_code="CRYPTO.SINGLE_VENUE_REFERENCE",
        )
    return CryptoMarketQuality(
        composite_mid=composite_mid,
        venue_count=len(venues),
        total_depth_1pct=total_depth,
        stablecoin_depeg_bps=depeg_bps,
        reason_code=None,
    )


def _empty_market_quality(reason_code: str) -> CryptoMarketQuality:
    return CryptoMarketQuality(
        composite_mid=None,
        venue_count=None,
        total_depth_1pct=None,
        stablecoin_depeg_bps=None,
        reason_code=reason_code,
    )
