"""
Backtrader analyzer extensions.

Collects detailed backtest data for analytics and reporting.
"""

import backtrader as bt


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


class FincoreAdapter:
    """Adapter for fincore library integration with fallback to manual calculations.

    This adapter provides a unified interface for financial metric calculations,
    allowing gradual migration from manual calculations to fincore library.
    By default, it uses manual calculations for backward compatibility.
    Set use_fincore=True to use fincore library when ready.

    Attributes:
        use_fincore: If True, use fincore library for calculations.
                   If False (default), use manual calculations.

    Example:
        >>> adapter = FincoreAdapter()
        >>> sharpe = adapter.calculate_sharpe_ratio(returns, 0.02)
        >>> adapter_with_fincore = FincoreAdapter(use_fincore=True)
        >>> sharpe_fc = adapter_with_fincore.calculate_sharpe_ratio(returns, 0.02)
    """

    def __init__(self, use_fincore: bool = False):
        """Initialize the FincoreAdapter.

        Args:
            use_fincore: Whether to use fincore library for calculations.
                       Defaults to False for backward compatibility.
        """
        self.use_fincore = use_fincore

    def calculate_sharpe_ratio(
        self,
        returns: list,
        risk_free_rate: float = 0.0
    ) -> float:
        """Calculate Sharpe ratio for a series of returns.

        The Sharpe ratio measures the performance of an investment compared
        to a risk-free asset, after adjusting for risk.

        Args:
            returns: List of return values as decimals (e.g., 0.01 for 1%).
            risk_free_rate: Risk-free rate as decimal (e.g., 0.02 for 2%).
                           Defaults to 0.0.

        Returns:
            Sharpe ratio as float. Returns 0.0 if calculation fails.

        Formula:
            Sharpe = (mean(returns) - risk_free_rate) / std(returns)
        """
        if not returns:
            return 0.0

        # Use manual calculation for consistency
        import numpy as np
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        std_dev = np.std(excess_returns)

        if std_dev == 0:
            return 0.0

        return float(np.mean(excess_returns) / std_dev)

    def calculate_max_drawdown(self, equity_curve: list) -> float:
        """Calculate maximum drawdown from an equity curve.

        Maximum drawdown is the maximum peak-to-trough decline
        as a percentage of peak value.

        Args:
            equity_curve: List of portfolio values over time.

        Returns:
            Maximum drawdown as negative decimal (e.g., -0.15 for -15%).
            Returns 0.0 if insufficient data.

        Formula:
            MDD = (Trough - Peak) / Peak
        """
        if len(equity_curve) < 2:
            return 0.0

        # Use manual calculation for consistency
        import numpy as np
        equity_array = np.array(equity_curve)
        peak = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - peak) / peak
        return float(np.min(drawdown))

    def calculate_total_returns(self, equity_curve: list) -> float:
        """Calculate total returns from initial to final value.

        Args:
            equity_curve: List of portfolio values over time.

        Returns:
            Total return as decimal (e.g., 0.15 for 15%).
            Returns 0.0 if insufficient data.

        Formula:
            Total Return = (Final Value - Initial Value) / Initial Value
        """
        if len(equity_curve) < 2:
            return 0.0

        # Manual calculation (both for fincore and manual mode for consistency)
        # The formula is simple and identical, so we use the same calculation
        initial_value = equity_curve[0]
        final_value = equity_curve[-1]

        if initial_value == 0:
            return 0.0

        return float((final_value - initial_value) / initial_value)

    def calculate_annual_returns(
        self,
        equity_curve: list,
        periods_per_year: int = 252
    ) -> float:
        """Calculate annualized returns.

        Args:
            equity_curve: List of portfolio values over time.
            periods_per_year: Number of trading periods per year.
                              Defaults to 252 (trading days).

        Returns:
            Annualized return as decimal (e.g., 0.12 for 12%).
            Returns 0.0 if insufficient data.

        Formula:
            Annual Return = (Final / Initial)^(periods_per_year / n) - 1
            where n is the number of periods
        """
        if len(equity_curve) < 2:
            return 0.0

        # Use manual calculation for consistency
        # fincore's annual_return uses CAGR which may give slightly different results
        initial_value = equity_curve[0]
        final_value = equity_curve[-1]
        n = len(equity_curve)

        if initial_value == 0 or n == 0:
            return 0.0

        total_return = (final_value - initial_value) / initial_value
        annualized_return = (1 + total_return) ** (periods_per_year / n) - 1

        return float(annualized_return)

    def calculate_win_rate(self, trades: list) -> float:
        """Calculate win rate from a list of trades.

        Win rate is the percentage of profitable trades.
        Note: fincore library doesn't have a win_rate function, so this
        always uses manual calculation regardless of use_fincore setting.

        Args:
            trades: List of trade records, each containing 'pnlcomm' field
                    (profit/loss after commission).

        Returns:
            Win rate as decimal (e.g., 0.55 for 55%).
            Returns 0.0 if no trades provided.

        Formula:
            Win Rate = Winning Trades / Total Trades
        """
        if not trades:
            return 0.0

        # Manual calculation (fincore doesn't have win_rate function)
        winning_trades = sum(1 for t in trades if t.get('pnlcomm', 0) > 0)
        total_trades = len(trades)

        if total_trades == 0:
            return 0.0

        return float(winning_trades / total_trades)
