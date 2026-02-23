"""
Analytics Service Unit Tests.

Tests the performance metrics calculation functionality including:
- Return metrics (total return, win rate, etc.)
- Drawdown calculation
- Daily returns computation
- Sharpe ratio calculation
- Consecutive wins/losses tracking
- Trade and equity curve processing
- Technical indicator calculation
"""
from app.services.analytics_service import AnalyticsService
from app.services.backtest_analyzers import FincoreAdapter


svc = AnalyticsService()


class TestCalculateMetrics:
    """Tests for performance metrics calculation."""

    def test_empty_equity_curve(self):
        """Test metrics calculation with empty equity curve."""
        m = svc.calculate_metrics({})
        assert m.total_return == 0
        assert m.initial_capital == 0

    def test_basic_metrics(self):
        """Test basic metrics calculation."""
        equity = [
            {"total_assets": 100000},
            {"total_assets": 105000},
            {"total_assets": 103000},
            {"total_assets": 110000},
        ]
        trades = [
            {"pnl": 5000, "pnlcomm": 5000, "value": 50000, "barlen": 3},
            {"pnl": -2000, "pnlcomm": -2000, "value": 30000, "barlen": 2},
            {"pnl": 7000, "pnlcomm": 7000, "value": 60000, "barlen": 5},
        ]
        m = svc.calculate_metrics({"equity_curve": equity, "trades": trades})
        assert m.initial_capital == 100000
        assert m.final_assets == 110000
        assert m.total_return > 0
        assert m.trade_count == 3
        assert m.win_rate > 0

    def test_no_trades(self):
        """Test metrics calculation with no trades."""
        equity = [{"total_assets": 100000}, {"total_assets": 100000}]
        m = svc.calculate_metrics({"equity_curve": equity, "trades": []})
        assert m.trade_count == 0
        assert m.win_rate == 0


class TestMaxDrawdown:
    """Tests for maximum drawdown calculation."""

    def test_no_drawdown(self):
        """Test drawdown calculation with no drawdown scenario."""
        adapter = FincoreAdapter()
        curve = [100, 110, 120, 130]
        dd, dur = adapter.calculate_max_drawdown_with_duration(curve)
        assert dd == 0
        assert dur == 0

    def test_with_drawdown(self):
        """Test drawdown calculation with drawdown scenario."""
        adapter = FincoreAdapter()
        curve = [100, 120, 90, 110]
        dd, dur = adapter.calculate_max_drawdown_with_duration(curve)
        assert dd < 0  # drawdown is negative
        assert dur > 0

    def test_empty_curve(self):
        """Test drawdown calculation with empty curve."""
        adapter = FincoreAdapter()
        dd, dur = adapter.calculate_max_drawdown_with_duration([])
        assert dd == 0


class TestDailyReturns:
    """Tests for daily returns calculation."""

    def test_basic(self):
        """Test basic daily returns calculation."""
        curve = [{"total_assets": v} for v in [100, 110, 105]]
        returns = svc._calculate_daily_returns(curve)
        assert len(returns) == 2
        assert abs(returns[0] - 0.1) < 0.001

    def test_single_point(self):
        """Test daily returns with single data point."""
        returns = svc._calculate_daily_returns([{"total_assets": 100}])
        assert returns == []


class TestSharpe:
    """Tests for Sharpe ratio calculation."""

    def test_basic(self):
        """Test basic Sharpe ratio calculation."""
        adapter = FincoreAdapter()
        returns = [0.01, 0.02, -0.005, 0.015, 0.01]
        sharpe = adapter.calculate_sharpe_ratio(returns, 0.02)
        assert sharpe is not None
        # Can be positive or negative depending on returns

    def test_insufficient_data(self):
        """Test Sharpe ratio with insufficient data."""
        adapter = FincoreAdapter()
        assert adapter.calculate_sharpe_ratio([0.01], 0.02) == 0.0
        assert adapter.calculate_sharpe_ratio([], 0.02) == 0.0

    def test_zero_std(self):
        """Test Sharpe ratio with zero standard deviation."""
        adapter = FincoreAdapter()
        assert adapter.calculate_sharpe_ratio([0.01, 0.01, 0.01], 0.02) == 0.0


class TestMaxConsecutive:
    """Tests for maximum consecutive wins/losses."""

    def test_consecutive_wins(self):
        """Test maximum consecutive wins calculation."""
        adapter = FincoreAdapter()
        trades = [{"pnlcomm": 10}, {"pnlcomm": 20}, {"pnlcomm": -5}, {"pnlcomm": 15}]
        assert adapter.calculate_max_consecutive(trades, True) == 2

    def test_consecutive_losses(self):
        """Test maximum consecutive losses calculation."""
        adapter = FincoreAdapter()
        trades = [{"pnlcomm": -10}, {"pnlcomm": -20}, {"pnlcomm": 5}]
        assert adapter.calculate_max_consecutive(trades, False) == 2

    def test_empty_trades(self):
        """Test consecutive calculation with empty trades."""
        adapter = FincoreAdapter()
        assert adapter.calculate_max_consecutive([], True) == 0


class TestProcessTrades:
    """Tests for trade record processing."""

    def test_basic(self):
        """Test basic trade processing."""
        raw = [
            {"datetime": "2024-01-01", "direction": "buy", "price": 10, "size": 100, "value": 1000, "pnl": 50, "barlen": 3},
            {"datetime": "2024-01-05", "direction": "sell", "price": 11, "size": 100, "value": 1100, "pnl": -20},
        ]
        result = svc.process_trades(raw)
        assert len(result) == 2
        assert result[0].id == 1
        assert result[0].pnl == 50
        assert result[1].cumulative_pnl == 30  # 50 + (-20)


class TestProcessEquityCurve:
    """Tests for equity curve processing."""

    def test_basic(self):
        """Test basic equity curve processing."""
        raw = [{"date": "2024-01-01", "total_assets": 100000, "cash": 50000, "position_value": 50000}]
        result = svc.process_equity_curve(raw)
        assert len(result) == 1
        assert result[0].total_assets == 100000


class TestProcessDrawdown:
    """Tests for drawdown curve processing."""

    def test_basic(self):
        """Test basic drawdown curve processing."""
        raw = [{"date": "2024-01-01", "drawdown": -0.05, "peak": 100000, "trough": 95000}]
        result = svc.process_drawdown_curve(raw)
        assert len(result) == 1
        assert result[0].drawdown == -0.05


class TestProcessSignals:
    """Tests for trading signal processing."""

    def test_basic(self):
        """Test basic signal processing."""
        raw = [{"date": "2024-01-01", "type": "buy", "price": 10.5, "size": 100}]
        result = svc.process_signals(raw)
        assert len(result) == 1
        assert result[0].type == "buy"


class TestProcessMonthlyReturns:
    """Tests for monthly returns processing."""

    def test_basic(self):
        """Test basic monthly returns processing."""
        raw = {(2024, 1): 0.05, (2024, 2): -0.02, (2024, 3): 0.03}
        result = svc.process_monthly_returns(raw)
        assert len(result.returns) == 3
        assert 2024 in result.years
        assert 2024 in result.summary


class TestCalculateIndicators:
    """Tests for technical indicator calculation."""

    def test_ma_calculation(self):
        """Test moving average calculation."""
        klines = [{"close": float(i)} for i in range(1, 25)]
        indicators = svc.calculate_indicators(klines)
        assert "ma5" in indicators
        assert "ma10" in indicators
        assert "ma20" in indicators
        assert len(indicators["ma5"]) == 24
        assert indicators["ma5"][0] is None  # not enough data
        assert indicators["ma5"][4] is not None

    def test_empty_klines(self):
        """Test indicators with empty klines."""
        assert svc.calculate_indicators([]) == {}

    def test_short_klines_no_ma60(self):
        """Test MA60 is not calculated for short data series."""
        klines = [{"close": float(i)} for i in range(1, 11)]
        indicators = svc.calculate_indicators(klines)
        assert indicators["ma60"] == []
