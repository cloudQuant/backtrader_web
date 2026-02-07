#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TD Sequential Strategy - Trading based on Tom DeMark's TD Sequential indicator.

This strategy implements Tom DeMark's TD Sequential indicator which identifies
potential price exhaustion points through a setup and countdown phase.

Reference: https://github.com/mk99999/TD-seq
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class TDSequentialStrategy(bt.Strategy):
    """TD Sequential strategy.

    Based on Tom DeMark's TD Sequential indicator.
    - Setup: Compare closing prices of 9 consecutive candlesticks with
      the closing price 4 periods earlier.
    - Countdown: Begins counting down after Setup completion.

    Attributes:
        dataprimary: Primary data feed.
        dataclose: Close price series.
        order: Current pending order.
        buyTrig: Buy trigger flag.
        sellTrig: Sell trigger flag.
        tdsl: TD sequence long counter.
        tdss: TD sequence short counter.
        buySetup: Buy setup active flag.
        sellSetup: Sell setup active flag.
        buyCountdown: Buy countdown counter.
        sellCountdown: Sell countdown counter.
        buyVal: Buy comparison value.
        sellVal: Sell comparison value.
        buySig: Buy signal flag.
        sellSig: Sell signal flag.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        candles_past_to_compare=4,
        cancel_1=True,
        cancel_2=True,
        cancel_3=2,
        recycle_12=True,
        aggressive_countdown=False,
        cancel_1618=True,
    )

    def __init__(self):
        """Initialize the TD Sequential strategy.

        Sets up all necessary state variables for tracking TD Sequential
        setup and countdown phases.
        """
        # Load parameters from config.yaml if exists
        config_path = Path(__file__).parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if 'params' in config:
                    for key, value in config['params'].items():
                        if hasattr(self.p, key):
                            setattr(self.p, key, value)

        self.dataprimary = self.datas[0]
        self.dataclose = self.dataprimary.close

        self.order = None
        self.buyTrig = False
        self.sellTrig = False

        self.tdsl = 0  # TD sequence long
        self.tdss = 0  # TD sequence short
        self.buySetup = False
        self.sellSetup = False
        self.buyCountdown = 0
        self.sellCountdown = 0
        self.buyVal = 0
        self.sellVal = 0

        self.buySig = False
        self.sellSig = False

        self.buy_nine = False
        self.sell_nine = False

        self.buy_high = 999999
        self.buy_low = 0
        self.sell_high = 999999
        self.sell_low = 0

        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.setup_buy_count = 0
        self.setup_sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status information.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        self.order = None

    def reset_on_cancel_1(self):
        """Reset all setup and countdown state variables."""
        self.buySetup = False
        self.sellSetup = False
        self.buyCountdown = 0
        self.sellCountdown = 0
        self.buy_high = 999999
        self.buy_low = 0
        self.sell_high = 999999
        self.sell_low = 0

    def reset_setup(self, buy_or_sell):
        """Reset setup trigger and counter for buy or sell direction.

        Args:
            buy_or_sell: Either "B" for buy setup or "S" for sell setup.
        """
        if buy_or_sell == "B":
            self.buyTrig = False
            self.tdsl = 0
        elif buy_or_sell == "S":
            self.sellTrig = False
            self.tdss = 0

    def reset_countdown(self, buy_or_sell, count):
        """Reset countdown phase and initialize setup for buy or sell direction.

        Args:
            buy_or_sell: Either "B" for buy countdown or "S" for sell countdown.
            count: The number of bars in the completed setup (typically 9).
        """
        if buy_or_sell == "B":
            self.buySig = ((self.dataprimary.low[0] < self.dataprimary.low[-3]) and
                          (self.dataprimary.low[0] < self.dataprimary.low[-2])) or \
                         ((self.dataprimary.low[-1] < self.dataprimary.low[-2]) and
                          (self.dataprimary.low[-1] < self.dataprimary.low[-3]))
            if self.tdsl == 9:
                self.buy_nine = True
            self.reset_setup(buy_or_sell)
            self.buySetup = True
            if self.p.cancel_2:
                self.sellSetup = False
                self.sellCountdown = 0
            self.buyCountdown = 0
            self.buy_high = max(self.dataprimary.high[n] for n in range(-(count-1), 0))
            self.buy_low = min(self.dataprimary.low[n] for n in range(-(count-1), 0))

        if buy_or_sell == "S":
            self.sellSig = ((self.dataprimary.high[0] > self.dataprimary.high[-2]) and
                           (self.dataprimary.high[0] > self.dataprimary.high[-3])) or \
                          ((self.dataprimary.high[-1] > self.dataprimary.high[-3]) and
                           (self.dataprimary.high[-1] > self.dataprimary.high[-2]))
            if self.tdss == 9:
                self.sell_nine = True
            self.reset_setup(buy_or_sell)
            self.sellSetup = True
            if self.p.cancel_2:
                self.buySetup = False
                self.buyCountdown = 0
            self.sellCountdown = 0
            self.sell_high = max(self.dataprimary.high[n] for n in range(-(count-1), 0))
            self.sell_low = min(self.dataprimary.low[n] for n in range(-(count-1), 0))

    def next(self):
        """Execute the main strategy logic for each bar.

        Implements the TD Sequential algorithm:
        1. Detect buy/sell triggers based on price comparisons
        2. Track setup progression (count consecutive bars)
        3. Transition to countdown phase when setup reaches 9
        4. Generate buy/sell signals when countdown completes
        """
        self.bar_num += 1
        self.buySig = False
        self.sellSig = False
        self.buy_nine = False
        self.sell_nine = False

        if len(self.dataclose) > self.p.candles_past_to_compare:
            # Buy trigger
            if (self.dataclose[0] < self.dataclose[-self.p.candles_past_to_compare] and
                self.dataclose[-1] > self.dataclose[-(self.p.candles_past_to_compare + 1)]):
                self.buyTrig = True
                self.sellTrig = False
                self.tdsl = 0
                self.tdss = 0

            # Sell trigger
            elif (self.dataclose[0] > self.dataclose[-self.p.candles_past_to_compare] and
                  self.dataclose[-1] < self.dataclose[-(self.p.candles_past_to_compare + 1)]):
                self.sellTrig = True
                self.buyTrig = False
                self.tdss = 0
                self.tdsl = 0

            # Buy setup numbering
            if self.dataclose[0] < self.dataclose[-self.p.candles_past_to_compare] and self.buyTrig:
                self.tdsl += 1

            # Sell setup numbering
            elif self.dataclose[0] > self.dataclose[-self.p.candles_past_to_compare] and self.sellTrig:
                self.tdss += 1

            # Buy setup reaches 9
            if self.tdsl == 9:
                if self.buySetup is True:
                    if (self.p.recycle_12 is False) or (self.p.cancel_3 == 0):
                        pass
                else:
                    self.reset_countdown("B", self.tdsl)

            # Sell setup reaches 9
            if self.tdss == 9:
                if self.sellSetup is True:
                    if (self.p.recycle_12 is False) or (self.p.cancel_3 == 0):
                        pass
                else:
                    self.reset_countdown("S", self.tdss)

            # Cancel setup 1
            if self.p.cancel_1 and self.buySetup and (self.buy_high < self.dataprimary.low[0]):
                self.reset_on_cancel_1()
            elif self.p.cancel_1 and self.sellSetup and (self.sell_low > self.dataprimary.high[0]):
                self.reset_on_cancel_1()

            countdown_compare = self.dataprimary.low[0] if self.p.aggressive_countdown else self.dataprimary.close[0]

            # Buy countdown
            if self.buySetup:
                if countdown_compare <= self.dataprimary.low[-2]:
                    self.buyCountdown += 1
                    if self.buyCountdown > 13:
                        self.buyCountdown = 13
                if self.buyCountdown == 8:
                    self.buyVal = countdown_compare
                elif self.buyCountdown == 13:
                    if self.dataprimary.low[0] <= self.buyVal:
                        # Generate buy signal
                        if not self.position:
                            self.buy(size=10)
                        self.buySetup = False
                        self.buyCountdown = 0

            # Sell countdown
            if self.sellSetup:
                if countdown_compare >= self.dataprimary.high[-2]:
                    self.sellCountdown += 1
                    if self.sellCountdown > 13:
                        self.sellCountdown = 13
                if self.sellCountdown == 8:
                    self.sellVal = countdown_compare
                elif self.sellCountdown == 13:
                    if self.dataprimary.high[0] >= self.sellVal:
                        # Generate sell signal
                        if self.position:
                            self.close()
                        self.sellSetup = False
                        self.sellCountdown = 0

    def stop(self):
        """Called when the backtest is finished."""
        pass
