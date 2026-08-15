"""Pure basis and carry calculations for a frozen real futures contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FuturesTermStructureInput:
    """Comparable spot and contract facts for one delivery specification."""

    as_of: date
    expiry_date: date
    spot_price: Decimal
    futures_price: Decimal
    quote_unit: str
    spot_quality: str
    futures_quality: str
    spot_location: str
    futures_location: str
    tax_basis: str


@dataclass(frozen=True, slots=True)
class FuturesTermStructure:
    """Basis/carry metrics or a named reason that the contract cannot be compared."""

    basis: Decimal | None
    annualized_carry: Decimal | None
    days_to_expiry: int | None
    reason_code: str | None


def calculate_futures_term_structure(
    term_input: FuturesTermStructureInput,
) -> FuturesTermStructure:
    """Calculate a same-specification contract's absolute basis and annual carry."""
    if term_input.spot_price <= 0 or term_input.futures_price <= 0:
        return _empty_term_structure("FUTURES.PRICE_INPUT_INVALID")
    if not all(
        value.strip()
        for value in (
            term_input.quote_unit,
            term_input.spot_quality,
            term_input.futures_quality,
            term_input.spot_location,
            term_input.futures_location,
            term_input.tax_basis,
        )
    ):
        return _empty_term_structure("FUTURES.BASIS_SPECIFICATION_MISSING")
    if (
        term_input.spot_quality != term_input.futures_quality
        or term_input.spot_location != term_input.futures_location
    ):
        return _empty_term_structure("FUTURES.BASIS_NOT_COMPARABLE")
    days_to_expiry = (term_input.expiry_date - term_input.as_of).days
    if days_to_expiry <= 0:
        return _empty_term_structure("FUTURES.EXPIRY_INVALID")

    basis = term_input.futures_price - term_input.spot_price
    annualized_carry = (
        (term_input.futures_price / term_input.spot_price - Decimal("1"))
        * Decimal(365)
        / Decimal(days_to_expiry)
    )
    return FuturesTermStructure(
        basis=basis,
        annualized_carry=annualized_carry,
        days_to_expiry=days_to_expiry,
        reason_code=None,
    )


def _empty_term_structure(reason_code: str) -> FuturesTermStructure:
    return FuturesTermStructure(
        basis=None,
        annualized_carry=None,
        days_to_expiry=None,
        reason_code=reason_code,
    )
