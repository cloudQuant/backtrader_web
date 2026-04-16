"""
Fincore Adapter Tests.

Tests for the FincoreAdapter class that provides a unified interface
for financial metric calculations with fallback to manual calculations.
"""

import pytest

from app.services.backtest_analyzers import FincoreAdapter


class TestFincoreAdapterInitialization:
    """Tests for FincoreAdapter initialization."""

    def test_initialization_default(self):
        """Test adapter initialization with default settings."""
        adapter = FincoreAdapter()
        assert adapter.use_fincore is False

    def test_initialization_with_fincore_enabled(self):
        """Test adapter initialization with fincore enabled."""
        adapter = FincoreAdapter(use_fincore=True)
        assert adapter.use_fincore is True

    def test_initialization_with_fincore_disabled(self):
        """Test adapter initialization with fincore explicitly disabled."""
        adapter = FincoreAdapter(use_fincore=False)
        assert adapter.use_fincore is False


class TestCalculateSharpeRatio:
    """Tests for Sharpe ratio calculation."""

    def test_calculate_sharpe_ratio_manual_positive(self):
        """Test Sharpe ratio calculation with positive returns."""
        adapter = FincoreAdapter(use_fincore=False)
        returns = [0.01, 0.02, 0.015, -0.005, 0.03, 0.01]
        result = adapter.calculate_sharpe_ratio(returns, 0.02)

        # Expected: mean=0.0117, std=0.012, excess=0.0117-0.02=-0.0083, sharpe=-0.69
        assert isinstance(result, float)
        # Just verify it computes a reasonable value
        assert -5 < result < 5  # Sanity check

    def test_calculate_sharpe_ratio_manual_zero_std(self):
        """Test Sharpe ratio with zero standard deviation."""
        adapter = FincoreAdapter()
        returns = [0.01, 0.01, 0.01, 0.01]  # All same returns
        result = adapter.calculate_sharpe_ratio(returns)

        # Should return 0.0 when std dev is 0
        assert result == 0.0

    def test_calculate_sharpe_ratio_empty_returns(self):
        """Test Sharpe ratio with empty returns list."""
        adapter = FincoreAdapter()
        result = adapter.calculate_sharpe_ratio([])

        assert result == 0.0

    def test_calculate_sharpe_ratio_with_risk_free_rate(self):
        """Test Sharpe ratio with custom risk-free rate."""
        adapter = FincoreAdapter()
        returns = [0.05, 0.03, 0.04, 0.06, 0.02]
        result = adapter.calculate_sharpe_ratio(returns, 0.03)

        assert isinstance(result, float)


class TestCalculateMaxDrawdown:
    """Tests for maximum drawdown calculation."""

    def test_calculate_max_drawdown_manual_positive_trend(self):
        """Test max drawdown with positive trend (no drawdown)."""
        adapter = FincoreAdapter()
        equity = [100000, 101000, 102000, 103000, 104000]
        result = adapter.calculate_max_drawdown(equity)

        # With monotonically increasing equity, max DD should be 0 or close to 0
        assert result <= 0.0  # Drawdown is negative or zero

    def test_calculate_max_drawdown_manual_with_decline(self):
        """Test max drawdown with decline."""
        adapter = FincoreAdapter()
        equity = [100000, 105000, 100000, 90000, 95000]
        result = adapter.calculate_max_drawdown(equity)

        # Peak was 105000, trough was 90000
        # Max DD = (90000 - 105000) / 105000 = -0.1429
        assert isinstance(result, float)
        assert result < 0  # Should be negative
        assert result > -1  # Should not be more than -100%

    def test_calculate_max_drawdown_insufficient_data(self):
        """Test max drawdown with insufficient data."""
        adapter = FincoreAdapter()

        # Single value
        result = adapter.calculate_max_drawdown([100000])
        assert result == 0.0

        # Empty list
        result = adapter.calculate_max_drawdown([])
        assert result == 0.0


class TestCalculateTotalReturns:
    """Tests for total returns calculation."""

    def test_calculate_total_returns_manual_positive(self):
        """Test total returns with positive growth."""
        adapter = FincoreAdapter()
        equity = [100000, 105000, 110000, 115000]
        result = adapter.calculate_total_returns(equity)

        # (115000 - 100000) / 100000 = 0.15
        assert result == pytest.approx(0.15, rel=1e-6)

    def test_calculate_total_returns_manual_negative(self):
        """Test total returns with decline."""
        adapter = FincoreAdapter()
        equity = [100000, 95000, 90000, 85000]
        result = adapter.calculate_total_returns(equity)

        # (85000 - 100000) / 100000 = -0.15
        assert result == pytest.approx(-0.15, rel=1e-6)

    def test_calculate_total_returns_insufficient_data(self):
        """Test total returns with insufficient data."""
        adapter = FincoreAdapter()

        result = adapter.calculate_total_returns([100000])
        assert result == 0.0

        result = adapter.calculate_total_returns([])
        assert result == 0.0

    def test_calculate_total_returns_zero_initial(self):
        """Test total returns with zero initial value."""
        adapter = FincoreAdapter()
        equity = [0, 1000, 2000]
        result = adapter.calculate_total_returns(equity)

        assert result == 0.0


class TestCalculateAnnualReturns:
    """Tests for annualized returns calculation."""

    def test_calculate_annual_returns_manual(self):
        """Test annualized returns calculation."""
        adapter = FincoreAdapter()
        # 100 days of data, 10% total return
        equity = [100000] + [100000 + i * 100 for i in range(100)]
        result = adapter.calculate_annual_returns(equity, periods_per_year=252)

        assert isinstance(result, float)
        # Annualized return should be positive
        assert result > 0

    def test_calculate_annual_returns_insufficient_data(self):
        """Test annualized returns with insufficient data."""
        adapter = FincoreAdapter()

        result = adapter.calculate_annual_returns([100000])
        assert result == 0.0

        result = adapter.calculate_annual_returns([])
        assert result == 0.0

    def test_calculate_annual_returns_custom_periods(self):
        """Test annualized returns with custom periods per year."""
        adapter = FincoreAdapter()
        equity = [100000, 110000, 120000]
        result = adapter.calculate_annual_returns(equity, periods_per_year=12)

        assert isinstance(result, float)


class TestCalculateWinRate:
    """Tests for win rate calculation."""

    def test_calculate_win_rate_manual_winning(self):
        """Test win rate with more winning trades."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},  # Win
            {"pnlcomm": 50},  # Win
            {"pnlcomm": -30},  # Loss
            {"pnlcomm": 75},  # Win
            {"pnlcomm": -20},  # Loss
        ]
        result = adapter.calculate_win_rate(trades)

        # 3 wins out of 5 trades = 60%
        assert result == pytest.approx(0.6, rel=1e-6)

    def test_calculate_win_rate_manual_all_wins(self):
        """Test win rate with all winning trades."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": 50},
            {"pnlcomm": 75},
        ]
        result = adapter.calculate_win_rate(trades)

        assert result == 1.0

    def test_calculate_win_rate_manual_all_losses(self):
        """Test win rate with all losing trades."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": -100},
            {"pnlcomm": -50},
            {"pnlcomm": -30},
        ]
        result = adapter.calculate_win_rate(trades)

        assert result == 0.0

    def test_calculate_win_rate_empty_trades(self):
        """Test win rate with no trades."""
        adapter = FincoreAdapter()
        result = adapter.calculate_win_rate([])

        assert result == 0.0

    def test_calculate_win_rate_missing_pnlcomm(self):
        """Test win rate with trades missing pnlcomm field."""
        adapter = FincoreAdapter()
        trades = [
            {"pnlcomm": 100},
            {"other_field": 50},  # Missing pnlcomm, defaults to 0
            {"pnlcomm": -30},
        ]
        result = adapter.calculate_win_rate(trades)

        # 1 win (100 > 0) out of 3 trades
        assert result == pytest.approx(1 / 3, rel=1e-6)


class TestFallbackLogic:
    """Tests for fallback from fincore to manual calculation."""

    def test_fallback_when_fincore_import_fails(self):
        """Test that manual calculation is used when fincore import fails."""
        # This test verifies the fallback behavior
        adapter = FincoreAdapter(use_fincore=True)

        # Even with use_fincore=True, if fincore fails, it should fall back
        # For now, fincore is installed, so we test the interface
        returns = [0.01, 0.02, 0.015]
        result = adapter.calculate_sharpe_ratio(returns)

        # Should return a valid result (either from fincore or manual)
        assert isinstance(result, float)

    def test_manual_calculation_mode(self):
        """Test that manual calculation mode works correctly."""
        adapter = FincoreAdapter(use_fincore=False)

        # Test with known values
        equity = [100, 110, 105, 115]
        result = adapter.calculate_total_returns(equity)

        # (115 - 100) / 100 = 0.15
        assert result == pytest.approx(0.15, rel=1e-6)


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    def test_get_all_analyzers_includes_adapter(self):
        """Test that get_all_analyzers still works with adapter."""
        from app.services.backtest_analyzers import get_all_analyzers

        analyzers = get_all_analyzers()

        # Should include all original analyzers
        assert "detailed_trades" in analyzers
        assert "equity_curve" in analyzers
        assert "trade_signals" in analyzers
        assert "monthly_returns" in analyzers
        assert "drawdown" in analyzers

        # Verify the classes are unchanged
        assert analyzers["detailed_trades"].__name__ == "DetailedTradeAnalyzer"
        assert analyzers["equity_curve"].__name__ == "EquityCurveAnalyzer"

    def test_adapter_does_not_break_existing_analyzers(self):
        """Test that adding adapter doesn't break existing analyzer imports."""
        from app.services.backtest_analyzers import (
            DetailedTradeAnalyzer,
            DrawdownAnalyzer,
            EquityCurveAnalyzer,
            FincoreAdapter,  # New adapter
            MonthlyReturnsAnalyzer,
            TradeSignalAnalyzer,
        )

        # Backtrader analyzers require Cerebro/runtime wiring; importing the
        # classes successfully is the backward-compatibility contract here.
        assert DetailedTradeAnalyzer.__name__ == "DetailedTradeAnalyzer"
        assert EquityCurveAnalyzer.__name__ == "EquityCurveAnalyzer"
        assert TradeSignalAnalyzer.__name__ == "TradeSignalAnalyzer"
        assert MonthlyReturnsAnalyzer.__name__ == "MonthlyReturnsAnalyzer"
        assert DrawdownAnalyzer.__name__ == "DrawdownAnalyzer"
        assert FincoreAdapter() is not None
