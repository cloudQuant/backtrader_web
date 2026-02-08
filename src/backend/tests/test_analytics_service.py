"""
分析服务单元测试
"""
from app.services.analytics_service import AnalyticsService


svc = AnalyticsService()


class TestCalculateMetrics:
    """绩效指标计算测试"""

    def test_empty_equity_curve(self):
        m = svc.calculate_metrics({})
        assert m.total_return == 0
        assert m.initial_capital == 0

    def test_basic_metrics(self):
        equity = [
            {"total_assets": 100000},
            {"total_assets": 105000},
            {"total_assets": 103000},
            {"total_assets": 110000},
        ]
        trades = [
            {"pnl": 5000, "value": 50000, "barlen": 3},
            {"pnl": -2000, "value": 30000, "barlen": 2},
            {"pnl": 7000, "value": 60000, "barlen": 5},
        ]
        m = svc.calculate_metrics({"equity_curve": equity, "trades": trades})
        assert m.initial_capital == 100000
        assert m.final_assets == 110000
        assert m.total_return > 0
        assert m.trade_count == 3
        assert m.win_rate > 0

    def test_no_trades(self):
        equity = [{"total_assets": 100000}, {"total_assets": 100000}]
        m = svc.calculate_metrics({"equity_curve": equity, "trades": []})
        assert m.trade_count == 0
        assert m.win_rate == 0


class TestMaxDrawdown:
    """最大回撤计算测试"""

    def test_no_drawdown(self):
        curve = [{"total_assets": v} for v in [100, 110, 120, 130]]
        dd, dur = svc._calculate_max_drawdown(curve)
        assert dd == 0
        assert dur == 0

    def test_with_drawdown(self):
        curve = [{"total_assets": v} for v in [100, 120, 90, 110]]
        dd, dur = svc._calculate_max_drawdown(curve)
        assert dd < 0  # drawdown is negative
        assert dur > 0

    def test_empty_curve(self):
        dd, dur = svc._calculate_max_drawdown([])
        assert dd == 0


class TestDailyReturns:
    """日收益率计算测试"""

    def test_basic(self):
        curve = [{"total_assets": v} for v in [100, 110, 105]]
        returns = svc._calculate_daily_returns(curve)
        assert len(returns) == 2
        assert abs(returns[0] - 0.1) < 0.001

    def test_single_point(self):
        returns = svc._calculate_daily_returns([{"total_assets": 100}])
        assert returns == []


class TestSharpe:
    """夏普比率计算测试"""

    def test_basic(self):
        returns = [0.01, 0.02, -0.005, 0.015, 0.01]
        sharpe = svc._calculate_sharpe(returns)
        assert sharpe is not None
        assert sharpe > 0

    def test_insufficient_data(self):
        assert svc._calculate_sharpe([0.01]) is None
        assert svc._calculate_sharpe([]) is None

    def test_zero_std(self):
        assert svc._calculate_sharpe([0.01, 0.01, 0.01]) is None


class TestMaxConsecutive:
    """最大连续盈亏测试"""

    def test_consecutive_wins(self):
        trades = [{"pnl": 10}, {"pnl": 20}, {"pnl": -5}, {"pnl": 15}]
        assert svc._max_consecutive(trades, True) == 2

    def test_consecutive_losses(self):
        trades = [{"pnl": -10}, {"pnl": -20}, {"pnl": 5}]
        assert svc._max_consecutive(trades, False) == 2

    def test_empty_trades(self):
        assert svc._max_consecutive([], True) == 0


class TestProcessTrades:
    """交易记录处理测试"""

    def test_basic(self):
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
    """资金曲线处理测试"""

    def test_basic(self):
        raw = [{"date": "2024-01-01", "total_assets": 100000, "cash": 50000, "position_value": 50000}]
        result = svc.process_equity_curve(raw)
        assert len(result) == 1
        assert result[0].total_assets == 100000


class TestProcessDrawdown:
    """回撤曲线处理测试"""

    def test_basic(self):
        raw = [{"date": "2024-01-01", "drawdown": -0.05, "peak": 100000, "trough": 95000}]
        result = svc.process_drawdown_curve(raw)
        assert len(result) == 1
        assert result[0].drawdown == -0.05


class TestProcessSignals:
    """交易信号处理测试"""

    def test_basic(self):
        raw = [{"date": "2024-01-01", "type": "buy", "price": 10.5, "size": 100}]
        result = svc.process_signals(raw)
        assert len(result) == 1
        assert result[0].type == "buy"


class TestProcessMonthlyReturns:
    """月度收益处理测试"""

    def test_basic(self):
        raw = {(2024, 1): 0.05, (2024, 2): -0.02, (2024, 3): 0.03}
        result = svc.process_monthly_returns(raw)
        assert len(result.returns) == 3
        assert 2024 in result.years
        assert 2024 in result.summary


class TestCalculateIndicators:
    """技术指标计算测试"""

    def test_ma_calculation(self):
        klines = [{"close": float(i)} for i in range(1, 25)]
        indicators = svc.calculate_indicators(klines)
        assert "ma5" in indicators
        assert "ma10" in indicators
        assert "ma20" in indicators
        assert len(indicators["ma5"]) == 24
        assert indicators["ma5"][0] is None  # not enough data
        assert indicators["ma5"][4] is not None

    def test_empty_klines(self):
        assert svc.calculate_indicators([]) == {}

    def test_short_klines_no_ma60(self):
        klines = [{"close": float(i)} for i in range(1, 11)]
        indicators = svc.calculate_indicators(klines)
        assert indicators["ma60"] == []
