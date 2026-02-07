#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Triple Cross Moving Average Crossover Strategy.

This script runs the triple moving average crossover strategy backtest.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
import yaml
from pathlib import Path

import backtrader as bt

# Import strategy from strategy module
from strategy_triple_cross import TripleCrossStrategy

# Base directory for data file resolution
BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml.

    Returns:
        dict: Configuration dictionary containing strategy parameters
            and backtest settings.
    """
    config_path = BASE_DIR / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script's directory.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            search paths.
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


def run():
    """Run the triple moving average crossover strategy backtest.

    This test performs the following operations:
        1. Loads historical Oracle stock data from 2010-2014
        2. Runs the TripleCrossStrategy with default parameters (5/8/13 MA periods)
        3. Validates performance metrics against expected values

    The test validates:
        - Number of bars processed: 1245
        - Final portfolio value: ~100063.63
        - Sharpe ratio: ~0.361
        - Annual return: ~0.00013
        - Maximum drawdown: ~0.109

    Raises:
        AssertionError: If any of the performance metrics don't match
            expected values within tolerance (0.01 for final_value, 1e-6 for others).
    """
    # Load configuration
    config = load_config()

    cerebro = bt.Cerebro()

    # Load data
    data_path = resolve_data_path("orcl-1995-2014.txt")
    data = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y-%m-%d',
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=-1,
        fromdate=datetime.datetime(2010, 1, 1),
        todate=datetime.datetime(2014, 12, 31),
    )

    cerebro.adddata(data)
    cerebro.addstrategy(TripleCrossStrategy)




    # Set broker parameters from config
    cerebro.broker.setcash(config['backtest']['initial_cash'])
    cerebro.broker.setcommission(commission=config['backtest']['commission'])

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
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

    results = cerebro.run()
    strat = results[0]

    # Get analysis results
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("Triple Cross Moving Average Crossover Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 1245, f"Expected bar_num=1245, got {strat.bar_num}"
    assert abs(final_value - 100063.63) < 0.01, f"Expected final_value=100063.63, got {final_value}"
    assert abs(sharpe_ratio - (0.3608428642726115)) < 1e-6, f"Expected sharpe_ratio=0.0, got {sharpe_ratio}"
    assert abs(annual_return - (0.00012752914318585638)) < 1e-6, f"Expected annual_return=0.0, got {annual_return}"
    assert abs(max_drawdown - 0.10941659904491363) < 1e-6, f"Expected max_drawdown=0.0, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Triple Cross Moving Average Crossover Strategy Test")
    print("=" * 60)
    run()
