#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run script for OCO (One Cancels Other) Order Strategy

This script runs the OCO Order Strategy backtest with configuration
loaded from config.yaml and validates results against expected values.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import datetime
from pathlib import Path
from typing import Dict, Any

import backtrader as bt

from strategy_oco_order import load_config, OCOOrderStrategy


def resolve_data_path(filename: str) -> Path:
    """Resolve data file path by searching in common locations.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Absolute path to the data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            search locations.
    """
    BASE_DIR = Path(__file__).resolve().parent
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
    """Run the OCO Order Strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates and configures a Cerebro backtesting engine
    3. Loads historical data
    4. Runs the backtest
    5. Validates results against expected values

    Raises:
        AssertionError: If any performance metric doesn't match expected values.
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})
    data_config = config.get('data', {})

    # Create Cerebro engine
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))

    # Load data
    print("Loading data...")
    data_path = resolve_data_path(data_config.get('symbol', '2005-2006-day-001.txt') + ".txt")
    data = bt.feeds.BacktraderCSVData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2005, 1, 1),
        todate=datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data, name="DATA")

    # Add strategy with default parameters
    cerebro.addstrategy(OCOOrderStrategy)




    # Attach performance analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="my_sharpe")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="my_returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="my_drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trade")
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

    # Run backtest
    print("Running backtest...")
    results = cerebro.run()
    strat = results[0]

    # Extract performance metrics
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get('sharperatio', None)
    returns = strat.analyzers.my_returns.get_analysis()
    annual_return = returns.get('rnorm', 0)
    drawdown = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.my_trade.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # Display results
    print("=" * 50)
    print("OCO Order Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assert results match expected values
    assert strat.bar_num == 497, f"Expected bar_num=497, got {strat.bar_num}"
    assert abs(final_value - 99936.2) < 0.01, f"Expected final_value=99936.20, got {final_value}"
    assert abs(sharpe_ratio - (-728.1006016110281)) < 1e-6, f"Expected sharpe_ratio=-728.10, got {sharpe_ratio}"
    assert abs(annual_return - (-0.00031405198515841587)) < 1e-6, f"Expected annual_return=-0.000314, got {annual_return}"
    assert abs(max_drawdown - 0.3665283801049814) < 1e-6, f"Expected max_drawdown=0.3665, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    run()
