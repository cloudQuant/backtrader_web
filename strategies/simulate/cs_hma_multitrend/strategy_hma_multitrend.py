#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HMA MultiTrend multi-period Hull Moving Average trend strategy.

HMA MultiTrend strategy - multi-period system using 4 HMAs to determine trend direction.
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


class HmaMultiTrendStrategy(bt.Strategy):
    """HMA MultiTrend multi-period Hull Moving Average trend strategy.

    Entry conditions:
        - Long: fast > mid1 > mid2 > mid3 (all HMAs in ascending order)
        - Short: fast < mid1 < mid2 < mid3 (all HMAs in descending order)

    Exit conditions:
        - Reverse trend signal
    """
    params = dict(
        stake=10,
        fast=10,
        mid1=20,
        mid2=30,
        mid3=50,
        atr_period=14,
        adx_period=14,
        adx_threshold=0.0,  # Disable ADX filter
    )

    def __init__(self):
        """Initialize the HMA MultiTrend strategy with indicators and tracking variables.

        Creates four Hull Moving Average indicators with different periods to
        establish a trend-following system. Also initializes ATR for volatility
        measurement and ADX for trend strength filtering. Sets up counters to
        track trading activity.
        """
        self.hma_fast = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.fast
        )
        self.hma_mid1 = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.mid1
        )
        self.hma_mid2 = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.mid2
        )
        self.hma_mid3 = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.mid3
        )

        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.adx = bt.indicators.ADX(self.data, period=self.p.adx_period)

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
        """Handle order status updates and track completed trades.

        Called by Backtrader when an order changes status. Counts completed
        buy and sell orders for performance tracking. Resets the order reference
        when the order is complete or cancelled.

        Args:
            order: The Backtrader Order object with updated status.
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
        """Execute trading logic for each bar in the backtest.

        Implements the core strategy logic:
        1. Checks if there's a pending order (no action if order pending)
        2. Applies ADX filter if enabled
        3. Evaluates trend conditions using HMA alignment
        4. Enters long when all HMAs are in ascending order
        5. Enters short when all HMAs are in descending order
        6. Exits positions when the trend reverses
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

        # ADX filter
        if self.adx[0] < self.p.adx_threshold:
            return

        # Trend conditions
        long_cond = (self.hma_fast[0] > self.hma_mid1[0] >
                     self.hma_mid2[0] > self.hma_mid3[0])
        short_cond = (self.hma_fast[0] < self.hma_mid1[0] <
                      self.hma_mid2[0] < self.hma_mid3[0])

        if not self.position:
            if long_cond:
                self.order = self.buy(size=self.p.stake)
            elif short_cond:
                self.order = self.sell(size=self.p.stake)
        else:
            # Close position on reverse signal
            if self.position.size > 0 and short_cond:
                self.order = self.close()
            elif self.position.size < 0 and long_cond:
                self.order = self.close()


# Convenience function to load parameters from configuration file
def create_strategy_from_config():
    """Convenience function to create strategy instance from config.yaml.

    Returns:
        HmaMultiTrendStrategy: Configured strategy class
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredHmaMultiTrendStrategy(HmaMultiTrendStrategy):
        params = params

    return ConfiguredHmaMultiTrendStrategy
