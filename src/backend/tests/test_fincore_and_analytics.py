"""
Tests for FincoreAdapter financial calculations and analytics service.

Covers:
- Sharpe ratio calculation
- Max drawdown calculation
- Total/annual returns
- Win rate, profit factor
- Holding period, consecutive wins/losses
- Comparison service helper methods
"""


from app.services.backtest.analyzers import FincoreAdapter

# ============================================================
# FincoreAdapter Tests
# ============================================================


class TestSharpeRatio:
    """Test Sharpe ratio calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter(use_fincore=False)

    def test_positive_sharpe(self):
        """Positive returns should give positive Sharpe."""
        returns = [0.01, 0.02, 0.015, 0.01, 0.025, 0.01, 0.02]
        sharpe = self.adapter.calculate_sharpe_ratio(returns)
        assert sharpe > 0

    def test_negative_sharpe(self):
        """Negative returns should give negative Sharpe."""
        returns = [-0.01, -0.02, -0.015, -0.01, -0.025]
        sharpe = self.adapter.calculate_sharpe_ratio(returns)
        assert sharpe < 0

    def test_empty_returns(self):
        """Empty returns list should return 0."""
        assert self.adapter.calculate_sharpe_ratio([]) == 0.0

    def test_zero_std_returns_zero(self):
        """Constant returns (zero std) should return 0."""
        returns = [0.01, 0.01, 0.01, 0.01]
        sharpe = self.adapter.calculate_sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_risk_free_rate_reduces_sharpe(self):
        """Higher risk-free rate should reduce Sharpe ratio."""
        returns = [0.01, 0.02, 0.015, 0.01, 0.025]
        sharpe_0 = self.adapter.calculate_sharpe_ratio(returns, risk_free_rate=0.0)
        sharpe_high = self.adapter.calculate_sharpe_ratio(returns, risk_free_rate=0.05)
        assert sharpe_0 > sharpe_high


class TestMaxDrawdown:
    """Test maximum drawdown calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_no_drawdown(self):
        """Monotonically increasing curve should have 0 drawdown."""
        equity = [100, 110, 120, 130, 140]
        dd = self.adapter.calculate_max_drawdown(equity)
        assert dd == 0.0

    def test_simple_drawdown(self):
        """Simple peak-to-trough should calculate correctly."""
        equity = [100, 120, 90, 110]  # 25% drawdown from 120 to 90
        dd = self.adapter.calculate_max_drawdown(equity)
        assert abs(dd - (-0.25)) < 0.001

    def test_multiple_drawdowns(self):
        """Should find the maximum drawdown among multiple."""
        equity = [100, 110, 95, 105, 80, 100]  # Max DD: 110→80 = -27.3%
        dd = self.adapter.calculate_max_drawdown(equity)
        assert dd < -0.25

    def test_insufficient_data(self):
        """Less than 2 points should return 0."""
        assert self.adapter.calculate_max_drawdown([100]) == 0.0
        assert self.adapter.calculate_max_drawdown([]) == 0.0

    def test_drawdown_is_negative(self):
        """Drawdown should always be negative or zero."""
        equity = [100, 90, 80, 70]
        dd = self.adapter.calculate_max_drawdown(equity)
        assert dd <= 0


class TestTotalReturns:
    """Test total returns calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_positive_return(self):
        """100 → 150 should be 50% return."""
        equity = [100, 110, 120, 150]
        ret = self.adapter.calculate_total_returns(equity)
        assert abs(ret - 0.5) < 0.001

    def test_negative_return(self):
        """100 → 80 should be -20% return."""
        equity = [100, 90, 80]
        ret = self.adapter.calculate_total_returns(equity)
        assert abs(ret - (-0.2)) < 0.001

    def test_zero_return(self):
        """Same start and end should be 0% return."""
        equity = [100, 110, 90, 100]
        ret = self.adapter.calculate_total_returns(equity)
        assert abs(ret) < 0.001

    def test_insufficient_data(self):
        """Less than 2 points should return 0."""
        assert self.adapter.calculate_total_returns([100]) == 0.0
        assert self.adapter.calculate_total_returns([]) == 0.0

    def test_zero_initial_value(self):
        """Zero initial value should return 0 (avoid division by zero)."""
        equity = [0, 100, 200]
        ret = self.adapter.calculate_total_returns(equity)
        assert ret == 0.0


class TestAnnualReturns:
    """Test annualized returns calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_one_year_return(self):
        """252 days of data with 10% total return should give ~10% annual."""
        equity = [100] + [100 + i * (10 / 252) for i in range(1, 253)]
        equity[-1] = 110  # Ensure exactly 10% total
        ret = self.adapter.calculate_annual_returns(equity, periods_per_year=252)
        assert abs(ret - 0.1) < 0.02  # Allow small rounding

    def test_insufficient_data(self):
        """Less than 2 points should return 0."""
        assert self.adapter.calculate_annual_returns([100]) == 0.0

    def test_zero_initial_value(self):
        """Zero initial value should return 0."""
        equity = [0, 100, 200]
        ret = self.adapter.calculate_annual_returns(equity)
        assert ret == 0.0


class TestWinRate:
    """Test win rate calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_all_winners(self):
        """All winning trades should give 100% win rate."""
        trades = [{"pnlcomm": 100}, {"pnlcomm": 50}, {"pnlcomm": 200}]
        assert self.adapter.calculate_win_rate(trades) == 1.0

    def test_all_losers(self):
        """All losing trades should give 0% win rate."""
        trades = [{"pnlcomm": -100}, {"pnlcomm": -50}]
        assert self.adapter.calculate_win_rate(trades) == 0.0

    def test_mixed_trades(self):
        """3 wins out of 5 should give 60% win rate."""
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": -50},
            {"pnlcomm": 200},
            {"pnlcomm": -30},
            {"pnlcomm": 150},
        ]
        assert abs(self.adapter.calculate_win_rate(trades) - 0.6) < 0.001

    def test_empty_trades(self):
        """Empty trades should return 0."""
        assert self.adapter.calculate_win_rate([]) == 0.0

    def test_zero_pnl_not_counted_as_win(self):
        """Zero PnL should not count as a win."""
        trades = [{"pnlcomm": 0}, {"pnlcomm": 100}]
        assert self.adapter.calculate_win_rate(trades) == 0.5


class TestProfitFactor:
    """Test profit factor calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_profit_factor_greater_than_one(self):
        """Avg win > avg loss should give PF > 1."""
        trades = [
            {"pnlcomm": 200},
            {"pnlcomm": 150},
            {"pnlcomm": -50},
            {"pnlcomm": -75},
        ]
        pf = self.adapter.calculate_profit_factor(trades)
        assert pf > 1.0

    def test_profit_factor_less_than_one(self):
        """Avg win < avg loss should give PF < 1."""
        trades = [
            {"pnlcomm": 50},
            {"pnlcomm": -200},
            {"pnlcomm": -150},
        ]
        pf = self.adapter.calculate_profit_factor(trades)
        assert pf < 1.0

    def test_no_trades(self):
        """Empty trades should return 0."""
        assert self.adapter.calculate_profit_factor([]) == 0.0

    def test_no_losses(self):
        """No losing trades should return 0 (undefined)."""
        trades = [{"pnlcomm": 100}, {"pnlcomm": 200}]
        assert self.adapter.calculate_profit_factor(trades) == 0.0

    def test_no_wins(self):
        """No winning trades should return 0."""
        trades = [{"pnlcomm": -100}, {"pnlcomm": -200}]
        assert self.adapter.calculate_profit_factor(trades) == 0.0


class TestHoldingPeriod:
    """Test average holding period calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_average_holding(self):
        """Should calculate average of barlen values."""
        trades = [{"barlen": 5}, {"barlen": 10}, {"barlen": 15}]
        avg = self.adapter.calculate_avg_holding_period(trades)
        assert avg == 10.0

    def test_empty_trades(self):
        """Empty trades should return 0."""
        assert self.adapter.calculate_avg_holding_period([]) == 0.0

    def test_missing_barlen(self):
        """Trades without barlen should be skipped."""
        trades = [{"barlen": 10}, {"pnlcomm": 100}]
        avg = self.adapter.calculate_avg_holding_period(trades)
        assert avg == 10.0


class TestMaxConsecutive:
    """Test max consecutive wins/losses calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_consecutive_wins(self):
        """Should find longest winning streak."""
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": 50},
            {"pnlcomm": 200},
            {"pnlcomm": -10},
            {"pnlcomm": 100},
        ]
        assert self.adapter.calculate_max_consecutive(trades, win=True) == 3

    def test_consecutive_losses(self):
        """Should find longest losing streak."""
        trades = [
            {"pnlcomm": 100},
            {"pnlcomm": -50},
            {"pnlcomm": -200},
            {"pnlcomm": -10},
            {"pnlcomm": 100},
        ]
        assert self.adapter.calculate_max_consecutive(trades, win=False) == 3

    def test_empty_trades(self):
        """Empty trades should return 0."""
        assert self.adapter.calculate_max_consecutive([], win=True) == 0

    def test_all_same(self):
        """All wins should return total count."""
        trades = [{"pnlcomm": 100}] * 5
        assert self.adapter.calculate_max_consecutive(trades, win=True) == 5


class TestMaxDrawdownWithDuration:
    """Test max drawdown with duration calculation."""

    def setup_method(self):
        self.adapter = FincoreAdapter()

    def test_drawdown_with_duration(self):
        """Should return both drawdown value and duration."""
        equity = [100, 120, 110, 90, 95, 130]
        dd, duration = self.adapter.calculate_max_drawdown_with_duration(equity)
        assert dd < 0
        assert duration > 0

    def test_no_drawdown(self):
        """Monotonically increasing should have 0 drawdown and 0 duration."""
        equity = [100, 110, 120, 130]
        dd, duration = self.adapter.calculate_max_drawdown_with_duration(equity)
        assert dd == 0.0
        assert duration == 0

    def test_insufficient_data(self):
        """Less than 2 points should return (0, 0)."""
        dd, duration = self.adapter.calculate_max_drawdown_with_duration([100])
        assert dd == 0.0
        assert duration == 0


# ============================================================
# ComparisonService Helper Tests
# ============================================================


class TestComparisonHelpers:
    """Test comparison service static helper methods."""

    def _make_results(self):
        """Create sample backtest results dict keyed by task_id."""
        return {
            "task-1": {
                "sharpe_ratio": 1.5,
                "total_return": 0.2,
                "annual_return": 0.15,
                "max_drawdown": -0.1,
                "win_rate": 0.6,
                "total_trades": 10,
                "profitable_trades": 6,
                "losing_trades": 4,
                "equity_curve": [100000, 110000, 120000],
                "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "drawdown_curve": [0, -0.05, -0.1],
            },
            "task-2": {
                "sharpe_ratio": 1.2,
                "total_return": 0.3,
                "annual_return": 0.25,
                "max_drawdown": -0.15,
                "win_rate": 0.55,
                "total_trades": 15,
                "profitable_trades": 8,
                "losing_trades": 7,
                "equity_curve": [100000, 105000, 130000],
                "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "drawdown_curve": [0, -0.03, -0.15],
            },
        }

    def test_compare_metrics(self):
        """_compare_metrics should identify differences between results."""
        from app.services.comparison_service import ComparisonService

        svc = ComparisonService()
        results = self._make_results()
        result = svc._compare_metrics(results)
        assert "total_return" in result
        assert "task-1" in result["total_return"]
        assert result["total_return"]["task-1"] == 0.2

    def test_find_best_metrics(self):
        """_find_best_metrics should identify the best performer."""
        from app.services.comparison_service import ComparisonService

        svc = ComparisonService()
        results = self._make_results()
        best = svc._find_best_metrics(results)
        assert best["total_return"]["task_id"] == "task-2"  # 0.3 > 0.2
        assert best["sharpe_ratio"]["task_id"] == "task-1"  # 1.5 > 1.2

    def test_compare_equity(self):
        """_compare_equity should compare equity curves."""
        from app.services.comparison_service import ComparisonService

        svc = ComparisonService()
        results = self._make_results()
        result = svc._compare_equity(results)
        assert "dates" in result
        assert "curves" in result
        assert "task-1" in result["curves"]

    def test_compare_trades(self):
        """_compare_trades should compare trade statistics."""
        from app.services.comparison_service import ComparisonService

        svc = ComparisonService()
        results = self._make_results()
        result = svc._compare_trades(results)
        assert "trade_counts" in result
        assert "win_rates" in result
        assert result["trade_counts"]["task-1"]["total"] == 10

    def test_compare_drawdown(self):
        """_compare_drawdown should compare drawdown curves."""
        from app.services.comparison_service import ComparisonService

        svc = ComparisonService()
        results = self._make_results()
        result = svc._compare_drawdown(results)
        assert isinstance(result, dict)
