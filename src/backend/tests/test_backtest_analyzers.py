"""
回测分析器测试

测试自定义的 Backtrader 分析器：
- DetailedTradeAnalyzer
- EquityCurveAnalyzer
- TradeSignalAnalyzer
- MonthlyReturnsAnalyzer
- DrawdownAnalyzer
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from app.services.backtest_analyzers import (
    DetailedTradeAnalyzer,
    EquityCurveAnalyzer,
    TradeSignalAnalyzer,
    MonthlyReturnsAnalyzer,
    DrawdownAnalyzer,
    get_all_analyzers,
)


class TestDetailedTradeAnalyzer:
    """测试详细交易分析器"""

    def test_initialization(self):
        """测试初始化"""
        analyzer = DetailedTradeAnalyzer()
        assert analyzer.trades == []
        assert analyzer.trade_count == 0

    def test_notify_trade_buy(self):
        """测试记录买入交易"""
        analyzer = DetailedTradeAnalyzer()

        # 创建模拟交易对象
        trade = Mock()
        trade.isclosed = True
        trade.ref = 1
        trade.size = 100
        trade.price = 10.5
        trade.value = 1050.0
        trade.commission = 5.0
        trade.pnl = 50.0
        trade.pnlcomm = 45.0
        trade.barlen = 5

        # 创建模拟历史记录 - history[0].event.size 决定买卖方向
        history_event = Mock()
        history_event.event = Mock()
        history_event.event.size = 100  # 正数表示买入
        trade.history = [history_event]

        # 创建 trade.data._name (实际代码使用 trade.data._name)
        trade_data = Mock()
        trade_data._name = 'AAPL'
        trade.data = trade_data

        # 创建模拟数据源用于 datetime
        data = Mock()
        dt = datetime(2024, 1, 1, 10, 30, 0)

        # 正确设置datetime mock的链式调用
        # self.datas[0].datetime.datetime(0).strftime(...)
        dt_mock = Mock()
        dt_mock.strftime = Mock(return_value='2024-01-01 10:30:00')

        datetime_mock = Mock()
        datetime_mock.datetime = Mock(return_value=dt_mock)

        data.datetime = datetime_mock
        analyzer.datas = [data]

        # 调用notify_trade
        analyzer.notify_trade(trade)

        # 验证
        assert analyzer.trade_count == 1
        assert len(analyzer.trades) == 1
        assert analyzer.trades[0]['symbol'] == 'AAPL'
        assert analyzer.trades[0]['direction'] == 'buy'

    def test_notify_trade_sell(self):
        """测试记录卖出交易"""
        analyzer = DetailedTradeAnalyzer()

        trade = Mock()
        trade.isclosed = True
        trade.ref = 2
        trade.size = -50
        trade.price = 11.0
        trade.value = -550.0
        trade.commission = 3.0
        trade.pnl = 25.0
        trade.pnlcomm = 22.0
        trade.barlen = 3
        # history[0].event.size 为负数表示卖出
        trade.history = [Mock(event=Mock(size=-50))]

        # 创建 trade.data._name
        trade_data = Mock()
        trade_data._name = 'MSFT'
        trade.data = trade_data

        # 创建模拟数据源用于 datetime
        dt_mock = Mock()
        dt_mock.strftime = Mock(return_value='2024-01-02 14:00:00')
        datetime_mock = Mock()
        datetime_mock.datetime = Mock(return_value=dt_mock)
        data = Mock()
        data.datetime = datetime_mock
        analyzer.datas = [data]

        analyzer.notify_trade(trade)

        assert analyzer.trades[0]['direction'] == 'sell'
        assert analyzer.trades[0]['size'] == 50

    def test_notify_trade_not_closed(self):
        """测试未完成的交易不记录"""
        analyzer = DetailedTradeAnalyzer()

        trade = Mock()
        trade.isclosed = False

        analyzer.notify_trade(trade)

        assert analyzer.trade_count == 0
        assert len(analyzer.trades) == 0

    def test_get_analysis(self):
        """测试获取分析结果"""
        analyzer = DetailedTradeAnalyzer()
        analyzer.trades = [{'test': 'trade'}]

        result = analyzer.get_analysis()

        assert result == {'trades': [{'test': 'trade'}]}


class TestEquityCurveAnalyzer:
    """测试资金曲线分析器"""

    def test_initialization(self):
        """测试初始化"""
        analyzer = EquityCurveAnalyzer()
        assert analyzer.equity_curve == []
        assert analyzer._last_value is None

    def test_start(self):
        """测试start方法"""
        analyzer = EquityCurveAnalyzer()

        # 模拟strategy和broker
        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.start()

        assert analyzer._last_value == 100000

    def test_next(self):
        """测试next方法"""
        analyzer = EquityCurveAnalyzer()

        # 模拟数据
        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100500
        broker.getcash.return_value = 50000
        strategy.broker = broker

        data = Mock()
        dt = datetime(2024, 1, 1)
        data.datetime = Mock()
        data.datetime.datetime = Mock(return_value=dt)

        analyzer.datas = [data]
        analyzer.strategy = strategy
        analyzer.next()

        assert len(analyzer.equity_curve) == 1
        assert analyzer.equity_curve[0]['total_assets'] == 100500
        assert analyzer.equity_curve[0]['cash'] == 50000
        assert analyzer.equity_curve[0]['position_value'] == 50500

    def test_get_analysis(self):
        """测试获取分析结果"""
        analyzer = EquityCurveAnalyzer()
        analyzer.equity_curve = [{'date': '2024-01-01', 'total_assets': 100000}]

        result = analyzer.get_analysis()

        assert result == {'equity_curve': [{'date': '2024-01-01', 'total_assets': 100000}]}


class TestTradeSignalAnalyzer:
    """测试交易信号分析器"""

    def test_initialization(self):
        """测试初始化"""
        analyzer = TradeSignalAnalyzer()
        assert analyzer.signals == []

    def test_notify_order_buy(self):
        """测试记录买入信号"""
        analyzer = TradeSignalAnalyzer()

        order = Mock()
        order.status = order.Completed
        order.isbuy.return_value = True
        order.executed.price = 100.5
        order.executed.size = 10

        data = Mock()
        dt = datetime(2024, 1, 1, 10, 0, 0)
        data.datetime = Mock()
        data.datetime.datetime = Mock(return_value=dt)

        analyzer.datas = [data]
        analyzer.notify_order(order)

        assert len(analyzer.signals) == 1
        assert analyzer.signals[0]['type'] == 'buy'
        assert analyzer.signals[0]['price'] == 100.5

    def test_notify_order_sell(self):
        """测试记录卖出信号"""
        analyzer = TradeSignalAnalyzer()

        order = Mock()
        order.status = order.Completed
        order.isbuy.return_value = False
        order.executed.price = 105.0
        order.executed.size = 10

        data = Mock()
        dt = datetime(2024, 1, 2, 14, 30, 0)
        data.datetime = Mock()
        data.datetime.datetime = Mock(return_value=dt)

        analyzer.datas = [data]
        analyzer.notify_order(order)

        assert analyzer.signals[0]['type'] == 'sell'

    def test_notify_order_not_completed(self):
        """测试未完成的订单不记录"""
        analyzer = TradeSignalAnalyzer()

        order = Mock()
        order.status = order.Pending

        analyzer.notify_order(order)

        assert len(analyzer.signals) == 0

    def test_get_analysis(self):
        """测试获取分析结果"""
        analyzer = TradeSignalAnalyzer()
        analyzer.signals = [{'type': 'buy'}]

        result = analyzer.get_analysis()

        assert result == {'signals': [{'type': 'buy'}]}


class TestMonthlyReturnsAnalyzer:
    """测试月度收益分析器"""

    def test_initialization(self):
        """测试初始化"""
        analyzer = MonthlyReturnsAnalyzer()
        assert analyzer.monthly_returns == {}
        assert analyzer.month_start_value is None
        assert analyzer.current_month is None

    def test_start(self):
        """测试start方法"""
        analyzer = MonthlyReturnsAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.start()

        assert analyzer.month_start_value == 100000

    def test_next_same_month(self):
        """测试同一个月不记录"""
        analyzer = MonthlyReturnsAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        data = Mock()
        dt = datetime(2024, 1, 1)
        data.datetime = Mock()
        data.datetime.datetime = Mock(return_value=dt)

        analyzer.datas = [data]
        analyzer.strategy = strategy
        analyzer.start()
        analyzer.next()

        assert analyzer.current_month == (2024, 1)
        assert len(analyzer.monthly_returns) == 0

    def test_next_month_change(self):
        """测试月份变化时记录收益"""
        analyzer = MonthlyReturnsAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 101000
        strategy.broker = broker

        data = Mock()
        dt_jan = datetime(2024, 1, 15)
        dt_feb = datetime(2024, 2, 1)
        data.datetime = Mock()

        analyzer.datas = [data]
        analyzer.strategy = strategy

        # 第一个月
        data.datetime.datetime = Mock(return_value=dt_jan)
        broker.getvalue.return_value = 100000
        analyzer.start()
        analyzer.next()

        # 第二个月
        data.datetime.datetime = Mock(return_value=dt_feb)
        broker.getvalue.return_value = 102000
        analyzer.next()

        assert (2024, 1) in analyzer.monthly_returns
        assert analyzer.monthly_returns[(2024, 1)] == pytest.approx(0.02)

    def test_stop(self):
        """测试stop方法记录最后收益"""
        analyzer = MonthlyReturnsAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 102000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.current_month = (2024, 1)
        analyzer.month_start_value = 100000

        analyzer.stop()

        assert analyzer.monthly_returns[(2024, 1)] == 0.02

    def test_get_analysis(self):
        """测试获取分析结果"""
        analyzer = MonthlyReturnsAnalyzer()
        analyzer.monthly_returns = {(2024, 1): 0.05}

        result = analyzer.get_analysis()

        assert result == {'monthly_returns': {(2024, 1): 0.05}}


class TestDrawdownAnalyzer:
    """测试回撤分析器"""

    def test_initialization(self):
        """测试初始化"""
        analyzer = DrawdownAnalyzer()
        assert analyzer.drawdown_curve == []
        assert analyzer.peak == 0

    def test_start(self):
        """测试start方法"""
        analyzer = DrawdownAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.start()

        assert analyzer.peak == 100000

    def test_next_increasing_peak(self):
        """测试创新高"""
        analyzer = DrawdownAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 101000
        strategy.broker = broker

        data = Mock()
        dt = datetime(2024, 1, 1)
        data.datetime = Mock()
        data.datetime.datetime = Mock(return_value=dt)

        analyzer.datas = [data]
        analyzer.strategy = strategy
        analyzer.start()
        analyzer.next()

        assert analyzer.peak == 101000
        assert analyzer.drawdown_curve[0]['drawdown'] == 0

    def test_next_drawdown(self):
        """测试回撤"""
        analyzer = DrawdownAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 99000
        strategy.broker = broker

        data = Mock()
        dt = datetime(2024, 1, 2)
        data.datetime = Mock()
        data.datetime.datetime = Mock(return_value=dt)

        analyzer.datas = [data]
        analyzer.strategy = strategy
        analyzer.start()
        # 先设置peak为100000
        analyzer.peak = 100000
        analyzer.next()

        assert analyzer.peak == 100000
        assert analyzer.drawdown_curve[0]['drawdown'] == pytest.approx(-0.01)

    def test_get_analysis(self):
        """测试获取分析结果"""
        analyzer = DrawdownAnalyzer()
        analyzer.drawdown_curve = [{'date': '2024-01-01', 'drawdown': -0.05}]

        result = analyzer.get_analysis()

        assert result == {'drawdown_curve': [{'date': '2024-01-01', 'drawdown': -0.05}]}


class TestGetAllAnalyzers:
    """测试获取所有分析器"""

    def test_returns_all_analyzers(self):
        """测试返回所有分析器"""
        analyzers = get_all_analyzers()

        assert 'detailed_trades' in analyzers
        assert 'equity_curve' in analyzers
        assert 'trade_signals' in analyzers
        assert 'monthly_returns' in analyzers
        assert 'drawdown' in analyzers

    def test_analyzer_classes(self):
        """测试分析器类正确"""
        analyzers = get_all_analyzers()

        assert analyzers['detailed_trades'] == DetailedTradeAnalyzer
        assert analyzers['equity_curve'] == EquityCurveAnalyzer
        assert analyzers['trade_signals'] == TradeSignalAnalyzer
        assert analyzers['monthly_returns'] == MonthlyReturnsAnalyzer
        assert analyzers['drawdown'] == DrawdownAnalyzer
