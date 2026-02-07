#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RSI Dip Buy Strategy.

Reference: https://github.com/Backtesting/strategies
Buy when RSI crosses above 50, sell when RSI crosses below or hits take profit/stop loss.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class RSIDipBuyStrategy(bt.Strategy):
    """RSI Dip Buy Strategy.

    This strategy buys when RSI crosses above 50 from below (indicating
    momentum shift) and sells when RSI falls below 45 or hits stop loss/take profit.

    Entry conditions:
        - RSI crosses above 50 from below

    Exit conditions:
        - RSI falls below 45
        - Stop loss hit (0.5% below entry price)
        - Take profit hit (0.5% above entry price)
    """
    params = dict(
        stake=10,
        rsi_period=10,
        rsi_buy=50,
        rsi_sell=45,
        stop_loss=0.005,
        take_profit=0.005,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.order = None
        self.buy_price = 0

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object that was updated.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.buy_price = order.executed.price
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1
        if self.order:
            return

        if not self.position:
            # Buy when RSI crosses above 50 from below
            if self.rsi[-1] <= self.p.rsi_buy and self.rsi[0] > self.p.rsi_buy:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit on stop loss, take profit, or RSI drop
            stop_loss_hit = self.dataclose[0] < self.buy_price * (1 - self.p.stop_loss)
            take_profit_hit = self.dataclose[0] > self.buy_price * (1 + self.p.take_profit)
            rsi_exit = self.rsi[0] < self.p.rsi_sell

            if stop_loss_hit or take_profit_hit or rsi_exit:
                self.order = self.sell(size=self.p.stake)


def load_config(config_path=None):
    """Load strategy configuration from YAML file.

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


def get_strategy_from_config(config_path=None):
    """Get strategy class with parameters loaded from config.yaml.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Tuple: (Strategy class, params dict)
    """
    config = load_config(config_path)
    params = config.get('params', {})

    return RSIDipBuyStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
