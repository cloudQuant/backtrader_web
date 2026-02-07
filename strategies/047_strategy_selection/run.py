#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run script for Strategy Selection.

This script runs multiple strategies (StrategyA and StrategyB) with data loading
and validates results against expected values.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt

from strategy_selection import load_config, StrategyA, StrategyB

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching in common locations.

    This function searches for a data file in several standard locations
    relative to the strategy directory.

    Args:
        filename: The name of the data file to locate.

    Returns:
        The resolved Path object pointing to the data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of
            the search paths.
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


def run_strategy_with_analyzer(strategy_class, data_path, strategy_params=None):
    """Run a single strategy with analyzers and return results.

    Args:
        strategy_class: The strategy class to run.
        data_path: Path to the data file for backtesting.
        strategy_params: Parameters to pass to the strategy (optional).

    Returns:
        A dictionary containing strategy performance metrics including
        bar_num, buy_count, sell_count, sharpe_ratio, annual_return,
        max_drawdown, total_trades, and final_value.
    """
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(100000.0)

    data = bt.feeds.BacktraderCSVData(dataname=str(data_path))
    cerebro.adddata(data)

    if strategy_params:
        cerebro.addstrategy(strategy_class, **strategy_params)



    else:
        cerebro.addstrategy(strategy_class)

    cerebro.addsizer(bt.sizers.FixedSize, stake=10)

    # Add analyzers - calculate Sharpe ratio using daily timeframe
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

    results = cerebro.run()
    strat = results[0]

    # Get analysis results
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # Print results in standard format
    print("=" * 50)
    print(f"{strategy_class.__name__} Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    return {
        'strat': strat,
        'bar_num': strat.bar_num,
        'buy_count': strat.buy_count,
        'sell_count': strat.sell_count,
        'sharpe_ratio': sharpe_ratio,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'total_trades': total_trades,
        'final_value': final_value,
    }


def run():
    """Run the Strategy Selection backtest for both strategies.

    Loads configuration from config.yaml, sets up the cerebro engines,
    loads historical data, runs both strategies, and validates results.

    Returns:
        Dictionary containing results from both strategies.

    Raises:
        AssertionError: If any performance metric deviates from expected values.
    """
    # Load configuration from config.yaml
    config = load_config()
    data_config = config.get('data', {})
    strategy_a_params = config.get('strategy_a', {})
    strategy_b_params = config.get('strategy_b', {})

    print("Loading data...")
    data_file = data_config.get('symbol', '2005-2006-day-001') + ".txt"
    data_path = resolve_data_path(data_file)

    # Test StrategyA
    print("\n--- Testing StrategyA ---")
    result_a = run_strategy_with_analyzer(StrategyA, data_path, strategy_a_params)

    # Test StrategyB
    print("\n--- Testing StrategyB ---")
    result_b = run_strategy_with_analyzer(StrategyB, data_path, strategy_b_params)

    # Assert test results match expected values from original test
    assert result_a['bar_num'] == 482, f"Expected bar_num=482, got {result_a['bar_num']}"
    assert abs(result_a['final_value'] - 104966.80) < 0.01, f"Expected final_value=104966.80, got {result_a['final_value']}"
    assert abs(result_a['sharpe_ratio'] - 0.7210685207398165) < 1e-6, f"Expected sharpe=0.7210685207398165, got {result_a['sharpe_ratio']}"
    assert abs(result_a['annual_return'] - 0.024145144571516192) < 1e-6, f"Expected annual=0.024145144571516192, got {result_a['annual_return']}"
    assert abs(result_a['max_drawdown'] - 3.430658473286522) < 1e-6, f"Expected maxdd=3.430658473286522, got {result_a['max_drawdown']}"
    assert result_a['total_trades'] == 9, f"Expected total_trades=9, got {result_a['total_trades']}"

    assert result_b['bar_num'] == 502, f"Expected bar_num=502, got {result_b['bar_num']}"
    assert abs(result_b['final_value'] - 105258.30) < 0.01, f"Expected final_value=105258.30, got {result_b['final_value']}"
    assert abs(result_b['sharpe_ratio'] - 0.8804632119159153) < 1e-6, f"Expected sharpe=0.8804632119159153, got {result_b['sharpe_ratio']}"
    assert abs(result_b['annual_return'] - 0.025543999840699848) < 1e-6, f"Expected annual=0.025543999840699848, got {result_b['annual_return']}"
    assert abs(result_b['max_drawdown'] - 3.474930243071327) < 1e-6, f"Expected maxdd=3.474930243071327, got {result_b['max_drawdown']}"
    assert result_b['total_trades'] == 43, f"Expected total_trades=43, got {result_b['total_trades']}"

    print("\nAll tests passed!")
    return {'StrategyA': result_a, 'StrategyB': result_b}


if __name__ == "__main__":
    print("=" * 60)
    print("Strategy Selection Backtest")
    print("=" * 60)
    run()
