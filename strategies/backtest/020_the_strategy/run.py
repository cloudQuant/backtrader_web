#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EMA Dual Moving Average Crossover Strategy backtest runner script.

Loads configuration from config.yaml, runs backtest, and verifies results match expected values.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path

import backtrader as bt
import yaml

# Import strategy class
from strategy_ema_cross import EmaCrossStrategy

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Locate data files by searching multiple directory paths."""
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent.parent / filename,
        BASE_DIR.parent.parent / "datas" / filename,
        BASE_DIR.parent.parent / "tests" / "datas" / filename,
    ]

    # Check additional data directory from environment variable
    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    # Return first existing path
    for candidate in search_paths:
        if candidate.exists():
            return candidate

    # File not found
    raise FileNotFoundError(f"Data file not found: {filename}")


def load_minute_data():
    """Load 5-minute data."""
    minute_data_path = resolve_data_path("2006-min-005.txt")
    minute_data = bt.feeds.GenericCSVData(
        dataname=str(minute_data_path),
        fromdate=datetime.datetime(2006, 1, 1),
        todate=datetime.datetime(2006, 12, 31),
        dtformat="%Y-%m-%d",
        tmformat="%H:%M:%S",
        datetime=0,
        time=1,
        open=2,
        high=3,
        low=4,
        close=5,
        volume=6,
        openinterest=7,
        timeframe=bt.TimeFrame.Minutes,
        compression=5,  # 5-minute bar
    )
    return minute_data


def load_daily_data():
    """Load daily data."""
    daily_data_path = resolve_data_path("2006-day-001.txt")
    daily_data = bt.feeds.GenericCSVData(
        dataname=str(daily_data_path),
        fromdate=datetime.datetime(2006, 1, 1),
        todate=datetime.datetime(2006, 12, 31),
        dtformat="%Y-%m-%d",
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=6,
        timeframe=bt.TimeFrame.Days,
    )
    return daily_data


def run():
    """Run backtest."""
    # Load configuration
    config = load_config()
    params = config['params']
    backtest_config = config['backtest']

    # Create cerebro engine
    cerebro = bt.Cerebro(stdstats=True)

    # Set initial capital and commission settings
    cerebro.broker.setcash(backtest_config['initial_cash'])
    if backtest_config.get('coc', False):
        cerebro.broker.set_coc(True)  # Cheat On Close - execute at close price

    # Load 5-minute data (datas[0])
    print("Loading minute data...")
    minute_data = load_minute_data()
    cerebro.adddata(minute_data, name="minute")

    # Load daily data (datas[1])
    print("Loading daily data...")
    daily_data = load_daily_data()
    cerebro.adddata(daily_data, name="daily")

    # Add strategy with parameters
    cerebro.addstrategy(
        EmaCrossStrategy,
        fast_period=params['fast_period'],
        slow_period=params['slow_period'],
        short_size=params['short_size'],
        long_size=params['long_size'],
    )

    # Add performance analyzers
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
    # Use daily timeframe for Sharpe ratio to avoid RATEFACTORS issues with minute data
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="my_sharpe",
        timeframe=bt.TimeFrame.Days,
        annualize=True,
        riskfreerate=0.0
    )
    cerebro.addanalyzer(bt.analyzers.Returns, _name="my_returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="my_drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trade_analyzer")
    # Log configuration
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    cerebro.addobserver(
        bt.observers.TradeLogger,
        log_orders=True,
        log_trades=True,
        log_positions=True,
        log_data=True,
        log_indicators=True,       # Include strategy indicators in data logs
        log_dir=log_dir,
        log_file_enabled=True,
        file_format='log',         # Default log (tab-separated), also supports 'csv'
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

    # Extract results
    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    drawdown_info = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = (
        drawdown_info["max"]["drawdown"] / 100
        if drawdown_info["max"]["drawdown"]
        else 0
    )
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("\n" + "=" * 50)
    print("EMA Dual Moving Average Crossover Strategy Backtest Results:")
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

    # Verify results match expected values
    assert strat.bar_num == 1780, f"Expected bar_num=1780, got {strat.bar_num}"
    assert abs(final_value - 99981.71) < 0.01, f"Expected final_value=99981.71, got {final_value}"
    assert total_trades == 2, f"Expected total_trades=2, got {total_trades}"
    assert (
        abs(max_drawdown - 0.0012456157963720896) < 1e-6
    ), f"Expected max_drawdown=0.0012456157963720896, got {max_drawdown}"
    assert (
        abs(annual_return - (-7.631068888840081e-08)) < 1e-6
    ), f"Expected annual_return=-7.631068888840081e-08, got {annual_return}"

    print("\nTest passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("EMA Dual Moving Average Crossover Strategy Test")
    print("=" * 60)
    run()
