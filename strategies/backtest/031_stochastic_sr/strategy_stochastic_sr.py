"""Stochastic SR (Stochastic Support/Resistance) strategy.

This module implements a trading strategy that utilizes the Stochastic Oscillator
indicator for oversold/overbought entry points, and previous support/resistance
via Donchian Channels as well as a max loss in pips for risk levels.

Strategy Overview:
    - Entry signals based on Stochastic Oscillator crossovers at extreme levels
    - Stop loss based on fixed pip amount and Donchian Channel levels
    - Exit when Stochastic returns to neutral levels

Reference:
    backtrader-backtests/StochasticSR/Stochastic_SR_Backtest.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class StochasticSRStrategy(bt.Strategy):
    """Trading strategy that utilizes the Stochastic Oscillator indicator for oversold/overbought entry points,
    and previous support/resistance via Donchian Channels as well as a max loss in pips for risk levels.

    Strategy Logic:
        Entry:
            - Short: When stochastic crosses back below 80 (overbought reversal)
            - Long: When stochastic crosses back above 20 (oversold reversal)
        Exit:
            - Long exit: When stochastic is above 70
            - Short exit: When stochastic is below 30
        Risk Management:
            - Fixed stop loss (stop_pips)
            - Donchian Channel stop (previous high/low over period)

    Attributes:
        order: Reference to current pending order.
        donchian_stop_price: Stop loss price based on Donchian Channel.
        price: Execution price of most recent order.
        stop_price: Fixed stop loss order reference.
        stop_donchian: Donchian-based stop loss order reference.
        stochastic: Stochastic Oscillator indicator.
        bar_num: Counter for total bars processed.
        buy_count: Counter for buy orders executed.
        sell_count: Counter for sell orders executed.
        win_count: Counter for profitable trades.
        loss_count: Counter for unprofitable trades.
        sum_profit: Total profit/loss from all closed trades.
    """

    params = (
        ('period', 14),
        ('pfast', 3),
        ('pslow', 3),
        ('upperLimit', 80),
        ('lowerLimit', 20),
        ('stop_pips', 0.5),  # Stop loss in points adjusted for stock prices
    )

    def __init__(self):
        """Initializes variables required for the strategy implementation."""
        self.order = None
        self.donchian_stop_price = None
        self.price = None
        self.stop_price = None
        self.stop_donchian = None

        self.stochastic = bt.indicators.Stochastic(
            self.data,
            period=self.params.period,
            period_dfast=self.params.pfast,
            period_dslow=self.params.pslow,
            upperband=self.params.upperLimit,
            lowerband=self.params.lowerLimit
        )

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_trade(self, trade):
        """Run on every next iteration, logs the P/L with and without commission whenever a trade is closed."""
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def notify_order(self, order):
        """Run on every next iteration, logs the order execution status."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.price = order.executed.price
            elif order.issell():
                self.sell_count += 1
                self.price = order.executed.price
        elif order.status in [order.Rejected, order.Margin]:
            pass

        self.order = None

    def next(self):
        """Checks to see if Stochastic Oscillator, position, and order conditions meet the entry or exit conditions."""
        self.bar_num += 1

        if self.order:
            return

        if self.position.size == 0:
            # When stochastic crosses back below 80, enter short position.
            if self.stochastic.lines.percD[-1] >= 80 and self.stochastic.lines.percD[0] <= 80:
                self.donchian_stop_price = max(self.data.high.get(size=self.params.period))
                self.order = self.sell()
                self.stop_price = self.buy(exectype=bt.Order.Stop, price=self.data.close[0] + self.params.stop_pips, oco=self.stop_donchian)
                self.stop_donchian = self.buy(exectype=bt.Order.Stop, price=self.donchian_stop_price, oco=self.stop_price)
            # when stochastic crosses back above 20, enter long position.
            elif self.stochastic.lines.percD[-1] <= 20 and self.stochastic.lines.percD[0] >= 20:
                self.donchian_stop_price = min(self.data.low.get(size=self.params.period))
                self.order = self.buy()
                self.stop_price = self.sell(exectype=bt.Order.Stop, price=self.data.close[0] - self.params.stop_pips, oco=self.stop_donchian)
                self.stop_donchian = self.sell(exectype=bt.Order.Stop, price=self.donchian_stop_price, oco=self.stop_price)

        if self.position.size > 0:
            # When stochastic is above 70, close out of long position
            if self.stochastic.lines.percD[0] >= 70:
                self.close(oco=self.stop_price)
        if self.position.size < 0:
            # When stochastic is below 30, close out of short position
            if self.stochastic.lines.percD[0] <= 30:
                self.close(oco=self.stop_price)

    def stop(self):
        """Output statistics information when the strategy stops."""
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )
