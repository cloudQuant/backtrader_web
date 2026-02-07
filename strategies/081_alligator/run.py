#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Alligator Strategy."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_alligator import AlligatorStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching in common directories.

    This function searches for a data file in several possible locations
    relative to the current script's directory. It checks the script's
    directory, parent directory, and 'datas' subdirectories.

    Args:
        filename: The name of the data file to locate.

    Returns:
        Path: The absolute path to the found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of
            the search paths.
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
    """Run the Alligator strategy backtest.

    This function sets up and runs a backtest of the Alligator strategy
    using historical Oracle stock data from 2010-2014. It validates
    the strategy performance against expected values.

    The test uses:
    - Oracle stock data (2010-2014)
    - Initial cash: $100,000
    - Commission: 0.1%
    - Position size: 10 shares per trade

    Raises:
        AssertionError: If any of the performance metrics don't match
            expected values within specified tolerance.
    """
    # Load configuration
    config = load_config()
    backtest_config = config.get('backtest', {})

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
    cerebro.addstrategy(AlligatorStrategy)



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
    print("Alligator Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 1245, f"Expected bar_num=1245, got {strat.bar_num}"
    assert abs(final_value - 100011.2) < 0.01, f"Expected final_value=100011.2, got {final_value}"
    assert abs(sharpe_ratio - (0.04724483526577409)) < 1e-6, f"Expected sharpe_ratio=0.04724483526577409, got {sharpe_ratio}"
    assert abs(annual_return - (2.2461836991998968e-05)) < 1e-6, f"Expected annual_return=2.2461836991998968e-05, got {annual_return}"
    assert abs(max_drawdown - 0.1353106121383434) < 1e-6, f"Expected max_drawdown=0.1353106121383434, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Alligator Strategy Backtest")
    print("=" * 60)
    run()
