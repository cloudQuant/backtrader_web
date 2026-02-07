#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BB_ADX Bollinger Bands + ADX mean reversion strategy runner.

This module provides a run() function to execute the BB_ADX strategy backtest.
It loads configuration from config.yaml, data from strategy_bb_adx module,
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
from strategy_bb_adx import BBADXStrategy

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
    """Locate data files based on the script directory to avoid relative path reading failures.

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


def load_sh600000_data():
    """Load Shanghai stock data (SH600000) for backtesting.

    Returns:
        bt.feeds.PandasData: Data feed for backtrader.
    """
    print("Loading Shanghai stock data...")
    data_path = resolve_data_path("sh600000.csv")
    df = pd.read_csv(data_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')
    df = df.set_index('datetime')
    df = df[(df.index >= '2000-01-01') & (df.index <= '2022-12-31')]
    df = df[df['close'] > 0]

    df = df[['open', 'high', 'low', 'close', 'volume']]

    data_feed = bt.feeds.PandasData(
        dataname=df,
        datetime=None,
        open=0,
        high=1,
        low=2,
        close=3,
        volume=4,
        openinterest=-1,
    )
    return data_feed


def run():
    """Run the BB_ADX strategy backtest.

    This function creates a cerebro instance, loads Shanghai stock data,
    runs the backtesting with BBADXStrategy, and verifies results using
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
    data_feed = load_sh600000_data()
    cerebro.adddata(data_feed, name="SH600000")

    # Add strategy with parameters from config
    params = config.get('params', {})
    cerebro.addstrategy(BBADXStrategy, **params)




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

    print("Starting backtesting...")
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
    print("BB_ADX Bollinger Bands + ADX mean reversion strategy backtest results:")
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

    # Assertions - ensure strategy runs correctly (matching original test file)
    assert strat.bar_num == 5388, f"Expected bar_num=5388, got {strat.bar_num}"
    assert strat.buy_count == 296, f"Expected buy_count=296, got {strat.buy_count}"
    assert strat.sell_count == 295, f"Expected sell_count=295, got {strat.sell_count}"
    assert strat.win_count == 59, f"Expected win_count=59, got {strat.win_count}"
    assert strat.loss_count == 234, f"Expected loss_count=234, got {strat.loss_count}"
    assert total_trades == 293, f"Expected total_trades=293, got {total_trades}"
    assert abs(final_value - 99971.15) < 0.01, f"Expected final_value=99971.15, got {final_value}"
    assert abs(sharpe_ratio - (-317.95948928473916)) < 1e-6, f"Expected sharpe_ratio=-317.95948928473916, got {sharpe_ratio}"
    assert abs(annual_return - (-1.3426746125718879e-05)) < 1e-9, f"Expected annual_return=-1.3426746125718879e-05, got {annual_return}"
    assert abs(max_drawdown - 0.037680134320528774) < 1e-6, f"Expected max_drawdown=0.037680134320528774, got {max_drawdown}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("BB_ADX Bollinger Bands + ADX mean reversion strategy run")
    print("=" * 60)
    run()
