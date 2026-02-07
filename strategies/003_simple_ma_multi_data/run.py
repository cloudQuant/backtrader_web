#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略运行脚本 - 多品种简单均线策略"""

import os
import yaml
from pathlib import Path

import backtrader as bt
import backtrader.indicators as btind
import pandas as pd

# 导入策略类
from strategy_simple_ma_multi_data import SimpleMAMultiDataStrategy, ExtendPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """查找数据文件路径"""
    search_paths = []

    # 1. Current directory
    search_paths.append(BASE_DIR / filename)

    # 2. tests directory and project root directory
    search_paths.append(BASE_DIR.parent / filename)
    repo_root = BASE_DIR.parent.parent
    search_paths.append(repo_root / filename)

    # 3. Common data directories
    search_paths.append(repo_root / "datas" / filename)
    search_paths.append(repo_root / "examples" / filename)
    search_paths.append(repo_root / "tests" / "datas" / filename)

    # 4. Directory specified by environment variable
    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    fallback = Path(filename)
    if fallback.exists():
        return fallback

    searched = " , ".join(str(path) for path in search_paths + [fallback.resolve()])
    raise FileNotFoundError(f"Data file not found: {filename}. Tried paths: {searched}")


def load_index_data(csv_file):
    """加载指数数据"""
    df = pd.read_csv(csv_file)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime")
    df = df.dropna()
    df = df.astype(float)
    return df


def load_bond_data_multi(csv_file, max_bonds=100):
    """加载多可转债数据"""
    df = pd.read_csv(csv_file)
    df.columns = [
        "BOND_CODE",
        "BOND_SYMBOL",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "pure_bond_value",
        "convert_value",
        "pure_bond_premium_rate",
        "convert_premium_rate",
    ]

    # 获取唯一可转债代码
    bond_codes = df["BOND_CODE"].unique()[:max_bonds]

    result = {}
    for code in bond_codes:
        bond_df = df[df["BOND_CODE"] == code].copy()
        bond_df["datetime"] = pd.to_datetime(bond_df["datetime"])
        bond_df = bond_df.set_index("datetime")
        bond_df = bond_df.drop(["BOND_CODE", "BOND_SYMBOL"], axis=1)
        bond_df = bond_df.dropna()
        bond_df = bond_df.astype(float)

        # 只保留数据充足的可转债（至少60个交易日）
        if len(bond_df) >= 60:
            result[str(code)] = bond_df

    return result


def run(max_bonds=30):
    """运行策略回测"""
    config = load_config()

    # 创建cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # 添加策略（从config加载参数）
    params = config.get('params', {})
    cerebro.addstrategy(SimpleMAMultiDataStrategy, **params)




    # 加载指数数据（用于时间对齐）
    print("Loading index data...")
    index_file = resolve_data_path("bond_index_000000.csv")
    index_df = load_index_data(index_file)
    index_feed = ExtendPandasFeed(dataname=index_df)
    cerebro.adddata(index_feed, name="index")

    # 加载可转债数据
    print("Loading convertible bond data...")
    bond_file = resolve_data_path("bond_merged_all_data.csv")
    bond_data_dict = load_bond_data_multi(bond_file, max_bonds=max_bonds)

    print(f"Loaded {len(bond_data_dict)} convertible bond data files")

    for bond_code, bond_df in bond_data_dict.items():
        feed = ExtendPandasFeed(dataname=bond_df)
        cerebro.adddata(feed, name=bond_code)

    # 回测配置
    bt_config = config.get('backtest', {})
    cerebro.broker.setcash(bt_config.get('initial_cash', 10000000.0))
    cerebro.broker.setcommission(commission=bt_config.get('commission', 0.0002), stocklike=True)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="total_value")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
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

    # 运行回测
    print("Starting backtest...")
    results = cerebro.run()
    strat = results[0]

    # 获取结果
    final_value = cerebro.broker.getvalue()
    sharpe_analysis = strat.analyzers.sharpe.get_analysis()
    returns_analysis = strat.analyzers.returns.get_analysis()
    drawdown_analysis = strat.analyzers.drawdown.get_analysis()
    trades_analysis = strat.analyzers.trades.get_analysis()

    total_trades = trades_analysis.get("total", {}).get("total", 0)
    sharpe_ratio = sharpe_analysis.get("sharperatio")
    annual_return = returns_analysis.get("rnorm")
    max_drawdown = (
        drawdown_analysis["max"]["drawdown"] if drawdown_analysis["max"]["drawdown"] else 0
    )

    # 打印结果
    print("\n" + "=" * 60)
    print("Backtest Results:")
    print(f"  Bonds loaded: {len(bond_data_dict)}")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown:.4f}%")
    print("=" * 60)

    # **关键**：与原test文件完全相同的断言
    assert len(bond_data_dict) == 30, f"Expected bonds_loaded=30, got {len(bond_data_dict)}"
    assert strat.bar_num == 4434, f"Expected bar_num=4434, got {strat.bar_num}"
    assert strat.buy_count == 463, f"Expected buy_count=463, got {strat.buy_count}"
    assert strat.sell_count == 450, f"Expected sell_count=450, got {strat.sell_count}"
    assert total_trades == 460, f"Expected total_trades=460, got {total_trades}"
    assert abs(sharpe_ratio - 0.1920060395982071) < 1e-6, f"Expected sharpe_ratio=0.1920060395982071, got {sharpe_ratio}"
    assert abs(max_drawdown - 17.7630) < 0.01, f"Expected max_drawdown=17.7630%, got {max_drawdown}"
    assert abs(final_value - 14535803.03) < 1.0, f"Expected final_value=14535803.03, got {final_value}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Multi-data Simple MA Strategy Backtest")
    print("=" * 60)
    run(max_bonds=30)
