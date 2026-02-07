#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EMA双均线交叉策略回测运行脚本

从config.yaml加载配置，运行回测并验证结果与预期值一致。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path

import backtrader as bt
import yaml

# 导入策略类
from strategy_ema_cross import EmaCrossStrategy

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """通过搜索多个目录路径来定位数据文件"""
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent.parent / filename,
        BASE_DIR.parent.parent / "datas" / filename,
        BASE_DIR.parent.parent / "tests" / "datas" / filename,
    ]

    # 检查环境变量中的额外数据目录
    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    # 返回第一个存在的路径
    for candidate in search_paths:
        if candidate.exists():
            return candidate

    # 文件未找到
    raise FileNotFoundError(f"Data file not found: {filename}")


def load_minute_data():
    """加载5分钟数据"""
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
        compression=5,  # 5分钟bar
    )
    return minute_data


def load_daily_data():
    """加载日线数据"""
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
    """运行回测"""
    # 加载配置
    config = load_config()
    params = config['params']
    backtest_config = config['backtest']

    # 创建cerebro引擎
    cerebro = bt.Cerebro(stdstats=True)

    # 设置初始资金和手续费设置
    cerebro.broker.setcash(backtest_config['initial_cash'])
    if backtest_config.get('coc', False):
        cerebro.broker.set_coc(True)  # Cheat On Close - 收盘价执行

    # 加载5分钟数据 (datas[0])
    print("Loading minute data...")
    minute_data = load_minute_data()
    cerebro.adddata(minute_data, name="minute")

    # 加载日线数据 (datas[1])
    print("Loading daily data...")
    daily_data = load_daily_data()
    cerebro.adddata(daily_data, name="daily")

    # 添加策略及参数
    cerebro.addstrategy(



        EmaCrossStrategy,
        fast_period=params['fast_period'],
        slow_period=params['slow_period'],
        short_size=params['short_size'],
        long_size=params['long_size'],
    )

    # 添加性能分析器
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
    # 使用日线时间框架计算Sharpe比率，避免分钟数据的RATEFACTORS问题
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
    max_drawdown = (
        drawdown_info["max"]["drawdown"] / 100
        if drawdown_info["max"]["drawdown"]
        else 0
    )
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # 打印结果
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

    # 验证结果与预期值一致
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
