#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Order Close Strategy.

This script runs the Order Close strategy which executes orders at closing price.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import datetime
from pathlib import Path
import backtrader as bt
import yaml

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml.

    Returns:
        dict: Configuration dictionary containing strategy parameters,
              data configuration, and backtest settings.
    """
    config_path = BASE_DIR / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """Resolve data file path by searching common locations.

    Args:
        filename: Name of the data file to find

    Returns:
        Path object pointing to the data file

    Raises:
        FileNotFoundError: If data file cannot be found in any search path
    """
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR / "datas" / filename,
        BASE_DIR.parent / "datas" / filename,
    BASE_DIR.parent.parent / "datas" / filename,  # Add repository root datas folder
    ]
    for p in search_paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot find data file: {filename}")


def load_data(symbol: str):
    """Load data for the strategy.

    Args:
        symbol: Data file name or symbol

    Returns:
        Backtrader data feed
    """
    data_path = resolve_data_path(f"{symbol}.txt")
    return bt.feeds.BacktraderCSVData(dataname=str(data_path))


def run():
    """Run the Order Close strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates and configures a Cerebro engine
    3. Adds data and strategy
    4. Runs the backtest
    5. Validates results against expected values
    """
    config = load_config()

    # Get strategy parameters from config
    strategy_params = config.get('params', {})
    data_config = config.get('data', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))
    cerebro.broker.seteosbar(True)  # End of session bar

    print("Loading data...")
    symbol = data_config.get('symbol', '2005-2006-day-001')
    data = load_data(symbol)
    cerebro.adddata(data)

    cerebro.addstrategy(OrderCloseStrategy, period=strategy_params.get('period', 15))



    cerebro.addsizer(bt.sizers.FixedSize, stake=10)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    # 日志配置
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    cerebro.addobserver(
        bt.observers.TradeLogger,
        log_orders=True,
        log_trades=True,
        log_positions=True,
        log_data=True,
        log_indicators=True,       # 在data日志中包含策略指标
        log_dir=log_dir,
        log_file_enabled=True,
        file_format='log',         # 默认log(tab分隔)，也可选'csv'
        # MySQL disabled by default - uncomment to enable
        # mysql_enabled=True,
        # mysql_host='localhost',
        # mysql_port=3306,
        # mysql_user='root',
        # mysql_password='your_password',
        # mysql_database='backtrder_web',
        # mysql_table_prefix='bt',
    )

    print("Running backtest...")
    results = cerebro.run()
    strat = results[0]
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("Order Close Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Validate results - final_value tolerance: 0.01, others: 1e-6
    assert strat.bar_num == 497, f"Expected bar_num=497, got {strat.bar_num}"
    assert abs(final_value - 102995.5) < 0.01, f"Expected final_value=102995.50, got {final_value}"
    assert abs(sharpe_ratio - (0.3210201519350739)) < 1e-6, f"Expected sharpe_ratio=0.3210201519350739, got {sharpe_ratio}"
    assert abs(annual_return - (0.014632998393384895)) < 1e-6, f"Expected annual_return=0.014632998393384895, got {annual_return}"
    assert abs(max_drawdown - 4.113455968673918) < 1e-6, f"Expected max_drawdown=4.113455968673918, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    # Import the strategy class
    from strategy_order_close import OrderCloseStrategy

    print("=" * 60)
    print("Order Close Strategy")
    print("=" * 60)
    run()
