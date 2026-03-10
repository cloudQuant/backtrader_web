#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VIXVolatility IndexStrategyBacktestRunscript

Load configuration from config.yaml，RunBacktestand verify resultsandmatch expected values。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path

import backtrader as bt
import yaml

# Import strategy classand data class
from strategy_vix import VIXStrategy, SPYVixData

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """locate by searching multiple possible directory pathsDatafile"""
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent.parent / filename,
        BASE_DIR.parent.parent / "datas" / filename,
        BASE_DIR.parent.parent / "tests" / "datas" / filename,
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found: {filename}")


def load_data():
    """LoadSPY + VIXData"""
    data_path = resolve_data_path("spy-put-call-fear-greed-vix.csv")
    data_feed = SPYVixData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2011, 1, 1),
        todate=datetime.datetime(2021, 12, 31),
    )
    return data_feed


def run():
    """RunBacktest"""
    # Load configuration
    config = load_config()
    params = config['params']
    backtest_config = config['backtest']

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Set initial cash
    cerebro.broker.setcash(backtest_config['initial_cash'])

    # Load data (datas[0])
    print("Loading SPY + VIX data...")
    data_feed = load_data()
    cerebro.adddata(data_feed, name="SPY")

    # AddStrategy
    cerebro.addstrategy(



        VIXStrategy,
        high_threshold=params['high_threshold'],
        low_threshold=params['low_threshold'],
    )

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="my_sharpe")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="my_returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="my_drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trade_analyzer")
    # Logging configuration
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    cerebro.addobserver(
        bt.observers.TradeLogger,
        log_orders=True,
        log_trades=True,
        log_positions=True,
        log_data=True,
        log_indicators=True,       # Include strategy indicators in data log
        log_dir=log_dir,
        log_file_enabled=True,
        file_format='log',         # Default log (tab-separated), 'csv' also available
        # MySQL disabled by default - uncomment to enable
        # mysql_enabled=True,
        # mysql_host='localhost',
        # mysql_port=3306,
        # mysql_user='root',
        # mysql_password='your_password',
        # mysql_database='backtrder_web',
        # mysql_table_prefix='bt',
    )

    # Run backtest
    print("Starting backtest...")
    results = cerebro.run()

    # Get results
    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    drawdown_info = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown_info["max"]["drawdown"] / 100 if drawdown_info["max"]["drawdown"] else 0
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("\n" + "=" * 50)
    print("VIX Volatility Index Strategy Backtest Results:")
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

    # Assert - EnsureStrategyRun correctly
    assert strat.bar_num == 2445, f"Expected bar_num=2445, got {strat.bar_num}"
    assert strat.buy_count == 3, f"Expected buy_count=3, got {strat.buy_count}"
    assert strat.sell_count == 1, f"Expected sell_count=1, got {strat.sell_count}"
    assert strat.win_count == 1, f"Expected win_count=1, got {strat.win_count}"
    assert strat.loss_count == 0, f"Expected loss_count=0, got {strat.loss_count}"
    assert total_trades == 2, f"Expected total_trades=2, got {total_trades}"
    assert abs(sharpe_ratio - 0.918186863324403) < 1e-6, f"Expected sharpe_ratio=0.918186863324403, got {sharpe_ratio}"
    assert abs(annual_return - (0.1040505783834931)) < 1e-6, f"Expected annual_return=0.1040505783834931, got {annual_return}"
    assert abs(max_drawdown - 0.3367517000981378) < 1e-6, f"Expected max_drawdown=0.3367517000981378, got {max_drawdown}"
    assert abs(final_value - 261273.5) < 0.01, f"Expected final_value=261273.50, got {final_value}"

    print("\nTest passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("VIX Volatility Index Strategy Test")
    print("=" * 60)
    run()
