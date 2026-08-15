"""Pure NAV and ETF-market calculations for fund research.

These helpers only consume frozen official NAV, benchmark and market facts.
They intentionally do not substitute an indicative NAV or an equity-price
proxy when the corresponding fund input is unavailable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FundNavPoint:
    """One official end-of-period NAV and its paid per-share distribution."""

    as_of: date
    nav: Decimal
    distribution: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class BenchmarkPoint:
    """One official benchmark total-return level on the same valuation date."""

    as_of: date
    level: Decimal


@dataclass(frozen=True, slots=True)
class FundMetricsInput:
    """Frozen inputs for one share class and one official benchmark."""

    nav_points: tuple[FundNavPoint, ...]
    benchmark_points: tuple[BenchmarkPoint, ...]
    official_nav: Decimal | None
    market_mid: Decimal | None
    periods_per_year: int


@dataclass(frozen=True, slots=True)
class FundMetrics:
    """Returns and structural ETF metrics, or a stable missing-input reason."""

    nav_total_return: Decimal | None
    benchmark_total_return: Decimal | None
    excess_return: Decimal | None
    tracking_error: Decimal | None
    premium_discount: Decimal | None
    reason_code: str | None


def calculate_fund_metrics(metrics_input: FundMetricsInput) -> FundMetrics:
    """Calculate distribution-reinvested NAV return and aligned benchmark metrics."""
    if metrics_input.official_nav is None or metrics_input.official_nav <= 0:
        return _empty_metrics("FUND.OFFICIAL_NAV_MISSING")
    if metrics_input.periods_per_year <= 0:
        return _empty_metrics("FUND.PERIOD_FREQUENCY_INVALID")
    if len(metrics_input.nav_points) < 2:
        return _empty_metrics("FUND.NAV_HISTORY_INSUFFICIENT")
    if len(metrics_input.benchmark_points) < 2:
        return _empty_metrics("COMMON.BENCHMARK_MISSING")
    if not _strictly_increasing(point.as_of for point in metrics_input.nav_points):
        return _empty_metrics("FUND.NAV_SERIES_INVALID")
    if not _strictly_increasing(point.as_of for point in metrics_input.benchmark_points):
        return _empty_metrics("FUND.BENCHMARK_SERIES_INVALID")
    if tuple(point.as_of for point in metrics_input.nav_points) != tuple(
        point.as_of for point in metrics_input.benchmark_points
    ):
        return _empty_metrics("FUND.BENCHMARK_ALIGNMENT_MISSING")
    if any(point.nav <= 0 or point.distribution < 0 for point in metrics_input.nav_points):
        return _empty_metrics("FUND.NAV_SERIES_INVALID")
    if any(point.level <= 0 for point in metrics_input.benchmark_points):
        return _empty_metrics("FUND.BENCHMARK_SERIES_INVALID")
    if metrics_input.market_mid is not None and metrics_input.market_mid <= 0:
        return _empty_metrics("FUND.MARKET_PRICE_INVALID")

    nav_period_returns = tuple(
        (current.nav + current.distribution) / previous.nav - Decimal("1")
        for previous, current in zip(
            metrics_input.nav_points, metrics_input.nav_points[1:], strict=False
        )
    )
    benchmark_period_returns = tuple(
        current.level / previous.level - Decimal("1")
        for previous, current in zip(
            metrics_input.benchmark_points, metrics_input.benchmark_points[1:], strict=False
        )
    )
    nav_growth = math.prod(
        float(Decimal("1") + period_return) for period_return in nav_period_returns
    )
    benchmark_growth = math.prod(
        float(Decimal("1") + period_return) for period_return in benchmark_period_returns
    )
    if not math.isfinite(nav_growth) or not math.isfinite(benchmark_growth):
        return _empty_metrics("FUND.RETURN_CALCULATION_FAILED")

    nav_total_return = Decimal(str(nav_growth - 1.0))
    benchmark_total_return = Decimal(str(benchmark_growth - 1.0))
    excess_returns = tuple(
        float(nav_return - benchmark_return)
        for nav_return, benchmark_return in zip(
            nav_period_returns, benchmark_period_returns, strict=True
        )
    )
    tracking_error = _annualized_sample_standard_deviation(
        excess_returns, periods_per_year=metrics_input.periods_per_year
    )
    premium_discount = (
        metrics_input.market_mid / metrics_input.official_nav - Decimal("1")
        if metrics_input.market_mid is not None
        else None
    )
    return FundMetrics(
        nav_total_return=nav_total_return,
        benchmark_total_return=benchmark_total_return,
        excess_return=nav_total_return - benchmark_total_return,
        tracking_error=tracking_error,
        premium_discount=premium_discount,
        reason_code=None,
    )


def _empty_metrics(reason_code: str) -> FundMetrics:
    return FundMetrics(
        nav_total_return=None,
        benchmark_total_return=None,
        excess_return=None,
        tracking_error=None,
        premium_discount=None,
        reason_code=reason_code,
    )


def _strictly_increasing(dates: Iterable[date]) -> bool:
    values = tuple(dates)
    return all(previous < current for previous, current in zip(values, values[1:], strict=False))


def _annualized_sample_standard_deviation(
    values: tuple[float, ...], *, periods_per_year: int
) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    annualized = math.sqrt(variance * periods_per_year)
    return Decimal(str(annualized)) if math.isfinite(annualized) else None
