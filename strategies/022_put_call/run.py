#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Put/Call比率情绪策略回测运行脚本

从config.yaml加载配置，运行回测并验证结果与预期值一致。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path

import backtrader as bt
import yaml

# 导入策略类和数据类
from strategy_put_call import PutCallStrategy, SPYPutCallData

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """通过搜索多个可能的目录路径来定位数据文件"""
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
    """加载SPY + Put/Call比率数据"""
    data_path = resolve_data_path("spy-put-call-fear-greed-vix.csv")
    data_feed = SPYPutCallData(
        dataname=str(data_path),
        fromdate=datetime.datetime(2011, 1, 1),
        todate=datetime.datetime(2021, 12, 31),
    )
    return data_feed


def run():
    """运行回测"""
    # 加载配置
    config = load_config()
    params = config['params']
    backtest_config = config['backtest']

    # 创建cerebro引擎
    cerebro = bt.Cerebro(stdstats=True)

    # 设置初始资金
    cerebro.broker.setcash(backtest_config['initial_cash'])

    # 加载SPY + Put/Call比率数据
    print("Loading SPY + Put/Call data...")
    data_feed = load_data()
    cerebro.adddata(data_feed, name="SPY")

    # 添加策略及默认参数
    cerebro.addstrategy(



        PutCallStrategy,
        high_threshold=params['high_threshold'],
        low_threshold=params['low_threshold'],
    )

    # 添加性能分析器
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="my_sharpe")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="my_returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="my_drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trade_analyzer")
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

    # 运行回测
    print("Starting backtest...")
    results = cerebro.run()

    # 提取结果
    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    drawdown_info = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown_info["max"]["drawdown"] / 100 if drawdown_info["max"]["drawdown"] else 0
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # 打印结果摘要
    print("\n" + "=" * 50)
    print("Put/Call Ratio Strategy Backtest Results:")
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

    # 验证结果与预期值一致
    assert strat.bar_num == 2445, f"Expected bar_num=2445, got {strat.bar_num}"
    assert strat.buy_count == 6, f"Expected buy_count=6, got {strat.buy_count}"
    assert strat.sell_count == 3, f"Expected sell_count=3, got {strat.sell_count}"
    assert strat.win_count == 3, f"Expected win_count=3, got {strat.win_count}"
    assert strat.loss_count == 0, f"Expected loss_count=0, got {strat.loss_count}"
    assert total_trades == 3, f"Expected total_trades=3, got {total_trades}"
    assert abs(sharpe_ratio - 0.8266766851573092) < 1e-6, f"Expected sharpe_ratio=0.8266766851573092, got {sharpe_ratio}"
    assert abs(annual_return - (0.09446114583761168)) < 1e-6, f"Expected annual_return=0.09446114583761168, got {annual_return}"
    assert abs(max_drawdown - 0.24769723055528914) < 1e-6, f"Expected max_drawdown=0.24769723055528914, got {max_drawdown}"
    assert abs(final_value - 240069.35) < 0.01, f"Expected final_value=240069.35, got {final_value}"

    print("\nTest passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Put/Call Ratio Strategy Test")
    print("=" * 60)
    run()
