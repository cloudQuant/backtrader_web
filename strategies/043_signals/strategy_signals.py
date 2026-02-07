#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Signals Strategy

Reference: backtrader-master2/samples/signals-strategy/signals-strategy.py
Uses cerebro.add_signal() for indicator-based trading without writing a Strategy class
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from pathlib import Path
from typing import Dict, Any

import yaml
import backtrader as bt


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Configuration dictionary.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class SMACloseSignal(bt.Indicator):
    """Simple Moving Average (SMA) close price signal indicator.

    This indicator calculates the difference between the current price and
    its Simple Moving Average (SMA). The resulting signal can be used with
    cerebro.add_signal() to implement trend-following strategies.

    Signal Calculation:
        signal = price - SMA(period)

    Signal Interpretation:
        - Positive signal (> 0): Price is above SMA (bullish)
        - Negative signal (< 0): Price is below SMA (bearish)
        - Signal magnitude: Distance from SMA (strength of trend)

    Trading Logic:
        When used with SIGNAL_LONG:
        - Signal > 0: Take long position (price above average = uptrend)
        - Signal < 0: Exit position (price below average = downtrend)

        The actual position size is proportional to the signal value,
        meaning stronger trends (larger signal) result in larger positions.

    Lines:
        signal: The calculated signal value (price - SMA).

    Parameters:
        period (int): Period for the SMA calculation (default: 30).
            Longer periods produce smoother signals with fewer crossovers.
            Shorter periods produce more responsive signals with more noise.
    """

    lines = ('signal',)
    params = (('period', 30),)

    def __init__(self):
        """Calculate the SMA signal indicator.

        The signal is calculated as the difference between the current
        price and its Simple Moving Average. This provides a measure
        of whether price is above or below its average value.

        Signal = price - SMA(period)

        A positive signal indicates price is trading above the moving
        average (bullish), while negative indicates below (bearish).
        """
        # Calculate signal as price minus SMA
        # Positive when price above SMA (bullish trend)
        # Negative when price below SMA (bearish trend)
        # Magnitude indicates distance from average (trend strength)
        self.lines.signal = self.data - bt.indicators.SMA(period=self.p.period)


def run_signals_strategy(config: Dict[str, Any] = None):
    """Run the Signals Strategy backtest.

    This demonstrates the signal-based approach to trading strategies.
    Unlike traditional Strategy classes, signals use indicator values
    to drive trading decisions directly via cerebro.add_signal().

    Args:
        config: Configuration dictionary. If None, loads from config.yaml.

    Returns:
        Configured Cerebro instance.
    """
    if config is None:
        config = load_config()

    # Extract parameters from config
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 50000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Add signal-based strategy using cerebro.add_signal
    # SIGNAL_LONG: Take long position when signal is positive
    # SMACloseSignal: Custom indicator calculating price - SMA(period)
    # period: SMA period for signal calculation
    period = params.get('period', 30)
    cerebro.add_signal(bt.SIGNAL_LONG, SMACloseSignal, period=period)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_signals_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
