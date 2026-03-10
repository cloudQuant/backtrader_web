#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VIX Volatility Index Strategy.

A contrarian investment strategy based on VIX Volatility Index:
- VIX > 35 (market panic) -> Buy
- VIX < 10 (market calm) -> Sell

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class SPYVixData(bt.feeds.GenericCSVData):
    """Custom data feed for loading SPY price data and VIX & sentiment indicators.

    This data feed extends GenericCSVData to load SPY (S&P 500 ETF) historical price data
    as well as additional sentiment indicators, including Put/Call Ratio, Fear & Greed Index, and CBOE Volatility Index (VIX).

    CSV file must contain the following columns (in order):
    Date, Open, High, Low, Close, Adj Close, Volume, Put Call, Fear Greed, VIX
    """
    lines = ('put_call', 'fear_greed', 'vix')

    params = (
        ('dtformat', '%Y-%m-%d'),
        ('datetime', 0),
        ('open', 1),
        ('high', 2),
        ('low', 3),
        ('close', 4),
        ('volume', 6),
        ('openinterest', -1),
        ('put_call', 7),
        ('fear_greed', 8),
        ('vix', 9),
    )


class VIXStrategy(bt.Strategy):
    """Trading strategy based on VIX Volatility Index.

    This strategy uses a mean-reversion approach, trading based on VIX (CBOE Volatility Index).
    VIX is a fear gauge measuring expected market volatility.

    Strategy Logic:
        - Entry: Establish long position when VIX spikes (> 35) (extreme fear indicates oversold)
        - Exit: Exit position when VIX drops to low levels (< 10) (extreme calm indicates overbought)

    This is a mean-reversion strategy based on the principle that
    extreme fear periods often precede market recovery,
    while extreme complacency may precede market pullbacks.
    """

    params = (
        ("high_threshold", 35),  # High threshold: buy when above this level (fear)
        ("low_threshold", 10),   # Low threshold: sell when below this level (calm)
    )

    def log(self, txt, dt=None, force=False):
        """Log strategy information."""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the VIX strategy."""
        # Record statistics
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # Get data references - follow best practices through datas list
        self.data0 = self.datas[0]
        self.vix = self.data0.vix
        self.close = self.data0.close

    def notify_trade(self, trade):
        """Handle trade completion events."""
        if not trade.isclosed:
            return
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl
        self.log(f"Trade completed: gross_profit={trade.pnl:.2f}, net_profit={trade.pnlcomm:.2f}, cumulative={self.sum_profit:.2f}")

    def notify_order(self, order):
        """Handle order status change events."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY EXECUTED: price={order.executed.price:.2f}, size={order.executed.size}")
            else:
                self.log(f"SELL EXECUTED: price={order.executed.price:.2f}, size={order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"ORDER STATUS: {order.Status[order.status]}")

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1

        # Calculate buyable quantity
        size = int(self.broker.getcash() / self.close[0])

        # Buy when VIX is high (market fear)
        if self.vix[0] > self.p.high_threshold and not self.position:
            if size > 0:
                self.buy(size=size)
                self.buy_count += 1

        # Sell when VIX is low (market calm)
        if self.vix[0] < self.p.low_threshold and self.position.size > 0:
            self.sell(size=self.position.size)
            self.sell_count += 1

    def stop(self):
        """Output statistics when strategy execution completes."""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
