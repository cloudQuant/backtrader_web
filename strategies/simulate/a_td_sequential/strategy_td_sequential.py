#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TD Sequential Strategy - Trading based on Tom DeMark's TD Sequential indicator.

This strategy implements Tom DeMark's TD Sequential indicator which identifies
potential price exhaustion points through a setup and countdown phase.

Reference: https://github.com/mk99999/TD-seq
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import logging
import os
from datetime import datetime
from pathlib import Path

import backtrader as bt
import yaml

logger = logging.getLogger(__name__)


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
        setup and countdown phases. Loads params and position_size from config.yaml.
        """
        config_path = Path(__file__).parent / "config.yaml"
        self.position_size = 1
        self._debug = os.environ.get("TD_DEBUG", "").strip().lower() in ("1", "true", "yes")

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if config:
                        if config.get("params"):
                            for key, value in config["params"].items():
                                if hasattr(self.p, key):
                                    setattr(self.p, key, value)
                        backtest = config.get("backtest") or {}
                        pos = backtest.get("position_size")
                        if pos is not None:
                            try:
                                self.position_size = int(pos)
                            except (TypeError, ValueError):
                                logger.warning(
                                    "Invalid position_size in config: %s, using 1",
                                    pos,
                                )
            except (OSError, yaml.YAMLError) as e:
                logger.warning("Failed to load config.yaml: %s", e)

        self.dataprimary = self.datas[0]
        self.dataclose = self.dataprimary.close

        self.order = None
        self.buyTrig = False
        self.sellTrig = False

        self.tdsl = 0
        self.tdss = 0
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

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.setup_buy_count = 0
        self.setup_sell_count = 0
        self.tick_count = 0

    def notify_tick(self, tick):
        """Handle tick data. Logs tick info only when TD_DEBUG=1."""
        self.tick_count += 1
        if not self._debug:
            return
        price = float(getattr(tick, "price", 0) or 0)
        volume = float(getattr(tick, "volume", 0) or 0)
        symbol = getattr(tick, "symbol", "")
        ts = getattr(tick, "timestamp", None)
        dt_attr = getattr(tick, "datetime", None)
        direction = getattr(tick, "direction", "")
        if dt_attr is not None:
            time_str = str(dt_attr)
        elif ts is not None:
            try:
                time_str = datetime.fromtimestamp(float(ts)).isoformat()
            except (ValueError, TypeError, OSError) as e:
                logger.debug("Could not convert timestamp %s: %s", ts, e)
                time_str = str(ts)
        else:
            time_str = "-"
        print(
            f"[TICK #{self.tick_count}] symbol={symbol} price={price:.2f} "
            f"volume={volume:.0f} direction={direction} time={time_str}"
        )

    def notify_order(self, order):
        """Handle order status updates."""
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
        """Reset setup trigger and counter for buy or sell direction."""
        if buy_or_sell == "B":
            self.buyTrig = False
            self.tdsl = 0
        elif buy_or_sell == "S":
            self.sellTrig = False
            self.tdss = 0

    def reset_countdown(self, buy_or_sell, count):
        """Reset countdown phase and initialize setup for buy or sell direction."""
        if buy_or_sell == "B":
            self.buySig = (
                (self.dataprimary.low[0] < self.dataprimary.low[-3])
                and (self.dataprimary.low[0] < self.dataprimary.low[-2])
            ) or (
                (self.dataprimary.low[-1] < self.dataprimary.low[-2])
                and (self.dataprimary.low[-1] < self.dataprimary.low[-3])
            )
            if self.tdsl == 9:
                self.buy_nine = True
            self.reset_setup(buy_or_sell)
            self.buySetup = True
            if self.p.cancel_2:
                self.sellSetup = False
                self.sellCountdown = 0
            self.buyCountdown = 0
            self.buy_high = max(self.dataprimary.high[n] for n in range(-(count - 1), 0))
            self.buy_low = min(self.dataprimary.low[n] for n in range(-(count - 1), 0))

        elif buy_or_sell == "S":
            self.sellSig = (
                (self.dataprimary.high[0] > self.dataprimary.high[-2])
                and (self.dataprimary.high[0] > self.dataprimary.high[-3])
            ) or (
                (self.dataprimary.high[-1] > self.dataprimary.high[-3])
                and (self.dataprimary.high[-1] > self.dataprimary.high[-2])
            )
            if self.tdss == 9:
                self.sell_nine = True
            self.reset_setup(buy_or_sell)
            self.sellSetup = True
            if self.p.cancel_2:
                self.buySetup = False
                self.buyCountdown = 0
            self.sellCountdown = 0
            self.sell_high = max(self.dataprimary.high[n] for n in range(-(count - 1), 0))
            self.sell_low = min(self.dataprimary.low[n] for n in range(-(count - 1), 0))

    def next(self):
        """Execute the main strategy logic for each bar."""
        self.bar_num += 1

        if self._debug and len(self.dataprimary) > 0:
            dt = bt.num2date(self.dataprimary.datetime[0])
            vol = int(self.dataprimary.volume[0]) if len(self.dataprimary.volume) > 0 else 0
            print(
                f"[BAR #{self.bar_num}] {dt} O={self.dataprimary.open[0]:.2f} "
                f"H={self.dataprimary.high[0]:.2f} L={self.dataprimary.low[0]:.2f} "
                f"C={self.dataprimary.close[0]:.2f} V={vol}"
            )

        self.buySig = False
        self.sellSig = False
        self.buy_nine = False
        self.sell_nine = False

        if len(self.dataclose) > self.p.candles_past_to_compare:
            if (
                self.dataclose[0] < self.dataclose[-self.p.candles_past_to_compare]
                and self.dataclose[-1] > self.dataclose[-(self.p.candles_past_to_compare + 1)]
            ):
                self.buyTrig = True
                self.sellTrig = False
                self.tdsl = 0
                self.tdss = 0

            elif (
                self.dataclose[0] > self.dataclose[-self.p.candles_past_to_compare]
                and self.dataclose[-1] < self.dataclose[-(self.p.candles_past_to_compare + 1)]
            ):
                self.sellTrig = True
                self.buyTrig = False
                self.tdss = 0
                self.tdsl = 0

            if self.dataclose[0] < self.dataclose[-self.p.candles_past_to_compare] and self.buyTrig:
                self.tdsl += 1

            elif self.dataclose[0] > self.dataclose[-self.p.candles_past_to_compare] and self.sellTrig:
                self.tdss += 1

            if self.tdsl == 9:
                if self.buySetup is True:
                    if (self.p.recycle_12 is False) or (self.p.cancel_3 == 0):
                        pass
                else:
                    self.reset_countdown("B", self.tdsl)

            if self.tdss == 9:
                if self.sellSetup is True:
                    if (self.p.recycle_12 is False) or (self.p.cancel_3 == 0):
                        pass
                else:
                    self.reset_countdown("S", self.tdss)

            if self.p.cancel_1 and self.buySetup and (self.buy_high < self.dataprimary.low[0]):
                self.reset_on_cancel_1()
            elif self.p.cancel_1 and self.sellSetup and (self.sell_low > self.dataprimary.high[0]):
                self.reset_on_cancel_1()

            countdown_compare = (
                self.dataprimary.low[0] if self.p.aggressive_countdown else self.dataprimary.close[0]
            )

            if self.buySetup:
                if countdown_compare <= self.dataprimary.low[-2]:
                    self.buyCountdown += 1
                    if self.buyCountdown > 13:
                        self.buyCountdown = 13
                if self.buyCountdown == 8:
                    self.buyVal = countdown_compare
                elif self.buyCountdown == 13:
                    if self.dataprimary.low[0] <= self.buyVal:
                        if not self.position:
                            self.buy(size=self.position_size)
                        self.buySetup = False
                        self.buyCountdown = 0

            if self.sellSetup:
                if countdown_compare >= self.dataprimary.high[-2]:
                    self.sellCountdown += 1
                    if self.sellCountdown > 13:
                        self.sellCountdown = 13
                if self.sellCountdown == 8:
                    self.sellVal = countdown_compare
                elif self.sellCountdown == 13:
                    if self.dataprimary.high[0] >= self.sellVal:
                        if self.position:
                            self.close()
                        self.sellSetup = False
                        self.sellCountdown = 0

    def stop(self):
        """Called when the backtest or live session is finished."""
        if self._debug:
            print(
                f"[TD Sequential] Finished: bars={self.bar_num} "
                f"buys={self.buy_count} sells={self.sell_count}"
            )
