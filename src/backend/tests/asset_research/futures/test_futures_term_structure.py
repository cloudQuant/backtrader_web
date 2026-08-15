"""Golden contracts for comparable futures basis and annualised carry."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.asset_research.plugins.futures.term_structure import (
    FuturesTermStructureInput,
    calculate_futures_term_structure,
)


def test_futures_term_structure_calculates_basis_and_carry_for_comparable_quotes() -> None:
    result = calculate_futures_term_structure(
        FuturesTermStructureInput(
            as_of=date(2026, 1, 1),
            expiry_date=date(2026, 4, 1),
            spot_price=Decimal("100"),
            futures_price=Decimal("102"),
            quote_unit="USD_PER_BARREL",
            spot_quality="WTI_CUSHING",
            futures_quality="WTI_CUSHING",
            spot_location="CUSHING",
            futures_location="CUSHING",
            tax_basis="EX_TAX",
        )
    )

    assert result.reason_code is None
    assert result.days_to_expiry == 90
    assert float(result.basis or 0) == pytest.approx(2.0)
    assert float(result.annualized_carry or 0) == pytest.approx(0.02 * 365 / 90)


def test_futures_term_structure_refuses_to_compare_different_delivery_specifications() -> None:
    result = calculate_futures_term_structure(
        FuturesTermStructureInput(
            as_of=date(2026, 1, 1),
            expiry_date=date(2026, 4, 1),
            spot_price=Decimal("100"),
            futures_price=Decimal("102"),
            quote_unit="USD_PER_BARREL",
            spot_quality="WTI_CUSHING",
            futures_quality="BRENT",
            spot_location="CUSHING",
            futures_location="CUSHING",
            tax_basis="EX_TAX",
        )
    )

    assert result.reason_code == "FUTURES.BASIS_NOT_COMPARABLE"
    assert result.basis is None
    assert result.annualized_carry is None
