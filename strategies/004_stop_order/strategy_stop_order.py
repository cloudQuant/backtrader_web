#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stop Loss Order Strategy with Moving Average Crossover.

This strategy implements a trend-following approach with automatic risk management:

Entry Logic:
    - Golden cross (short MA crosses above long MA) triggers buy signal
    - Uses 90% of available cash for each trade
    - Only enters when no position is held

Exit Logic:
    - Death cross (short MA crosses below long MA) triggers manual sell
    - Stop loss orders automatically trigger at 3% below buy price
    - Stop loss orders are placed immediately after each buy execution

Risk Management:
    - Stop loss percentage: 3% (configurable via stop_loss_pct parameter)
    - Stop loss price: buy_price * (1 - stop_loss_pct)
    - Automatic stop loss placement on every buy
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class ExtendPandasFeed(bt.feeds.PandasData):
    """Extended Pandas data source with convertible bond specific fields."""

    params = (
        ("datetime", None),
        ("open", 0),
        ("high", 1),
        ("low", 2),
        ("close", 3),
        ("volume", 4),
        ("openinterest", -1),
        ("pure_bond_value", 5),
        ("convert_value", 6),
        ("pure_bond_premium_rate", 7),
        ("convert_premium_rate", 8),
    )

    lines = ("pure_bond_value", "convert_value", "pure_bond_premium_rate", "convert_premium_rate")


class StopOrderStrategy(bt.Strategy):
    """Stop Loss Order Strategy with Moving Average Crossover.

    Strategy Logic:
        - Golden cross: Short MA crosses above long MA -> Buy
        - Death cross: Short MA crosses below long MA -> Sell (cancel stop loss first)
        - Stop loss: Automatically placed at buy_price * (1 - stop_loss_pct)

    Parameters:
        short_period (int): Short MA period (default: 5)
        long_period (int): Long MA period (default: 20)
        stop_loss_pct (float): Stop loss percentage (default: 0.03 = 3%)
    """

    params = (
        ("short_period", 5),
        ("long_period", 20),
        ("stop_loss_pct", 0.03),  # 3% stop loss
    )

    def log(self, txt, dt=None, force=False):
        """Log strategy information with optional timestamp."""
        if not force:
            return

        if dt is None:
            try:
                dt_val = self.datas[0].datetime[0]
                if dt_val > 0:
                    dt = bt.num2date(dt_val)
                else:
                    dt = None
            except (IndexError, ValueError):
                dt = None

        if dt:
            print("{}, {}".format(dt.isoformat(), txt))
        else:
            print("%s" % txt)

    def __init__(self):
        """Initialize the StopOrderStrategy with indicators and tracking variables."""
        # Calculate moving average indicators
        self.short_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.short_period
        )
        self.long_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.long_period
        )

        # Crossover indicator: positive = golden cross, negative = death cross
        self.crossover = bt.indicators.CrossOver(self.short_ma, self.long_ma)

        # Initialize tracking counters
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.stop_count = 0  # Stop loss trigger count

        # Save order references
        self.order = None
        self.stop_order = None
        self.buy_price = None

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1

        # If there are pending orders, wait for completion
        if self.order:
            return

        # If there is a stop loss order waiting, handle death cross exit
        if self.stop_order:
            # Check if death cross appears, need to actively close position
            if self.crossover < 0:
                # Cancel stop loss order before manual close
                self.cancel(self.stop_order)
                self.stop_order = None
                # Close position manually
                self.order = self.close()
                self.sell_count += 1
            return

        # If no position and golden cross appears, execute buy
        if not self.position:
            if self.crossover > 0:
                # Use 90% of current funds to buy
                cash = self.broker.get_cash()
                price = self.datas[0].close[0]
                size = int(cash * 0.9 / price)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.buy_count += 1

    def stop(self):
        """Log final strategy statistics when backtesting completes."""
        self.log(
            f"bar_num = {self.bar_num}, buy_count = {self.buy_count}, sell_count = {self.sell_count}, stop_count = {self.stop_count}",
            force=True,
        )

    def notify_order(self, order):
        """Handle order status changes and manage stop loss orders."""
        # Ignore submitted/accepted orders
        if order.status in [order.Submitted, order.Accepted]:
            return

        # Handle completed orders
        if order.status == order.Completed:
            if order.isbuy():
                # Log buy execution
                self.log(
                    f"Buy executed: Price={order.executed.price:.2f}, Size={order.executed.size:.0f}",
                    force=True,
                )
                self.buy_price = order.executed.price

                # After successful buy, set stop loss order
                stop_price = self.buy_price * (1 - self.p.stop_loss_pct)
                self.log(f"Set stop loss order: Stop price={stop_price:.2f}", force=True)
                self.stop_order = self.sell(
                    size=order.executed.size, exectype=bt.Order.Stop, price=stop_price
                )
            else:
                # Log sell execution
                self.log(
                    f"Sell executed: Price={order.executed.price:.2f}, Size={abs(order.executed.size):.0f}",
                    force=True,
                )
                self.buy_price = None

                # Check if this is a stop loss order trigger
                if order == self.stop_order:
                    self.stop_count += 1
                    self.log("Stop loss order triggered!", force=True)
                    self.stop_order = None

        # Handle failed orders
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order canceled/insufficient margin/rejected: {order.status}", force=True)

        # Reset order status if not the stop loss order
        if self.stop_order is None or order.ref != self.stop_order.ref:
            self.order = None

    def notify_trade(self, trade):
        """Handle trade completion notifications and log profit/loss."""
        if trade.isclosed:
            self.log(
                f"Trade completed: Gross profit={trade.pnl:.2f}, Net profit={trade.pnlcomm:.2f}",
                force=True,
            )
