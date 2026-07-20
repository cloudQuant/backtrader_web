"""Canonical metrics service tests."""

from app.services.metrics_service import MetricsService


def test_metrics_normalize_calculates_canonical_profit_loss_ratio_once():
    result = MetricsService().normalize(
        {"total_return": "5", "total_trades": "2", "initial_cash": 100000},
        trades=[{"pnl": 200}, {"pnl": -100}],
    )

    assert result["total_return"] == 5
    assert result["total_trades"] == 2
    assert result["profit_loss_ratio"] == 2
    assert result["final_value"] == 100000


def test_metrics_normalize_is_safe_for_empty_trades_and_non_finite_values():
    result = MetricsService().normalize(
        {"sharpe_ratio": float("nan"), "max_drawdown": float("inf")}, trades=[]
    )

    assert result["sharpe_ratio"] == 0
    assert result["max_drawdown"] == 0
    assert result["total_trades"] == 0
    assert result["profit_loss_ratio"] == 0
