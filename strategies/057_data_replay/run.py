#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Data Replay Strategy Runner.

This module runs the data replay strategy backtest.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_data_replay import ReplayMAStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching in common locations.

    This function searches for a data file in multiple standard locations
    relative to the test file directory, including the current directory,
    parent directory, and 'datas' subdirectories.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            searched locations.
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
    """Run the Data Replay strategy backtest.

    This function loads configuration, sets up the Cerebro engine,
    runs the backtest, and verifies results against expected values.

    Raises:
        AssertionError: If any of the test assertions fail.
        FileNotFoundError: If the required data file cannot be found.
    """
    # Load configuration
    config = load_config()
    initial_cash = config['backtest']['initial_cash']
    params = config.get('params', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(initial_cash)

    print("Loading data...")
    data_path = resolve_data_path("2005-2006-day-001.txt")
    data = bt.feeds.BacktraderCSVData(dataname=str(data_path))

    # Use replay functionality to replay daily data as weekly data
    cerebro.replaydata(
        data,
        timeframe=bt.TimeFrame.Weeks,
        compression=1
    )

    cerebro.addstrategy(ReplayMAStrategy, fast_period=params.get('fast_period', 5), slow_period=params.get('slow_period', 15))



    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Add complete analyzers - calculate Sharpe ratio using weekly timeframe
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Weeks, annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

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

    print("Starting backtest...")
    results = cerebro.run(preload=False)
    strat = results[0]

    # Get analysis results
    sharpe = strat.analyzers.sharpe.get_analysis()
    ret = strat.analyzers.returns.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    sharpe_ratio = sharpe.get('sharperatio', None)
    annual_return = ret.get('rnorm', 0)
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    total_trades = trades.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # Print results in standard format
    print("\n" + "=" * 50)
    print("Data Replay Backtest Results (Weekly):")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assert test results
    assert strat.bar_num == 439, f"Expected bar_num=439, got {strat.bar_num}"
    assert abs(final_value - 108263.90) < 0.01, f"Expected final_value=108263.90, got {final_value}"
    assert abs(sharpe_ratio - 1.17880670695321) < 1e-6, f"Expected sharpe_ratio=1.17880670695321, got {sharpe_ratio}"
    assert abs(annual_return - 0.04049939932707298) < 1e-6, f"Expected annual_return=0.04049939932707298, got {annual_return}"
    assert abs(max_drawdown - 2.668267546216064) < 1e-6, f"Expected max_drawdown=2.668267546216064, got {max_drawdown}"
    assert total_trades == 13, f"Expected total_trades=13, got {total_trades}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Data Replay Strategy")
    print("=" * 60)
    run()
