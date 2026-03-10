#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ichimoku Cloud trading strategy.

Ichimoku Cloud strategy - trend-following system based on Ichimoku Kinko Hyo indicator.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import yaml
from datetime import datetime
from pathlib import Path
import backtrader as bt


def load_config(config_path: str = None) -> dict:
    """Load configuration file from config.yaml.

    Args:
        config_path: Path to configuration file, defaults to config.yaml in current directory

    Returns:
        dict: Configuration dictionary
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


class IchimokuCloudStrategy(bt.Strategy):
    """Ichimoku Cloud trading strategy.

    This strategy implements a trend-following approach using the Ichimoku Kinko
    Hyo technical indicator. The Ichimoku Cloud (Kumo) is used to determine
    market trend direction and generate trading signals based on price position
    relative to the cloud boundaries.

    Entry Conditions:
        - Long: Price > Senkou Span A and Price > Senkou Span B (price is above
          the cloud, indicating bullish trend)

    Exit Conditions:
        - Price < Senkou Span A and Price < Senkou Span B (price breaks below
          both cloud boundaries, indicating trend reversal)

    Attributes:
        ichimoku: The Ichimoku indicator instance providing cloud calculations.
        order: Reference to the current pending order, or None if no order is
            pending.
        bar_num: Counter tracking the total number of bars processed.
        buy_count: Counter tracking the number of executed buy orders.
        sell_count: Counter tracking the number of executed sell orders.

    Parameters:
        stake: Number of shares/units per trade (default: 10).
        tenkan: Tenkan-sen (Conversion Line) period in bars (default: 9).
        kijun: Kijun-sen (Base Line) period in bars (default: 26).
        senkou: Senkou Span B period in bars (default: 52).
        senkou_lead: Forward displacement for cloud in bars (default: 26).
        chikou: Chikou Span (Lagging Line) displacement in bars (default: 26).
    """
    params = dict(
        stake=10,
        tenkan=9,
        kijun=26,
        senkou=52,
        senkou_lead=26,
        chikou=26,
    )

    def __init__(self):
        """Initialize the Ichimoku Cloud strategy.

        Sets up the Ichimoku indicator with configurable parameters and
        initializes tracking variables for order management and statistics.
        """
        self.ichimoku = bt.indicators.Ichimoku(
            self.data,
            tenkan=self.p.tenkan,
            kijun=self.p.kijun,
            senkou=self.p.senkou,
            senkou_lead=self.p.senkou_lead,
            chikou=self.p.chikou,
        )

        self.order = None
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
        """Handle order status updates and track trade execution statistics.

        This method is called by the backtrader engine when an order's status
        changes. It updates the buy/sell counters when orders are completed
        and resets the order reference when the order is no longer active.

        Args:
            order: The backtrader Order object with updated status information.
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

        This method is called by the backtrader engine for each new bar.
        It implements the core strategy logic:
        1. Checks for pending orders and returns if one exists
        2. Retrieves current price and Ichimoku cloud values
        3. Enters long position when price is above cloud
        4. Exits position when price breaks below cloud

        Trading Logic:
            - No position: Enter long if close > senkou_a AND close > senkou_b
            - Has position: Close position if close < senkou_a AND close < senkou_b
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

        close = self.data.close[0]
        senkou_a = self.ichimoku.senkou_span_a[0]
        senkou_b = self.ichimoku.senkou_span_b[0]

        if not self.position:
            # Price is above cloud (relaxed condition)
            if close > senkou_a and close > senkou_b:
                self.order = self.buy(size=self.p.stake)
        else:
            # Price breaks below both cloud boundaries
            if close < senkou_a and close < senkou_b:
                self.order = self.close()


# Convenience function to load parameters from configuration file
def create_strategy_from_config():
    """Convenience function to create strategy instance from config.yaml.

    Returns:
        IchimokuCloudStrategy: Configured strategy class
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredIchimokuCloudStrategy(IchimokuCloudStrategy):
        params = params

    return ConfiguredIchimokuCloudStrategy
