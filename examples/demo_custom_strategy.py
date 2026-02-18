#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Example: Loading custom strategy scripts.

This example demonstrates how to load your own strategy files.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
from backtrader_web import WebServer
from backtrader_web.data import get_stock_data


# ============================================
# Define your strategy here, or import from other files
# ============================================

class RSIStrategy(bt.Strategy):
    """RSI overbought/oversold strategy."""
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
    """Bollinger Bands strategy."""
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
    Run backtest and display results.

    Args:
        strategy_class: Strategy class.
        symbol: Stock code.
        start_date: Start date.
        end_date: End date.
        initial_cash: Initial capital.
        commission: Commission rate.
        port: Web server port.
        **strategy_params: Strategy parameters.
    """
    # Create Cerebro
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)

    # Load data
    print(f"📥 Downloading {symbol} data: {start_date} ~ {end_date}")
    data = get_stock_data(symbol, start_date, end_date)
    cerebro.adddata(data)

    # Add strategy
    cerebro.addstrategy(strategy_class, **strategy_params)

    # Run and display
    server = WebServer(cerebro)
    server.run(port=port)


if __name__ == '__main__':
    # Example 1: Run RSI strategy
    # run_backtest(
    #     RSIStrategy,
    #     symbol='000001',
    #     start_date='2023-01-01',
    #     end_date='2024-01-01',
    #     period=14,
    #     overbought=70,
    #     oversold=30,
    # )

    # Example 2: Run Bollinger Bands strategy
    run_backtest(
        BollingerStrategy,
        symbol='600519',  # Kweichow Moutai
        start_date='2022-01-01',
        end_date='2024-01-01',
        initial_cash=200000,
        period=20,
        devfactor=2.0,
    )
