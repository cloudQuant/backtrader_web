#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pairs Trading Strategy - Based on OLS transformation and Z-Score.

This strategy implements a statistical arbitrage approach using pairs trading.
When Z-Score exceeds the upper limit, short the spread; when Z-Score
falls below the lower limit, long the spread.

Reference: https://github.com/arikaufman/algorithmicTrading
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import backtrader.indicators as btind
import yaml
import math
from pathlib import Path


class PairsTradingStrategy(bt.Strategy):
    """Pairs trading strategy.

    Uses OLS transformation to calculate the Z-Score between two assets.
    When Z-Score exceeds the upper limit, short the spread; when Z-Score
    falls below the lower limit, long the spread.

    Attributes:
        orderid: ID of the current order.
        qty1: Quantity of the first asset.
        qty2: Quantity of the second asset.
        upper_limit: Upper threshold for Z-Score to trigger short position.
        lower_limit: Lower threshold for Z-Score to trigger long position.
        up_medium: Upper medium threshold for closing positions.
        low_medium: Lower medium threshold for closing positions.
        status: Current position status (0=none, 1=short, 2=long).
        portfolio_value: Total portfolio value.
        stop_loss: Stop loss threshold.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        period=20,
        stake=10,
        qty1=0,
        qty2=0,
        upper=2.5,
        lower=-2.5,
        up_medium=0.5,
        low_medium=-0.5,
        status=0,
        portfolio_value=100000,
        stop_loss=3.0
    )

    def log(self, txt, dt=None):
        """Log trading messages with timestamp.

        Args:
            txt: Text message to log.
            dt: Datetime object for the log entry.
        """
        dt = dt or self.data.datetime[0]

    def notify_order(self, order):
        """Handle order status notifications.

        Args:
            order: Order object with status information.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

        elif order.status in [order.Expired, order.Canceled, order.Margin]:
            pass

        self.orderid = None

    def __init__(self):
        """Initialize the pairs trading strategy.

        Sets up instance variables, parameters, and indicators including
        simple moving averages and the OLS transformation for calculating
        the Z-score between the two assets.
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

        self.orderid = None
        self.qty1 = self.p.qty1
        self.qty2 = self.p.qty2
        self.upper_limit = self.p.upper
        self.lower_limit = self.p.lower
        self.up_medium = self.p.up_medium
        self.low_medium = self.p.low_medium
        self.status = self.p.status
        self.portfolio_value = self.p.portfolio_value
        self.stop_loss = self.p.stop_loss

        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

        self.sma1 = bt.indicators.SimpleMovingAverage(self.datas[0], period=50)
        self.sma2 = bt.indicators.SimpleMovingAverage(self.datas[1], period=50)

        # Calculate Z-Score using OLS transformation
        self.transform = btind.OLS_TransformationN(self.data0, self.data1,
                                                   period=self.p.period)
        self.zscore = self.transform.zscore

    def next(self):
        """Execute trading logic for each bar.

        Implements the pairs trading strategy:
        - Short the spread when Z-score exceeds upper limit
        - Long the spread when Z-score falls below lower limit
        - Close positions when Z-score returns to mean range
        """
        self.bar_num += 1
        x = 0
        y = 0
        if self.orderid:
            return

        # SHORT condition: zscore exceeds upper limit
        if (self.zscore[0] > self.upper_limit) and (self.status != 1):
            deviationOffSMA1 = math.fabs((self.data0.close[0]/self.sma1[0])-1)
            deviationOffSMA2 = math.fabs((self.data1.close[0]/self.sma2[0])-1)
            value1 = 0.6 * self.portfolio_value
            value2 = 0.4 * self.portfolio_value
            if deviationOffSMA1 > deviationOffSMA2:
                x = int(value1 / (self.data0.close))
                y = int(value2 / (self.data1.close))
            else:
                x = int(value2 / (self.data0.close))
                y = int(value1 / (self.data1.close))

            self.sell(data=self.data0, size=(x + self.qty1))
            self.buy(data=self.data1, size=(y + self.qty2))

            self.qty1 = x
            self.qty2 = y
            self.status = 1

        # LONG condition: zscore falls below lower limit
        elif (self.zscore[0] < self.lower_limit) and (self.status != 2):
            deviationOffSMA1 = math.fabs((self.data0.close[0]/self.sma1[0])-1)
            deviationOffSMA2 = math.fabs((self.data1.close[0]/self.sma2[0])-1)
            value1 = 0.6 * self.portfolio_value
            value2 = 0.4 * self.portfolio_value
            if deviationOffSMA1 > deviationOffSMA2:
                x = int(value1 / (self.data0.close))
                y = int(value2 / (self.data1.close))
            else:
                x = int(value2 / (self.data0.close))
                y = int(value1 / (self.data1.close))

            self.buy(data=self.data0, size=(x + self.qty1))
            self.sell(data=self.data1, size=(y + self.qty2))

            self.qty1 = x
            self.qty2 = y
            self.status = 2

        # Close position condition: zscore returns to mean range
        elif ((self.zscore[0] < self.up_medium and self.zscore[0] > self.low_medium)):
            self.close(self.data0)
            self.close(self.data1)

    def stop(self):
        """Called when the strategy execution is stopped."""
        pass
