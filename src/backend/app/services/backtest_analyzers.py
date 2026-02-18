"""
Backtrader analyzer extensions.

Collects detailed backtest data for analytics and reporting.
"""
import backtrader as bt
from collections import OrderedDict
from datetime import datetime


class DetailedTradeAnalyzer(bt.Analyzer):
    """Detailed trade analyzer that records detailed information for each trade.

    Attributes:
        trades: List of trade records with detailed information.
        trade_count: Total number of trades recorded.
    """

    def __init__(self):
        """Initialize the trade analyzer."""
        self.trades = []
        self.trade_count = 0

    def notify_trade(self, trade):
        """Called when a trade is closed to record its details.

        Args:
            trade: The closed trade object from backtrader.
        """
        if trade.isclosed:
            self.trade_count += 1
            self.trades.append({
                'id': self.trade_count,
                'ref': trade.ref,
                'datetime': self.datas[0].datetime.datetime(0).strftime('%Y-%m-%d %H:%M:%S'),
                'symbol': trade.data._name or 'unknown',
                'direction': 'buy' if trade.history[0].event.size > 0 else 'sell',
                'size': abs(trade.size),
                'price': trade.price,
                'value': abs(trade.value),
                'commission': trade.commission,
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm,
                'barlen': trade.barlen,
            })

    def get_analysis(self):
        """Return the analysis results.

        Returns:
            A dictionary containing the list of detailed trades.
        """
        return {'trades': self.trades}


class EquityCurveAnalyzer(bt.Analyzer):
    """Equity curve analyzer that records daily changes in account value.

    Attributes:
        equity_curve: List of daily equity records.
        _last_value: The last recorded portfolio value.
    """

    def __init__(self):
        """Initialize the equity curve analyzer."""
        self.equity_curve = []
        self._last_value = None

    def start(self):
        """Record the initial portfolio value when backtest starts."""
        self._last_value = self.strategy.broker.getvalue()

    def next(self):
        """Record equity data for each bar."""
        dt = self.datas[0].datetime.datetime(0)
        total = self.strategy.broker.getvalue()
        cash = self.strategy.broker.getcash()
        position_value = total - cash

        self.equity_curve.append({
            'date': dt.strftime('%Y-%m-%d'),
            'total_assets': round(total, 2),
            'cash': round(cash, 2),
            'position_value': round(position_value, 2),
        })

    def get_analysis(self):
        """Return the analysis results.

        Returns:
            A dictionary containing the equity curve data.
        """
        return {'equity_curve': self.equity_curve}


class TradeSignalAnalyzer(bt.Analyzer):
    """Trade signal analyzer that records buy and sell signals.

    Attributes:
        signals: List of trade signals with execution details.
    """

    def __init__(self):
        """Initialize the trade signal analyzer."""
        self.signals = []

    def notify_order(self, order):
        """Called when an order is completed to record the signal.

        Args:
            order: The completed order object from backtrader.
        """
        if order.status == order.Completed:
            signal_type = 'buy' if order.isbuy() else 'sell'
            dt = self.datas[0].datetime.datetime(0)
            self.signals.append({
                'date': dt.strftime('%Y-%m-%d'),
                'type': signal_type,
                'price': round(order.executed.price, 4),
                'size': abs(order.executed.size),
            })

    def get_analysis(self):
        """Return the analysis results.

        Returns:
            A dictionary containing the list of trade signals.
        """
        return {'signals': self.signals}


class MonthlyReturnsAnalyzer(bt.Analyzer):
    """Monthly returns analyzer that calculates returns for each month.

    Attributes:
        monthly_returns: Dictionary mapping (year, month) tuples to return values.
        month_start_value: Portfolio value at the start of the current month.
        current_month: The current (year, month) tuple being tracked.
    """

    def __init__(self):
        """Initialize the monthly returns analyzer."""
        self.monthly_returns = {}
        self.month_start_value = None
        self.current_month = None

    def start(self):
        """Record the initial portfolio value when backtest starts."""
        self.month_start_value = self.strategy.broker.getvalue()

    def next(self):
        """Calculate monthly returns when month changes."""
        dt = self.datas[0].datetime.datetime(0)
        month_key = (dt.year, dt.month)
        current_value = self.strategy.broker.getvalue()

        if self.current_month != month_key:
            # Record last month's return
            if self.current_month and self.month_start_value:
                ret = (current_value - self.month_start_value) / self.month_start_value
                self.monthly_returns[self.current_month] = round(ret, 6)

            # Start new month
            self.month_start_value = current_value
            self.current_month = month_key

    def stop(self):
        """Record the final month's return when backtest ends."""
        if self.current_month and self.month_start_value:
            current_value = self.strategy.broker.getvalue()
            ret = (current_value - self.month_start_value) / self.month_start_value
            self.monthly_returns[self.current_month] = round(ret, 6)

    def get_analysis(self):
        """Return the analysis results.

        Returns:
            A dictionary containing monthly return data.
        """
        return {'monthly_returns': self.monthly_returns}


class DrawdownAnalyzer(bt.Analyzer):
    """Drawdown analyzer that records daily drawdown metrics.

    Attributes:
        drawdown_curve: List of daily drawdown records.
        peak: The highest portfolio value observed.
    """

    def __init__(self):
        """Initialize the drawdown analyzer."""
        self.drawdown_curve = []
        self.peak = 0

    def start(self):
        """Initialize the peak value when backtest starts."""
        self.peak = self.strategy.broker.getvalue()

    def next(self):
        """Calculate drawdown for each bar."""
        dt = self.datas[0].datetime.datetime(0)
        current = self.strategy.broker.getvalue()

        if current > self.peak:
            self.peak = current

        dd = (current - self.peak) / self.peak if self.peak > 0 else 0

        self.drawdown_curve.append({
            'date': dt.strftime('%Y-%m-%d'),
            'drawdown': round(dd, 6),
            'peak': round(self.peak, 2),
            'trough': round(current, 2),
        })

    def get_analysis(self):
        """Return the analysis results.

        Returns:
            A dictionary containing the drawdown curve data.
        """
        return {'drawdown_curve': self.drawdown_curve}


def get_all_analyzers():
    """Get all custom analyzers.

    Returns:
        A dictionary mapping analyzer names to their classes.
    """
    return {
        'detailed_trades': DetailedTradeAnalyzer,
        'equity_curve': EquityCurveAnalyzer,
        'trade_signals': TradeSignalAnalyzer,
        'monthly_returns': MonthlyReturnsAnalyzer,
        'drawdown': DrawdownAnalyzer,
    }
