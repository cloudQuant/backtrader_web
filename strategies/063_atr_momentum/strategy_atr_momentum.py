#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ATR Momentum Strategy - Momentum trading with volatility-based risk management.

This strategy combines multiple technical indicators to identify trend-following
entry opportunities with volatility-based risk management using ATR.

Reference source: https://github.com/papodetrader/backtest
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ATRMomentumStrategy(bt.Strategy):
    """ATR Momentum Trading Strategy.

    A momentum trading strategy that combines multiple technical indicators to
    identify trend-following entry opportunities with volatility-based risk
    management. The strategy uses RSI and SMA200 as trend filters, and ATR for
    dynamic stop-loss and take-profit level calculation.

    Entry Conditions:
        - **Long**: RSI crosses above 50 AND price is above SMA200
        - **Short**: RSI crosses below 50 AND price is below SMA200

    Exit Conditions:
        - Stop-loss: 2x ATR from entry price
        - Take-profit: 5x ATR from entry price

    Attributes:
        dataclose: Reference to the close price data series.
        atr: Average True Range indicator for volatility measurement.
        rsi: Relative Strength Index for momentum signals.
        sma200: 200-period Simple Moving Average for trend filter.
        order: Reference to the current pending order.
        stop_loss: Stop-loss price level for open position.
        take_profit: Take-profit price level for open position.
        entry_price: Price at which the current position was entered.
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for the number of buy orders executed.
        sell_count: Counter for the number of sell orders executed.
    """

    params = dict(
        bet=100,
        stop_atr_multiplier=2,
        target_atr_multiplier=5,
        rsi_period=14,
        sma_period=200,
        atr_period=14,
    )

    def __init__(self):
        """Initialize the ATR Momentum Strategy.

        Sets up data references, indicators, and state variables for tracking
        orders, positions, and statistics.
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

        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        # Indicators
        self.atr = bt.indicators.ATR(self.datas[0], period=self.p.atr_period)
        self.rsi = bt.indicators.RSI(self.datas[0], period=self.p.rsi_period)
        self.sma200 = bt.indicators.SMA(self.datas[0], period=self.p.sma_period)

        # Trade management
        self.order = None
        self.stop_loss = None
        self.take_profit = None
        self.entry_price = None

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

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
                self.entry_price = order.executed.price
            else:
                self.sell_count += 1

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            pass

        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        This method implements the core strategy logic:
        1. Manages existing positions by checking stop-loss and take-profit levels
        2. Checks entry conditions for new positions when no position is held
        3. Calculates position size based on ATR volatility
        """
        self.bar_num += 1

        if self.order:
            return

        # Check if there are positions that need to be managed
        if self.position.size > 0:
            # Long position stop-loss and take-profit
            if self.datahigh[0] >= self.take_profit:
                self.close()
            elif self.datalow[0] <= self.stop_loss:
                self.close()

        elif self.position.size < 0:
            # Short position stop-loss and take-profit
            if self.datalow[0] <= self.take_profit:
                self.close()
            elif self.datahigh[0] >= self.stop_loss:
                self.close()

        else:
            # Check entry conditions when there is no position
            # Long condition: RSI crosses above 50 + price above SMA200
            cond_long = (self.rsi[0] > 50 and self.rsi[-1] <= 50 and
                        self.dataclose[0] > self.sma200[0])

            # Short condition: RSI crosses below 50 + price below SMA200
            cond_short = (self.rsi[0] < 50 and self.rsi[-1] >= 50 and
                         self.dataclose[0] < self.sma200[0])

            if cond_long:
                atr_val = self.atr[0] if self.atr[0] > 0 else 0.01
                size = max(1, int(self.p.bet / (self.p.stop_atr_multiplier * atr_val)))
                self.buy(size=size)
                self.stop_loss = self.dataclose[0] - (self.p.stop_atr_multiplier * self.atr[0])
                self.take_profit = self.dataclose[0] + (self.p.target_atr_multiplier * self.atr[0])

            elif cond_short:
                atr_val = self.atr[0] if self.atr[0] > 0 else 0.01
                size = max(1, int(self.p.bet / (self.p.stop_atr_multiplier * atr_val)))
                self.sell(size=size)
                self.stop_loss = self.dataclose[0] + (self.p.stop_atr_multiplier * self.atr[0])
                self.take_profit = self.dataclose[0] - (self.p.target_atr_multiplier * self.atr[0])

    def stop(self):
        """Called when the backtest is finished."""
        pass
