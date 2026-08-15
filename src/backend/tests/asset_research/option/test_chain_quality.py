"""Static-arbitrage and executable-liquidity contracts for frozen option chains."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.asset_research.plugins.option.chain import (
    OptionChainQualityPolicy,
    parse_option_chain_quality_policy,
    validate_option_chain,
)
from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    calculate_option_analytics,
)

_CUTOFF = datetime(2026, 8, 1, tzinfo=timezone.utc)
_EXPIRIES = (datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2027, 2, 1, tzinfo=timezone.utc))
_STRIKES = (90.0, 100.0, 110.0)


def _policy() -> OptionChainQualityPolicy:
    return OptionChainQualityPolicy(
        version="fixture-v1",
        min_expiries=2,
        min_strikes_per_expiry=3,
        min_calendar_pairs=2,
        max_quote_age_seconds=60.0,
        max_underlying_lag_seconds=60.0,
        max_relative_spread=0.10,
        min_visible_size=1.0,
        min_volume=1.0,
        min_open_interest=1.0,
        parity_tolerance=0.02,
        static_arbitrage_tolerance=1e-8,
    )


def _time_to_expiry(expiry_at: datetime) -> float:
    return (expiry_at - _CUTOFF).total_seconds() / (365.0 * 24 * 60 * 60)


def _chain() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for expiry_index, expiry_at in enumerate(_EXPIRIES):
        for strike in _STRIKES:
            for option_right in ("CALL", "PUT"):
                analytics = calculate_option_analytics(
                    OptionPricingInput(
                        model="BSM",
                        option_right=option_right,
                        underlying_price=100.0,
                        strike=strike,
                        time_to_expiry_years=_time_to_expiry(expiry_at),
                        risk_free_rate=0.05,
                        dividend_yield=0.0,
                        volatility=0.20 + expiry_index * 0.03,
                    )
                )
                assert analytics.theoretical_value is not None
                records.append(
                    {
                        "expiry_at": expiry_at.isoformat(),
                        "strike": strike,
                        "option_right": option_right,
                        "bid": analytics.theoretical_value * 0.995,
                        "ask": analytics.theoretical_value * 1.005,
                        "bid_size": 100.0,
                        "ask_size": 100.0,
                        "volume": 500.0,
                        "open_interest": 1000.0,
                        "quote_at": _CUTOFF.isoformat(),
                    }
                )
    return records


def _template() -> OptionPricingInput:
    return OptionPricingInput(
        model="BSM",
        option_right="CALL",
        underlying_price=100.0,
        strike=100.0,
        time_to_expiry_years=1.0,
        risk_free_rate=0.05,
        dividend_yield=0.0,
        volatility=None,
    )


def test_chain_policy_parser_requires_every_product_limit() -> None:
    policy, reason = parse_option_chain_quality_policy({"version": "fixture-v1"})

    assert policy is None
    assert reason == "OPTION.CHAIN_POLICY_INVALID"


def test_complete_synchronized_chain_passes_static_arbitrage_and_coverage_checks() -> None:
    result = validate_option_chain(
        records=_chain(),
        pricing_template=_template(),
        cutoff_at=_CUTOFF,
        underlying_quote_at=_CUTOFF,
        target_expiry_at=_EXPIRIES[0],
        target_strike=100.0,
        target_right="CALL",
        policy=_policy(),
    )

    assert result.eligible is True
    assert result.reason_codes == []
    assert result.checks["option_chain_coverage_sufficient"] is True
    assert result.checks["option_chain_static_arbitrage_passed"] is True
    assert result.checks["option_chain_calendar_variance_passed"] is True
    assert result.checks["option_chain_expiry_count"] == 2


def test_chain_rejects_a_provable_put_call_parity_violation() -> None:
    records = _chain()
    for record in records:
        if (
            record["expiry_at"] == _EXPIRIES[0].isoformat()
            and record["strike"] == 100.0
            and record["option_right"] == "CALL"
        ):
            record["bid"] = 40.0
            record["ask"] = 40.1

    result = validate_option_chain(
        records=records,
        pricing_template=_template(),
        cutoff_at=_CUTOFF,
        underlying_quote_at=_CUTOFF,
        target_expiry_at=_EXPIRIES[0],
        target_strike=100.0,
        target_right="CALL",
        policy=_policy(),
    )

    assert result.eligible is False
    assert "OPTION.CHAIN_PUT_CALL_PARITY_VIOLATION" in result.reason_codes


def test_chain_rejects_when_cleaned_coverage_cannot_support_a_surface() -> None:
    result = validate_option_chain(
        records=_chain()[:4],
        pricing_template=_template(),
        cutoff_at=_CUTOFF,
        underlying_quote_at=_CUTOFF,
        target_expiry_at=_EXPIRIES[0],
        target_strike=100.0,
        target_right="CALL",
        policy=_policy(),
    )

    assert result.eligible is False
    assert "OPTION.CHAIN_COVERAGE_INSUFFICIENT" in result.reason_codes


def test_chain_rejects_stale_or_unexecutable_quotes_before_surface_analysis() -> None:
    records = _chain()
    records[0] = {
        **records[0],
        "bid_size": 0.0,
        "quote_at": datetime(2026, 7, 31, tzinfo=timezone.utc).isoformat(),
    }

    result = validate_option_chain(
        records=records,
        pricing_template=_template(),
        cutoff_at=_CUTOFF,
        underlying_quote_at=_CUTOFF,
        target_expiry_at=_EXPIRIES[0],
        target_strike=100.0,
        target_right="CALL",
        policy=_policy(),
    )

    assert result.eligible is False
    assert "OPTION.CHAIN_QUOTE_STALE" in result.reason_codes
    assert "OPTION.CHAIN_DEPTH_INSUFFICIENT" in result.reason_codes
