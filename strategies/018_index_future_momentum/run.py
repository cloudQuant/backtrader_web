#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""国债期货MACD策略回测运行脚本

从config.yaml加载配置，运行回测并验证结果与预期值一致。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from pathlib import Path

import pandas as pd
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent
import yaml

# 导入策略类
from strategy_index_future_momentum import TreasuryFuturesMacdStrategy

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory to avoid relative path failures."""
    search_paths = [
        BASE_DIR / "datas" / filename,
        BASE_DIR.parent / "datas" / filename,
        BASE_DIR.parent.parent / "datas" / filename,  # 项目根目录datas
        BASE_DIR.parent.parent / "tests" / "datas" / filename,
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent.parent / filename,
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found: {filename}")


def load_futures_data(variety: str = "T"):
    """Load futures data and construct index contract

    Args:
        variety: Variety code, default is T (Treasury futures)

    Returns:
        index_df: Index contract DataFrame
        data: Original data DataFrame
    """
    data = pd.read_csv(resolve_data_path("CFFEX_Futures_Contract_Data.csv"), index_col=0)
    data = data[data['variety'] == variety]
    data['datetime'] = pd.to_datetime(data['date'], format="%Y%m%d")
    data = data.dropna()

    # Synthesize index contract weighted by open interest
    result = []
    for index, df in data.groupby("datetime"):
        total_open_interest = df['open_interest'].sum()
        open_price = (df['open'] * df['open_interest']).sum() / total_open_interest
        high_price = (df['high'] * df['open_interest']).sum() / total_open_interest
        low_price = (df['low'] * df['open_interest']).sum() / total_open_interest
        close_price = (df['close'] * df['open_interest']).sum() / total_open_interest
        volume = (df['volume'] * df['open_interest']).sum() / total_open_interest
        open_interest = df['open_interest'].mean()
        result.append([index, open_price, high_price, low_price, close_price, volume, open_interest])

    index_df = pd.DataFrame(result, columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest'])
    index_df.index = pd.to_datetime(index_df['datetime'])
    index_df = index_df.drop(["datetime"], axis=1)

    return index_df, data


def run():
    """运行回测"""
    # 加载配置
    config = load_config()
    params = config['params']
    data_config = config['data']
    backtest_config = config['backtest']

    cerebro = bt.Cerebro(stdstats=True)

    # 加载期货数据
    print("Loading futures data...")
    index_df, data = load_futures_data(data_config['symbol'])
    print(f"Index data range: {index_df.index[0]} to {index_df.index[-1]}, total {len(index_df)} bars")

    # 加载指数合约
    feed = bt.feeds.PandasDirectData(dataname=index_df)
    cerebro.adddata(feed, name='index')
    comm = ComminfoFuturesPercent(
        commission=backtest_config['commission'],
        margin=backtest_config['margin'],
        mult=backtest_config['mult']
    )
    cerebro.broker.addcommissioninfo(comm, name="index")

    # 加载具体合约数据
    contract_count = 0
    for symbol, df in data.groupby("symbol"):
        df.index = pd.to_datetime(df['datetime'])
        df = df[['open', 'high', 'low', 'close', 'volume', 'open_interest']]
        df.columns = ['open', 'high', 'low', 'close', 'volume', 'openinterest']
        feed = bt.feeds.PandasDirectData(dataname=df)
        cerebro.adddata(feed, name=symbol)
        comm = ComminfoFuturesPercent(
            commission=backtest_config['commission'],
            margin=backtest_config['margin'],
            mult=backtest_config['mult']
        )
        cerebro.broker.addcommissioninfo(comm, name=symbol)
        contract_count += 1

    print(f"Successfully loaded {contract_count} contracts")

    # 设置初始资金
    cerebro.broker.setcash(backtest_config['initial_cash'])

    # 添加策略
    cerebro.addstrategy(



        TreasuryFuturesMacdStrategy,
        period_me1=params['period_me1'],
        period_me2=params['period_me2'],
        period_dif=params['period_dif']
    )

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
    print("\nStarting backtest...")
    results = cerebro.run()

    # 获取结果
    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    max_drawdown = strat.analyzers.my_drawdown.get_analysis()["max"]["drawdown"] / 100
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # 打印结果
    print("\n" + "=" * 50)
    print("Treasury Futures MACD Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # 断言测试结果（与原test文件完全一致）
    assert strat.bar_num == 1990, f"Expected bar_num=1990, got {strat.bar_num}"
    assert strat.buy_count == 38, f"Expected buy_count=38, got {strat.buy_count}"
    assert strat.sell_count == 38, f"Expected sell_count=38, got {strat.sell_count}"
    assert total_trades == 90, f"Expected total_trades=90, got {total_trades}"
    assert abs(sharpe_ratio - (-700.977360693882)) < 1e-6, f"Expected sharpe_ratio=-700.977360693882, got {sharpe_ratio}"
    assert abs(annual_return - (-2.2430503547013427e-06)) < 1e-12, f"Expected annual_return=-2.2430503547013427e-06, got {annual_return}"
    assert abs(max_drawdown - 6.587175196273877e-05) < 1e-9, f"Expected max_drawdown=6.587175196273877e-05, got {max_drawdown}"
    assert abs(final_value - 999982.2871600012) < 0.01, f"Expected final_value=999982.2871600012, got {final_value}"

    print("\nAll tests passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Treasury Futures MACD Strategy Backtest")
    print("=" * 60)
    run()
