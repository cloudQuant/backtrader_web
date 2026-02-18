#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EMA Dual Moving Average Crossover Strategy.

A trading strategy based on dual EMA crossover:
- Death cross (fast line crosses below slow line) -> Open short position
- Golden cross (fast line crosses above slow line) -> Open long position
- Uses multi-period data (5-minute + daily) for filtering

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class EmaCrossStrategy(bt.Strategy):
    """EMA Dual Moving Average Crossover Strategy with multi-period support.

    This strategy uses two EMAs of different periods to generate trading signals:
    - Fast line crosses above slow line (golden cross) -> Open long position
    - Fast line crosses below slow line (death cross) -> Open short position
    - Uses daily data for filtering trade timing

    Strategy Parameters:
        fast_period: Fast EMA period (default 80)
        slow_period: Slow EMA period (default 200)
        short_size: Short position size (default 2)
        long_size: Long position size (default 1)

    Data Sources:
        datas[0]: 5-minute bar data (for signal generation)
        datas[1]: Daily data (for date synchronization filtering, optional)
    """

    params = (
        ("fast_period", 80),
        ("slow_period", 200),
        ("short_size", 2),
        ("long_size", 1),
    )

    def log(self, txt, dt=None, force=False):
        """Log strategy information."""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        # Initialize statistical tracking
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # Get data references - standard access through datas list
        self.minute_data = self.datas[0]  # 5-minute data (primary)
        self.daily_data = self.datas[1] if len(self.datas) > 1 else None  # Daily data (filter)

        # Calculate EMA indicators on minute data
        self.fast_ema = bt.ind.EMA(self.minute_data, period=self.p.fast_period)
        self.slow_ema = bt.ind.EMA(self.minute_data, period=self.p.slow_period)
        self.ema_cross = bt.indicators.CrossOver(self.fast_ema, self.slow_ema)

        # If daily data exists, calculate SMA on daily data for filtering
        if self.daily_data is not None:
            self.sma_day = bt.ind.SMA(self.daily_data, period=6)

    def notify_trade(self, trade):
        """Handle trade completion events and update statistics."""
        if not trade.isclosed:
            return

        # Update win/loss statistics
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1

        # Track cumulative profit
        self.sum_profit += trade.pnl
        self.log(
            f"Trade completed: Gross profit={trade.pnl:.2f}, "
            f"Net profit={trade.pnlcomm:.2f}, Cumulative={self.sum_profit:.2f}"
        )

    def notify_order(self, order):
        """Handle order status updates and log executions."""
        # Skip pending orders
        if order.status in [order.Submitted, order.Accepted]:
            return

        # Log completed orders
        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    f"Buy executed: Price={order.executed.price:.2f}, "
                    f"Size={order.executed.size}"
                )
            else:
                self.log(
                    f"Sell executed: Price={order.executed.price:.2f}, "
                    f"Size={order.executed.size}"
                )
        # Log order issues
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1

        # Get EMA crossover signal history (recent 80 bars)
        # CrossOver returns 1 on golden cross, -1 on death cross, 0 otherwise
        crosslist = [i for i in self.ema_cross.get(size=80) if i == 1 or i == -1]

        # Check date synchronization (if daily data exists)
        # Only trade when both data feeds have data for the same day, preventing mismatch
        date_synced = True
        if self.daily_data is not None:
            date_synced = (
                self.minute_data.datetime.date(0) == self.daily_data.datetime.date(0)
            )

        # Open position logic (no current position)
        if not self.position and date_synced:
            # Sum of crossover signals indicates overall trend direction
            if len(crosslist) > 0:
                signal_sum = sum(crosslist)

                # Death cross signal - open short position
                if signal_sum == -1:
                    self.sell(data=self.minute_data, size=self.p.short_size)
                    self.sell_count += 1
                # Golden cross signal - open long position
                elif signal_sum == 1:
                    self.buy(data=self.minute_data, size=self.p.long_size)
                    self.buy_count += 1

        # Close position logic (has position)
        elif self.position and date_synced:
            signal_sum = sum(crosslist) if len(crosslist) > 0 else 0

            # When holding short, golden cross closes position
            if self.position.size < 0 and signal_sum == 1:
                self.close()
                self.buy_count += 1
            # When holding long, death cross closes position
            elif self.position.size > 0 and signal_sum == -1:
                self.close()
                self.sell_count += 1

    def stop(self):
        """Output final statistics when strategy completes."""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0

        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, "
            f"sell_count={self.sell_count}, wins={self.win_count}, "
            f"losses={self.loss_count}, win_rate={win_rate:.2f}%, "
            f"profit={self.sum_profit:.2f}",
            force=True
        )
