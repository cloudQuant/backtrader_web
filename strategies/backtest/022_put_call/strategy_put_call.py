#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Put/Call Ratio Sentiment Strategy.

A contrarian investment strategy based on Put/Call Ratio:
- Put/Call > 1.0 (market fear) -> Buy
- Put/Call < 0.45 (market greed) -> Sell

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class SPYPutCallData(bt.feeds.GenericCSVData):
    """Custom data feed for loading SPY price data and sentiment indicators.

    This data feed extends GenericCSVData to load SPY (S&P 500 ETF) historical price data
    as well as market sentiment indicators including Put/Call ratio, Fear & Greed Index, and VIX volatility index.

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


class PutCallStrategy(bt.Strategy):
    """Contrarian sentiment strategy based on Put/Call Ratio.

    This strategy uses a contrarian investment approach, using Put/Call Ratio as a market sentiment indicator:
    - High ratio (> 1.0) indicates fear -> Buy signal (contrarian)
    - Low ratio (< 0.45) indicates greed/optimism -> Sell signal

    The strategy assumes extreme sentiment often precedes market reversals,
    allowing contrarian positioning when the crowd is excessively bearish or bullish.
    """

    params = (
        ("high_threshold", 1.0),   # High threshold, buy when above this (fear)
        ("low_threshold", 0.45),   # Low threshold, sell when below this (greed)
    )

    def log(self, txt, dt=None, force=False):
        """Log strategy information."""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize strategy attributes and data references."""
        # Initialize statistical counters
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # Create data references for access
        self.data0 = self.datas[0]
        self.put_call = self.data0.put_call
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
        """Handle order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"Buy executed: price={order.executed.price:.2f}, size={order.executed.size}")
            else:
                self.log(f"Sell executed: price={order.executed.price:.2f}, size={order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1

        # Calculate position size based on available cash
        size = int(self.broker.getcash() / self.close[0])

        # Buy signal: High Put/Call ratio indicates market fear (contrarian buy)
        if self.put_call[0] > self.p.high_threshold and not self.position:
            if size > 0:
                self.buy(size=size)
                self.buy_count += 1

        # Sell signal: Low Put/Call ratio indicates market greed (contrarian sell)
        if self.put_call[0] < self.p.low_threshold and self.position.size > 0:
            self.sell(size=self.position.size)
            self.sell_count += 1

    def stop(self):
        """Calculate and log final statistics when strategy completes."""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
