"""Tests for fincore_metrics_helper - financial metric calculations."""

from app.services.backtest.analyzers import FincoreAdapter
from app.services.fincore_metrics_helper import (
    MetricsSource,
    _calculate_annual_return,
    _calculate_max_drawdown,
    _calculate_sharpe_ratio,
    _calculate_total_return,
    _calculate_win_rate,
    calculate_extended_metrics,
    calculate_metrics_from_log_data,
    compare_calculation_methods,
    validate_calculation_consistency,
)


class TestMetricsSource:
    """Test MetricsSource constants."""

    def test_manual_value(self):
        assert MetricsSource.MANUAL == "manual"

    def test_fincore_value(self):
        assert MetricsSource.FINCORE == "fincore"


class TestCalculateTotalReturn:
    """Test total return calculation."""

    def test_empty_equity(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_total_return(adapter, []) == 0.0

    def test_single_value(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_total_return(adapter, [100000.0]) == 0.0

    def test_positive_return(self):
        adapter = FincoreAdapter(use_fincore=False)
        equity = [100000.0, 110000.0]
        result = _calculate_total_return(adapter, equity)
        assert abs(result - 10.0) < 0.01  # 10% return

    def test_negative_return(self):
        adapter = FincoreAdapter(use_fincore=False)
        equity = [100000.0, 90000.0]
        result = _calculate_total_return(adapter, equity)
        assert result < 0


class TestCalculateAnnualReturn:
    """Test annualized return calculation."""

    def test_empty_equity(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_annual_return(adapter, []) == 0.0

    def test_single_value(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_annual_return(adapter, [100000.0]) == 0.0

    def test_positive_annual_return(self):
        adapter = FincoreAdapter(use_fincore=False)
        # Simulate 252 trading days with ~10% total return
        equity = [100000.0 + i * 40 for i in range(253)]  # ~10% over a year
        result = _calculate_annual_return(adapter, equity)
        assert result > 0


class TestCalculateSharpeRatio:
    """Test Sharpe ratio calculation."""

    def test_empty_equity(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_sharpe_ratio(adapter, []) == 0.0

    def test_single_value(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_sharpe_ratio(adapter, [100000.0]) == 0.0

    def test_constant_equity_sharpe(self):
        adapter = FincoreAdapter(use_fincore=False)
        equity = [100000.0] * 100
        result = _calculate_sharpe_ratio(adapter, equity)
        # With zero returns, sharpe calculation may produce extreme values
        # due to zero std dev - just verify it returns a number
        assert isinstance(result, float)

    def test_varying_equity_sharpe(self):
        adapter = FincoreAdapter(use_fincore=False)
        # Equity with some variance
        import random

        random.seed(42)
        equity = [100000.0]
        for _ in range(99):
            equity.append(equity[-1] * (1 + random.uniform(-0.01, 0.02)))
        result = _calculate_sharpe_ratio(adapter, equity)
        # Just verify it returns a finite number
        assert isinstance(result, float)


class TestCalculateMaxDrawdown:
    """Test maximum drawdown calculation."""

    def test_empty_equity(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_max_drawdown(adapter, []) == 0.0

    def test_single_value(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_max_drawdown(adapter, [100000.0]) == 0.0

    def test_no_drawdown(self):
        adapter = FincoreAdapter(use_fincore=False)
        equity = [100000.0, 110000.0, 120000.0]
        result = _calculate_max_drawdown(adapter, equity)
        assert result == 0.0 or abs(result) < 0.01

    def test_drawdown_present(self):
        adapter = FincoreAdapter(use_fincore=False)
        equity = [100000.0, 110000.0, 90000.0, 95000.0]
        result = _calculate_max_drawdown(adapter, equity)
        # Drawdown from 110000 to 90000 = ~18.18%
        assert result < 0  # Drawdown is negative


class TestCalculateWinRate:
    """Test win rate calculation."""

    def test_empty_trades(self):
        adapter = FincoreAdapter(use_fincore=False)
        assert _calculate_win_rate(adapter, []) == 0.0

    def test_all_winning(self):
        adapter = FincoreAdapter(use_fincore=False)
        trades = [{"pnlcomm": 100}, {"pnlcomm": 200}, {"pnlcomm": 50}]
        result = _calculate_win_rate(adapter, trades)
        assert result == 100.0

    def test_all_losing(self):
        adapter = FincoreAdapter(use_fincore=False)
        trades = [{"pnlcomm": -100}, {"pnlcomm": -200}]
        result = _calculate_win_rate(adapter, trades)
        assert result == 0.0

    def test_mixed_trades(self):
        adapter = FincoreAdapter(use_fincore=False)
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": -50},
            {"pnlcomm": 200},
            {"pnlcomm": -30},
        ]
        result = _calculate_win_rate(adapter, trades)
        assert result == 50.0  # 2 out of 4


class TestCalculateMetricsFromLogData:
    """Test the main metrics calculation function."""

    def test_empty_log_data(self):
        result = calculate_metrics_from_log_data({})
        assert result["total_return"] == 0.0
        assert result["total_trades"] == 0
        assert result["metrics_source"] == MetricsSource.MANUAL
        assert result["initial_cash"] == 100000.0

    def test_basic_log_data(self):
        log_data = {
            "equity_curve": [100000.0, 105000.0, 110000.0],
            "trades": [
                {"pnlcomm": 5000},
                {"pnlcomm": 5000},
            ],
        }
        result = calculate_metrics_from_log_data(log_data)
        assert result["total_return"] > 0
        assert result["total_trades"] == 2
        assert result["profitable_trades"] == 2
        assert result["losing_trades"] == 0
        assert result["initial_cash"] == 100000.0
        assert result["final_value"] == 110000.0

    def test_with_losing_trades(self):
        log_data = {
            "equity_curve": [100000.0, 95000.0],
            "trades": [
                {"pnlcomm": -3000},
                {"pnlcomm": -2000},
            ],
        }
        result = calculate_metrics_from_log_data(log_data)
        assert result["total_return"] < 0
        assert result["profitable_trades"] == 0
        assert result["losing_trades"] == 2

    def test_use_fincore_flag_without_fincore(self):
        """When fincore is not installed, falls back to manual."""
        log_data = {
            "equity_curve": [100000.0, 110000.0],
            "trades": [],
        }
        result = calculate_metrics_from_log_data(log_data, use_fincore=True)
        # Should still work regardless of fincore availability
        assert result["total_return"] > 0
        assert result["metrics_source"] in (MetricsSource.MANUAL, MetricsSource.FINCORE)


class TestCalculateExtendedMetrics:
    """Test extended metrics calculation."""

    def test_empty_data(self):
        result = calculate_extended_metrics({})
        assert result["total_trades"] == 0
        assert result["net_value"] == 1.0
        assert result["net_profit"] == 0.0
        assert result["trading_days"] == 0

    def test_basic_extended_metrics(self):
        log_data = {
            "equity_curve": [100000.0, 102000.0, 101000.0, 105000.0],
            "trades": [
                {"pnlcomm": 2000, "commission": 10},
                {"pnlcomm": -1000, "commission": 10},
                {"pnlcomm": 4000, "commission": 10},
            ],
            "dates": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        }
        result = calculate_extended_metrics(log_data)
        assert result["total_trades"] == 3
        assert result["profitable_trades"] == 2
        assert result["losing_trades"] == 1
        assert result["net_profit"] == 5000.0
        assert result["net_value"] > 1.0
        assert result["total_win_amount"] == 6000.0
        assert result["total_loss_amount"] == 1000.0
        assert result["profit_factor"] == 6.0
        assert result["trading_cost"] == 30.0
        assert result["trading_days"] == 4

    def test_initial_cash_override(self):
        log_data = {
            "equity_curve": [50000.0, 55000.0],
            "trades": [{"pnlcomm": 5000}],
        }
        result = calculate_extended_metrics(log_data, initial_cash=50000.0)
        assert result["initial_cash"] == 50000.0
        assert result["net_profit"] == 5000.0

    def test_max_drawdown_value(self):
        log_data = {
            "equity_curve": [100000.0, 110000.0, 95000.0, 100000.0],
            "trades": [],
        }
        result = calculate_extended_metrics(log_data)
        # Max drawdown from 110000 to 95000 = 15000
        assert result["max_drawdown_value"] == 15000.0

    def test_daily_return_stats(self):
        log_data = {
            "equity_curve": [100000.0, 101000.0, 99000.0, 102000.0],
            "trades": [],
        }
        result = calculate_extended_metrics(log_data)
        assert result["daily_avg_return"] is not None
        assert result["daily_max_loss"] < 0
        assert result["daily_max_profit"] > 0

    def test_profit_loss_ratio(self):
        log_data = {
            "equity_curve": [100000.0, 110000.0],
            "trades": [
                {"pnlcomm": 3000},
                {"pnlcomm": -1000},
            ],
        }
        result = calculate_extended_metrics(log_data)
        # avg_win = 3000, avg_loss = 1000, ratio = 3.0
        assert result["profit_loss_ratio"] == 3.0


class TestCompareCalculationMethods:
    """Test comparison between calculation methods."""

    def test_comparison_structure(self):
        log_data = {
            "equity_curve": [100000.0, 105000.0, 110000.0],
            "trades": [{"pnlcomm": 5000}, {"pnlcomm": 5000}],
        }
        result = compare_calculation_methods(log_data)
        assert "manual" in result
        assert "fincore" in result
        assert "differences" in result
        assert "relative_errors" in result

    def test_comparison_keys(self):
        log_data = {
            "equity_curve": [100000.0, 110000.0],
            "trades": [{"pnlcomm": 10000}],
        }
        result = compare_calculation_methods(log_data)
        for key in ["total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate"]:
            assert key in result["differences"]
            assert key in result["relative_errors"]


class TestValidateCalculationConsistency:
    """Test calculation consistency validation."""

    def test_consistent_calculations(self):
        log_data = {
            "equity_curve": [100000.0, 105000.0, 110000.0],
            "trades": [{"pnlcomm": 5000}, {"pnlcomm": 5000}],
        }
        # Since both use the same underlying formulas, should be consistent
        result = validate_calculation_consistency(log_data)
        assert result is True

    def test_empty_data_consistent(self):
        result = validate_calculation_consistency({})
        assert result is True
