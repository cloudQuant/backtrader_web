#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Adaptive SuperTrend Strategy

自适应SuperTrend策略 - 基于ATR动态调整倍数的趋势跟踪系统。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import yaml
from pathlib import Path
import backtrader as bt


def load_config(config_path: str = None) -> dict:
    """从config.yaml加载配置文件

    Args:
        config_path: 配置文件路径，默认为当前目录下的config.yaml

    Returns:
        dict: 配置字典
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


class AdaptiveSuperTrendIndicator(bt.Indicator):
    """Adaptive SuperTrend Indicator.

    Dynamically adjusts multiplier based on ATR:
    base_mult = a_coef + b_coef * avg_atr
    dyn_mult = base_mult * (avg_atr / atr)
    """
    lines = ('st',)
    params = dict(
        period=20,
        vol_lookback=20,
        a_coef=0.5,
        b_coef=2.0,
        min_mult=0.5,
        max_mult=3.0,
    )

    def __init__(self):
        """Initialize the Adaptive SuperTrend indicator with sub-indicators.

        Sets up the ATR (Average True Range) indicator, smoothed ATR using EMA,
        and the mid-price (HL/2) calculation. Also configures the minimum
        period required for calculation based on the ATR and EMA periods.

        The indicator uses:
            - ATR: Measures market volatility
            - EMA of ATR: Provides baseline volatility for adaptive calculation
            - HL/2: Mid-price for band calculation
        """
        # ATR indicator
        self.atr = bt.indicators.ATR(self.data, period=self.p.period)

        # Smoothed ATR as baseline
        self.avg_atr = bt.indicators.EMA(self.atr, period=self.p.vol_lookback)

        # Mid-price (H+L)/2
        self.hl2 = (self.data.high + self.data.low) / 2.0

        self.addminperiod(max(self.p.period, self.p.vol_lookback) + 1)

    def _calc_bands(self):
        """Calculate upper and lower bands.

        Returns:
            tuple: A tuple containing (upper, lower) band values.
        """
        atr_val = float(self.atr[0])
        avg_atr_val = float(self.avg_atr[0])

        if atr_val <= 0:
            atr_val = 0.0001

        # Calculate base multiplier
        base_mult = self.p.a_coef + self.p.b_coef * avg_atr_val

        # Clamp multiplier to allowed range
        base_mult = max(self.p.min_mult, min(self.p.max_mult, base_mult))

        # Dynamic multiplier
        dyn_mult = base_mult * (avg_atr_val / atr_val) if atr_val > 0 else base_mult
        dyn_mult = max(self.p.min_mult, min(self.p.max_mult, dyn_mult))

        # Calculate upper and lower bands
        hl2 = float(self.hl2[0])
        upper = hl2 + dyn_mult * atr_val
        lower = hl2 - dyn_mult * atr_val

        return upper, lower

    def nextstart(self):
        """Initialize SuperTrend value on first call (replaces len(self)==1 check).

        Uses UPPER band as initial value to maintain consistency with master branch.
        """
        upper, lower = self._calc_bands()
        # Use UPPER band as initial value, consistent with master branch behavior
        self.l.st[0] = upper

    def next(self):
        """Calculate SuperTrend value for current bar using recursive logic.

        This method implements the core SuperTrend algorithm that adapts
        the multiplier based on ATR volatility. The recursive logic ensures
        the SuperTrend line maintains direction until a confirmed reversal.

        Algorithm:
            1. Calculate current upper and lower bands using dynamic multiplier
            2. If close price > previous SuperTrend: use max(lower, previous ST)
            3. If close price <= previous SuperTrend: use min(upper, previous ST)

        The recursive logic prevents whipsaws by requiring the SuperTrend
        line to maintain its direction (uptrend or downtrend) until price
        conclusively breaks through the opposite band.

        Band Calculation:
            - Uses dynamic multiplier based on ATR volatility
            - Upper band = HL/2 + (dynamic_multiplier * ATR)
            - Lower band = HL/2 - (dynamic_multiplier * ATR)
            - Dynamic multiplier adapts to current vs average volatility
        """
        upper, lower = self._calc_bands()

        # Recursive SuperTrend logic
        prev_st = self.l.st[-1]
        if self.data.close[0] > prev_st:
            # In uptrend: maintain highest value between lower band and previous ST
            # This ensures the ST line doesn't drop below established support
            self.l.st[0] = max(lower, prev_st)
        else:
            # In downtrend: maintain lowest value between upper band and previous ST
            # This ensures the ST line doesn't rise above established resistance
            self.l.st[0] = min(upper, prev_st)

    def preonce(self, start, end):
        """Preprocessing in runonce mode - no operation, handled by once().

        Args:
            start: Start index for processing.
            end: End index for processing.
        """
        pass

    def oncestart(self, start, end):
        """Initial runonce mode processing - no operation, handled by once().

        Args:
            start: Start index for processing.
            end: End index for processing.
        """
        pass

    def once(self, start, end):
        """Populate arrays directly in runonce mode, ensuring consistency with nextstart/next logic.

        Args:
            start: Start index for processing.
            end: End index for processing.
        """
        atr_array = self.atr.lines[0].array
        avg_atr_array = self.avg_atr.lines[0].array
        hl2_array = self.hl2.array
        close_array = self.data.close.array
        st_array = self.lines.st.array

        # Use EMA's minperiod since EMA is the last sub-indicator to be ready
        minperiod = self.avg_atr._minperiod
        actual_end = min(end, len(atr_array), len(avg_atr_array), len(hl2_array), len(close_array))

        # Ensure array size is sufficient
        while len(st_array) < actual_end:
            st_array.append(0.0)

        # Start calculation from EMA minperiod-1 (corresponds to nextstart call time)
        for i in range(minperiod - 1, actual_end):
            atr_val = float(atr_array[i])
            avg_atr_val = float(avg_atr_array[i])

            if atr_val <= 0:
                atr_val = 0.0001

            base_mult = self.p.a_coef + self.p.b_coef * avg_atr_val
            base_mult = max(self.p.min_mult, min(self.p.max_mult, base_mult))
            dyn_mult = base_mult * (avg_atr_val / atr_val) if atr_val > 0 else base_mult
            dyn_mult = max(self.p.min_mult, min(self.p.max_mult, dyn_mult))

            hl2 = float(hl2_array[i])
            upper = hl2 + dyn_mult * atr_val
            lower = hl2 - dyn_mult * atr_val

            if i == minperiod - 1:
                # Seed first value (use UPPER band, consistent with master branch)
                st_array[i] = upper
            else:
                # Recursive logic (corresponds to next)
                prev_st = st_array[i - 1]
                close_val = float(close_array[i])
                if close_val > prev_st:
                    st_array[i] = max(lower, prev_st)
                else:
                    st_array[i] = min(upper, prev_st)


class AdaptiveSuperTrendStrategy(bt.Strategy):
    """Adaptive SuperTrend Strategy.

    Entry conditions:
        - Long: Price breaks above SuperTrend line
        - Exit: Price breaks below SuperTrend line
    """
    params = dict(
        stake=10,
        st_period=20,
        vol_lookback=20,
        a_coef=0.5,
        b_coef=2.0,
        min_mult=0.5,
        max_mult=3.0,
    )

    def __init__(self):
        """Initialize the Adaptive SuperTrend strategy.

        Sets up the Adaptive SuperTrend indicator with strategy parameters,
        initializes order tracking, and sets up counters for tracking
        trading activity (bar number, buy count, sell count).

        The strategy uses:
            - dataclose: Reference to close prices for convenience
            - st: Adaptive SuperTrend indicator instance
            - order: Tracks pending orders to prevent over-trading
            - bar_num: Counts total bars processed
            - buy_count: Counts total buy orders executed
            - sell_count: Counts total sell orders executed
        """
        self.dataclose = self.datas[0].close

        # Adaptive SuperTrend indicator
        self.st = AdaptiveSuperTrendIndicator(
            self.data,
            period=self.p.st_period,
            vol_lookback=self.p.vol_lookback,
            a_coef=self.p.a_coef,
            b_coef=self.p.b_coef,
            min_mult=self.p.min_mult,
            max_mult=self.p.max_mult,
        )

        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status notifications and update trade statistics.

        This method is called by the broker whenever an order's status changes.
        It updates the buy/sell counters when orders are completed and clears
        the pending order reference.

        Args:
            order: The order object with updated status information.

        Behavior:
            - Submitted/Accepted orders: No action taken, awaiting completion
            - Completed orders: Increment buy_count or sell_count based on order type
            - Clears self.order reference to allow new orders
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

        This method is called on every bar (after prenext/nextstart phases).
        It implements the trend-following logic:
            - Enter long when price breaks above SuperTrend line
            - Exit long when price breaks below SuperTrend line

        The strategy only holds long positions and exits by closing
        the position (no short selling).

        Trading Rules:
            - Only one active order at a time (checked via self.order)
            - Long entry: close price > SuperTrend value
            - Long exit: close price < SuperTrend value
        """
        self.bar_num += 1

        if self.order:
            return

        price = self.data.close[0]
        st_val = self.st.st[0]

        if not self.position:
            # Long entry: price above ST line
            if price > st_val:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: price breaks below ST line
            if price < st_val:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        AdaptiveSuperTrendStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredAdaptiveSuperTrendStrategy(AdaptiveSuperTrendStrategy):
        params = params

    return ConfiguredAdaptiveSuperTrendStrategy
