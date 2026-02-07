#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略运行脚本 - MACD+EMA期货趋势策略"""

import os
import datetime
import yaml
from pathlib import Path

import backtrader as bt
import pandas as pd
from backtrader.comminfo import ComminfoFuturesPercent

# 导入策略类
from strategy_macd_ema_fase import MacdEmaStrategy, RbPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """查找数据文件路径"""
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


def load_rb_data(filename: str = "rb/RB99.csv") -> pd.DataFrame:
    """加载螺纹钢期货数据"""
    data_kwargs = dict(
        fromdate=datetime.datetime(2010, 1, 1),
        todate=datetime.datetime(2020, 12, 31),
    )

    df = pd.read_csv(resolve_data_path(filename))
    # 只保留这些列
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']]
    # 设置datetime为索引
    df.index = pd.to_datetime(df['datetime'])
    df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]
    df = df[(df.index <= data_kwargs['todate']) & (df.index >= data_kwargs['fromdate'])]
    return df


def run():
    """运行策略回测"""
    config = load_config()

    # 创建cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # 添加策略（从config加载参数）
    params = config.get('params', {})
    cerebro.addstrategy(MacdEmaStrategy, **params)




    # 加载数据
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', 'RB99')
    print(f"Loading rebar futures data: {symbol}.csv...")
    df = load_rb_data(f"rb/{symbol}.csv")
    print(f"Data range: {df.index[0]} to {df.index[-1]}, total {len(df)} records")

    # 使用RbPandasFeed加载数据
    name = symbol
    feed = RbPandasFeed(dataname=df)
    cerebro.adddata(feed, name=name)

    # 设置合约交易信息
    bt_config = config.get('backtest', {})
    comm = ComminfoFuturesPercent(
        commission=bt_config.get('commission', 0.0002),
        margin=bt_config.get('margin', 0.1),
        mult=bt_config.get('multiplier', 10)
    )
    cerebro.broker.addcommissioninfo(comm, name=name)
    cerebro.broker.setcash(bt_config.get('initial_cash', 50000.0))

    # 添加分析器
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
    strat = results[0]

    # 获取结果
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    max_drawdown = strat.analyzers.my_drawdown.get_analysis()["max"]["drawdown"] / 100
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # 打印结果
    print("\n" + "=" * 60)
    print("Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 60)

    # **关键**：与原test文件完全相同的断言
    assert strat.bar_num == 28069, f"Expected bar_num=28069, got {strat.bar_num}"
    assert strat.buy_count == 1008, f"Expected buy_count=1008, got {strat.buy_count}"
    assert strat.sell_count == 1008, f"Expected sell_count=1008, got {strat.sell_count}"
    assert total_trades == 1008, f"Expected total_trades=1008, got {total_trades}"
    assert abs(sharpe_ratio - (-0.4094093376341401)) < 1e-6, f"Expected sharpe_ratio=-0.4094093376341401, got {sharpe_ratio}"
    assert abs(annual_return - (-0.016850037618788616)) < 1e-6, f"Expected annual_return=-0.016850037618788616, got {annual_return}"
    assert abs(max_drawdown - 0.3294344677230617) < 1e-6, f"Expected max_drawdown=0.3294344677230617, got {max_drawdown}"
    assert abs(final_value - 41589.93032683378) < 0.01, f"Expected final_value=41589.93032683378, got {final_value}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("MACD EMA Futures Strategy Backtest")
    print("=" * 60)
    run()
