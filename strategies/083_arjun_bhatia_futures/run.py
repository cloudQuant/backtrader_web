#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Arjun Bhatia Futures Trading Strategy."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_arjun_bhatia_futures import ArjunBhatiaFuturesStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching multiple possible locations.

    This function searches for a data file in several common locations relative
    to the current test file directory, making the test suite more portable across
    different project structures.

    Args:
        filename: Name of the data file to locate (e.g., 'orcl-1995-2014.txt').

    Returns:
        Path: Absolute path to the located data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            searched locations.

    Search Order:
        1. Current test directory (tests/strategies/)
        2. Parent tests directory (tests/)
        3. Current test directory/datas (tests/strategies/datas/)
        4. Parent tests directory/datas (tests/datas/)
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
    """Run the Arjun Bhatia Futures Trading Strategy backtest.

    This test runs a backtest of the Arjun Bhatia strategy on historical data
    and verifies that key performance metrics match expected values.

    The test:
    1. Loads Oracle stock data from 2010-2014
    2. Runs the Arjun Bhatia strategy with default parameters
    3. Calculates performance metrics (Sharpe ratio, returns, drawdown)
    4. Asserts that results match expected values within tolerance

    Raises:
        AssertionError: If any performance metric falls outside expected tolerance.
    """
    # Load configuration with fallback to defaults
    try:
        config = load_config()
        backtest_config = config.get('backtest', {})
    except Exception as e:
        print(f"Warning: Could not load config file: {e}")
        print("Using default configuration values.")
        backtest_config = {}

    cerebro = bt.Cerebro()
    data_path = resolve_data_path("orcl-1995-2014.txt")
    data = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y-%m-%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        fromdate=datetime.datetime(2010, 1, 1),
        todate=datetime.datetime(2014, 12, 31),
    )
    cerebro.adddata(data)
    cerebro.addstrategy(ArjunBhatiaFuturesStrategy)



    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000))
    cerebro.broker.setcommission(commission=backtest_config.get('commission', 0.001))
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

    results = cerebro.run()
    strat = results[0]
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("Arjun Bhatia Futures Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 1243, f"Expected bar_num=1243, got {strat.bar_num}"
    assert abs(final_value - 100008.3) < 0.01, f"Expected final_value=100008.3, got {final_value}"
    assert abs(sharpe_ratio - (0.03545852568934664)) < 1e-6, f"Expected sharpe_ratio=0.03545852568934664, got {sharpe_ratio}"
    assert abs(annual_return - (1.6643997595262782e-05)) < 1e-6, f"Expected annual_return=1.6643997595262782e-05, got {annual_return}"
    assert abs(max_drawdown - 0.13555290823752497) < 1e-6, f"Expected max_drawdown=0.13555290823752497, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Arjun Bhatia Futures Strategy Backtest")
    print("=" * 60)
    run()
