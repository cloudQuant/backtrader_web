#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
示例: 加载自定义策略脚本

这个示例展示如何加载您自己的策略文件
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
from backtrader_web import WebServer
from backtrader_web.data import get_stock_data


# ============================================
# 在这里定义您的策略，或者从其他文件导入
# ============================================

class RSIStrategy(bt.Strategy):
    """RSI超买超卖策略"""
    params = (
        ('period', 14),
        ('overbought', 70),
        ('oversold', 30),
    )
    
    def __init__(self):
        self.rsi = bt.indicators.RSI(period=self.params.period)
    
    def next(self):
        if not self.position:
            if self.rsi < self.params.oversold:
                self.buy()
        elif self.rsi > self.params.overbought:
            self.sell()


class BollingerStrategy(bt.Strategy):
    """布林带策略"""
    params = (
        ('period', 20),
        ('devfactor', 2.0),
    )
    
    def __init__(self):
        self.boll = bt.indicators.BollingerBands(
            period=self.params.period,
            devfactor=self.params.devfactor
        )
    
    def next(self):
        if not self.position:
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.buy()
        elif self.data.close[0] > self.boll.lines.top[0]:
            self.sell()


def run_backtest(
    strategy_class,
    symbol: str = '000001',
    start_date: str = '2023-01-01',
    end_date: str = '2024-01-01',
    initial_cash: float = 100000,
    commission: float = 0.001,
    port: int = 8000,
    **strategy_params
):
    """
    运行回测并展示结果
    
    Args:
        strategy_class: 策略类
        symbol: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        initial_cash: 初始资金
        commission: 手续费率
        port: Web服务端口
        **strategy_params: 策略参数
    """
    # 创建Cerebro
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    
    # 加载数据
    print(f"📥 下载 {symbol} 数据: {start_date} ~ {end_date}")
    data = get_stock_data(symbol, start_date, end_date)
    cerebro.adddata(data)
    
    # 添加策略
    cerebro.addstrategy(strategy_class, **strategy_params)
    
    # 运行并展示
    server = WebServer(cerebro)
    server.run(port=port)


if __name__ == '__main__':
    # 示例1: 运行RSI策略
    # run_backtest(
    #     RSIStrategy,
    #     symbol='000001',
    #     start_date='2023-01-01',
    #     end_date='2024-01-01',
    #     period=14,
    #     overbought=70,
    #     oversold=30,
    # )
    
    # 示例2: 运行布林带策略
    run_backtest(
        BollingerStrategy,
        symbol='600519',  # 贵州茅台
        start_date='2022-01-01',
        end_date='2024-01-01',
        initial_cash=200000,
        period=20,
        devfactor=2.0,
    )
