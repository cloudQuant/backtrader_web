"""Golden contracts for deterministic fixed-rate bond valuation."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.asset_research.plugins.bond.valuation import (
    BondCashflow,
    BondValuationInput,
    calculate_accrued_interest,
    calculate_fixed_rate_bond_analytics,
)


def test_accrued_interest_uses_the_declared_day_count_instead_of_a_zero_default() -> None:
    result = calculate_accrued_interest(
        accrual_start=date(2026, 1, 1),
        settlement_date=date(2026, 3, 2),
        next_coupon_date=date(2027, 1, 1),
        coupon_amount=Decimal("5"),
        day_count="ACT_365F",
    )

    assert result.reason_code is None
    assert float(result.accrued_interest or 0) == pytest.approx(5 * 60 / 365)


def test_zero_coupon_analytics_match_the_closed_form_yield_duration_and_dv01() -> None:
    result = calculate_fixed_rate_bond_analytics(
        BondValuationInput(
            settlement_date=date(2026, 1, 1),
            clean_price=Decimal("100"),
            accrued_interest=Decimal("0"),
            face_value=Decimal("100"),
            coupon_frequency=1,
            day_count="ACT_365F",
            cashflows=(BondCashflow(payment_date=date(2027, 1, 1), amount=Decimal("105")),),
        )
    )

    assert result.reason_code is None
    assert result.dirty_price == Decimal("100")
    assert float(result.yield_to_maturity or 0) == pytest.approx(0.05, abs=1e-10)
    assert float(result.modified_duration or 0) == pytest.approx(1 / 1.05, abs=1e-8)
    assert float(result.dv01 or 0) == pytest.approx((100 / 1.05) * 0.0001, abs=1e-10)


def test_no_future_cashflow_returns_named_missing_metrics_instead_of_zero() -> None:
    result = calculate_fixed_rate_bond_analytics(
        BondValuationInput(
            settlement_date=date(2026, 1, 1),
            clean_price=Decimal("100"),
            accrued_interest=Decimal("0"),
            face_value=Decimal("100"),
            coupon_frequency=1,
            day_count="ACT_365F",
            cashflows=(BondCashflow(payment_date=date(2026, 1, 1), amount=Decimal("105")),),
        )
    )

    assert result.reason_code == "BOND.NO_FUTURE_CASHFLOWS"
    assert result.yield_to_maturity is None
    assert result.modified_duration is None
    assert result.dv01 is None
