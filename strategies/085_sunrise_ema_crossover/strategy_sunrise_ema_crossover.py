#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sunrise Volatility Expansion Strategy

日出波动率扩展策略 - 完整的四阶段状态机入场系统。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import yaml
import math
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


class SunriseVolatilityExpansionStrategy(bt.Strategy):
    """Sunrise Volatility Expansion Strategy (Complete 4-Phase State Machine)

    Core Logic:
    - Phase 1 (SCANNING): Scan EMA crossover signals, apply multiple filters
    - Phase 2 (ARMED): Wait for pullback candle confirmation
    - Phase 3 (WINDOW_OPEN): Calculate dual-side price channel
    - Phase 4: Monitor price breakthrough of channel upper (long)/lower (short) edge

    Filters:
    - EMA alignment conditions
    - Price filter EMA
    - Candle direction filter
    - EMA slope angle filter
    - ATR volatility filter
    """
    params = dict(
        stake=10,
        # EMA parameters
        ema_fast=14,
        ema_medium=14,
        ema_slow=24,
        ema_confirm=1,
        ema_filter_price=100,
        # ATR parameters
        atr_period=10,
        atr_sl_mult=4.5,
        atr_tp_mult=6.5,
        # Long position filters
        long_use_ema_order=False,
        long_use_price_filter=True,
        long_use_candle_direction=False,
        long_use_angle_filter=False,
        long_min_angle=35.0,
        long_max_angle=95.0,
        long_angle_scale=10.0,
        # Pullback entry parameters
        use_pullback_entry=True,
        long_pullback_candles=3,
        entry_window_periods=1,
        window_price_offset_mult=0.001,
        # Global invalidation
        use_global_invalidation=True,
    )

    def __init__(self):
        """Initialize the Sunrise Volatility Expansion Strategy.

        Sets up all necessary indicators, data references, and state machine
        variables for the 4-phase entry system.

        Initialization includes:
        - Data access references (open, high, low, close)
        - EMA indicators for trend detection and filtering
        - ATR indicator for volatility-based stop loss/take profit
        - State machine variables for tracking entry phases
        - Trade tracking variables (orders, entry price, stop loss, take profit)
        - Performance counters (bar count, buy/sell counts)
        """
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        # EMA indicators
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast)
        self.ema_medium = bt.indicators.EMA(self.data.close, period=self.p.ema_medium)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow)
        self.ema_confirm = bt.indicators.EMA(self.data.close, period=self.p.ema_confirm)
        self.ema_filter_price = bt.indicators.EMA(self.data.close, period=self.p.ema_filter_price)

        # ATR
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)

        self.order = None
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.last_entry_bar = None

        # 4-phase state machine
        self.entry_state = "SCANNING"  # SCANNING, ARMED_LONG, ARMED_SHORT, WINDOW_OPEN
        self.armed_direction = None
        self.pullback_candle_count = 0
        self.last_pullback_candle_high = None
        self.last_pullback_candle_low = None
        self.window_top_limit = None
        self.window_bottom_limit = None
        self.window_expiry_bar = None
        self.window_bar_start = None
        self.signal_detection_atr = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def _cross_above(self, a, b):
        """Detect if a crosses above b."""
        try:
            return (float(a[0]) > float(b[0])) and (float(a[-1]) <= float(b[-1]))
        except (IndexError, ValueError, TypeError):
            return False

    def _cross_below(self, a, b):
        """Detect if a crosses below b."""
        try:
            return (float(a[0]) < float(b[0])) and (float(a[-1]) >= float(b[-1]))
        except (IndexError, ValueError, TypeError):
            return False

    def _angle(self):
        """Calculate EMA slope angle."""
        try:
            current_ema = float(self.ema_confirm[0])
            previous_ema = float(self.ema_confirm[-1])
            rise = (current_ema - previous_ema) * self.p.long_angle_scale
            return math.degrees(math.atan(rise))
        except (IndexError, ValueError, TypeError, ZeroDivisionError):
            return float('nan')

    def _reset_entry_state(self):
        """Reset entry state machine."""
        self.entry_state = "SCANNING"
        self.armed_direction = None
        self.pullback_candle_count = 0
        self.last_pullback_candle_high = None
        self.last_pullback_candle_low = None
        self.window_top_limit = None
        self.window_bottom_limit = None
        self.window_expiry_bar = None
        self.window_bar_start = None

    def _phase1_scan_for_signal(self):
        """Phase 1: Scan EMA crossover signals."""
        # Check long signal
        try:
            prev_bull = self.data.close[-1] > self.data.open[-1]
        except IndexError:
            prev_bull = False

        # EMA crossover detection (confirm crosses above any EMA)
        cross_fast = self._cross_above(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_above(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_above(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        # Candle direction filter
        candle_ok = True
        if self.p.long_use_candle_direction:
            candle_ok = prev_bull

        if candle_ok and cross_any:
            signal_valid = True

            # EMA alignment conditions
            if self.p.long_use_ema_order:
                ema_order_ok = (
                    self.ema_confirm[0] > self.ema_fast[0] and
                    self.ema_confirm[0] > self.ema_medium[0] and
                    self.ema_confirm[0] > self.ema_slow[0]
                )
                if not ema_order_ok:
                    signal_valid = False

            # Price filter EMA
            if signal_valid and self.p.long_use_price_filter:
                price_above = self.data.close[0] > self.ema_filter_price[0]
                if not price_above:
                    signal_valid = False

            # Angle filter
            if signal_valid and self.p.long_use_angle_filter:
                current_angle = self._angle()
                if not (self.p.long_min_angle <= current_angle <= self.p.long_max_angle):
                    signal_valid = False

            if signal_valid:
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                self.signal_detection_atr = current_atr
                return 'LONG'

        return None

    def _phase2_confirm_pullback(self, armed_direction):
        """Phase 2: Confirm pullback candles."""
        is_pullback = False
        if armed_direction == 'LONG':
            is_pullback = self.data.close[0] < self.data.open[0]  # Bearish candle

        if is_pullback:
            self.pullback_candle_count += 1
            max_candles = self.p.long_pullback_candles

            if self.pullback_candle_count >= max_candles:
                self.last_pullback_candle_high = float(self.data.high[0])
                self.last_pullback_candle_low = float(self.data.low[0])
                return True
        else:
            # Non-pullback candle, global invalidation
            if self.p.use_global_invalidation:
                self._reset_entry_state()

        return False

    def _phase3_open_breakout_window(self, armed_direction):
        """Phase 3: Open breakout window."""
        current_bar = len(self)
        self.window_bar_start = current_bar

        window_periods = self.p.entry_window_periods
        self.window_expiry_bar = current_bar + window_periods

        # Calculate dual-side price channel
        last_high = self.last_pullback_candle_high
        last_low = self.last_pullback_candle_low
        candle_range = last_high - last_low
        price_offset = candle_range * self.p.window_price_offset_mult

        self.window_top_limit = last_high + price_offset
        self.window_bottom_limit = last_low - price_offset

        self.entry_state = "WINDOW_OPEN"

    def _phase4_monitor_window(self, armed_direction):
        """Phase 4: Monitor breakout window."""
        current_bar = len(self)

        if current_bar < self.window_bar_start:
            return None

        # Timeout check
        if current_bar > self.window_expiry_bar:
            self.entry_state = f"ARMED_{armed_direction}"
            self.pullback_candle_count = 0
            self.window_top_limit = None
            self.window_bottom_limit = None
            self.window_expiry_bar = None
            return None

        current_high = self.data.high[0]
        current_low = self.data.low[0]

        if armed_direction == 'LONG':
            # Success: Price breaks through upper edge
            if current_high >= self.window_top_limit:
                return 'SUCCESS'
            # Failure: Price breaks through lower edge
            elif current_low <= self.window_bottom_limit:
                self.entry_state = "ARMED_LONG"
                self.pullback_candle_count = 0
                self.window_top_limit = None
                self.window_bottom_limit = None
                return None

        return None

    def notify_order(self, order):
        """Handle order notifications and update strategy state.

        This method is called by the backtrader engine when an order's status
        changes. It updates trade tracking variables and calculates stop loss
        and take profit levels for completed buy orders.

        Args:
            order (bt.Order): The order object with updated status.

        Order Handling:
        - Ignores Submitted and Accepted orders (still pending)
        - For Completed buy orders:
            - Increments buy counter
            - Records entry price
            - Calculates ATR-based stop loss (bar low - ATR * multiplier)
            - Calculates ATR-based take profit (bar high + ATR * multiplier)
            - Records entry bar number
        - For Completed sell orders:
            - Increments sell counter
        - Clears pending order reference after processing
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.entry_price = order.executed.price
                atr_now = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 1.0
                bar_low = float(self.data.low[0])
                bar_high = float(self.data.high[0])
                self.stop_loss = bar_low - atr_now * self.p.atr_sl_mult
                self.take_profit = bar_high + atr_now * self.p.atr_tp_mult
                self.last_entry_bar = len(self)
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute the main strategy logic for each bar.

        This method implements the complete 4-phase state machine for trade entry:
        1. Position management (stop loss/take profit checks)
        2. Phase 1 (SCANNING): EMA crossover signal detection
        3. Phase 2 (ARMED): Pullback candle confirmation
        4. Phase 3 (WINDOW_OPEN): Price channel calculation
        5. Phase 4: Breakout monitoring and trade execution

        The method also handles global invalidation when opposite signals appear
        during armed states, and manages the transition between all phases.
        """
        self.bar_num += 1
        current_bar = len(self)

        if self.order:
            return

        # Position management: Stop loss and take profit
        if self.position:
            if self.datalow[0] <= self.stop_loss:
                self.order = self.close()
                self._reset_entry_state()
                return
            elif self.datahigh[0] >= self.take_profit:
                self.order = self.close()
                self._reset_entry_state()
                return
            return  # No new entry logic while in position

        # Clear orders when not in position
        if not self.position:
            self.stop_loss = 0
            self.take_profit = 0

        # 4-phase state machine
        if not self.p.use_pullback_entry:
            # Non-pullback mode: Direct entry
            signal = self._phase1_scan_for_signal()
            if signal == 'LONG':
                self.order = self.buy(size=self.p.stake)
            return

        # Global invalidation check
        if self.entry_state in ["ARMED_LONG", "ARMED_SHORT"]:
            if self.entry_state == "ARMED_LONG":
                # Check if short signal appears
                try:
                    prev_bear = self.data.close[-1] < self.data.open[-1]
                    cross_fast = self._cross_below(self.ema_confirm, self.ema_fast)
                    cross_medium = self._cross_below(self.ema_confirm, self.ema_medium)
                    cross_slow = self._cross_below(self.ema_confirm, self.ema_slow)
                    if prev_bear and (cross_fast or cross_medium or cross_slow):
                        self._reset_entry_state()
                except IndexError:
                    pass

        # State machine routing
        if self.entry_state == "SCANNING":
            signal_direction = self._phase1_scan_for_signal()
            if signal_direction:
                self.entry_state = f"ARMED_{signal_direction}"
                self.armed_direction = signal_direction
                self.pullback_candle_count = 0

        elif self.entry_state in ["ARMED_LONG", "ARMED_SHORT"]:
            if self._phase2_confirm_pullback(self.armed_direction):
                self.entry_state = "WINDOW_OPEN"
                self._phase3_open_breakout_window(self.armed_direction)

        elif self.entry_state == "WINDOW_OPEN":
            breakout_status = self._phase4_monitor_window(self.armed_direction)

            if breakout_status == 'SUCCESS':
                signal_direction = self.armed_direction

                atr_now = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                if atr_now <= 0:
                    self._reset_entry_state()
                    return

                entry_price = float(self.data.close[0])
                bar_low = float(self.data.low[0])
                bar_high = float(self.data.high[0])

                if signal_direction == 'LONG':
                    self.stop_loss = bar_low - atr_now * self.p.atr_sl_mult
                    self.take_profit = bar_high + atr_now * self.p.atr_tp_mult
                    self.order = self.buy(size=self.p.stake)

                self.last_entry_bar = current_bar
                self._reset_entry_state()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        SunriseVolatilityExpansionStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredSunriseVolatilityExpansionStrategy(SunriseVolatilityExpansionStrategy):
        params = params

    return ConfiguredSunriseVolatilityExpansionStrategy
