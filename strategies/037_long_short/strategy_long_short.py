#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Long Short Strategy

Reference: backtrader-master2/samples/analyzer-annualreturn/analyzer-annualreturn.py
A long-short strategy based on price and SMA crossover.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from pathlib import Path
from typing import Dict, Any

import yaml
import backtrader as bt


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Configuration dictionary.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class LongShortStrategy(bt.Strategy):
    """Long Short Strategy.

    This strategy goes long when price crosses above SMA, and goes short
    when price crosses below SMA.

    Attributes:
        orderid: ID of the current pending order.
        signal: Crossover signal indicator.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
        win_count: Number of profitable trades.
        loss_count: Number of losing trades.
        sum_profit: Total profit/loss from all closed trades.
    """
    params = dict(
        period=15,
        stake=1,
        onlylong=False,
    )

    def __init__(self):
        """Initialize the Long Short Strategy.

        Sets up the Simple Moving Average (SMA) indicator and crossover
        signal to detect when price crosses above or below the SMA.
        Initializes all tracking variables for trade statistics.
        """
        self.orderid = None
        sma = bt.ind.SMA(self.data, period=self.p.period)
        self.signal = bt.ind.CrossOver(self.data.close, sma)

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

        Called by the broker when an order changes status. Tracks completed
        buy and sell orders for statistics.

        Args:
            order: The order object with updated status information.
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

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Called when a trade is closed. Updates profit/loss statistics
        and win/loss counters.

        Args:
            trade: The closed trade object containing profit/loss information.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Called on every bar update. Implements the long-short strategy:
        - Go long when price crosses above SMA
        - Go short when price crosses below SMA (if not in long-only mode)
        - Close existing positions before opening new ones

        The strategy ensures only one order is pending at a time.
        """
        self.bar_num += 1

        if self.orderid:
            return

        if self.signal > 0.0:
            if self.position:
                self.close()
            self.buy(size=self.p.stake)

        elif self.signal < 0.0:
            if self.position:
                self.close()
            if not self.p.onlylong:
                self.sell(size=self.p.stake)

    def stop(self):
        """Called when the backtest is finished.

        Prints final statistics including bar count, trade counts,
        win/loss ratio, and total profit/loss.

        The win rate is calculated as: (wins / total trades) * 100
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )


def run_long_short_strategy(config: Dict[str, Any] = None):
    """Run the Long Short Strategy backtest.

    Args:
        config: Configuration dictionary. If None, loads from config.yaml.

    Returns:
        Configured Cerebro instance.
    """
    if config is None:
        config = load_config()

    # Extract parameters from config
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Add strategy with parameters from config
    cerebro.addstrategy(LongShortStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_long_short_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
