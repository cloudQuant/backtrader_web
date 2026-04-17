"""Capacity-analysis plotting functions.

Includes capacity sweep and cone plots.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
from matplotlib import figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from fincore.constants import (
    CAPACITY_SWEEP_MAX_PV,
    CAPACITY_SWEEP_MIN_PV,
    CAPACITY_SWEEP_STEP,
    MM_DISPLAY_UNIT,
)

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["plot_capacity_sweep", "plot_cones"]


def plot_capacity_sweep(
    empyrical_instance: Any,
    returns: pd.Series,
    transactions: pd.DataFrame,
    market_data: Any,
    bt_starting_capital: float,
    min_pv: int = CAPACITY_SWEEP_MIN_PV,
    max_pv: int = CAPACITY_SWEEP_MAX_PV,
    step_size: int = CAPACITY_SWEEP_STEP,
    ax: Any = None,
) -> Any:
    """
    Plots capacity sweep showing Sharpe ratio vs. capital base.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy.
    transactions : pd.DataFrame
        Executed trade volumes and fill prices.
    market_data : pd.Panel or dict
        Panel/dict with items axis of 'price' and 'volume' DataFrames.
    bt_starting_capital : float
        Starting capital of the backtest.
    min_pv : int, optional
        Minimum portfolio value.
    max_pv : int, optional
        Maximum portfolio value.
    step_size : int, optional
        Step size for the sweep.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    import pandas as pd

    txn_daily_w_bar = empyrical_instance.daily_txns_with_bar_data(transactions, market_data)

    # Avoid dtype FutureWarning for empty Series construction.
    captial_base_sweep = pd.Series(dtype=float)
    for start_pv in range(min_pv, max_pv, step_size):
        adj_ret = empyrical_instance.apply_slippage_penalty(returns, txn_daily_w_bar, start_pv, bt_starting_capital)
        sharpe = empyrical_instance.sharpe_ratio(adj_ret)
        if sharpe < -1:
            break
        captial_base_sweep.loc[start_pv] = sharpe
    captial_base_sweep.index = captial_base_sweep.index / MM_DISPLAY_UNIT

    if ax is None:
        ax = plt.gca()

    captial_base_sweep.plot(ax=ax)
    ax.set_xlabel("Capital base ($mm)")
    ax.set_ylabel("Sharpe ratio")
    ax.set_title("Capital base performance sweep")

    return ax


def plot_cones(
    empyrical_instance: Any,
    name: str,
    bounds: Any,
    oos_returns: pd.Series,
    _num_samples: int = 1000,
    ax: Any = None,
    cone_std: tuple[float, ...] = (1.0, 1.5, 2.0),
    _random_seed: int | None = None,
    num_strikes: int = 3,
) -> Any:
    """
    Plots the upper and lower bounds of an n standard deviation
    cone of forecasted cumulative returns. Redraws a new cone when
    cumulative returns fall outside of the last cone drawn.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    name : str
        Account name to be used as figure title.
    bounds : pandas.core.frame.DataFrame
        Contains upper and lower cone boundaries.
    oos_returns : pandas.core.frame.DataFrame
        Non-cumulative out-of-sample returns.
    _num_samples : int, optional
        Number of samples to draw from the in-sample daily returns.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    cone_std : list of int/float, optional
        Number of standard deviations to use in the boundaries of
        the cone.
    _random_seed : int, optional
        Seed for the pseudorandom number generator.
    num_strikes : int, optional
        Upper limit for number of cones drawn.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    fig : matplotlib.figure
        The figure instance which contains all the plot elements.
    """
    if ax is None:
        fig = figure.Figure(figsize=(10, 8))
        FigureCanvasAgg(fig)
        axes = fig.add_subplot(111)
    else:
        axes = ax

    returns = empyrical_instance.cum_returns(oos_returns, starting_value=1.0)
    bounds_tmp = bounds.copy()
    returns_tmp = returns.copy()
    cone_start = returns.index[0]
    colors = ["green", "orange", "orangered", "darkred"]

    for c in range(num_strikes + 1):
        if c > 0:
            tmp = returns.loc[cone_start:]
            bounds_tmp = bounds_tmp.iloc[0 : len(tmp)]
            bounds_tmp = bounds_tmp.set_index(tmp.index)
            crossing = tmp < bounds_tmp[(-2.0)].iloc[: len(tmp)]
            if crossing.sum() <= 0:
                break
            cone_start = crossing.loc[crossing].index[0]
            returns_tmp = returns.loc[cone_start:]
            bounds_tmp = bounds - (1 - returns.loc[cone_start])
        for std in cone_std:
            x = returns_tmp.index
            y1 = bounds_tmp[float(std)].iloc[: len(returns_tmp)]
            y2 = bounds_tmp[float(-std)].iloc[: len(returns_tmp)]
            axes.fill_between(x, y1, y2, color=colors[c], alpha=0.5)

    # Plot returns line graph
    label = f"Cumulative returns = {(returns.iloc[-1] - 1) * 100:.2f}%"
    axes.plot(returns.index, returns.values, color="black", lw=3.0, label=label)

    if name is not None:
        axes.set_title(name)
    axes.axhline(1, color="black", alpha=0.2)
    axes.legend(frameon=True, framealpha=0.5)

    if ax is None:
        return fig
    return axes
