"""Golden contracts for deterministic option valuation primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import InstrumentIdentity, OptionIdentityDetails
from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    build_option_pricing_input,
    calculate_option_analytics,
    solve_implied_volatility,
)


def _option_identity(*, exercise_style: str = "EUROPEAN") -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="option",
        identity_level="CONTRACT",
        canonical_id="option:fixture:CALL:2027-08-01:100:USD",
        display_symbol="OPT-C-100",
        name="fixture call",
        venue="FIXTURE",
        currency="USD",
        timezone="UTC",
        identifier_type="FIXTURE",
        identifier_value="OPT-C-100",
        product_type="OPTION",
        metadata_version="fixture-v1",
        details=OptionIdentityDetails(
            option_contract_id="OPT-C-100",
            exchange="FIXTURE",
            underlying_instrument_id="fixture-underlying",
            underlying_contract_id="fixture-underlying",
            expiry_at=datetime(2027, 8, 1, tzinfo=timezone.utc),
            last_trade_at=datetime(2027, 8, 1, tzinfo=timezone.utc),
            strike=Decimal("100"),
            option_right="CALL",
            exercise_style=exercise_style,
            contract_multiplier=Decimal("100"),
            settlement_type="CASH",
            deliverable="100 cash units",
            quote_unit="USD_PER_UNIT",
            tick_size=Decimal("0.01"),
            trading_calendar_id="FIXTURE",
            automatic_exercise_rule="EXERCISE_IF_ITM",
            position_limit_rule="FIXTURE_LIMIT_V1",
            margin_rule_version="FIXTURE_MARGIN_V1",
        ),
    )


def test_pricing_input_builder_uses_only_frozen_contract_and_snapshot_fields() -> None:
    pricing_input, reason = build_option_pricing_input(
        identity=_option_identity(),
        cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_fields={
            "option": {
                "underlying_price": 100.0,
                "underlying_kind": "SPOT",
                "risk_free_rate": 0.05,
                "dividend_yield": 0.0,
            }
        },
    )

    assert reason is None
    assert pricing_input is not None
    assert pricing_input.model == "BSM"
    assert pricing_input.option_right == "CALL"
    assert pricing_input.strike == 100.0
    assert pricing_input.time_to_expiry_years == pytest.approx(1.0)


def test_pricing_input_builder_refuses_to_invent_a_dividend_yield() -> None:
    pricing_input, reason = build_option_pricing_input(
        identity=_option_identity(),
        cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_fields={
            "option": {
                "underlying_price": 100.0,
                "underlying_kind": "SPOT",
                "risk_free_rate": 0.05,
            }
        },
    )

    assert pricing_input is None
    assert reason == "OPTION.DIVIDEND_YIELD_MISSING"


def test_bsm_call_matches_the_standard_at_the_money_golden_values() -> None:
    result = calculate_option_analytics(
        OptionPricingInput(
            model="BSM",
            option_right="CALL",
            underlying_price=100.0,
            strike=100.0,
            time_to_expiry_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
        )
    )

    assert result.reason_code is None
    assert result.theoretical_value == pytest.approx(10.4505835722, abs=1e-8)
    assert result.delta == pytest.approx(0.6368306512, abs=1e-8)
    assert result.gamma == pytest.approx(0.0187620173, abs=1e-8)
    assert result.break_even == pytest.approx(110.4505835722, abs=1e-8)
    assert result.max_loss == pytest.approx(10.4505835722, abs=1e-8)


def test_black_76_matches_the_standard_at_the_money_futures_golden_value() -> None:
    result = calculate_option_analytics(
        OptionPricingInput(
            model="BLACK_76",
            option_right="CALL",
            underlying_price=100.0,
            strike=100.0,
            time_to_expiry_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
        )
    )

    assert result.reason_code is None
    assert result.theoretical_value == pytest.approx(7.5770821464, abs=1e-8)
    assert result.price_lower_bound == pytest.approx(0.0)
    assert result.price_upper_bound == pytest.approx(95.1229424501, abs=1e-8)


def test_american_binomial_put_preserves_early_exercise_value() -> None:
    european_put = calculate_option_analytics(
        OptionPricingInput(
            model="BSM",
            option_right="PUT",
            underlying_price=100.0,
            strike=100.0,
            time_to_expiry_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
        )
    )
    american_put = calculate_option_analytics(
        OptionPricingInput(
            model="AMERICAN_BINOMIAL",
            option_right="PUT",
            underlying_price=100.0,
            strike=100.0,
            time_to_expiry_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            binomial_steps=400,
        )
    )

    assert european_put.reason_code is None
    assert american_put.reason_code is None
    assert american_put.theoretical_value > european_put.theoretical_value
    assert american_put.theoretical_value < 100.0
    assert american_put.delta is not None and american_put.delta < 0


def test_implied_volatility_solver_recovers_a_valid_bsm_input() -> None:
    result = solve_implied_volatility(
        OptionPricingInput(
            model="BSM",
            option_right="CALL",
            underlying_price=100.0,
            strike=100.0,
            time_to_expiry_years=1.0,
            risk_free_rate=0.05,
            volatility=None,
        ),
        observed_price=10.4505835722,
    )

    assert result.reason_code is None
    assert result.implied_volatility == pytest.approx(0.20, abs=1e-6)


def test_solver_refuses_a_price_outside_the_no_arbitrage_bounds() -> None:
    result = solve_implied_volatility(
        OptionPricingInput(
            model="BSM",
            option_right="CALL",
            underlying_price=100.0,
            strike=100.0,
            time_to_expiry_years=1.0,
            risk_free_rate=0.05,
            volatility=None,
        ),
        observed_price=120.0,
    )

    assert result.implied_volatility is None
    assert result.reason_code == "OPTION.PRICE_OUTSIDE_ARBITRAGE_BOUNDS"
