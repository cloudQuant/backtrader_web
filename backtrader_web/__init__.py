"""
Backtrader Web - Quantitative backtest visualization framework.

This package provides web-based visualization for backtrader backtest results.

Usage:
    >>> from backtrader_web import WebServer
    >>> import backtrader as bt
    >>>
    >>> cerebro = bt.Cerebro()
    >>> # ... configure strategy and data
    >>>
    >>> server = WebServer(cerebro)
    >>> server.run(port=8000)
"""

from .server import WebServer
from .analyzer import BacktestAnalyzer

__version__ = "0.1.0"
__all__ = ["WebServer", "BacktestAnalyzer"]
