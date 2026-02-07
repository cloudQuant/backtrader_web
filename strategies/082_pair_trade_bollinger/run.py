#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Pair Trade Bollinger Strategy."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_pair_trade_bollinger import PairTradeBollingerStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching in common directories.

    This function searches for a data file in multiple possible locations
    relative to the current test file directory. This allows tests to find
    their data files regardless of whether they are run from the tests/
    directory or the project root.

    Args:
        filename: The name of the data file to locate.

    Returns:
        Path: The absolute path to the first matching data file found.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            searched directories.

    Search Order:
        1. Current test directory (tests/strategies/)
        2. Parent test directory (tests/)
        3. Current test directory/datas/
        4. Parent test directory/datas/
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
    """Run a backtest of the Pair Trade Bollinger strategy.

    This test function sets up and executes a complete backtest using historical
    data for two assets (ORCL and NVDA) to validate the Pair Trade Bollinger
    strategy implementation. It verifies that the strategy produces expected
    results for key performance metrics.

    Test Setup:
        - Initial capital: $100,000
        - Commission: 0.1% per trade
        - Data period: 2010-01-01 to 2014-12-31
        - Assets: Oracle (ORCL) and NVIDIA (NVDA)
        - Strategy parameters: lookback=20, entry_zscore=1.5, exit_zscore=0.2, stake=10

    Analyzers:
        - Sharpe Ratio: Risk-adjusted return metric
        - Returns: Annualized normalized returns
        - DrawDown: Maximum drawdown analysis

    Assertions:
        - bar_num equals 1257
        - final_value equals 99877.16 (within 0.01 tolerance)
        - sharpe_ratio equals -1.4903824617023596 (within 1e-6 tolerance)
        - annual_return equals -0.00024639413813618824 (within 1e-6 tolerance)
        - max_drawdown equals 0.14492238860330459 (within 1e-6 tolerance)

    Raises:
        AssertionError: If any of the expected values do not match within tolerance.
        FileNotFoundError: If the required data files cannot be located.
    """
    # Load configuration
    config = load_config()
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro()

    # Load two data sources (using same data but different time periods to simulate pairs)
    data_path = resolve_data_path("orcl-1995-2014.txt")

    data0 = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y-%m-%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        fromdate=datetime.datetime(2010, 1, 1),
        todate=datetime.datetime(2014, 12, 31),
    )
    data_path_1 = resolve_data_path("nvda-1999-2014.txt")
    data1 = bt.feeds.GenericCSVData(
        dataname=str(data_path_1),
        dtformat='%Y-%m-%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        fromdate=datetime.datetime(2010, 1, 1),
        todate=datetime.datetime(2014, 12, 31),
    )

    cerebro.adddata(data0, name='asset0')
    cerebro.adddata(data1, name='asset1')
    cerebro.addstrategy(PairTradeBollingerStrategy)



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
    print("Pair Trade Bollinger Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    assert strat.bar_num == 1257, f"Expected bar_num=1257, got {strat.bar_num}"
    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert abs(final_value - 99877.16) < 0.01, f"Expected final_value=99877.16, got {final_value}"
    assert abs(sharpe_ratio - (-1.4903824617023596)) < 1e-6, f"Expected sharpe_ratio=-1.4903824617023596, got {sharpe_ratio}"
    assert abs(annual_return - (-0.00024639413813618824)) < 1e-6, f"Expected annual_return=-0.00024639413813618824, got {annual_return}"
    assert abs(max_drawdown - 0.14492238860330459) < 1e-6, f"Expected max_drawdown=0.14492238860330459, got {max_drawdown}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Pair Trade Bollinger Strategy Backtest")
    print("=" * 60)
    run()
