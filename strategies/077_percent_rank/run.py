#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Percent Rank Strategy.

This script runs a backtest for the Percent Rank strategy and validates
the results against expected performance metrics.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_percent_rank import PercentRankStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve data file path by searching common locations.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any search path.
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
    """Run the Percent Rank strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates and configures a Cerebro backtest engine
    3. Loads historical data
    4. Runs the backtest
    5. Validates results against expected values

    Raises:
        AssertionError: If any metric does not match expected values
    """
    # Load configuration
    config = load_config()
    backtest_config = config.get('backtest', {})

    # Create cerebro
    cerebro = bt.Cerebro()

    # Load data
    data_path = resolve_data_path("orcl-1995-2014.txt")
    data = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y-%m-%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        fromdate=datetime.datetime(2000, 1, 1),
        todate=datetime.datetime(2014, 12, 31),
    )
    cerebro.adddata(data)

    # Add strategy with parameters from config
    params = config.get('params', {})
    cerebro.addstrategy(PercentRankStrategy, **params)




    # Set broker settings from config
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000))
    cerebro.broker.setcommission(commission=backtest_config.get('commission', 0.001))

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
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
    results = cerebro.run()
    strat = results[0]

    # Get analysis results
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("=" * 50)
    print("Percent Rank Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 3548, f"Expected bar_num=3548, got {strat.bar_num}"
    assert abs(final_value - 100302.26) < 0.01, f"Expected final_value=100302.26, got {final_value}"
    assert abs(sharpe_ratio - (0.8675517538455737)) < 1e-6, f"Expected sharpe_ratio=0.8675517538455737, got {sharpe_ratio}"
    assert abs(annual_return - (0.00020164856372564902)) < 1e-6, f"Expected annual_return=0.00020164856372564902, got {annual_return}"
    assert abs(max_drawdown - 0.11557448332367173) < 1e-6, f"Expected max_drawdown=0.11557448332367173, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    run()
