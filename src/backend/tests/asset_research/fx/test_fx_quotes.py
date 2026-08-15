"""Golden contracts for FX quote convention and executable side handling."""

from decimal import Decimal

import pytest

from app.services.asset_research.plugins.fx.quotes import (
    FxExecutionInput,
    calculate_fx_execution_return,
)


def test_fx_long_uses_ask_to_bid_when_the_quote_is_quote_currency_per_base() -> None:
    result = calculate_fx_execution_return(
        FxExecutionInput(
            base_currency="EUR",
            quote_currency="USD",
            price_convention="USD_PER_EUR",
            direction="LONG",
            entry_bid=Decimal("1.1000"),
            entry_ask=Decimal("1.1002"),
            exit_bid=Decimal("1.1098"),
            exit_ask=Decimal("1.1100"),
        )
    )

    assert result.reason_code is None
    assert result.entry_price == Decimal("1.1002")
    assert result.exit_price == Decimal("1.1098")
    assert float(result.gross_return or 0) == pytest.approx(1.1098 / 1.1002 - 1)


def test_fx_long_inverts_bid_ask_sides_when_source_reports_base_per_quote() -> None:
    result = calculate_fx_execution_return(
        FxExecutionInput(
            base_currency="EUR",
            quote_currency="USD",
            price_convention="EUR_PER_USD",
            direction="LONG",
            entry_bid=Decimal("0.9090"),
            entry_ask=Decimal("0.9092"),
            exit_bid=Decimal("0.9010"),
            exit_ask=Decimal("0.9012"),
        )
    )

    assert result.reason_code is None
    assert result.entry_price == Decimal("1") / Decimal("0.9090")
    assert result.exit_price == Decimal("1") / Decimal("0.9012")
    assert float(result.gross_return or 0) == pytest.approx(0.9090 / 0.9012 - 1)


def test_fx_short_uses_the_reciprocal_ask_then_bid_when_source_reports_base_per_quote() -> None:
    result = calculate_fx_execution_return(
        FxExecutionInput(
            base_currency="EUR",
            quote_currency="USD",
            price_convention="EUR_PER_USD",
            direction="SHORT",
            entry_bid=Decimal("0.9090"),
            entry_ask=Decimal("0.9092"),
            exit_bid=Decimal("0.9010"),
            exit_ask=Decimal("0.9012"),
        )
    )

    assert result.reason_code is None
    assert result.entry_price == Decimal("1") / Decimal("0.9092")
    assert result.entry_price_basis == "inverse_ask"
    assert result.exit_price == Decimal("1") / Decimal("0.9010")
    assert result.exit_price_basis == "inverse_bid"
    assert float(result.gross_return or 0) == pytest.approx(0.9010 / 0.9092 - 1)


def test_fx_return_refuses_an_unrelated_or_crossed_quote_convention() -> None:
    result = calculate_fx_execution_return(
        FxExecutionInput(
            base_currency="EUR",
            quote_currency="USD",
            price_convention="JPY_PER_USD",
            direction="LONG",
            entry_bid=Decimal("1.1000"),
            entry_ask=Decimal("1.1002"),
            exit_bid=Decimal("1.1098"),
            exit_ask=Decimal("1.1100"),
        )
    )

    assert result.reason_code == "FX.PRICE_CONVENTION_UNKNOWN"
    assert result.gross_return is None
