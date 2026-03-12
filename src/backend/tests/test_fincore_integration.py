"""
Fincore Integration Tests.

Tests for the integration of FincoreAdapter into the backtest service.
These tests verify that fincore calculations are consistent with
manual calculations within acceptable error bounds.
"""

import numpy as np

from app.services.fincore_metrics_helper import (
    MetricsSource,
    calculate_metrics_from_log_data,
    compare_calculation_methods,
    validate_calculation_consistency,
)


def create_sample_log_data() -> dict:
    """Create sample log data for testing.

    Returns:
        Dictionary with sample equity curve and trades.
    """
    # Create a realistic equity curve
    equity = [
        100000,
        100200,
        100500,
        100100,
        100800,
        101200,
        100900,
        101500,
        102000,
        101800,
        102500,
        103000,
        102700,
        103200,
        103800,
    ]

    # Create sample trades
    trades = [
        {"pnlcomm": 200},
        {"pnlcomm": 300},
        {"pnlcomm": -400},
        {"pnlcomm": 700},
        {"pnlcomm": 400},
        {"pnlcomm": -300},
        {"pnlcomm": 600},
        {"pnlcomm": 500},
        {"pnlcomm": -200},
        {"pnlcomm": 700},
        {"pnlcomm": 500},
        {"pnlcomm": -300},
        {"pnlcomm": 500},
        {"pnlcomm": 600},
    ]

    return {"equity_curve": equity, "trades": trades}


class TestFincoreIntegrationBasic:
    """Tests for basic fincore integration functionality."""

    def test_calculate_metrics_with_fincore_enabled(self):
        """Test metric calculation with fincore enabled."""
        log_data = create_sample_log_data()

        result = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Verify all metrics are calculated
        assert "total_return" in result
        assert "annual_return" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown" in result
        assert "win_rate" in result
        assert "metrics_source" in result

        # Verify source is marked as fincore
        assert result["metrics_source"] == MetricsSource.FINCORE

        # Verify basic metric ranges
        assert -100 <= result["total_return"] <= 1000  # Reasonable return range
        assert -100 <= result["max_drawdown"] <= 0  # Drawdown is negative or zero
        assert 0 <= result["win_rate"] <= 100  # Win rate is percentage

    def test_calculate_metrics_with_fincore_disabled(self):
        """Test metric calculation with fincore disabled (manual)."""
        log_data = create_sample_log_data()

        result = calculate_metrics_from_log_data(log_data, use_fincore=False)

        # Verify source is marked as manual
        assert result["metrics_source"] == MetricsSource.MANUAL

        # Verify all metrics are still calculated
        assert "total_return" in result
        assert "annual_return" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown" in result
        assert "win_rate" in result

    def test_calculate_metrics_empty_data(self):
        """Test metric calculation with empty data."""
        log_data = {"equity_curve": [], "trades": []}

        result_manual = calculate_metrics_from_log_data(log_data, use_fincore=False)
        result_fincore = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Both should return zero values
        assert result_manual["total_return"] == 0.0
        assert result_fincore["total_return"] == 0.0
        assert result_manual["metrics_source"] == MetricsSource.MANUAL
        assert result_fincore["metrics_source"] == MetricsSource.FINCORE


class TestFincoreVsManualConsistency:
    """Tests for consistency between fincore and manual calculations."""

    def test_sharpe_ratio_consistency(self):
        """Test that Sharpe ratio is consistent between methods."""
        log_data = create_sample_log_data()
        comparison = compare_calculation_methods(log_data)

        comparison["manual"]["sharpe_ratio"]
        comparison["fincore"]["sharpe_ratio"]
        rel_error = comparison["relative_errors"]["sharpe_ratio"]

        # Values should be close (within 0.01% as per AC)
        assert rel_error < 0.01, f"Sharpe ratio relative error: {rel_error}%"

    def test_max_drawdown_consistency(self):
        """Test that max drawdown is consistent between methods."""
        log_data = create_sample_log_data()
        comparison = compare_calculation_methods(log_data)

        comparison["manual"]["max_drawdown"]
        comparison["fincore"]["max_drawdown"]
        rel_error = comparison["relative_errors"]["max_drawdown"]

        # Drawdown should be very close (same calculation logic)
        assert rel_error < 0.01, f"Max drawdown relative error: {rel_error}%"

    def test_total_return_consistency(self):
        """Test that total return is consistent between methods."""
        log_data = create_sample_log_data()
        comparison = compare_calculation_methods(log_data)

        comparison["manual"]["total_return"]
        comparison["fincore"]["total_return"]
        rel_error = comparison["relative_errors"]["total_return"]

        # Should be identical (same formula)
        assert rel_error < 0.01, f"Total return relative error: {rel_error}%"

    def test_annual_return_consistency(self):
        """Test that annual return is consistent between methods."""
        log_data = create_sample_log_data()
        comparison = compare_calculation_methods(log_data)

        comparison["manual"]["annual_return"]
        comparison["fincore"]["annual_return"]
        rel_error = comparison["relative_errors"]["annual_return"]

        # Should be very close
        assert rel_error < 0.01, f"Annual return relative error: {rel_error}%"

    def test_win_rate_consistency(self):
        """Test that win rate is consistent between methods."""
        log_data = create_sample_log_data()
        comparison = compare_calculation_methods(log_data)

        comparison["manual"]["win_rate"]
        comparison["fincore"]["win_rate"]
        rel_error = comparison["relative_errors"]["win_rate"]

        # Should be identical (same counting logic)
        assert rel_error < 0.01, f"Win rate relative error: {rel_error}%"

    def test_validate_calculation_consistency_pass(self):
        """Test validation function with consistent data."""
        log_data = create_sample_log_data()

        # Should pass validation with default 0.01% threshold
        assert validate_calculation_consistency(log_data) is True

    def test_validate_calculation_consistency_strict_threshold(self):
        """Test validation with very strict threshold."""
        log_data = create_sample_log_data()

        # Should still pass with even stricter threshold
        assert validate_calculation_consistency(log_data, max_relative_error=0.001) is True


class TestFincoreIntegrationEdgeCases:
    """Tests for edge cases in fincore integration."""

    def test_single_day_equity(self):
        """Test with only one day of equity data."""
        log_data = {"equity_curve": [100000], "trades": []}

        result = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Should handle gracefully
        assert result["total_return"] == 0.0
        assert result["annual_return"] == 0.0
        assert result["sharpe_ratio"] == 0.0

    def test_constant_equity(self):
        """Test with constant equity (no change)."""
        log_data = {"equity_curve": [100000, 100000, 100000, 100000], "trades": []}

        result_manual = calculate_metrics_from_log_data(log_data, use_fincore=False)
        result_fincore = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Both should return 0 for return metrics
        assert result_manual["total_return"] == 0.0
        assert result_fincore["total_return"] == 0.0

    def test_all_winning_trades(self):
        """Test with all winning trades."""
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": 200},
            {"pnlcomm": 150},
        ]
        log_data = {"equity_curve": [100000, 100100, 100300, 100450], "trades": trades}

        result = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Win rate should be 100%
        assert result["win_rate"] == 100.0
        assert result["profitable_trades"] == 3
        assert result["losing_trades"] == 0

    def test_all_losing_trades(self):
        """Test with all losing trades."""
        trades = [
            {"pnlcomm": -100},
            {"pnlcomm": -200},
            {"pnlcomm": -150},
        ]
        log_data = {"equity_curve": [100000, 99900, 99700, 99550], "trades": trades}

        result = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Win rate should be 0%
        assert result["win_rate"] == 0.0
        assert result["profitable_trades"] == 0
        assert result["losing_trades"] == 3

    def test_large_drawdown_scenario(self):
        """Test with large drawdown scenario."""
        # Create equity curve with significant drawdown
        equity = [100000, 105000, 110000, 95000, 85000, 90000]
        log_data = {
            "equity_curve": equity,
            "trades": [
                {"pnlcomm": 5000},
                {"pnlcomm": -15000},
                {"pnlcomm": -10000},
                {"pnlcomm": 5000},
            ],
        }

        comparison = compare_calculation_methods(log_data)

        # Both methods should detect similar drawdown
        manual_dd = comparison["manual"]["max_drawdown"]
        fincore_dd = comparison["fincore"]["max_drawdown"]

        # Peak was 110000, trough was 85000
        # Drawdown = (85000 - 110000) / 110000 = -22.73%
        assert manual_dd < -20  # Significant drawdown
        assert fincore_dd < -20

        # Should be consistent
        rel_error = comparison["relative_errors"]["max_drawdown"]
        assert rel_error < 0.01


class TestFincoreIntegrationRealisticScenarios:
    """Tests with realistic trading scenarios."""

    def test_profitable_strategy(self):
        """Test metrics for a profitable strategy."""
        # Simulate a profitable strategy with some volatility
        equity = [100000, 100500, 101200, 100800, 102500, 103000, 102200, 104000, 105500, 106800]
        trades = [
            {"pnlcomm": 500},
            {"pnlcomm": 700},
            {"pnlcomm": -400},
            {"pnlcomm": 1700},
            {"pnlcomm": 500},
            {"pnlcomm": -800},
            {"pnlcomm": 1800},
            {"pnlcomm": 1500},
            {"pnlcomm": 1300},
        ]

        log_data = {"equity_curve": equity, "trades": trades}
        result = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Verify positive returns
        assert result["total_return"] > 0
        assert result["annual_return"] > 0
        assert result["final_value"] > result["initial_cash"]

        # Verify consistency
        assert validate_calculation_consistency(log_data) is True

    def test_volatile_strategy(self):
        """Test metrics for a highly volatile strategy."""
        # Create volatile equity curve
        equity = [100000, 95000, 108000, 92000, 105000, 98000, 112000, 89000, 103000, 97000]
        trades = [
            {"pnlcomm": -5000},
            {"pnlcomm": 13000},
            {"pnlcomm": -16000},
            {"pnlcomm": 13000},
            {"pnlcomm": -7000},
            {"pnlcomm": 14000},
            {"pnlcomm": -23000},
            {"pnlcomm": 14000},
            {"pnlcomm": -6000},
        ]

        log_data = {"equity_curve": equity, "trades": trades}
        comparison = compare_calculation_methods(log_data)

        # High volatility should result in noticeable drawdown
        assert comparison["manual"]["max_drawdown"] < -10  # At least 10% drawdown

        # Methods should still be consistent
        for metric, error in comparison["relative_errors"].items():
            assert error < 0.01, f"{metric} error: {error}%"

    def test_long_period_strategy(self):
        """Test metrics for a strategy over a long period."""
        # Simulate 252 days (one trading year)
        np.random.seed(42)
        returns = np.random.normal(0.0005, 0.01, 252)  # Daily returns

        equity = [100000]
        for r in returns:
            equity.append(equity[-1] * (1 + r))

        # Generate corresponding trades
        trades = []
        for _i in range(50):
            pnl = np.random.normal(100, 500)
            trades.append({"pnlcomm": pnl})

        log_data = {"equity_curve": equity, "trades": trades}
        result = calculate_metrics_from_log_data(log_data, use_fincore=True)

        # Verify calculations completed
        assert "sharpe_ratio" in result
        assert "annual_return" in result

        # Verify consistency
        assert validate_calculation_consistency(log_data) is True
