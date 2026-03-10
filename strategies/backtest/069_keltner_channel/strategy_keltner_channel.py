#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Keltner Channel Strategy - Trend-following strategy using Keltner Channel breakout.

Uses Keltner Channel breakout to determine trend direction and entry signals.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class KeltnerChannelIndicator(bt.Indicator):
    """Keltner Channel indicator.

    Calculates the Keltner Channel, which consists of a middle line (EMA),
    an upper band, and a lower band based on Average True Range (ATR).
    """
    lines = ('mid', 'top', 'bot')
    params = dict(period=20, atr_mult=2.0, atr_period=14)

    def __init__(self):
        """Initialize the Keltner Channel indicator.

        Calculates the middle line as an Exponential Moving Average (EMA) and
        the upper/lower bands by adding/subtracting a multiple of the Average
        True Range (ATR) to/from the middle line.
        """
        self.l.mid = bt.indicators.EMA(self.data.close, period=self.p.period)
        atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.l.top = self.l.mid + self.p.atr_mult * atr
        self.l.bot = self.l.mid - self.p.atr_mult * atr


class KeltnerChannelStrategy(bt.Strategy):
    """Keltner Channel strategy.

    Entry conditions:
        - Long: Price breaks above upper band

    Exit conditions:
        - Price falls below middle band

    Attributes:
        kc: Keltner Channel indicator instance.
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        stake=10,
        period=20,
        atr_mult=2.0,
    )

    def __init__(self):
        """Initialize the Keltner Channel strategy.

        Sets up the Keltner Channel indicator and initializes tracking variables
        for orders, bar count, and trade statistics.
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

        self.kc = KeltnerChannelIndicator(
            self.data, period=self.p.period, atr_mult=self.p.atr_mult
        )

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order notifications and update trade statistics.

        Args:
            order: The order object with status information.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements the Keltner Channel breakout strategy:
        - Long entry when price breaks above the upper band
        - Exit when price falls below the middle band
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Price breaks above upper band
            if self.data.close[0] > self.kc.top[0]:
                self.order = self.buy(size=self.p.stake)
        else:
            # Price falls below middle band
            if self.data.close[0] < self.kc.mid[0]:
                self.order = self.close()
