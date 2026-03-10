"""SMA Cross Signal moving average crossover strategy.

This module implements a simple moving average crossover strategy that generates
trading signals based on the relationship between a short-term and long-term
simple moving average.

Strategy Overview:
    - Buy (golden cross): Short-term SMA crosses above long-term SMA
    - Sell (death cross): Short-term SMA crosses below long-term SMA

Reference:
    backtrader-master2/samples/sigsmacross/sigsmacross.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class SmaCrossSignalStrategy(bt.Strategy):
    """Simple Moving Average (SMA) crossover signal trading strategy.

    This strategy implements a classic moving average crossover approach where
    trading signals are generated based on the relationship between a short-term
    and long-term simple moving average. The crossover indicator detects when
    the short-term SMA crosses above or below the long-term SMA, triggering
    buy and sell signals respectively.

    The strategy tracks performance metrics including total bars processed,
    buy/sell order counts, win/loss ratios, and cumulative profit/loss.

    Attributes:
        crossover: CrossOver indicator that detects SMA crossovers.
        order: Reference to the currently pending order (if any).
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for total buy orders executed.
        sell_count: Counter for total sell orders executed.
        win_count: Counter for profitable closed trades.
        loss_count: Counter for unprofitable closed trades.
        sum_profit: Cumulative profit/loss from all closed trades.

    Parameters:
        sma1 (int): Period for the short-term SMA. Default is 10.
        sma2 (int): Period for the long-term SMA. Default is 20.
    """
    params = dict(
        sma1=10,
        sma2=20,
    )

    def __init__(self):
        """Initialize the SMA crossover strategy.

        Creates the short-term and long-term simple moving average indicators
        and a CrossOver indicator to detect when they intersect. Initializes
        tracking variables for order management and performance statistics.

        The strategy sets up two SMAs:
        - Short-term SMA (default 10 periods) for fast price movement tracking
        - Long-term SMA (default 20 periods) for trend identification
        - CrossOver indicator generates +1 on bullish crossover, -1 on bearish
        """
        sma1 = bt.ind.SMA(period=self.params.sma1)
        sma2 = bt.ind.SMA(period=self.params.sma2)
        self.crossover = bt.ind.CrossOver(sma1, sma2)

        self.order = None
        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

        Called by the backtrader engine when an order changes status. This method
        updates the buy/sell counters when orders are completed and clears the
        order reference when the order is no longer alive (filled, cancelled,
        or expired).

        Args:
            order: The order object that has changed status.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Called by the backtrader engine when a trade is closed. This method
        updates performance statistics including cumulative profit/loss and
        the count of winning versus losing trades.

        Args:
            trade: The trade object that has been closed. Contains information
                about the trade including profit/loss (pnlcomm).
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        This method is called by the backtrader engine for each new bar of data.
        It implements the core trading logic:

        1. Increments the bar counter
        2. Skips trading if an order is already pending
        3. On bullish crossover (short SMA crosses above long SMA):
           - Closes any existing position
           - Opens a new long position
        4. On bearish crossover (short SMA crosses below long SMA):
           - Closes any existing position

        The crossover indicator returns:
        - +1: Bullish crossover (buy signal)
        - -1: Bearish crossover (sell signal)
        - 0: No crossover
        """
        self.bar_num += 1
        if self.order:
            return
        if self.crossover > 0:
            if self.position:
                self.order = self.close()
            self.order = self.buy()
        elif self.crossover < 0:
            if self.position:
                self.order = self.close()

    def stop(self):
        """Display final performance metrics when backtesting completes.

        This method is called by the backtrader engine when the backtest finishes.
        It calculates and prints a summary of the strategy's performance including
        total bars processed, order counts, win/loss statistics, win rate, and
        total profit/loss.

        The win rate is calculated as: (win_count / total_closed_trades) * 100
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )
