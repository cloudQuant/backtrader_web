#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Donchian Channel Strategy - Classic trend-following breakout strategy.

This strategy implements a classic trend-following approach using the
Donchian Channel indicator. It goes long when price breaks above the
upper channel and short when price breaks below the lower channel.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from datetime import datetime
from pathlib import Path


class DonchianChannelIndicator(bt.Indicator):
    """Donchian Channel indicator.

    The Donchian Channel is a trend-following indicator that calculates
    the highest high and lowest low over a specified period.

    Attributes:
        dch: Donchian Channel High (upper band) - highest high over period.
        dcl: Donchian Channel Low (lower band) - lowest low over period.
        dcm: Donchian Channel Middle (middle band) - average of upper and lower.
    """
    lines = ('dch', 'dcl', 'dcm')
    params = dict(period=20)

    def __init__(self):
        """Initialize the Donchian Channel indicator.

        Sets up the three channel lines using the Highest and Lowest indicators.
        """
        self.lines.dch = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.lines.dcl = bt.indicators.Lowest(self.data.low, period=self.p.period)
        self.lines.dcm = (self.lines.dch + self.lines.dcl) / 2


class DonchianChannelStrategy(bt.Strategy):
    """Donchian Channel breakout strategy.

    This strategy implements a classic trend-following approach using the
    Donchian Channel indicator:
    - Go long when price breaks above the upper channel
    - Go short when price breaks below the lower channel

    Attributes:
        dataclose: Reference to the close price data.
        indicator: Donchian Channel indicator instance.
        order: Current pending order.
        last_operation: Last executed operation ("BUY" or "SELL").
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        stake=10,
        period=20,
    )

    def __init__(self):
        """Initialize the Donchian Channel strategy.

        Sets up the indicator, data references, and tracking variables for
        orders and statistics.
        """
        # Load parameters from config.yaml if exists
        config_path = Path(__file__).parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if config.get('params'):
                    for key, value in config['params'].items():
                        if hasattr(self.p, key):
                            setattr(self.p, key, value)

        self.dataclose = self.datas[0].close
        self.indicator = DonchianChannelIndicator(self.datas[0], period=self.p.period)

        self.order = None
        self.last_operation = "SELL"

        # Statistics variables
        self.bar_num = 0
        self.tick_count = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_tick(self, tick):
        """收到 tick 数据时调用，打印 tick 以证明策略在接收实时行情。"""
        self.tick_count += 1
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
            except Exception:
                time_str = str(ts)
        else:
            time_str = "-"
        print(f"[TICK #{self.tick_count}] symbol={symbol} price={price:.2f} volume={volume:.0f} direction={direction} time={time_str}")

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.last_operation = "BUY"
            else:
                self.sell_count += 1
                self.last_operation = "SELL"

        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements the Donchian Channel breakout strategy:
        - Buy when close price breaks above the upper channel
        - Sell when close price breaks below the lower channel
        """
        self.bar_num += 1

        # 打印 bar 数据，证明策略在接收实时行情并运行
        d = self.datas[0] if hasattr(self, 'datas') else getattr(self, 'data', getattr(self, 'data0', self.datas[0]))
        if len(d) > 0:
            dt = bt.num2date(d.datetime[0])
            vol = int(d.volume[0]) if len(d.volume) > 0 else 0
            bn = getattr(self, 'bar_num', getattr(self, 'bar_count', 0))
            print(f"[BAR #{bn}] {dt} O={d.open[0]:.2f} H={d.high[0]:.2f} L={d.low[0]:.2f} C={d.close[0]:.2f} V={vol}")

        if self.order:
            return

        if self.dataclose[0] > self.indicator.dch[0] and self.last_operation != "BUY":
            self.order = self.buy(size=self.p.stake)
        elif self.dataclose[0] < self.indicator.dcl[0] and self.last_operation != "SELL":
            self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Called when the backtest is finished."""
        pass
