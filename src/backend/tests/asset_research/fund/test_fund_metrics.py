"""Golden contracts for fund NAV, benchmark and ETF-market metrics."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.asset_research.plugins.fund.metrics import (
    BenchmarkPoint,
    FundMetricsInput,
    FundNavPoint,
    calculate_fund_metrics,
)


def test_fund_metrics_reinvest_distributions_and_keep_the_etf_premium_separate() -> None:
    result = calculate_fund_metrics(
        FundMetricsInput(
            nav_points=(
                FundNavPoint(as_of=date(2026, 1, 1), nav=Decimal("100")),
                FundNavPoint(
                    as_of=date(2026, 1, 2), nav=Decimal("101"), distribution=Decimal("1")
                ),
                FundNavPoint(as_of=date(2026, 1, 3), nav=Decimal("103")),
            ),
            benchmark_points=(
                BenchmarkPoint(as_of=date(2026, 1, 1), level=Decimal("100")),
                BenchmarkPoint(as_of=date(2026, 1, 2), level=Decimal("101")),
                BenchmarkPoint(as_of=date(2026, 1, 3), level=Decimal("102")),
            ),
            official_nav=Decimal("103"),
            market_mid=Decimal("104.03"),
            periods_per_year=252,
        )
    )

    assert result.reason_code is None
    assert float(result.nav_total_return or 0) == pytest.approx((102 / 100) * (103 / 101) - 1)
    assert float(result.benchmark_total_return or 0) == pytest.approx(0.02)
    assert float(result.excess_return or 0) == pytest.approx((102 / 100) * (103 / 101) - 1 - 0.02)
    assert float(result.premium_discount or 0) == pytest.approx(0.01)
    assert result.tracking_error is not None


def test_fund_metrics_return_a_reason_when_official_nav_is_missing_instead_of_zero() -> None:
    result = calculate_fund_metrics(
        FundMetricsInput(
            nav_points=(),
            benchmark_points=(),
            official_nav=None,
            market_mid=None,
            periods_per_year=252,
        )
    )

    assert result.reason_code == "FUND.OFFICIAL_NAV_MISSING"
    assert result.nav_total_return is None
    assert result.premium_discount is None
