"""Frozen option-chain validation before a surface or recommendation is emitted.

The validator is intentionally conservative: it does not synthesize a chain
mark, interpolate a missing contract or use a visual surface to repair a bad
quote.  A caller supplies one already-resolved pricing template, one source
cutoff and an explicit product policy.  The returned checks are therefore
safe to persist with the raw snapshot and replay later.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    option_price_bounds,
    solve_implied_volatility,
)

OptionRight = Literal["CALL", "PUT"]


@dataclass(frozen=True, slots=True)
class OptionChainQualityPolicy:
    """Explicit product-level limits for a point-in-time option-chain snapshot."""

    version: str
    min_expiries: int
    min_strikes_per_expiry: int
    min_calendar_pairs: int
    max_quote_age_seconds: float
    max_underlying_lag_seconds: float
    max_relative_spread: float
    min_visible_size: float
    min_volume: float
    min_open_interest: float
    parity_tolerance: float
    static_arbitrage_tolerance: float


@dataclass(frozen=True, slots=True)
class OptionChainQuote:
    """One exact, two-sided contract quote from a frozen chain."""

    expiry_at: datetime
    strike: float
    option_right: OptionRight
    bid: float
    ask: float
    bid_size: float | None
    ask_size: float | None
    volume: float | None
    open_interest: float | None
    quote_at: datetime


@dataclass(frozen=True, slots=True)
class OptionChainQualityResult:
    """Deterministic chain eligibility and an audit-friendly set of checks."""

    eligible: bool
    reason_codes: list[str]
    checks: dict[str, bool | str | int | float | None]


def parse_option_chain_quality_policy(
    value: object,
) -> tuple[OptionChainQualityPolicy | None, str | None]:
    """Parse an explicit source/product policy without introducing defaults."""
    if not isinstance(value, Mapping):
        return None, "OPTION.CHAIN_POLICY_MISSING"
    version = value.get("version")
    if not isinstance(version, str) or not version.strip():
        return None, "OPTION.CHAIN_POLICY_INVALID"
    integers = {
        name: _integer(value.get(name))
        for name in ("min_expiries", "min_strikes_per_expiry", "min_calendar_pairs")
    }
    decimals = {
        name: _number(value.get(name))
        for name in (
            "max_quote_age_seconds",
            "max_underlying_lag_seconds",
            "max_relative_spread",
            "min_visible_size",
            "min_volume",
            "min_open_interest",
            "parity_tolerance",
            "static_arbitrage_tolerance",
        )
    }
    if any(item is None for item in integers.values()) or any(
        item is None for item in decimals.values()
    ):
        return None, "OPTION.CHAIN_POLICY_INVALID"
    policy = OptionChainQualityPolicy(
        version=version,
        min_expiries=integers["min_expiries"] or 0,
        min_strikes_per_expiry=integers["min_strikes_per_expiry"] or 0,
        min_calendar_pairs=integers["min_calendar_pairs"] or 0,
        max_quote_age_seconds=decimals["max_quote_age_seconds"] or 0.0,
        max_underlying_lag_seconds=decimals["max_underlying_lag_seconds"] or 0.0,
        max_relative_spread=decimals["max_relative_spread"] or 0.0,
        min_visible_size=decimals["min_visible_size"] or 0.0,
        min_volume=decimals["min_volume"] or 0.0,
        min_open_interest=decimals["min_open_interest"] or 0.0,
        parity_tolerance=decimals["parity_tolerance"] or 0.0,
        static_arbitrage_tolerance=decimals["static_arbitrage_tolerance"] or 0.0,
    )
    return (
        (policy, None)
        if _validate_policy(policy) is None
        else (None, "OPTION.CHAIN_POLICY_INVALID")
    )


def parse_option_chain_timestamp(value: object) -> datetime | None:
    """Parse a source timestamp, rejecting a naive value at the boundary."""
    return _parse_datetime(value)


def validate_option_chain(
    *,
    records: Iterable[object],
    pricing_template: OptionPricingInput,
    cutoff_at: datetime,
    underlying_quote_at: datetime,
    target_expiry_at: datetime,
    target_strike: float,
    target_right: OptionRight,
    policy: OptionChainQualityPolicy,
) -> OptionChainQualityResult:
    """Validate a normalized exact-contract chain without midpoint substitution.

    Price and IV calculations use bid and ask separately.  A quote midpoint is
    never fed into the IV solver or exposed as an executable value.  Static
    shape tests operate on bid/ask intervals, so a violation means there is a
    provable inconsistency even after allowing the declared tolerances.
    """
    checks: dict[str, bool | str | int | float | None] = {
        "option_chain_policy_version": policy.version,
        "option_chain_record_count": 0,
        "option_chain_valid_record_count": 0,
        "option_chain_expiry_count": 0,
        "option_chain_coverage_sufficient": False,
        "option_target_chain_quote_present": False,
        "option_chain_static_arbitrage_passed": False,
        "option_chain_calendar_variance_passed": False,
    }
    policy_reason = _validate_policy(policy)
    if policy_reason is not None:
        return OptionChainQualityResult(False, [policy_reason], checks)

    normalized_cutoff = _as_utc(cutoff_at)
    normalized_underlying_quote_at = _as_utc(underlying_quote_at)
    parsed_quotes: list[OptionChainQuote] = []
    reasons: list[str] = []
    for record in records:
        quote, reason = _parse_quote(record)
        if quote is None:
            reasons.append(reason or "OPTION.CHAIN_RECORD_INVALID")
            continue
        parsed_quotes.append(quote)
    checks["option_chain_record_count"] = len(parsed_quotes)

    valid_quotes: list[OptionChainQuote] = []
    iv_intervals: dict[tuple[datetime, float, OptionRight], tuple[float, float]] = {}
    for quote in parsed_quotes:
        quote_reasons = _quote_reasons(
            quote=quote,
            cutoff_at=normalized_cutoff,
            underlying_quote_at=normalized_underlying_quote_at,
            policy=policy,
        )
        time_to_expiry_years = (quote.expiry_at - normalized_cutoff).total_seconds() / (
            365.0 * 24 * 60 * 60
        )
        if time_to_expiry_years <= 0:
            quote_reasons.append("OPTION.CHAIN_EXPIRY_NONPOSITIVE")
        else:
            quote_input = replace(
                pricing_template,
                option_right=quote.option_right,
                strike=quote.strike,
                time_to_expiry_years=time_to_expiry_years,
                volatility=None,
            )
            lower_bound, upper_bound, bounds_reason = option_price_bounds(quote_input)
            if bounds_reason is not None:
                quote_reasons.append(bounds_reason)
            elif (
                lower_bound is None
                or upper_bound is None
                or quote.bid < lower_bound - policy.static_arbitrage_tolerance
                or quote.ask > upper_bound + policy.static_arbitrage_tolerance
            ):
                quote_reasons.append("OPTION.CHAIN_PRICE_OUTSIDE_BOUNDS")
            else:
                bid_iv = solve_implied_volatility(quote_input, observed_price=quote.bid)
                ask_iv = solve_implied_volatility(quote_input, observed_price=quote.ask)
                if bid_iv.implied_volatility is None or ask_iv.implied_volatility is None:
                    quote_reasons.append("OPTION.CHAIN_IV_SOLVER_FAILED")
                else:
                    iv_intervals[(quote.expiry_at, quote.strike, quote.option_right)] = (
                        bid_iv.implied_volatility,
                        ask_iv.implied_volatility,
                    )
        if quote_reasons:
            reasons.extend(quote_reasons)
            continue
        valid_quotes.append(quote)

    checks["option_chain_valid_record_count"] = len(valid_quotes)
    normalized_target_expiry_at = _as_utc(target_expiry_at)
    target_present = any(
        quote.expiry_at == normalized_target_expiry_at
        and quote.strike == target_strike
        and quote.option_right == target_right
        for quote in valid_quotes
    )
    checks["option_target_chain_quote_present"] = target_present
    if not target_present:
        reasons.append("OPTION.TARGET_CONTRACT_NOT_IN_CHAIN")
    quotes_by_expiry_right: dict[tuple[datetime, OptionRight], list[OptionChainQuote]] = (
        defaultdict(list)
    )
    quotes_by_expiry_strike: dict[tuple[datetime, float], dict[OptionRight, OptionChainQuote]] = (
        defaultdict(dict)
    )
    for quote in valid_quotes:
        quotes_by_expiry_right[(quote.expiry_at, quote.option_right)].append(quote)
        quotes_by_expiry_strike[(quote.expiry_at, quote.strike)][quote.option_right] = quote

    expiry_strikes: dict[datetime, set[float]] = defaultdict(set)
    for (expiry_at, strike), pair in quotes_by_expiry_strike.items():
        if {"CALL", "PUT"} <= set(pair):
            expiry_strikes[expiry_at].add(strike)
    covered_expiries = [
        expiry_at
        for expiry_at, strikes in expiry_strikes.items()
        if len(strikes) >= policy.min_strikes_per_expiry
    ]
    checks["option_chain_expiry_count"] = len(covered_expiries)
    coverage_sufficient = len(covered_expiries) >= policy.min_expiries
    checks["option_chain_coverage_sufficient"] = coverage_sufficient
    if not coverage_sufficient:
        reasons.append("OPTION.CHAIN_COVERAGE_INSUFFICIENT")

    static_reasons = _static_arbitrage_reasons(
        quotes_by_expiry_right=quotes_by_expiry_right,
        quotes_by_expiry_strike=quotes_by_expiry_strike,
        pricing_template=pricing_template,
        cutoff_at=normalized_cutoff,
        tolerance=policy.static_arbitrage_tolerance,
        parity_tolerance=policy.parity_tolerance,
    )
    reasons.extend(static_reasons)
    checks["option_chain_static_arbitrage_passed"] = not static_reasons

    calendar_reasons, calendar_pair_count = _calendar_variance_reasons(
        iv_intervals=iv_intervals,
        cutoff_at=normalized_cutoff,
        tolerance=policy.static_arbitrage_tolerance,
        min_calendar_pairs=policy.min_calendar_pairs,
    )
    reasons.extend(calendar_reasons)
    checks["option_chain_calendar_pair_count"] = calendar_pair_count
    checks["option_chain_calendar_variance_passed"] = not calendar_reasons
    return OptionChainQualityResult(
        eligible=not reasons,
        reason_codes=list(dict.fromkeys(reasons)),
        checks=checks,
    )


def _validate_policy(policy: OptionChainQualityPolicy) -> str | None:
    if not policy.version.strip():
        return "OPTION.CHAIN_POLICY_INVALID"
    if (
        policy.min_expiries < 2
        or policy.min_strikes_per_expiry < 3
        or policy.min_calendar_pairs < 1
    ):
        return "OPTION.CHAIN_POLICY_INVALID"
    nonnegative = (
        policy.max_quote_age_seconds,
        policy.max_underlying_lag_seconds,
        policy.max_relative_spread,
        policy.min_visible_size,
        policy.min_volume,
        policy.min_open_interest,
        policy.parity_tolerance,
        policy.static_arbitrage_tolerance,
    )
    if any(not math.isfinite(value) or value < 0 for value in nonnegative):
        return "OPTION.CHAIN_POLICY_INVALID"
    if policy.max_relative_spread <= 0:
        return "OPTION.CHAIN_POLICY_INVALID"
    return None


def _parse_quote(record: object) -> tuple[OptionChainQuote | None, str | None]:
    if not isinstance(record, Mapping):
        return None, "OPTION.CHAIN_RECORD_INVALID"
    expiry_at = _parse_datetime(record.get("expiry_at"))
    quote_at = _parse_datetime(record.get("quote_at"))
    strike = _number(record.get("strike"))
    bid = _number(record.get("bid"))
    ask = _number(record.get("ask"))
    option_right = str(record.get("option_right") or "").upper()
    if (
        expiry_at is None
        or quote_at is None
        or strike is None
        or bid is None
        or ask is None
        or option_right not in {"CALL", "PUT"}
    ):
        return None, "OPTION.CHAIN_RECORD_INVALID"
    return (
        OptionChainQuote(
            expiry_at=expiry_at,
            strike=strike,
            option_right=option_right,  # type: ignore[arg-type]
            bid=bid,
            ask=ask,
            bid_size=_number(record.get("bid_size")),
            ask_size=_number(record.get("ask_size")),
            volume=_number(record.get("volume")),
            open_interest=_number(record.get("open_interest")),
            quote_at=quote_at,
        ),
        None,
    )


def _quote_reasons(
    *,
    quote: OptionChainQuote,
    cutoff_at: datetime,
    underlying_quote_at: datetime,
    policy: OptionChainQualityPolicy,
) -> list[str]:
    reasons: list[str] = []
    if quote.strike <= 0 or quote.bid <= 0 or quote.ask <= 0 or quote.bid > quote.ask:
        reasons.append("OPTION.CHAIN_QUOTE_INCONSISTENT")
    quote_age = (cutoff_at - quote.quote_at).total_seconds()
    if quote_age < 0 or quote_age > policy.max_quote_age_seconds:
        reasons.append("OPTION.CHAIN_QUOTE_STALE")
    if (
        abs((quote.quote_at - underlying_quote_at).total_seconds())
        > policy.max_underlying_lag_seconds
    ):
        reasons.append("OPTION.CHAIN_UNDERLYING_DESYNCHRONIZED")
    if quote.bid > 0 and quote.ask > 0:
        relative_spread = (quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2.0)
        if relative_spread > policy.max_relative_spread:
            reasons.append("OPTION.CHAIN_SPREAD_TOO_WIDE")
    if (
        quote.bid_size is None
        or quote.ask_size is None
        or quote.bid_size < policy.min_visible_size
        or quote.ask_size < policy.min_visible_size
    ):
        reasons.append("OPTION.CHAIN_DEPTH_INSUFFICIENT")
    if quote.volume is None or quote.volume < policy.min_volume:
        reasons.append("OPTION.CHAIN_VOLUME_INSUFFICIENT")
    if quote.open_interest is None or quote.open_interest < policy.min_open_interest:
        reasons.append("OPTION.CHAIN_OPEN_INTEREST_INSUFFICIENT")
    return reasons


def _static_arbitrage_reasons(
    *,
    quotes_by_expiry_right: Mapping[tuple[datetime, OptionRight], list[OptionChainQuote]],
    quotes_by_expiry_strike: Mapping[
        tuple[datetime, float], Mapping[OptionRight, OptionChainQuote]
    ],
    pricing_template: OptionPricingInput,
    cutoff_at: datetime,
    tolerance: float,
    parity_tolerance: float,
) -> list[str]:
    reasons: list[str] = []
    for quotes in quotes_by_expiry_right.values():
        ordered = sorted(quotes, key=lambda quote: quote.strike)
        if ordered and ordered[0].option_right == "CALL":
            for lower, upper in zip(ordered, ordered[1:], strict=False):
                if lower.ask + tolerance < upper.bid:
                    reasons.append("OPTION.CHAIN_MONOTONICITY_VIOLATION")
        elif ordered:
            for lower, upper in zip(ordered, ordered[1:], strict=False):
                if lower.bid > upper.ask + tolerance:
                    reasons.append("OPTION.CHAIN_MONOTONICITY_VIOLATION")
        for left, middle, right in zip(ordered, ordered[1:], ordered[2:], strict=False):
            interpolation = (
                (right.strike - middle.strike) * left.ask
                + (middle.strike - left.strike) * right.ask
            ) / (right.strike - left.strike)
            if middle.bid > interpolation + tolerance:
                reasons.append("OPTION.CHAIN_CONVEXITY_VIOLATION")

    if pricing_template.model == "AMERICAN_BINOMIAL":
        return reasons
    for (expiry_at, strike), pair in quotes_by_expiry_strike.items():
        call = pair.get("CALL")
        put = pair.get("PUT")
        if call is None or put is None:
            continue
        time_to_expiry_years = (expiry_at - cutoff_at).total_seconds() / (365.0 * 24 * 60 * 60)
        if time_to_expiry_years <= 0:
            continue
        parity = _put_call_parity(
            pricing_template=pricing_template,
            strike=strike,
            time_to_expiry_years=time_to_expiry_years,
        )
        if call.bid - put.ask > parity + parity_tolerance:
            reasons.append("OPTION.CHAIN_PUT_CALL_PARITY_VIOLATION")
        if call.ask - put.bid < parity - parity_tolerance:
            reasons.append("OPTION.CHAIN_PUT_CALL_PARITY_VIOLATION")
    return list(dict.fromkeys(reasons))


def _put_call_parity(
    *,
    pricing_template: OptionPricingInput,
    strike: float,
    time_to_expiry_years: float,
) -> float:
    discount = math.exp(-pricing_template.risk_free_rate * time_to_expiry_years)
    if pricing_template.model == "BLACK_76":
        return discount * (pricing_template.underlying_price - strike)
    stock_discount = math.exp(-pricing_template.dividend_yield * time_to_expiry_years)
    return pricing_template.underlying_price * stock_discount - strike * discount


def _calendar_variance_reasons(
    *,
    iv_intervals: Mapping[tuple[datetime, float, OptionRight], tuple[float, float]],
    cutoff_at: datetime,
    tolerance: float,
    min_calendar_pairs: int,
) -> tuple[list[str], int]:
    by_strike_right: dict[tuple[float, OptionRight], list[tuple[datetime, float, float]]] = (
        defaultdict(list)
    )
    for (expiry_at, strike, option_right), (bid_iv, ask_iv) in iv_intervals.items():
        by_strike_right[(strike, option_right)].append((expiry_at, bid_iv, ask_iv))
    pair_count = 0
    reasons: list[str] = []
    for values in by_strike_right.values():
        ordered = sorted(values, key=lambda value: value[0])
        for shorter, longer in zip(ordered, ordered[1:], strict=False):
            shorter_expiry, _, shorter_ask = shorter
            longer_expiry, longer_bid, _ = longer
            shorter_time = (shorter_expiry - cutoff_at).total_seconds() / (365.0 * 24 * 60 * 60)
            longer_time = (longer_expiry - cutoff_at).total_seconds() / (365.0 * 24 * 60 * 60)
            pair_count += 1
            if (
                shorter_time <= 0
                or longer_time <= 0
                or longer_bid**2 * longer_time + tolerance < shorter_ask**2 * shorter_time
            ):
                reasons.append("OPTION.CHAIN_CALENDAR_VARIANCE_VIOLATION")
    if pair_count < min_calendar_pairs:
        reasons.append("OPTION.CHAIN_CALENDAR_COVERAGE_INSUFFICIENT")
    return list(dict.fromkeys(reasons)), pair_count


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value) if value.tzinfo is not None else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed) if parsed.tzinfo is not None else None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _integer(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if str(parsed) == str(value).strip() or isinstance(value, int) else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
