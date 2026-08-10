"""Pure fixed-rate bond valuation calculations used by the research plugin.

The module deliberately accepts only frozen, already-collected facts.  It has
no database or market-data dependency, and missing or unsupported facts are
represented by a stable reason code instead of a fabricated numeric zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BondCashflow:
    """One contractual payment expressed in the bond's price currency."""

    payment_date: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class BondValuationInput:
    """Frozen facts necessary for a conventional fixed-rate yield calculation."""

    settlement_date: date
    clean_price: Decimal
    accrued_interest: Decimal
    face_value: Decimal
    coupon_frequency: int
    day_count: str
    cashflows: tuple[BondCashflow, ...]


@dataclass(frozen=True, slots=True)
class AccruedInterestResult:
    """Accrued interest or a stable reason why it cannot be calculated."""

    accrued_interest: Decimal | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class BondAnalytics:
    """Value and risk measures derived from one frozen fixed-rate cashflow set."""

    clean_price: Decimal | None
    accrued_interest: Decimal | None
    dirty_price: Decimal | None
    yield_to_maturity: Decimal | None
    modified_duration: Decimal | None
    convexity: Decimal | None
    dv01: Decimal | None
    reason_code: str | None


def calculate_accrued_interest(
    *,
    accrual_start: date,
    settlement_date: date,
    next_coupon_date: date,
    coupon_amount: Decimal,
    day_count: str,
) -> AccruedInterestResult:
    """Calculate accrued interest from named dates and a declared convention.

    ``coupon_amount`` is the annual coupon amount for ACT/365F, ACT/360 and
    30/360 conventions.  For ACT/ACT ICMA it is the contractual coupon for
    the supplied accrual period.  The explicit convention prevents a missing
    value from silently becoming a zero coupon accrual.
    """
    if coupon_amount < 0:
        return AccruedInterestResult(None, "BOND.COUPON_AMOUNT_INVALID")
    if accrual_start >= next_coupon_date:
        return AccruedInterestResult(None, "BOND.COUPON_PERIOD_INVALID")
    if settlement_date < accrual_start or settlement_date > next_coupon_date:
        return AccruedInterestResult(None, "BOND.SETTLEMENT_OUTSIDE_ACCRUAL_PERIOD")

    normalized_day_count = _normalize_day_count(day_count)
    if normalized_day_count is None:
        return AccruedInterestResult(None, "BOND.DAY_COUNT_UNSUPPORTED")

    if normalized_day_count == "ACT_ACT_ICMA":
        period_days = (next_coupon_date - accrual_start).days
        if period_days <= 0:
            return AccruedInterestResult(None, "BOND.COUPON_PERIOD_INVALID")
        fraction = Decimal((settlement_date - accrual_start).days) / Decimal(period_days)
    else:
        fraction = _year_fraction(
            start=accrual_start,
            end=settlement_date,
            day_count=normalized_day_count,
        )
    return AccruedInterestResult(coupon_amount * fraction, None)


def calculate_fixed_rate_bond_analytics(valuation: BondValuationInput) -> BondAnalytics:
    """Solve fixed-rate YTM, duration, convexity and DV01 from frozen cashflows.

    Yield is an annual nominal rate compounded ``coupon_frequency`` times per
    year.  The result is suitable for research metrics only; instruments with
    embedded options, irregular contractual conventions or incomplete terms
    must remain on their specialised model path.
    """
    if valuation.clean_price < 0 or valuation.accrued_interest < 0:
        return _empty_analytics(valuation, "BOND.PRICE_INPUT_INVALID")
    if valuation.face_value <= 0:
        return _empty_analytics(valuation, "BOND.FACE_VALUE_INVALID")
    if valuation.coupon_frequency <= 0:
        return _empty_analytics(valuation, "BOND.COUPON_FREQUENCY_INVALID")
    normalized_day_count = _normalize_day_count(valuation.day_count)
    if normalized_day_count is None:
        return _empty_analytics(valuation, "BOND.DAY_COUNT_UNSUPPORTED")

    dirty_price = valuation.clean_price + valuation.accrued_interest
    if dirty_price <= 0:
        return _empty_analytics(valuation, "BOND.PRICE_INPUT_INVALID")

    cashflows = tuple(
        cashflow
        for cashflow in valuation.cashflows
        if cashflow.payment_date > valuation.settlement_date
    )
    if not cashflows:
        return _empty_analytics(valuation, "BOND.NO_FUTURE_CASHFLOWS", dirty_price=dirty_price)
    if any(cashflow.amount <= 0 for cashflow in cashflows):
        return _empty_analytics(valuation, "BOND.CASHFLOW_INVALID", dirty_price=dirty_price)

    times = tuple(
        float(
            _year_fraction(
                start=valuation.settlement_date,
                end=cashflow.payment_date,
                day_count=normalized_day_count,
            )
        )
        for cashflow in cashflows
    )
    if any(time <= 0 or not math.isfinite(time) for time in times):
        return _empty_analytics(valuation, "BOND.CASHFLOW_TIME_INVALID", dirty_price=dirty_price)

    cashflow_amounts = tuple(float(cashflow.amount) for cashflow in cashflows)
    solved_yield = _solve_yield(
        dirty_price=float(dirty_price),
        cashflow_amounts=cashflow_amounts,
        times=times,
        coupon_frequency=valuation.coupon_frequency,
    )
    if solved_yield is None:
        return _empty_analytics(valuation, "BOND.YIELD_SOLVER_FAILED", dirty_price=dirty_price)

    base = 1.0 + solved_yield / valuation.coupon_frequency
    present_values = tuple(
        amount / (base ** (valuation.coupon_frequency * time))
        for amount, time in zip(cashflow_amounts, times, strict=True)
    )
    price = sum(present_values)
    if price <= 0 or not math.isfinite(price):
        return _empty_analytics(valuation, "BOND.YIELD_SOLVER_FAILED", dirty_price=dirty_price)

    macaulay_duration = sum(
        time * present_value for time, present_value in zip(times, present_values, strict=True)
    ) / price
    modified_duration = macaulay_duration / base
    convexity = sum(
        time
        * (time + 1.0 / valuation.coupon_frequency)
        * present_value
        / (base**2)
        for time, present_value in zip(times, present_values, strict=True)
    ) / price
    dv01 = modified_duration * float(dirty_price) * 0.0001

    if not all(
        math.isfinite(value)
        for value in (solved_yield, modified_duration, convexity, dv01)
    ):
        return _empty_analytics(valuation, "BOND.YIELD_SOLVER_FAILED", dirty_price=dirty_price)

    return BondAnalytics(
        clean_price=valuation.clean_price,
        accrued_interest=valuation.accrued_interest,
        dirty_price=dirty_price,
        yield_to_maturity=_decimal(solved_yield),
        modified_duration=_decimal(modified_duration),
        convexity=_decimal(convexity),
        dv01=_decimal(dv01),
        reason_code=None,
    )


def _empty_analytics(
    valuation: BondValuationInput,
    reason_code: str,
    *,
    dirty_price: Decimal | None = None,
) -> BondAnalytics:
    return BondAnalytics(
        clean_price=valuation.clean_price,
        accrued_interest=valuation.accrued_interest,
        dirty_price=dirty_price,
        yield_to_maturity=None,
        modified_duration=None,
        convexity=None,
        dv01=None,
        reason_code=reason_code,
    )


def _solve_yield(
    *,
    dirty_price: float,
    cashflow_amounts: tuple[float, ...],
    times: tuple[float, ...],
    coupon_frequency: int,
) -> float | None:
    """Use monotonic bisection so failed prices return a reason, never a guess."""
    if dirty_price <= 0 or not math.isfinite(dirty_price):
        return None

    def present_value(yield_rate: float) -> float:
        base = 1.0 + yield_rate / coupon_frequency
        if base <= 0:
            return math.inf
        return sum(
            amount / (base ** (coupon_frequency * time))
            for amount, time in zip(cashflow_amounts, times, strict=True)
        )

    lower = -coupon_frequency + 1e-12
    upper = 1.0
    lower_price = present_value(lower)
    upper_price = present_value(upper)
    while upper_price > dirty_price and upper < 1_000.0:
        upper *= 2.0
        upper_price = present_value(upper)
    if lower_price < dirty_price or upper_price > dirty_price:
        return None

    for _ in range(160):
        midpoint = (lower + upper) / 2.0
        midpoint_price = present_value(midpoint)
        if abs(midpoint_price - dirty_price) <= 1e-12:
            return midpoint
        if midpoint_price > dirty_price:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _normalize_day_count(day_count: str) -> str | None:
    normalized = day_count.strip().upper().replace("-", "_").replace("/", "_")
    aliases = {
        "ACT_365F": "ACT_365F",
        "ACTUAL_365F": "ACT_365F",
        "ACT_360": "ACT_360",
        "ACTUAL_360": "ACT_360",
        "30_360": "30_360_US",
        "30_360_US": "30_360_US",
        "ACT_ACT_ICMA": "ACT_ACT_ICMA",
        "ACTUAL_ACTUAL_ICMA": "ACT_ACT_ICMA",
    }
    return aliases.get(normalized)


def _year_fraction(*, start: date, end: date, day_count: str) -> Decimal:
    if end < start:
        raise ValueError("end date must not precede start date")
    if day_count == "ACT_365F":
        return Decimal((end - start).days) / Decimal(365)
    if day_count == "ACT_360":
        return Decimal((end - start).days) / Decimal(360)
    if day_count == "30_360_US":
        start_day = min(start.day, 30)
        end_day = 30 if end.day == 31 and start_day == 30 else end.day
        days = 360 * (end.year - start.year) + 30 * (end.month - start.month) + end_day - start_day
        return Decimal(days) / Decimal(360)
    if day_count == "ACT_ACT_ICMA":
        return Decimal((end - start).days) / Decimal(365)
    raise ValueError(f"unsupported day count: {day_count}")


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))
