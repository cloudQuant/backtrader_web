#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BtcSentiment Bitcoin Sentiment strategy runner.

This module provides a run() function to execute the BtcSentiment strategy backtest.
It loads configuration from config.yaml, data from strategy_btc_sentiment module,
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
from strategy_btc_sentiment import BtcSentimentStrategy

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
    """Locate data files based on the script directory to avoid relative path failures.

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


def load_btc_data():
    """Load BTC price data and Google Trends sentiment data for backtesting.

    Returns:
        tuple: (btc_price_data_feed, gtrends_data_feed) for backtrader.
    """
    print("Loading BTC price data...")
    # First data source - BTC price data (Yahoo Finance CSV format)
    btc_price_path = resolve_data_path("BTCUSD_Weekly.csv")
    data1 = bt.feeds.YahooFinanceCSVData(
        dataname=str(btc_price_path),
        fromdate=datetime.datetime(2018, 1, 1),
        todate=datetime.datetime(2020, 1, 1),
        timeframe=bt.TimeFrame.Weeks
    )

    print("Loading Google Trends sentiment data...")
    # Second data source - Google Trends sentiment data
    gtrends_path = resolve_data_path("BTC_Gtrends.csv")
    data2 = bt.feeds.GenericCSVData(
        dataname=str(gtrends_path),
        fromdate=datetime.datetime(2018, 1, 1),
        todate=datetime.datetime(2020, 1, 1),
        nullvalue=0.0,
        dtformat='%Y-%m-%d',
        datetime=0,
        time=-1,
        high=-1,
        low=-1,
        open=-1,
        close=1,
        volume=-1,
        openinterest=-1,
        timeframe=bt.TimeFrame.Weeks
    )

    return data1, data2


def run():
    """Run the BtcSentiment strategy backtest.

    This function creates a cerebro instance, loads BTC price and sentiment data,
    runs the backtesting with BtcSentimentStrategy, and verifies results using
    assertions matching the original test file.

    Returns:
        Backtest results.
    """
    # Load configuration
    config = load_config()

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(config['backtest']['initial_cash'])
    cerebro.broker.setcommission(commission=config['backtest']['commission'])

    # Load data
    btc_data, gtrends_data = load_btc_data()
    cerebro.adddata(btc_data, name="BTCUSD")
    cerebro.adddata(gtrends_data, name="BTC_Gtrends")

    # Add strategy with parameters from config
    params = config.get('params', {})
    cerebro.addstrategy(BtcSentimentStrategy, **params)




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
    print("BtcSentiment Bitcoin Sentiment Strategy Backtest Results:")
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

    # Assertions - ensure the strategy runs correctly (matching original test file)
    assert strat.bar_num == 189, f"Expected bar_num=189, got {strat.bar_num}"
    assert strat.buy_count == 16, f"Expected buy_count=16, got {strat.buy_count}"
    assert strat.sell_count == 16, f"Expected sell_count=16, got {strat.sell_count}"
    assert strat.win_count == 8, f"Expected win_count=8, got {strat.win_count}"
    assert strat.loss_count == 8, f"Expected loss_count=8, got {strat.loss_count}"
    assert total_trades == 16, f"Expected total_trades=16, got {total_trades}"
    assert abs(final_value - 15301.43) < 0.01, f"Expected final_value=15301.43, got {final_value}"
    assert abs(sharpe_ratio - 0.8009805278904287) < 1e-6, f"Expected sharpe_ratio=0.8009805278904287, got {sharpe_ratio}"
    assert abs(annual_return - (0.2369894360907055)) < 1e-6, f"Expected annual_return=0.2369894360907055, got {annual_return}"
    assert abs(max_drawdown - 17.49122338684014) < 1e-6, f"Expected max_drawdown=17.49122338684014, got {max_drawdown}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("BtcSentiment Bitcoin Sentiment Strategy Run")
    print("=" * 60)
    run()
