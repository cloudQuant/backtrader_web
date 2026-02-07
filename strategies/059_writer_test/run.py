#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Writer Output Test Strategy Runner.

This module runs the Writer output test strategy backtest.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import datetime
from pathlib import Path
import backtrader as bt

from strategy_writer import WriterTestStrategy, load_config, setup_writer

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching common locations.

    This function searches for a data file in several standard locations
    relative to the test directory, including the current directory,
    parent directory, and 'datas' subdirectories.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            search locations.
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
    """Run the Writer output test strategy backtest.

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
    data = bt.feeds.BacktraderCSVData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2006, 1, 1),
        todate=datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data)

    cerebro.addstrategy(WriterTestStrategy, period=params.get('period', 15))



    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Add Writer (no CSV output, only for testing functionality)
    writer_config = config.get('writer', {})
    csv = writer_config.get('csv', False)
    rounding = writer_config.get('rounding', 4)
    cerebro.addwriter(bt.WriterFile, csv=csv, rounding=rounding)

    # Add complete analyzers - use daily timeframe to calculate Sharpe ratio
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)
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
    results = cerebro.run()
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
    print("Writer Output Functionality Backtest Results:")
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
    assert strat.bar_num == 240, f"Expected bar_num=240, got {strat.bar_num}"
    assert abs(final_value - 102841.00) < 0.01, f"Expected final_value=102841.00, got {final_value}"
    assert abs(sharpe_ratio - 0.8252115748419219) < 1e-6, f"Expected sharpe_ratio=0.8252115748419219, got {sharpe_ratio}"
    assert abs(annual_return - 0.0280711170741429) < 1e-6, f"Expected annual_return=0.0280711170741429, got {annual_return}"
    assert abs(max_drawdown - 2.615813541154893) < 1e-6, f"Expected max_drawdown=2.615813541154893, got {max_drawdown}"
    assert total_trades == 12, f"Expected total_trades=12, got {total_trades}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Writer Output Test Strategy")
    print("=" * 60)
    run()
