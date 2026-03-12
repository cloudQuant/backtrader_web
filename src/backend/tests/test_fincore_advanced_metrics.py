"""
Advanced metrics tests for fincore integration.

Tests for advanced analytics metrics using FincoreAdapter including:
- Profit factor calculation
- Average holding period calculation
- Maximum consecutive wins/losses calculation
- Maximum drawdown with duration calculation
- Integration with AnalyticsService
"""

import pytest

from app.services.backtest_analyzers import FincoreAdapter


class TestProfitFactor:
    """Tests for profit factor calculation."""

    def test_profit_factor_positive(self):
        """Test profit factor with profitable trades."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},  # Win
            {"pnlcomm": 200},  # Win
            {"pnlcomm": -50},  # Loss
            {"pnlcomm": 150},  # Win
            {"pnlcomm": -75},  # Loss
        ]
        result = adapter.calculate_profit_factor(trades)

        # Avg win = (100+200+150)/3 = 150
        # Avg loss = (50+75)/2 = 62.5
        # Profit factor = 150/62.5 = 2.4
        assert result > 0
        assert result == pytest.approx(2.4, rel=1e-6)

    def test_profit_factor_all_wins(self):
        """Test profit factor with all winning trades."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": 200},
            {"pnlcomm": 150},
        ]
        result = adapter.calculate_profit_factor(trades)

        # No losses, should return 0
        assert result == 0.0

    def test_profit_factor_all_losses(self):
        """Test profit factor with all losing trades."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": -100},
            {"pnlcomm": -200},
            {"pnlcomm": -150},
        ]
        result = adapter.calculate_profit_factor(trades)

        # No wins, should return 0
        assert result == 0.0

    def test_profit_factor_empty_trades(self):
        """Test profit factor with no trades."""
        adapter = FincoreAdapter()
        result = adapter.calculate_profit_factor([])

        assert result == 0.0


class TestAvgHoldingPeriod:
    """Tests for average holding period calculation."""

    def test_avg_holding_period_normal(self):
        """Test average holding period with normal data."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100, "barlen": 5},
            {"pnlcomm": -50, "barlen": 10},
            {"pnlcomm": 200, "barlen": 15},
            {"pnlcomm": -75, "barlen": 3},
        ]
        result = adapter.calculate_avg_holding_period(trades)

        # Avg = (5+10+15+3)/4 = 8.25
        assert result == pytest.approx(8.25, rel=1e-6)

    def test_avg_holding_period_missing_barlen(self):
        """Test average holding period with missing barlen."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100, "barlen": 5},
            {"pnlcomm": -50},  # No barlen
            {"pnlcomm": 200, "barlen": 15},
        ]
        result = adapter.calculate_avg_holding_period(trades)

        # Avg = (5+15)/2 = 10
        assert result == pytest.approx(10.0, rel=1e-6)

    def test_avg_holding_period_empty_trades(self):
        """Test average holding period with no trades."""
        adapter = FincoreAdapter()
        result = adapter.calculate_avg_holding_period([])

        assert result == 0.0


class TestMaxConsecutive:
    """Tests for maximum consecutive wins/losses calculation."""

    def test_max_consecutive_wins(self):
        """Test maximum consecutive wins."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},  # Win 1
            {"pnlcomm": 200},  # Win 2
            {"pnlcomm": 150},  # Win 3 (max)
            {"pnlcomm": -50},  # Loss
            {"pnlcomm": 75},  # Win 1
            {"pnlcomm": 125},  # Win 2
        ]
        result = adapter.calculate_max_consecutive(trades, win=True)

        assert result == 3

    def test_max_consecutive_losses(self):
        """Test maximum consecutive losses."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": -50},  # Loss 1
            {"pnlcomm": -100},  # Loss 2
            {"pnlcomm": -75},  # Loss 3 (max)
            {"pnlcomm": 200},  # Win
            {"pnlcomm": -25},  # Loss 1
            {"pnlcomm": -50},  # Loss 2
        ]
        result = adapter.calculate_max_consecutive(trades, win=False)

        assert result == 3

    def test_max_consecutive_empty_trades(self):
        """Test maximum consecutive with no trades."""
        adapter = FincoreAdapter()
        result_wins = adapter.calculate_max_consecutive([], win=True)
        result_losses = adapter.calculate_max_consecutive([], win=False)

        assert result_wins == 0
        assert result_losses == 0


class TestMaxDrawdownWithDuration:
    """Tests for maximum drawdown with duration calculation."""

    def test_max_drawdown_with_duration_simple(self):
        """Test max drawdown with simple decline."""
        adapter = FincoreAdapter()
        equity = [100000, 105000, 100000, 95000, 90000, 95000]
        max_dd, duration = adapter.calculate_max_drawdown_with_duration(equity)

        # Peak: 105000, Trough: 90000
        # Max DD = (90000-105000)/105000 = -0.142857...
        # Duration counts days from peak to trough (excluding peak day itself)
        assert max_dd < 0
        assert max_dd == pytest.approx(-0.142857, rel=1e-4)
        assert duration == 3  # Days declining from peak to trough

    def test_max_drawdown_with_duration_no_drawdown(self):
        """Test max drawdown with only upward movement."""
        adapter = FincoreAdapter()
        equity = [100000, 101000, 102000, 103000, 104000]
        max_dd, duration = adapter.calculate_max_drawdown_with_duration(equity)

        # Should be 0 or close to 0
        assert max_dd <= 0
        assert duration == 0

    def test_max_drawdown_with_duration_insufficient_data(self):
        """Test max drawdown with insufficient data."""
        adapter = FincoreAdapter()

        # Single value
        max_dd, duration = adapter.calculate_max_drawdown_with_duration([100000])
        assert max_dd == 0.0
        assert duration == 0

        # Empty list
        max_dd, duration = adapter.calculate_max_drawdown_with_duration([])
        assert max_dd == 0.0
        assert duration == 0


class TestAnalyticsServiceIntegration:
    """Tests for AnalyticsService integration with FincoreAdapter."""

    def test_analytics_service_uses_adapter(self):
        """Test that AnalyticsService uses FincoreAdapter."""
        from app.services.analytics_service import AnalyticsService

        service = AnalyticsService(use_fincore=True)

        # Should have adapter attribute
        assert hasattr(service, "adapter")
        assert service.adapter.use_fincore is True

    def test_analytics_service_calculate_metrics(self):
        """Test AnalyticsService calculate_metrics with adapter."""
        from app.services.analytics_service import AnalyticsService

        service = AnalyticsService(use_fincore=True)

        result_data = {
            "equity_curve": [
                {
                    "date": "2023-01-01",
                    "total_assets": 100000,
                    "cash": 50000,
                    "position_value": 50000,
                },
                {
                    "date": "2023-01-02",
                    "total_assets": 101000,
                    "cash": 50000,
                    "position_value": 51000,
                },
                {
                    "date": "2023-01-03",
                    "total_assets": 102000,
                    "cash": 50000,
                    "position_value": 52000,
                },
                {
                    "date": "2023-01-04",
                    "total_assets": 101500,
                    "cash": 50000,
                    "position_value": 51500,
                },
                {
                    "date": "2023-01-05",
                    "total_assets": 103000,
                    "cash": 50000,
                    "position_value": 53000,
                },
            ],
            "trades": [
                {"pnl": 100, "pnlcomm": 95, "barlen": 5, "value": 10000},
                {"pnl": -50, "pnlcomm": -55, "barlen": 3, "value": 10000},
                {"pnl": 200, "pnlcomm": 195, "barlen": 10, "value": 10000},
            ],
        }

        metrics = service.calculate_metrics(result_data)

        # Verify metrics are calculated
        assert metrics.initial_capital == 100000
        assert metrics.final_assets == 103000
        assert metrics.total_return > 0
        assert metrics.max_drawdown <= 0
        assert metrics.profit_factor > 0
        assert metrics.avg_holding_days > 0
        assert metrics.max_consecutive_wins >= 0
        assert metrics.max_consecutive_losses >= 0


class TestAdvancedMetricsEdgeCases:
    """Tests for edge cases in advanced metrics."""

    def test_profit_factor_zero_avg_loss(self):
        """Test profit factor when average loss is zero."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": 0},  # Zero loss
        ]
        result = adapter.calculate_profit_factor(trades)

        # Should return 0 when avg_loss is 0
        assert result == 0.0

    def test_holding_period_all_zero(self):
        """Test average holding period when all barlen are zero."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100, "barlen": 0},
            {"pnlcomm": -50, "barlen": 0},
        ]
        result = adapter.calculate_avg_holding_period(trades)

        # Should return 0
        assert result == 0.0

    def test_consecutive_with_zero_pnl(self):
        """Test consecutive calculation with zero PnL."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": 0},  # Zero is not a win
            {"pnlcomm": 200},
        ]

        wins = adapter.calculate_max_consecutive(trades, win=True)
        losses = adapter.calculate_max_consecutive(trades, win=False)

        # Should count 100 and 200 as separate win streaks
        assert wins == 1
        # Zero is counted as a loss (not > 0)
        assert losses == 1

    def test_drawdown_with_flat_equity(self):
        """Test max drawdown with flat equity curve."""
        adapter = FincoreAdapter()
        equity = [100000, 100000, 100000, 100000]
        max_dd, duration = adapter.calculate_max_drawdown_with_duration(equity)

        # No drawdown
        assert max_dd == 0.0
        assert duration == 0
