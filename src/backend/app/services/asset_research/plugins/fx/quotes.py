"""Quote-convention-safe FX execution return calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FxExecutionInput:
    """Frozen two-sided entry/exit quotes for one base-currency position."""

    base_currency: str
    quote_currency: str
    price_convention: str
    direction: str
    entry_bid: Decimal
    entry_ask: Decimal
    exit_bid: Decimal
    exit_ask: Decimal


@dataclass(frozen=True, slots=True)
class FxExecutionReturn:
    """Canonical quote-per-base execution values or a stable reason code."""

    entry_price: Decimal | None
    entry_price_basis: str | None
    exit_price: Decimal | None
    exit_price_basis: str | None
    gross_return: Decimal | None
    reason_code: str | None


def calculate_fx_execution_return(execution: FxExecutionInput) -> FxExecutionReturn:
    """Calculate a long/short base-currency return under the declared convention.

    Results are normalized to *quote currency per base currency*.  A source
    that reports the reciprocal convention must therefore invert both quote
    sides, not merely invert a midpoint, preserving executable spread costs.
    """
    base = execution.base_currency.strip().upper()
    quote = execution.quote_currency.strip().upper()
    if not base or not quote or base == quote:
        return _empty_execution_return("FX.PAIR_IDENTITY_INVALID")
    if execution.direction not in {"LONG", "SHORT"}:
        return _empty_execution_return("FX.DIRECTION_NOT_ACTIONABLE")
    if not _is_valid_quote(execution.entry_bid, execution.entry_ask) or not _is_valid_quote(
        execution.exit_bid, execution.exit_ask
    ):
        return _empty_execution_return("FX.QUOTE_INCONSISTENT")

    convention = execution.price_convention.strip().upper()
    quote_per_base = f"{quote}_PER_{base}"
    base_per_quote = f"{base}_PER_{quote}"
    if convention == quote_per_base:
        normalized_entry_bid, normalized_entry_ask = execution.entry_bid, execution.entry_ask
        normalized_exit_bid, normalized_exit_ask = execution.exit_bid, execution.exit_ask
        bid_basis, ask_basis = "bid", "ask"
    elif convention == base_per_quote:
        # If source prices are base/quote, the reciprocal executable bid is
        # 1/ask and the reciprocal executable ask is 1/bid.
        normalized_entry_bid = Decimal("1") / execution.entry_ask
        normalized_entry_ask = Decimal("1") / execution.entry_bid
        normalized_exit_bid = Decimal("1") / execution.exit_ask
        normalized_exit_ask = Decimal("1") / execution.exit_bid
        bid_basis, ask_basis = "inverse_ask", "inverse_bid"
    else:
        return _empty_execution_return("FX.PRICE_CONVENTION_UNKNOWN")

    if execution.direction == "LONG":
        entry_price = normalized_entry_ask
        exit_price = normalized_exit_bid
        entry_price_basis, exit_price_basis = ask_basis, bid_basis
        gross_return = exit_price / entry_price - Decimal("1")
    else:
        entry_price = normalized_entry_bid
        exit_price = normalized_exit_ask
        entry_price_basis, exit_price_basis = bid_basis, ask_basis
        gross_return = entry_price / exit_price - Decimal("1")
    return FxExecutionReturn(
        entry_price=entry_price,
        entry_price_basis=entry_price_basis,
        exit_price=exit_price,
        exit_price_basis=exit_price_basis,
        gross_return=gross_return,
        reason_code=None,
    )


def _is_valid_quote(bid: Decimal, ask: Decimal) -> bool:
    return bid > 0 and ask > 0 and bid <= ask


def _empty_execution_return(reason_code: str) -> FxExecutionReturn:
    return FxExecutionReturn(
        entry_price=None,
        entry_price_basis=None,
        exit_price=None,
        exit_price_basis=None,
        gross_return=None,
        reason_code=reason_code,
    )
