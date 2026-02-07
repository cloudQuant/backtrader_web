#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Pairs Trading Strategy.

This script runs the Pairs Trading strategy which uses OLS transformation
and Z-Score to trade pairs of assets.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from pathlib import Path

import pandas as pd
import backtrader as bt
import yaml

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml.

    Returns:
        dict: Configuration dictionary containing strategy parameters,
              data configuration, and backtest settings.
    """
    config_path = BASE_DIR / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the located data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            search paths.
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


def load_pair_data(symbol: str):
    """Load data for a pair of assets (V and MA).

    Args:
        symbol: Symbol pair identifier (e.g., "V-MA")

    Returns:
        tuple: (data_v, data_ma) - Two Backtrader data feeds
    """
    # Load Visa data
    data_path_v = resolve_data_path("V.csv")
    df_v = pd.read_csv(data_path_v, parse_dates=['Date'], index_col='Date')
    df_v = df_v[['Open', 'High', 'Low', 'Close', 'Volume']]
    df_v.columns = ['open', 'high', 'low', 'close', 'volume']

    # Load Mastercard data
    data_path_ma = resolve_data_path("MA.csv")
    df_ma = pd.read_csv(data_path_ma, parse_dates=['Date'], index_col='Date')
    df_ma = df_ma[['Open', 'High', 'Low', 'Close', 'Volume']]
    df_ma.columns = ['open', 'high', 'low', 'close', 'volume']

    # Align date ranges
    common_dates = df_v.index.intersection(df_ma.index)
    df_v = df_v.loc[common_dates]
    df_ma = df_ma.loc[common_dates]

    # Use only partial data for faster testing
    df_v = df_v.iloc[:500]
    df_ma = df_ma.iloc[:500]

    data_v = bt.feeds.PandasData(dataname=df_v, name='V')
    data_ma = bt.feeds.PandasData(dataname=df_ma, name='MA')

    return data_v, data_ma


def run():
    """Run the Pairs Trading strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates and configures a Cerebro engine
    3. Adds data feeds for both assets in the pair
    4. Runs the backtest
    5. Validates results against expected values
    """
    config = load_config()

    # Get strategy parameters from config
    strategy_params = config.get('params', {})
    data_config = config.get('data', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro()

    print("Loading data...")
    symbol = data_config.get('symbol', 'V-MA')
    data_v, data_ma = load_pair_data(symbol)
    cerebro.adddata(data_v)
    cerebro.adddata(data_ma)

    cerebro.addstrategy(PairsTradingStrategy)



    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000))
    cerebro.broker.setcommission(commission=backtest_config.get('commission', 0.001))

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
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

    results = cerebro.run()
    strat = results[0]

    # Get analysis results
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("Pairs Trading Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 451, f"Expected bar_num=451, got {strat.bar_num}"
    assert abs(final_value - 99699.43) < 0.01, f"Expected final_value=99699.43, got {final_value}"
    assert abs(sharpe_ratio - (-0.3156462969633222)) < 1e-6, f"Expected sharpe_ratio=-0.3156462969633222, got {sharpe_ratio}"
    assert abs(annual_return - (-0.0015160238352949257)) < 1e-6, f"Expected annual_return=-0.0015160238352949257, got {annual_return}"
    assert abs(max_drawdown - 1.1570119745556364) < 1e-6, f"Expected max_drawdown=0.0, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    # Import the strategy class
    from strategy_pairs_trading import PairsTradingStrategy

    print("=" * 60)
    print("Pairs Trading Strategy")
    print("=" * 60)
    run()
