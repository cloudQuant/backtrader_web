#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Strategy Selection Demo

Reference: backtrader-master2/samples/strategy-selection/strategy-selection.py
Demonstrates how to select different strategies at runtime
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from pathlib import Path
from typing import Dict, Any, Optional

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


class StrategyA(bt.Strategy):
    """Strategy A: Dual Moving Average Crossover.

    This strategy generates buy/sell signals when two simple moving
    averages cross each other.
    """
    params = (('p1', 10), ('p2', 30))

    def __init__(self):
        """Initialize the StrategyA indicators and state variables.

        Sets up two Simple Moving Average (SMA) indicators with periods
        defined by p1 and p2 parameters, and creates a crossover indicator
        to detect when the fast SMA crosses the slow SMA.
        """
        sma1 = bt.ind.SMA(period=self.p.p1)
        sma2 = bt.ind.SMA(period=self.p.p2)
        self.crossover = bt.ind.CrossOver(sma1, sma2)
        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track completed trades.

        Updates the buy/sell counters when orders are completed and
        clears the order reference when the order is no longer alive.

        Args:
            order: The order object with status information.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements the dual moving average crossover strategy:
        - Buy when fast SMA crosses above slow SMA
        - Sell (close position) when fast SMA crosses below slow SMA
        """
        self.bar_num += 1
        if self.order:
            return
        if self.crossover > 0:
            if self.position:
                self.order = self.close()
            self.order = self.buy()
        elif self.crossover < 0:
            if self.position:
                self.order = self.close()


class StrategyB(bt.Strategy):
    """Strategy B: Price and Moving Average Crossover.

    This strategy generates buy/sell signals when the price crosses
    above or below a simple moving average.
    """
    params = (('period', 10),)

    def __init__(self):
        """Initialize the StrategyB indicators and state variables.

        Sets up a Simple Moving Average (SMA) indicator with the period
        defined by the 'period' parameter, and creates a crossover indicator
        to detect when the price crosses above or below the SMA.
        """
        sma = bt.ind.SMA(period=self.p.period)
        self.crossover = bt.ind.CrossOver(self.data.close, sma)
        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track completed trades.

        Updates the buy/sell counters when orders are completed and
        clears the order reference when the order is no longer alive.

        Args:
            order: The order object with status information.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements the price and moving average crossover strategy:
        - Buy when price crosses above the SMA
        - Sell (close position) when price crosses below the SMA
        """
        self.bar_num += 1
        if self.order:
            return
        if self.crossover > 0:
            if self.position:
                self.order = self.close()
            self.order = self.buy()
        elif self.crossover < 0:
            if self.position:
                self.order = self.close()


def run_strategy(strategy_class, config: Dict[str, Any] = None, strategy_name: str = "Strategy"):
    """Run a single strategy with analyzers and return results.

    Args:
        strategy_class: The strategy class to run (StrategyA or StrategyB).
        config: Configuration dictionary. If None, loads from config.yaml.
        strategy_name: Name of the strategy for display purposes.

    Returns:
        A dictionary containing strategy performance metrics.
    """
    if config is None:
        config = load_config()

    backtest_config = config.get('backtest', {})

    # Determine which strategy params to use
    if strategy_class == StrategyA:
        params = config.get('strategy_a', {})
    elif strategy_class == StrategyB:
        params = config.get('strategy_b', {})
    else:
        params = {}

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    cerebro.addstrategy(strategy_class, **params)
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    results = cerebro.run()
    strat = results[0]

    # Get analysis results
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("=" * 50)
    print(f"{strategy_name} Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    return {
        'strat': strat,
        'bar_num': strat.bar_num,
        'buy_count': strat.buy_count,
        'sell_count': strat.sell_count,
        'sharpe_ratio': sharpe_ratio,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'total_trades': total_trades,
        'final_value': final_value,
    }


def compare_strategies(config: Dict[str, Any] = None):
    """Run both strategies and compare their performance.

    This is useful for strategy selection and comparison.

    Args:
        config: Configuration dictionary. If None, loads from config.yaml.

    Returns:
        Dictionary containing results from both strategies.
    """
    if config is None:
        config = load_config()

    print("\n--- Testing StrategyA (Dual SMA Crossover) ---")
    result_a = run_strategy(StrategyA, config, "StrategyA")

    print("\n--- Testing StrategyB (Price-SMA Crossover) ---")
    result_b = run_strategy(StrategyB, config, "StrategyB")

    # Compare results
    print("\n" + "=" * 50)
    print("Strategy Comparison:")
    print("=" * 50)
    print(f"{'Metric':<20} {'StrategyA':<15} {'StrategyB':<15}")
    print("-" * 50)
    print(f"{'Final Value':<20} {result_a['final_value']:<15.2f} {result_b['final_value']:<15.2f}")
    print(f"{'Total Trades':<20} {result_a['total_trades']:<15} {result_b['total_trades']:<15}")
    print(f"{'Sharpe Ratio':<20} {result_a['sharpe_ratio'] or 'N/A':<15} {result_b['sharpe_ratio'] or 'N/A':<15}")
    print(f"{'Annual Return':<20} {result_a['annual_return']:<15.6f} {result_b['annual_return']:<15.6f}")
    print(f"{'Max Drawdown':<20} {result_a['max_drawdown']:<15.6f} {result_b['max_drawdown']:<15.6f}")

    return {
        'StrategyA': result_a,
        'StrategyB': result_b,
    }


if __name__ == "__main__":
    # Load config and compare strategies
    config = load_config()
    results = compare_strategies(config)
