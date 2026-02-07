#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MACD ATR Strategy runner.

This module provides a run() function to execute the MACD ATR strategy backtest.
It loads configuration from config.yaml, data from strategy_macd_atr module,
and runs the backtest with the same assertions as the original test file.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import yaml
import datetime
from pathlib import Path

import pandas as pd
import backtrader as bt

# Import strategy class
from strategy_macd_atr import MACDATRStrategy

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml.

    Returns:
        dict: Configuration dictionary containing strategy parameters.
    """
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the located data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the search paths.
    """
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR / "datas" / filename,
        BASE_DIR.parent / "datas" / filename,
        BASE_DIR.parent.parent / "datas" / filename,  # Add repository root datas folder
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for p in search_paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot find data file: {filename}")


def load_yahoo_data():
    """Load Yahoo Finance CSV data for backtesting.

    Returns:
        bt.feeds.YahooFinanceCSVData: Data feed for backtrader.
    """
    print("Loading data...")
    data_path = resolve_data_path("yhoo-1996-2014.txt")
    data = bt.feeds.YahooFinanceCSVData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2005, 1, 1),
        todate=datetime.datetime(2014, 12, 31)
    )
    return data


def run():
    """Run the MACD ATR strategy backtest.

    This function creates a cerebro instance, loads Yahoo stock data,
    runs the backtesting with MACDATRStrategy, and verifies results using
    assertions matching the original test file.

    Returns:
        Backtest results.
    """
    # Load configuration
    config = load_config()

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(config['backtest']['initial_cash'])

    # Load data
    data = load_yahoo_data()
    cerebro.adddata(data, name="YHOO")

    # Add strategy with parameters from config
    params = config.get('params', {})
    cerebro.addstrategy(MACDATRStrategy, **params)




    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
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

    print("Starting backtest...")
    results = cerebro.run()
    strat = results[0]

    # Get analyzer results
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get('sharperatio', None)
    returns = strat.analyzers.my_returns.get_analysis()
    annual_return = returns.get('rnorm', 0)
    drawdown = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.my_trade.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("MACD ATR Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  win_count: {strat.win_count}")
    print(f"  loss_count: {strat.loss_count}")
    print(f"  sum_profit: {strat.sum_profit:.2f}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assertions (matching original test file)
    assert strat.bar_num == 2477, f"Expected bar_num=2477, got {strat.bar_num}"
    assert strat.buy_count == 46, f"Expected buy_count=46, got {strat.buy_count}"
    assert strat.sell_count == 45, f"Expected sell_count=45, got {strat.sell_count}"
    assert strat.win_count == 17, f"Expected win_count=17, got {strat.win_count}"
    assert strat.loss_count == 28, f"Expected loss_count=28, got {strat.loss_count}"
    assert total_trades == 46, f"Expected total_trades=46, got {total_trades}"
    assert abs(final_value - 49993.58) < 0.01, f"Expected final_value=49993.58, got {final_value}"
    assert abs(sharpe_ratio - (-66.34914054216533)) < 1e-6, f"Expected sharpe_ratio=-66.34914054216533, got {sharpe_ratio}"
    assert abs(annual_return - (-1.2861156358361e-05)) < 1e-9, f"Expected annual_return=-1.2861156358361e-05, got {annual_return}"
    assert abs(max_drawdown - 0.07560831095513623) < 1e-6, f"Expected max_drawdown=0.07560831095513623, got {max_drawdown}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("MACD ATR Strategy Run")
    print("=" * 60)
    run()
