#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bracket Order Strategy

Reference: backtrader-master2/samples/bracket/bracket.py
Trading using bracket orders (main order + stop loss + take profit)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
from pathlib import Path
from typing import Optional, Dict, Any

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


class BracketOrderStrategy(bt.Strategy):
    """Bracket Order Strategy.

    Enters using limit orders when moving averages cross over, while
    simultaneously setting stop loss and take profit orders.
    """
    params = dict(
        p1=5,
        p2=15,
        limit=0.005,
        limdays=3,
        limdays2=1000,
        hold=10,
    )

    def __init__(self):
        """Initialize the Bracket Order Strategy.

        Sets up the technical indicators and tracking variables for the strategy.
        Creates two simple moving averages (SMA) and a crossover indicator to
        generate entry signals. Also initializes tracking variables for order
        references, position holding, and performance statistics.
        """
        ma1 = bt.ind.SMA(period=self.p.p1)
        ma2 = bt.ind.SMA(period=self.p.p2)
        self.cross = bt.ind.CrossOver(ma1, ma2)
        self.orefs = list()
        self.holdstart = 0

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status notifications.

        Tracks completed orders by incrementing buy/sell counters and updating
        the hold start time. Also removes order references from the active order
        list when orders are no longer alive (completed, cancelled, or expired).

        Args:
            order: The order object that has changed status.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
            self.holdstart = len(self)

        if not order.alive() and order.ref in self.orefs:
            self.orefs.remove(order.ref)

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Updates performance statistics when a trade is closed, including
        total profit/loss, win count, and loss count based on the trade's
        net profit (pnlcomm).

        Args:
            trade: The trade object that has been closed.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        This method is called for each bar in the data series. It implements
        the bracket order strategy logic:
        1. Skips if there are active orders pending
        2. When not in a position and the fast SMA crosses above the slow SMA,
           creates a bracket order with:
           - Main limit buy order (p1) at current price * (1 - limit)
           - Stop loss sell order (p2) at p1 - 2% of close price
           - Take profit sell order (p3) at p1 + 2% of close price

        The bracket orders are transmitted together as a group, with the stop
        loss and take profit orders as children of the main limit order.
        """
        self.bar_num += 1

        if self.orefs:
            return

        if not self.position:
            if self.cross > 0.0:
                close = self.data.close[0]
                p1 = close * (1.0 - self.p.limit)
                p2 = p1 - 0.02 * close
                p3 = p1 + 0.02 * close

                valid1 = datetime.timedelta(self.p.limdays)
                valid2 = valid3 = datetime.timedelta(self.p.limdays2)

                o1 = self.buy(
                    exectype=bt.Order.Limit,
                    price=p1,
                    valid=valid1,
                    transmit=False
                )

                o2 = self.sell(
                    exectype=bt.Order.Stop,
                    price=p2,
                    valid=valid2,
                    parent=o1,
                    transmit=False
                )

                o3 = self.sell(
                    exectype=bt.Order.Limit,
                    price=p3,
                    valid=valid3,
                    parent=o1,
                    transmit=True
                )

                self.orefs = [o1.ref, o2.ref, o3.ref]

    def stop(self):
        """Print final performance statistics when backtesting completes.

        Calculates and displays the win rate along with other performance
        metrics including total bars processed, buy/sell counts, win/loss
        counts, and total profit/loss.
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )


def run_bracket_order_strategy(config: Dict[str, Any] = None):
    """Run the Bracket Order Strategy backtest.

    Args:
        config: Configuration dictionary. If None, loads from config.yaml.

    Returns:
        Final portfolio value.
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
    cerebro.addstrategy(BracketOrderStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_bracket_order_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
