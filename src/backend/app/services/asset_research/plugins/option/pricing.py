"""Versioned option valuation primitives used before research publication.

The module intentionally has no provider or persistence dependency.  It only
prices an already-resolved exact contract from a frozen input envelope, so a
provider cannot silently replace a contract, time-to-expiry or pricing model.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.schemas.asset_research import InstrumentIdentity, OptionIdentityDetails

OptionPricingModel = Literal["BSM", "BLACK_76", "AMERICAN_BINOMIAL"]
OptionRight = Literal["CALL", "PUT"]


@dataclass(frozen=True, slots=True)
class OptionPricingInput:
    """One fully specified valuation point in contract premium units."""

    model: OptionPricingModel
    option_right: OptionRight
    underlying_price: float
    strike: float
    time_to_expiry_years: float
    risk_free_rate: float
    volatility: float | None
    dividend_yield: float = 0.0
    binomial_steps: int = 200


@dataclass(frozen=True, slots=True)
class OptionAnalytics:
    """Theoretical price, risk and no-arbitrage bounds for one long option."""

    model: OptionPricingModel
    theoretical_value: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None
    break_even: float | None
    max_loss: float | None
    price_lower_bound: float | None
    price_upper_bound: float | None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ImpliedVolatilityResult:
    """A conservative implied-volatility solver result for one observed premium."""

    implied_volatility: float | None
    price_lower_bound: float | None
    price_upper_bound: float | None
    reason_code: str | None = None


def build_option_pricing_input(
    *,
    identity: InstrumentIdentity,
    cutoff_at: datetime,
    raw_fields: Mapping[str, Any],
) -> tuple[OptionPricingInput | None, str | None]:
    """Build a valuation envelope from one exact contract and frozen facts.

    The function deliberately refuses to default a rate, dividend, expiry,
    underlying kind or price.  Both publication-time analytics and outcome
    scoring call the same builder so neither path can reinterpret a contract
    with a live input or a provider-supplied IV field.
    """
    if identity.asset_type != "option" or identity.identity_level != "CONTRACT":
        return None, "OPTION.CONTRACT_IDENTITY_REQUIRED"
    details = identity.details
    if not isinstance(details, OptionIdentityDetails):
        return None, "OPTION.CONTRACT_IDENTITY_REQUIRED"

    expiry_at = details.expiry_at
    normalized_cutoff = cutoff_at
    if expiry_at.tzinfo is None and normalized_cutoff.tzinfo is None:
        return None, "OPTION.TIMEZONE_MISSING"
    if expiry_at.tzinfo is None:
        expiry_at = expiry_at.replace(tzinfo=normalized_cutoff.tzinfo)
    if normalized_cutoff.tzinfo is None:
        normalized_cutoff = normalized_cutoff.replace(tzinfo=expiry_at.tzinfo)
    time_to_expiry_years = (expiry_at - normalized_cutoff).total_seconds() / (365.0 * 24 * 60 * 60)
    if time_to_expiry_years <= 0:
        return None, "OPTION.TIME_TO_EXPIRY_NONPOSITIVE"

    option = _mapping(raw_fields.get("option"))
    underlying = _mapping(raw_fields.get("underlying"))
    underlying_price = _first_number(
        option.get("underlying_price"),
        option.get("underlying_mid"),
        underlying.get("price"),
        underlying.get("mid"),
    )
    risk_free_rate = _first_number(option.get("risk_free_rate"), option.get("interest_rate"))
    if underlying_price is None or underlying_price <= 0:
        return None, "OPTION.UNDERLYING_PRICE_MISSING"
    if risk_free_rate is None:
        return None, "OPTION.RISK_FREE_RATE_MISSING"

    exercise_style = details.exercise_style
    underlying_kind = str(
        option.get("underlying_kind") or option.get("underlying_type") or ""
    ).upper()
    if exercise_style == "AMERICAN":
        if underlying_kind not in {"SPOT", "EQUITY", "ETF", "INDEX"}:
            return None, "OPTION.AMERICAN_UNDERLYING_MODEL_UNSUPPORTED"
        model: OptionPricingModel = "AMERICAN_BINOMIAL"
    elif exercise_style == "EUROPEAN":
        if underlying_kind in {"FUTURE", "FUTURES"}:
            model = "BLACK_76"
        elif underlying_kind in {"SPOT", "EQUITY", "ETF", "INDEX"}:
            model = "BSM"
        else:
            return None, "OPTION.UNDERLYING_PRICING_KIND_MISSING"
    else:
        return None, "OPTION.EXERCISE_STYLE_UNSUPPORTED"

    dividend_yield = _number(option.get("dividend_yield"))
    if model != "BLACK_76" and dividend_yield is None:
        return None, "OPTION.DIVIDEND_YIELD_MISSING"
    binomial_steps, binomial_steps_reason = _binomial_steps(option.get("binomial_steps"))
    if binomial_steps_reason is not None:
        return None, binomial_steps_reason
    return (
        OptionPricingInput(
            model=model,
            option_right=details.option_right,
            underlying_price=underlying_price,
            strike=float(details.strike),
            time_to_expiry_years=time_to_expiry_years,
            risk_free_rate=risk_free_rate,
            volatility=None,
            dividend_yield=dividend_yield if dividend_yield is not None else 0.0,
            binomial_steps=binomial_steps,
        ),
        None,
    )


def calculate_option_analytics(inputs: OptionPricingInput) -> OptionAnalytics:
    """Price an exact option and compute Greeks without inventing missing inputs."""
    lower_bound, upper_bound, bound_reason = option_price_bounds(inputs)
    validation_reason = _validate_inputs(inputs, require_volatility=True)
    if validation_reason is not None:
        return _failed_analytics(inputs.model, lower_bound, upper_bound, validation_reason)
    if bound_reason is not None:
        return _failed_analytics(inputs.model, lower_bound, upper_bound, bound_reason)

    try:
        theoretical_value = _price(inputs)
        if inputs.model == "BSM":
            delta, gamma, theta, vega, rho = _bsm_greeks(inputs)
        else:
            delta, gamma, theta, vega, rho = _finite_difference_greeks(inputs, theoretical_value)
    except ValueError as exc:
        return _failed_analytics(inputs.model, lower_bound, upper_bound, str(exc))

    break_even = (
        inputs.strike + theoretical_value
        if inputs.option_right == "CALL"
        else max(inputs.strike - theoretical_value, 0.0)
    )
    return OptionAnalytics(
        model=inputs.model,
        theoretical_value=theoretical_value,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        break_even=break_even,
        max_loss=theoretical_value,
        price_lower_bound=lower_bound,
        price_upper_bound=upper_bound,
    )


def option_price_bounds(
    inputs: OptionPricingInput,
) -> tuple[float | None, float | None, str | None]:
    """Return contract premium bounds before an IV solver attempts convergence."""
    validation_reason = _validate_inputs(inputs, require_volatility=False)
    if validation_reason is not None:
        return None, None, validation_reason

    time_to_expiry = inputs.time_to_expiry_years
    discount = math.exp(-inputs.risk_free_rate * time_to_expiry)
    if inputs.model == "BLACK_76":
        forward = inputs.underlying_price
        if inputs.option_right == "CALL":
            return discount * max(forward - inputs.strike, 0.0), discount * forward, None
        return discount * max(inputs.strike - forward, 0.0), discount * inputs.strike, None

    if inputs.model == "AMERICAN_BINOMIAL":
        if inputs.option_right == "CALL":
            return max(inputs.underlying_price - inputs.strike, 0.0), inputs.underlying_price, None
        return max(inputs.strike - inputs.underlying_price, 0.0), inputs.strike, None

    stock_discount = math.exp(-inputs.dividend_yield * time_to_expiry)
    if inputs.option_right == "CALL":
        return (
            max(inputs.underlying_price * stock_discount - inputs.strike * discount, 0.0),
            inputs.underlying_price * stock_discount,
            None,
        )
    return (
        max(inputs.strike * discount - inputs.underlying_price * stock_discount, 0.0),
        inputs.strike * discount,
        None,
    )


def solve_implied_volatility(
    inputs: OptionPricingInput,
    *,
    observed_price: float,
    tolerance: float = 1e-8,
    max_iterations: int = 100,
) -> ImpliedVolatilityResult:
    """Solve IV by bisection only when the observed premium is arbitrage-valid."""
    lower_bound, upper_bound, bound_reason = option_price_bounds(inputs)
    if bound_reason is not None:
        return ImpliedVolatilityResult(None, lower_bound, upper_bound, bound_reason)
    if not _finite(observed_price) or observed_price < 0:
        return ImpliedVolatilityResult(
            None, lower_bound, upper_bound, "OPTION.OBSERVED_PRICE_INVALID"
        )
    if lower_bound is None or upper_bound is None:
        return ImpliedVolatilityResult(
            None, lower_bound, upper_bound, "OPTION.PRICING_INPUT_INVALID"
        )
    if observed_price < lower_bound - tolerance or observed_price > upper_bound + tolerance:
        return ImpliedVolatilityResult(
            None, lower_bound, upper_bound, "OPTION.PRICE_OUTSIDE_ARBITRAGE_BOUNDS"
        )
    if observed_price <= lower_bound + tolerance:
        return ImpliedVolatilityResult(
            None, lower_bound, upper_bound, "OPTION.IMPLIED_VOLATILITY_UNDEFINED_AT_BOUND"
        )

    lower_volatility = 1e-6
    upper_volatility = 5.0
    try:
        lower_price = _price(replace(inputs, volatility=lower_volatility))
        upper_price = _price(replace(inputs, volatility=upper_volatility))
        while upper_price < observed_price and upper_volatility < 16.0:
            upper_volatility *= 2.0
            upper_price = _price(replace(inputs, volatility=upper_volatility))
    except ValueError as exc:
        return ImpliedVolatilityResult(None, lower_bound, upper_bound, str(exc))

    if observed_price < lower_price - tolerance or observed_price > upper_price + tolerance:
        return ImpliedVolatilityResult(
            None, lower_bound, upper_bound, "OPTION.IMPLIED_VOLATILITY_NOT_CONVERGED"
        )

    for _ in range(max_iterations):
        midpoint = (lower_volatility + upper_volatility) / 2.0
        try:
            midpoint_price = _price(replace(inputs, volatility=midpoint))
        except ValueError as exc:
            return ImpliedVolatilityResult(None, lower_bound, upper_bound, str(exc))
        if abs(midpoint_price - observed_price) <= tolerance:
            return ImpliedVolatilityResult(midpoint, lower_bound, upper_bound)
        if midpoint_price < observed_price:
            lower_volatility = midpoint
        else:
            upper_volatility = midpoint

    return ImpliedVolatilityResult(
        (lower_volatility + upper_volatility) / 2.0,
        lower_bound,
        upper_bound,
        "OPTION.IMPLIED_VOLATILITY_NOT_CONVERGED",
    )


def _failed_analytics(
    model: OptionPricingModel,
    lower_bound: float | None,
    upper_bound: float | None,
    reason_code: str,
) -> OptionAnalytics:
    return OptionAnalytics(
        model=model,
        theoretical_value=None,
        delta=None,
        gamma=None,
        theta=None,
        vega=None,
        rho=None,
        break_even=None,
        max_loss=None,
        price_lower_bound=lower_bound,
        price_upper_bound=upper_bound,
        reason_code=reason_code,
    )


def _validate_inputs(inputs: OptionPricingInput, *, require_volatility: bool) -> str | None:
    numeric_inputs = (
        inputs.underlying_price,
        inputs.strike,
        inputs.time_to_expiry_years,
        inputs.risk_free_rate,
        inputs.dividend_yield,
    )
    if not all(_finite(value) for value in numeric_inputs):
        return "OPTION.PRICING_INPUT_INVALID"
    if inputs.underlying_price <= 0 or inputs.strike <= 0:
        return "OPTION.PRICING_INPUT_INVALID"
    if inputs.time_to_expiry_years <= 0:
        return "OPTION.TIME_TO_EXPIRY_NONPOSITIVE"
    if inputs.model == "AMERICAN_BINOMIAL" and inputs.binomial_steps < 2:
        return "OPTION.BINOMIAL_STEPS_INVALID"
    if require_volatility:
        if inputs.volatility is None:
            return "OPTION.VOLATILITY_MISSING"
        if not _finite(inputs.volatility) or inputs.volatility <= 0:
            return "OPTION.VOLATILITY_INVALID"
    return None


def _price(inputs: OptionPricingInput) -> float:
    validation_reason = _validate_inputs(inputs, require_volatility=True)
    if validation_reason is not None:
        raise ValueError(validation_reason)
    if inputs.model == "BSM":
        return _bsm_price(inputs)
    if inputs.model == "BLACK_76":
        return _black_76_price(inputs)
    return _american_binomial_price(inputs)


def _require_valid_volatility(inputs: OptionPricingInput) -> float:
    """Return a validated volatility or preserve a typed pricing failure."""
    volatility = inputs.volatility
    if volatility is None:
        raise ValueError("OPTION.VOLATILITY_MISSING")
    if not _finite(volatility) or volatility <= 0:
        raise ValueError("OPTION.VOLATILITY_INVALID")
    return volatility


def _bsm_price(inputs: OptionPricingInput) -> float:
    volatility = _require_valid_volatility(inputs)
    volatility_sqrt_time = volatility * math.sqrt(inputs.time_to_expiry_years)
    d1 = (
        math.log(inputs.underlying_price / inputs.strike)
        + (inputs.risk_free_rate - inputs.dividend_yield + 0.5 * volatility**2)
        * inputs.time_to_expiry_years
    ) / volatility_sqrt_time
    d2 = d1 - volatility_sqrt_time
    stock_discount = math.exp(-inputs.dividend_yield * inputs.time_to_expiry_years)
    strike_discount = math.exp(-inputs.risk_free_rate * inputs.time_to_expiry_years)
    if inputs.option_right == "CALL":
        return inputs.underlying_price * stock_discount * _normal_cdf(
            d1
        ) - inputs.strike * strike_discount * _normal_cdf(d2)
    return inputs.strike * strike_discount * _normal_cdf(
        -d2
    ) - inputs.underlying_price * stock_discount * _normal_cdf(-d1)


def _black_76_price(inputs: OptionPricingInput) -> float:
    volatility = _require_valid_volatility(inputs)
    volatility_sqrt_time = volatility * math.sqrt(inputs.time_to_expiry_years)
    d1 = (
        math.log(inputs.underlying_price / inputs.strike)
        + 0.5 * volatility**2 * inputs.time_to_expiry_years
    ) / volatility_sqrt_time
    d2 = d1 - volatility_sqrt_time
    discount = math.exp(-inputs.risk_free_rate * inputs.time_to_expiry_years)
    if inputs.option_right == "CALL":
        return discount * (
            inputs.underlying_price * _normal_cdf(d1) - inputs.strike * _normal_cdf(d2)
        )
    return discount * (
        inputs.strike * _normal_cdf(-d2) - inputs.underlying_price * _normal_cdf(-d1)
    )


def _american_binomial_price(inputs: OptionPricingInput) -> float:
    volatility = _require_valid_volatility(inputs)
    steps = inputs.binomial_steps
    dt = inputs.time_to_expiry_years / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    growth = math.exp((inputs.risk_free_rate - inputs.dividend_yield) * dt)
    probability = (growth - down) / (up - down)
    if probability < 0.0 or probability > 1.0:
        raise ValueError("OPTION.BINOMIAL_PROBABILITY_INVALID")
    discount = math.exp(-inputs.risk_free_rate * dt)
    values = [
        _intrinsic_value(inputs, inputs.underlying_price * up ** (steps - index) * down**index)
        for index in range(steps + 1)
    ]
    for step in range(steps - 1, -1, -1):
        for index in range(step + 1):
            continuation = discount * (
                probability * values[index] + (1.0 - probability) * values[index + 1]
            )
            spot = inputs.underlying_price * up ** (step - index) * down**index
            values[index] = max(continuation, _intrinsic_value(inputs, spot))
    return values[0]


def _bsm_greeks(inputs: OptionPricingInput) -> tuple[float, float, float, float, float]:
    volatility = _require_valid_volatility(inputs)
    sqrt_time = math.sqrt(inputs.time_to_expiry_years)
    volatility_sqrt_time = volatility * sqrt_time
    d1 = (
        math.log(inputs.underlying_price / inputs.strike)
        + (inputs.risk_free_rate - inputs.dividend_yield + 0.5 * volatility**2)
        * inputs.time_to_expiry_years
    ) / volatility_sqrt_time
    d2 = d1 - volatility_sqrt_time
    stock_discount = math.exp(-inputs.dividend_yield * inputs.time_to_expiry_years)
    strike_discount = math.exp(-inputs.risk_free_rate * inputs.time_to_expiry_years)
    density = _normal_density(d1)
    gamma = stock_discount * density / (inputs.underlying_price * volatility_sqrt_time)
    vega = inputs.underlying_price * stock_discount * density * sqrt_time
    common_theta = (
        -inputs.underlying_price * stock_discount * density * volatility / (2.0 * sqrt_time)
    )
    if inputs.option_right == "CALL":
        delta = stock_discount * _normal_cdf(d1)
        theta = (
            common_theta
            - inputs.risk_free_rate * inputs.strike * strike_discount * _normal_cdf(d2)
            + inputs.dividend_yield * inputs.underlying_price * stock_discount * _normal_cdf(d1)
        )
        rho = inputs.strike * inputs.time_to_expiry_years * strike_discount * _normal_cdf(d2)
    else:
        delta = stock_discount * (_normal_cdf(d1) - 1.0)
        theta = (
            common_theta
            + inputs.risk_free_rate * inputs.strike * strike_discount * _normal_cdf(-d2)
            - inputs.dividend_yield * inputs.underlying_price * stock_discount * _normal_cdf(-d1)
        )
        rho = -inputs.strike * inputs.time_to_expiry_years * strike_discount * _normal_cdf(-d2)
    return delta, gamma, theta, vega, rho


def _finite_difference_greeks(
    inputs: OptionPricingInput, base_price: float
) -> tuple[float, float, float, float, float]:
    volatility = _require_valid_volatility(inputs)
    price_bump = max(inputs.underlying_price * 1e-4, 1e-4)
    upper_price = _price(replace(inputs, underlying_price=inputs.underlying_price + price_bump))
    lower_underlying = max(inputs.underlying_price - price_bump, price_bump)
    lower_price = _price(replace(inputs, underlying_price=lower_underlying))
    delta = (upper_price - lower_price) / (inputs.underlying_price + price_bump - lower_underlying)
    gamma = (upper_price - 2.0 * base_price + lower_price) / price_bump**2

    volatility_bump = min(1e-4, volatility / 2.0)
    upper_vega = _price(replace(inputs, volatility=volatility + volatility_bump))
    lower_vega = _price(replace(inputs, volatility=volatility - volatility_bump))
    vega = (upper_vega - lower_vega) / (2.0 * volatility_bump)

    time_bump = min(1.0 / 365.0, inputs.time_to_expiry_years / 2.0)
    theta = (
        _price(replace(inputs, time_to_expiry_years=inputs.time_to_expiry_years - time_bump))
        - base_price
    ) / time_bump

    rate_bump = 1e-4
    rho = (
        _price(replace(inputs, risk_free_rate=inputs.risk_free_rate + rate_bump))
        - _price(replace(inputs, risk_free_rate=inputs.risk_free_rate - rate_bump))
    ) / (2.0 * rate_bump)
    return delta, gamma, theta, vega, rho


def _intrinsic_value(inputs: OptionPricingInput, spot: float) -> float:
    if inputs.option_right == "CALL":
        return max(spot - inputs.strike, 0.0)
    return max(inputs.strike - spot, 0.0)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_density(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(*values: object) -> float | None:
    for value in values:
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _binomial_steps(value: object) -> tuple[int, str | None]:
    if value is None:
        return 200, None
    if isinstance(value, bool):
        return 0, "OPTION.BINOMIAL_STEPS_INVALID"
    if not isinstance(value, (str, int, Decimal)):
        return 0, "OPTION.BINOMIAL_STEPS_INVALID"
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0, "OPTION.BINOMIAL_STEPS_INVALID"
    if parsed < 2:
        return 0, "OPTION.BINOMIAL_STEPS_INVALID"
    return parsed, None


def _finite(value: float) -> bool:
    return math.isfinite(value)
