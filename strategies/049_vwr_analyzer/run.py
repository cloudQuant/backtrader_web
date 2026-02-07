#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run module for VWR (Variability-Weighted Return) Analyzer Strategy.

This module runs the VWR analyzer backtest using the configuration
from config.yaml and the VWRTestStrategy from strategy_vwr.py.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import backtrader as bt
import yaml

from strategy_vwr import VWRTestStrategy

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


def load_backtrader_data(filename):
    """Load Backtrader CSV data.

    Args:
        filename: The data file name.

    Returns:
        bt.feeds.BacktraderCSVData: Backtrader data feed.
    """
    data_path = resolve_data_path(filename)
    return bt.feeds.BacktraderCSVData(dataname=str(data_path))


def run():
    """Run the VWR analyzer backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates and configures a Cerebro engine
    3. Loads historical price data
    4. Runs the VWRTestStrategy with multiple analyzers
    5. Validates results against expected values

    Returns:
        dict: Backtest results including all metrics.
    """
    # Load configuration
    config = load_config()
    strategy_params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    # Create Cerebro engine
    cerebro = bt.Cerebro(stdstats=True)
    initial_cash = backtest_config.get('initial_cash', 100000.0)
    cerebro.broker.setcash(initial_cash)

    # Load data
    print("Loading data...")
    data = load_backtrader_data("2005-2006-day-001.txt")
    cerebro.adddata(data)

    # Add strategy with parameters from config
    cerebro.addstrategy(VWRTestStrategy, **strategy_params)




    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")

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

    # Run backtest
    print("Starting backtest...")
    results = cerebro.run()
    strat = results[0]

    # Get analysis results
    returns = strat.analyzers.returns.get_analysis()
    sqn = strat.analyzers.sqn.get_analysis()
    vwr = strat.analyzers.vwr.get_analysis()
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = returns.get('rnorm', 0)
    drawdown = strat.analyzers.drawdown.get_analysis()
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # Extract VWR and SQN values
    vwr_ratio = vwr.get('vwr', None) if vwr else None
    sqn_ratio = sqn.get('sqn', None) if sqn else None

    # Print results
    print("\n" + "=" * 50)
    print("VWR Analyzer Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  vwr_ratio: {vwr_ratio}")
    print(f"  sqn_ratio: {sqn_ratio}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assert test results (matching original test file)
    assert strat.bar_num == 482, f"Expected bar_num=482, got {strat.bar_num}"
    assert abs(final_value - 100496.68) < 0.01, f"Expected final_value=100496.68, got {final_value}"
    assert abs(sharpe_ratio - 0.7052880693319075) < 1e-6, f"Expected sharpe_ratio=0.7052880693319075, got {sharpe_ratio}"
    assert abs(annual_return - 0.0024415216620913218) < 1e-6, f"Expected annual_return=0.0024415216620913218, got {annual_return}"
    assert abs(max_drawdown - 0.35642156216533016) < 1e-6, f"Expected max_drawdown=0.35642156216533016, got {max_drawdown}"
    assert total_trades == 9, f"Expected total_trades=9, got {total_trades}"
    assert vwr_ratio is not None, "VWR ratio should not be None"
    assert abs(vwr_ratio - 0.18671202740080534) < 1e-6, f"Expected vwr_ratio=0.18671202740080534, got {vwr_ratio}"
    assert sqn_ratio is not None, "SQN ratio should not be None"
    assert abs(sqn_ratio - 1.1860238182921676) < 1e-6, f"Expected sqn_ratio=1.1860238182921676, got {sqn_ratio}"

    print("\nTest passed!")

    return {
        'bar_num': strat.bar_num,
        'buy_count': strat.buy_count,
        'sell_count': strat.sell_count,
        'total_trades': total_trades,
        'vwr_ratio': vwr_ratio,
        'sqn_ratio': sqn_ratio,
        'sharpe_ratio': sharpe_ratio,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'final_value': final_value,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("VWR Analyzer Backtest")
    print("=" * 60)
    run()
