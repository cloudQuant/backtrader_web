#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fear & Greed Sentiment Strategy.

A contrarian investment strategy based on the Fear & Greed Index:
- Fear & Greed < 10 (extreme fear) -> Buy
- Fear & Greed > 94 (extreme greed) -> Sell

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class SPYFearGreedData(bt.feeds.GenericCSVData):
    """Custom data feed for loading SPY price data and Fear & Greed sentiment indicator.

    This data feed extends GenericCSVData to load SPY (S&P 500 ETF) historical price data
    along with three additional sentiment indicators:
    - Put/Call Ratio: Options market sentiment indicator
    - Fear & Greed Index: Market sentiment indicator (0-100 scale)
    - VIX: CBOE Volatility Index

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


class FearGreedStrategy(bt.Strategy):
    """Contrarian investment strategy based on Fear & Greed Index.

    This strategy uses a mean-reversion approach, trading based on extreme market sentiment:
    - Buy SPY when Fear & Greed Index shows extreme fear (< 10)
    - Sell SPY when Fear & Greed Index shows extreme greed (> 94)

    The underlying assumption is that extreme sentiment periods often precede market reversals,
    therefore buying during excessive fear (market oversold) and
    selling during excessive greed (market overbought).
    """

    params = (
        ("fear_threshold", 10),   # Fear threshold, buy when below this
        ("greed_threshold", 94),  # Greed threshold, sell when above this
    )

    def log(self, txt, dt=None, force=False):
        """Log strategy information."""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the strategy."""
        # Record statistics
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # Get data references
        self.data0 = self.datas[0]
        self.fear_greed = self.data0.fear_greed
        self.close = self.data0.close

    def notify_trade(self, trade):
        """Handle trade completion notifications."""
        if not trade.isclosed:
            return
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl
        self.log(f"Trade completed: Gross profit={trade.pnl:.2f}, Net profit={trade.pnlcomm:.2f}, Cumulative={self.sum_profit:.2f}")

    def notify_order(self, order):
        """Handle order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"Buy executed: Price={order.executed.price:.2f}, Size={order.executed.size}")
            else:
                self.log(f"Sell executed: Price={order.executed.price:.2f}, Size={order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1

        # Calculate buyable quantity
        size = int(self.broker.getcash() / self.close[0])

        # Buy during extreme fear
        if self.fear_greed[0] < self.p.fear_threshold and not self.position:
            if size > 0:
                self.buy(size=size)
                self.buy_count += 1

        # Sell during extreme greed
        if self.fear_greed[0] > self.p.greed_threshold and self.position.size > 0:
            self.sell(size=self.position.size)
            self.sell_count += 1

    def stop(self):
        """Output final statistics when strategy completes."""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
