#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MultiData Strategy Runner.

This module runs the multi-data source strategy backtest.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_multidata import MultiDataStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


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
    """Run the MultiData strategy backtest.

    This function loads configuration, sets up the Cerebro engine,
    runs the backtest, and verifies results against expected values.

    Raises:
        AssertionError: If any of the test assertions fail.
        FileNotFoundError: If the required data file cannot be found.
    """
    # Load configuration
    config = load_config()
    initial_cash = config['backtest']['initial_cash']
    commission = config['backtest']['commission']
    params = config.get('params', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(initial_cash)

    print("Loading data...")
    # Use the same data file twice to simulate multiple data sources
    data_path = resolve_data_path("yhoo-1996-2014.txt")

    data0 = bt.feeds.YahooFinanceCSVData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2005, 1, 1),
        todate=datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data0, name='Data0')

    data1 = bt.feeds.YahooFinanceCSVData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2005, 1, 1),
        todate=datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data1, name='Data1')

    cerebro.addstrategy(MultiDataStrategy, period=params.get('period', 15), stake=params.get('stake', 10))



    cerebro.broker.setcommission(commission=commission)
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
    print("MultiData Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Tolerance: 0.01 for final_value, 1e-6 for other metrics
    assert strat.bar_num == 488, f"Expected bar_num=488, got {strat.bar_num}"
    assert abs(final_value - 99847.01) < 0.01, f"Expected final_value=99847.01, got {final_value}"
    assert abs(sharpe_ratio - (-56.94920781443037)) < 1e-6, f"Expected sharpe_ratio=-56.94920781443037, got {sharpe_ratio}"
    assert abs(annual_return - (-0.0007667861342752088)) < 1e-6, f"Expected annual_return=-0.0007667861342752088, got {annual_return}"
    assert abs(max_drawdown - 0.1646592612119436) < 1e-6, f"Expected max_drawdown=0.1646592612119436, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("MultiData Strategy")
    print("=" * 60)
    run()
