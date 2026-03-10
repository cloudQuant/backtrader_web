#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TRIX (Triple Exponential Average) Strategy.

This strategy uses the TRIX indicator to identify momentum changes
by detecting zero-line crossovers. TRIX filters out short-term noise
and highlights the underlying trend direction.

The TRIX indicator was developed by Jack Hutson and is calculated as:
    1. Single exponential moving average of price
    2. Double exponential moving average of the result
    3. Triple exponential moving average of that result
    4. Rate of change (1-period percent change) of the triple EMA

By applying exponential smoothing three times, TRIX effectively filters
out price movements shorter than the indicator period. This makes it
useful for identifying the underlying trend without being distracted
by short-term fluctuations.

Trading Logic:
    Entry (Long): TRIX crosses above zero line (bullish momentum)
    Exit: TRIX crosses below zero line (bearish momentum)

The zero line represents the point where the triple-smoothed trend is
neither accelerating nor decelerating. Crossovers above zero indicate
positive momentum, while crossovers below zero indicate negative momentum.

Parameters:
    stake: Number of shares/contracts per trade (default: 10)
    period: Period for TRIX calculation (default: 15)

Note:
    TRIX is particularly effective in trending markets and can help
    distinguish between minor corrections and actual trend reversals.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from datetime import datetime
from pathlib import Path


class TrixStrategy(bt.Strategy):
    """TRIX (Triple Exponential Average) trend-following strategy.

    This strategy uses the TRIX indicator to identify momentum changes
    by detecting zero-line crossovers. TRIX filters out short-term noise
    and highlights the underlying trend direction.

    Entry Conditions:
        - Long: TRIX crosses above zero line (bullish momentum)

    Exit Conditions:
        - TRIX crosses below zero line (bearish momentum)

    Attributes:
        trix: TRIX indicator instance.
        order: Current pending order.
        bar_num: Counter for processed bars.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """

    params = dict(
        stake=10,
        period=15,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.trix = bt.indicators.TRIX(self.data.close, period=self.p.period)

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

        Args:
            order: The order object with updated status.
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

        Implements the core strategy logic:
        1. Track bar progression
        2. Check for pending orders
        3. Ensure minimum data availability
        4. Generate entry/exit signals based on TRIX zero-line crossovers
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

        if len(self) < 2:
            return

        if not self.position:
            # Entry: TRIX crossing above zero line
            if self.trix[-1] <= 0 and self.trix[0] > 0:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: TRIX crossing below zero line
            if self.trix[-1] >= 0 and self.trix[0] < 0:
                self.order = self.close()


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        dict: Configuration dictionary with strategy parameters.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def get_strategy_params(config=None):
    """Get strategy parameters from config.

    Args:
        config: Configuration dictionary. If None, loads from default path.

    Returns:
        dict: Strategy parameters for backtrader.
    """
    if config is None:
        config = load_config()

    return config.get('params', {})


__all__ = ['TrixStrategy', 'load_config', 'get_strategy_params']
