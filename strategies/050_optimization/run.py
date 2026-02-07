#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run module for Parameter Optimization Strategy.

This module runs the parameter optimization backtest using the configuration
from config.yaml and the OptimizeStrategy from strategy_optimization.py.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import datetime
from pathlib import Path
import backtrader as bt
import yaml

from strategy_optimization import OptimizeStrategy

BASE_DIR = Path(__file__).resolve().parent


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        dict: Configuration dictionary.
    """
    if config_path is None:
        config_path = BASE_DIR / 'config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Resolve the path to a data file by searching common locations.

    Args:
        filename: The name of the data file to locate.

    Returns:
        The absolute Path object pointing to the found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found.
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


def load_backtrader_data(filename, from_date=None, to_date=None):
    """Load Backtrader CSV data.

    Args:
        filename: The data file name.
        from_date: Start datetime for data loading.
        to_date: End datetime for data loading.

    Returns:
        bt.feeds.BacktraderCSVData: Backtrader data feed.
    """
    data_path = resolve_data_path(filename)
    return bt.feeds.BacktraderCSVData(
        dataname=str(data_path),
        fromdate=from_date,
        todate=to_date
    )


def run_optimization(config):
    """Run parameter optimization and return all results.

    Args:
        config: Configuration dictionary.

    Returns:
        A list of strategy run results from all parameter combinations.
    """
    strategy_params = config.get('params', {})
    optimization_config = config.get('optimization', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(maxcpus=optimization_config.get('maxcpus', 1))
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))

    data = load_backtrader_data(
        "2005-2006-day-001.txt",
        datetime.datetime(2006, 1, 1),
        datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data)

    # Use optimization range from config
    sma_range = optimization_config.get('smaperiod_range', [10, 11, 12])
    cerebro.optstrategy(
        OptimizeStrategy,
        smaperiod=sma_range,
        macdperiod1=[strategy_params.get('macdperiod1', 12)],
        macdperiod2=[strategy_params.get('macdperiod2', 26)],
        macdperiod3=[strategy_params.get('macdperiod3', 9)],
    )

    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)

    results = cerebro.run()
    return results


def run_best_strategy(best_params, config):
    """Run a complete backtest using the optimal parameter combination.

    Args:
        best_params: Dictionary containing the optimal parameter values.
        config: Configuration dictionary.

    Returns:
        A dictionary containing comprehensive strategy metrics.
    """
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))

    data = load_backtrader_data(
        "2005-2006-day-001.txt",
        datetime.datetime(2006, 1, 1),
        datetime.datetime(2006, 12, 31)
    )
    cerebro.adddata(data)

    # Use the best parameters
    cerebro.addstrategy(OptimizeStrategy, **best_params)




    # Add complete analyzers
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)
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
    ret = strat.analyzers.returns.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    return {
        'strat': strat,
        'bar_num': strat.bar_num,
        'buy_count': strat.buy_count,
        'sell_count': strat.sell_count,
        'sharpe_ratio': sharpe.get('sharperatio', None),
        'annual_return': ret.get('rnorm', 0),
        'max_drawdown': drawdown.get('max', {}).get('drawdown', 0),
        'total_trades': trades.get('total', {}).get('total', 0),
        'final_value': cerebro.broker.getvalue(),
    }


def run():
    """Run the parameter optimization backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Runs optimization over parameter space
    3. Selects best parameter combination
    4. Runs complete backtest with optimal parameters
    5. Validates results against expected values

    Returns:
        dict: Optimization results and best strategy metrics.
    """
    # Load configuration
    config = load_config()

    print("Loading data...")
    print("Starting optimization...")
    results = run_optimization(config)

    # Collect results from all parameter combinations
    all_results = []
    for stratrun in results:
        for strat in stratrun:
            params = strat.p._getkwargs()
            ret = strat.analyzers.returns.get_analysis()
            sharpe = strat.analyzers.sharpe.get_analysis()

            sharpe_ratio = sharpe.get('sharperatio', None)
            annual_return = ret.get('rnorm', 0)

            all_results.append({
                'smaperiod': params.get('smaperiod'),
                'sharpe_ratio': sharpe_ratio,
                'annual_return': annual_return,
            })

    # Print all optimization results
    print("\n" + "=" * 50)
    print("Parameter optimization results:")
    for r in all_results:
        print(f"  smaperiod={r['smaperiod']}: sharpe_ratio={r['sharpe_ratio']}, annual_return={r['annual_return']}")
    print(f"  Number of combinations: {len(all_results)}")
    print("=" * 50)

    # Find parameter combination with maximum Sharpe ratio
    best_result = max(all_results, key=lambda x: x['sharpe_ratio'] or -999)
    best_params = {'smaperiod': best_result['smaperiod']}

    print(f"\nBest parameter combination: {best_params}")
    print(f"  Sharpe ratio: {best_result['sharpe_ratio']}")
    print(f"  Annual return: {best_result['annual_return']}")

    # Run complete backtest with best parameters
    print("\nRunning complete backtest with best parameters...")
    best_metrics = run_best_strategy(best_params, config)

    # Print complete metrics for best strategy
    print("\n" + "=" * 50)
    print("Best strategy backtest results:")
    print(f"  params: smaperiod={best_params['smaperiod']}")
    print(f"  bar_num: {best_metrics['bar_num']}")
    print(f"  buy_count: {best_metrics['buy_count']}")
    print(f"  sell_count: {best_metrics['sell_count']}")
    print(f"  total_trades: {best_metrics['total_trades']}")
    print(f"  sharpe_ratio: {best_metrics['sharpe_ratio']}")
    print(f"  annual_return: {best_metrics['annual_return']}")
    print(f"  max_drawdown: {best_metrics['max_drawdown']}")
    print(f"  final_value: {best_metrics['final_value']:.2f}")
    print("=" * 50)

    # Assert test results (matching original test file)
    assert len(all_results) == 3, f"Expected 3 optimization runs, got {len(all_results)}"

    assert best_metrics['bar_num'] == 221, f"Expected bar_num=221, got {best_metrics['bar_num']}"
    assert abs(best_metrics['final_value'] - 100150.06) < 0.01, f"Expected final_value=100150.06, got {best_metrics['final_value']}"
    assert abs(best_metrics['sharpe_ratio'] - 0.4979380802957602) < 1e-6, f"Expected sharpe_ratio=0.4979380802957602, got {best_metrics['sharpe_ratio']}"
    assert abs(best_metrics['annual_return'] - 0.0014829327989227066) < 1e-6, f"Expected annual_return=0.0014829327989227066, got {best_metrics['annual_return']}"
    assert abs(best_metrics['max_drawdown'] - 0.2686681581344764) < 1e-6, f"Expected max_drawdown=0.2686681581344764, got {best_metrics['max_drawdown']}"
    assert best_metrics['total_trades'] == 10, f"Expected total_trades=10, got {best_metrics['total_trades']}"
    assert best_params['smaperiod'] == 10, f"Expected best smaperiod=10, got {best_params['smaperiod']}"

    print("\nTest passed!")

    return {
        'all_results': all_results,
        'best_params': best_params,
        'best_metrics': best_metrics,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("Optimization Parameter Backtest")
    print("=" * 60)
    run()
