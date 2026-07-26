"""Regression coverage for the public-Backtrader commission compatibility layer."""

from __future__ import annotations

import pytest

from app.utils.backtrader_commission import ComminfoFuturesInverse, ComminfoFuturesMixed


def test_mixed_futures_commission_uses_contract_roles_and_fixed_margin() -> None:
    """Exchange fee roles must work when only public Backtrader is installed."""
    comminfo = ComminfoFuturesMixed(
        commission=0.000023,
        open_commission=0.000023,
        close_commission=0.00003,
        close_today_commission=0.000345,
        commission_amount=1.2,
        open_commission_amount=1.2,
        close_commission_amount=2.0,
        margin=0.1,
        margin_amount=150000.0,
        mult=300.0,
    )

    assert comminfo.get_margin(5000.0) == pytest.approx(150000.0)
    assert comminfo.getcommission(1, 5000.0, role="open") == pytest.approx(35.7)
    assert comminfo.getcommission(1, 5000.0, role="close") == pytest.approx(47.0)


def test_inverse_futures_commission_uses_fixed_contract_notional() -> None:
    """Inverse products use fixed contract notional for fees, margin, and PnL."""
    comminfo = ComminfoFuturesInverse(
        commission=0.0005,
        maker_commission=-0.0001,
        margin=0.1,
        mult=100.0,
    )

    assert comminfo.getcommission(100, 50000.0) == pytest.approx(5.0)
    assert comminfo.getcommission(100, 50000.0, role="maker") == pytest.approx(-1.0)
    assert comminfo.get_margin(50000.0) == pytest.approx(10.0)
    assert comminfo.profitandloss(100, 50000.0, 55000.0) == pytest.approx(1000.0)
