"""
Backtest Analyzer Tests.

Tests custom Backtrader analyzers:
- DetailedTradeAnalyzer: Records detailed trade information
- EquityCurveAnalyzer: Tracks equity curve over time
- TradeSignalAnalyzer: Records buy/sell signals
- MonthlyReturnsAnalyzer: Calculates monthly returns
- DrawdownAnalyzer: Tracks drawdown curve
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
    """Tests for detailed trade analyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = DetailedTradeAnalyzer()
        assert analyzer.trades == []
        assert analyzer.trade_count == 0

    def test_notify_trade_buy(self):
        """Test recording buy trades."""
        analyzer = DetailedTradeAnalyzer()

        # Create mock trade object
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

        # Create mock history - history[0].event.size determines buy/sell direction
        history_event = Mock()
        history_event.event = Mock()
        history_event.event.size = 100  # Positive means buy
        trade.history = [history_event]

        # Create trade.data._name (actual code uses trade.data._name)
        trade_data = Mock()
        trade_data._name = 'AAPL'
        trade.data = trade_data

        # Create mock data source for datetime
        data = Mock()
        dt = datetime(2024, 1, 1, 10, 30, 0)

        # Correctly set datetime mock chain
        # self.datas[0].datetime.datetime(0).strftime(...)
        dt_mock = Mock()
        dt_mock.strftime = Mock(return_value='2024-01-01 10:30:00')

        datetime_mock = Mock()
        datetime_mock.datetime = Mock(return_value=dt_mock)

        data.datetime = datetime_mock
        analyzer.datas = [data]

        # Call notify_trade
        analyzer.notify_trade(trade)

        # Verify
        assert analyzer.trade_count == 1
        assert len(analyzer.trades) == 1
        assert analyzer.trades[0]['symbol'] == 'AAPL'
        assert analyzer.trades[0]['direction'] == 'buy'

    def test_notify_trade_sell(self):
        """Test recording sell trades."""
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
        # history[0].event.size negative means sell
        trade.history = [Mock(event=Mock(size=-50))]

        # Create trade.data._name
        trade_data = Mock()
        trade_data._name = 'MSFT'
        trade.data = trade_data

        # Create mock data source for datetime
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
        """Test that unclosed trades are not recorded."""
        analyzer = DetailedTradeAnalyzer()

        trade = Mock()
        trade.isclosed = False

        analyzer.notify_trade(trade)

        assert analyzer.trade_count == 0
        assert len(analyzer.trades) == 0

    def test_get_analysis(self):
        """Test getting analysis results."""
        analyzer = DetailedTradeAnalyzer()
        analyzer.trades = [{'test': 'trade'}]

        result = analyzer.get_analysis()

        assert result == {'trades': [{'test': 'trade'}]}


class TestEquityCurveAnalyzer:
    """Tests for equity curve analyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = EquityCurveAnalyzer()
        assert analyzer.equity_curve == []
        assert analyzer._last_value is None

    def test_start(self):
        """Test start method."""
        analyzer = EquityCurveAnalyzer()

        # Mock strategy and broker
        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.start()

        assert analyzer._last_value == 100000

    def test_next(self):
        """Test next method."""
        analyzer = EquityCurveAnalyzer()

        # Mock data
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
        """Test getting analysis results."""
        analyzer = EquityCurveAnalyzer()
        analyzer.equity_curve = [{'date': '2024-01-01', 'total_assets': 100000}]

        result = analyzer.get_analysis()

        assert result == {'equity_curve': [{'date': '2024-01-01', 'total_assets': 100000}]}


class TestTradeSignalAnalyzer:
    """Tests for trade signal analyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = TradeSignalAnalyzer()
        assert analyzer.signals == []

    def test_notify_order_buy(self):
        """Test recording buy signals."""
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
        """Test recording sell signals."""
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
        """Test that incomplete orders are not recorded."""
        analyzer = TradeSignalAnalyzer()

        order = Mock()
        order.status = order.Pending

        analyzer.notify_order(order)

        assert len(analyzer.signals) == 0

    def test_get_analysis(self):
        """Test getting analysis results."""
        analyzer = TradeSignalAnalyzer()
        analyzer.signals = [{'type': 'buy'}]

        result = analyzer.get_analysis()

        assert result == {'signals': [{'type': 'buy'}]}


class TestMonthlyReturnsAnalyzer:
    """Tests for monthly returns analyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = MonthlyReturnsAnalyzer()
        assert analyzer.monthly_returns == {}
        assert analyzer.month_start_value is None
        assert analyzer.current_month is None

    def test_start(self):
        """Test start method."""
        analyzer = MonthlyReturnsAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.start()

        assert analyzer.month_start_value == 100000

    def test_next_same_month(self):
        """Test that same month is not recorded."""
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
        """Test recording returns when month changes."""
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

        # First month
        data.datetime.datetime = Mock(return_value=dt_jan)
        broker.getvalue.return_value = 100000
        analyzer.start()
        analyzer.next()

        # Second month
        data.datetime.datetime = Mock(return_value=dt_feb)
        broker.getvalue.return_value = 102000
        analyzer.next()

        assert (2024, 1) in analyzer.monthly_returns
        assert analyzer.monthly_returns[(2024, 1)] == pytest.approx(0.02)

    def test_stop(self):
        """Test stop method records final returns."""
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
        """Test getting analysis results."""
        analyzer = MonthlyReturnsAnalyzer()
        analyzer.monthly_returns = {(2024, 1): 0.05}

        result = analyzer.get_analysis()

        assert result == {'monthly_returns': {(2024, 1): 0.05}}


class TestDrawdownAnalyzer:
    """Tests for drawdown analyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = DrawdownAnalyzer()
        assert analyzer.drawdown_curve == []
        assert analyzer.peak == 0

    def test_start(self):
        """Test start method."""
        analyzer = DrawdownAnalyzer()

        strategy = Mock()
        broker = Mock()
        broker.getvalue.return_value = 100000
        strategy.broker = broker

        analyzer.strategy = strategy
        analyzer.start()

        assert analyzer.peak == 100000

    def test_next_increasing_peak(self):
        """Test new peak is recorded."""
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
        """Test drawdown is recorded."""
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
        # Set peak to 100000 first
        analyzer.peak = 100000
        analyzer.next()

        assert analyzer.peak == 100000
        assert analyzer.drawdown_curve[0]['drawdown'] == pytest.approx(-0.01)

    def test_get_analysis(self):
        """Test getting analysis results."""
        analyzer = DrawdownAnalyzer()
        analyzer.drawdown_curve = [{'date': '2024-01-01', 'drawdown': -0.05}]

        result = analyzer.get_analysis()

        assert result == {'drawdown_curve': [{'date': '2024-01-01', 'drawdown': -0.05}]}


class TestGetAllAnalyzers:
    """Tests for getting all analyzers."""

    def test_returns_all_analyzers(self):
        """Test that all analyzers are returned."""
        analyzers = get_all_analyzers()

        assert 'detailed_trades' in analyzers
        assert 'equity_curve' in analyzers
        assert 'trade_signals' in analyzers
        assert 'monthly_returns' in analyzers
        assert 'drawdown' in analyzers

    def test_analyzer_classes(self):
        """Test that correct analyzer classes are returned."""
        analyzers = get_all_analyzers()

        assert analyzers['detailed_trades'] == DetailedTradeAnalyzer
        assert analyzers['equity_curve'] == EquityCurveAnalyzer
        assert analyzers['trade_signals'] == TradeSignalAnalyzer
        assert analyzers['monthly_returns'] == MonthlyReturnsAnalyzer
        assert analyzers['drawdown'] == DrawdownAnalyzer
