#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run script for Slippage Simulation Strategy.

This script runs the Slippage Strategy backtest with data loading
and validates results against expected values.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_slippage import load_config, SlippageStrategy

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the full path to a data file by searching common locations.

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
    """Run the Slippage Strategy backtest.

    Loads configuration from config.yaml, sets up the cerebro engine,
    applies slippage, loads historical data, runs the backtest, and validates results.

    Returns:
        The final portfolio value.

    Raises:
        AssertionError: If any performance metric deviates from expected values.
    """
    # Load configuration from config.yaml
    config = load_config()
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})
    data_config = config.get('data', {})

    # Create cerebro engine
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 50000.0))

    # Apply slippage to all orders
    slippage_perc = backtest_config.get('slippage_perc', 0.01)
    cerebro.broker.set_slippage_perc(slippage_perc)

    print("Loading data...")
    # Load historical price data
    data_file = data_config.get('symbol', '2005-2006-day-001') + ".txt"
    data_path = resolve_data_path(data_file)
    data = bt.feeds.BacktraderCSVData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2005, 1, 1),
        todate=datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data, name="DATA")

    # Add strategy with parameters from config
    cerebro.addstrategy(SlippageStrategy, **params)



    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Add analyzers
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

    print("Running backtest...")
    results = cerebro.run()
    strat = results[0]

    # Extract analysis results
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get('sharperatio', None)
    returns = strat.analyzers.my_returns.get_analysis()
    annual_return = returns.get('rnorm', 0)
    drawdown = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.my_trade.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("Slippage Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assert results match expected values from original test
    assert strat.bar_num == 482, f"Expected bar_num=482, got {strat.bar_num}"
    assert abs(final_value - 52702.98) < 0.01, f"Expected final_value=52702.98, got {final_value}"
    assert abs(sharpe_ratio - (7.146238384824227)) < 1e-6, f"Expected sharpe_ratio=7.146238384824227, got {sharpe_ratio}"
    assert abs(annual_return - (0.026251880915366368)) < 1e-6, f"Expected annual_return=0.026251880915366368, got {annual_return}"
    assert abs(max_drawdown - 7.696752586616294) < 1e-6, f"Expected max_drawdown=7.696752586616294, got {max_drawdown}"

    print("\nTest passed!")
    return final_value


if __name__ == "__main__":
    print("=" * 60)
    print("Slippage Strategy Backtest")
    print("=" * 60)
    run()
