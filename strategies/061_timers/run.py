#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run script for Timer Strategy.

This script runs the Timer strategy which tests timer functionality
using a dual moving average crossover strategy.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import datetime
from pathlib import Path
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
    """Resolve the path to a data file by searching in common locations.

    Args:
        filename: The name of the data file to locate.

    Returns:
        Path: The absolute path to the first found matching file.

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


def load_data(symbol: str):
    """Load data for the strategy.

    Args:
        symbol: Data file name or symbol

    Returns:
        Backtrader data feed with session time configured
    """
    data_path = resolve_data_path(f"{symbol}.txt")
    return bt.feeds.BacktraderCSVData(
        dataname=str(data_path),
        timeframe=bt.TimeFrame.Days,
        compression=1,
        sessionstart=datetime.time(9, 0),
        sessionend=datetime.time(17, 30),
    )


def run():
    """Run the Timer strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates and configures a Cerebro engine
    3. Adds data and strategy with timer enabled
    4. Runs the backtest
    5. Validates results against expected values
    """
    config = load_config()

    # Get strategy parameters from config
    strategy_params = config.get('params', {})
    data_config = config.get('data', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))

    print("Loading data...")
    symbol = data_config.get('symbol', '2005-2006-day-001')
    data = load_data(symbol)
    cerebro.adddata(data)

    # Map string config to bt.timer values
    when_value = strategy_params.get('when', 'SESSION_START')
    if isinstance(when_value, str) and when_value == 'SESSION_START':
        when_value = bt.timer.SESSION_START

    cerebro.addstrategy(



        TimerStrategy,
        timer=strategy_params.get('timer', True),
        when=when_value,
        fast_period=strategy_params.get('fast_period', 10),
        slow_period=strategy_params.get('slow_period', 30)
    )
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Add complete analyzers - calculate Sharpe ratio using daily timeframe
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)
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
    print("Timers Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  timer_count: {strat.timer_count}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assert test results
    assert strat.bar_num == 482, f"Expected bar_num=482, got {strat.bar_num}"
    assert strat.timer_count == 512, f"Expected timer_count=512, got {strat.timer_count}"
    assert abs(final_value - 104966.80) < 0.01, f"Expected final_value=104966.80, got {final_value}"
    assert abs(sharpe_ratio - 0.7210685207398165) < 1e-6, f"Expected sharpe_ratio=0.7210685207398165, got {sharpe_ratio}"
    assert abs(annual_return - 0.024145144571516192) < 1e-6, f"Expected annual_return=0.024145144571516192, got {annual_return}"
    assert abs(max_drawdown - 3.430658473286522) < 1e-6, f"Expected max_drawdown=3.430658473286522, got {max_drawdown}"
    assert total_trades == 9, f"Expected total_trades=9, got {total_trades}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    # Import the strategy class
    from strategy_timers import TimerStrategy

    print("=" * 60)
    print("Timer Strategy")
    print("=" * 60)
    run()
