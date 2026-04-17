"""
Transaction-related plotting and display functions.

Includes turnover, trading volume, slippage, and related charts.
"""

import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from fincore.utils import get_month_end_freq, two_dec_places

__all__ = [
    "plot_daily_turnover_hist",
    "plot_daily_volume",
    "plot_slippage_sensitivity",
    "plot_slippage_sweep",
    "plot_turnover",
    "plot_txn_time_hist",
]


def plot_turnover(empyrical_instance, returns, transactions, positions, legend_loc="best", ax=None, **kwargs):
    """
    Plots turnover vs. date.

    Turnover is the number of shares traded for a period as a fraction
    of total shares.

    Displays daily total, daily average per month, and all-time daily
    average.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    positions : pd.DataFrame
        Daily net position values.
    legend_loc : matplotlib.loc, optional
        The location of the legend on the plot.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    y_axis_formatter = FuncFormatter(two_dec_places)
    ax.yaxis.set_major_formatter(FuncFormatter(y_axis_formatter))

    df_turnover = empyrical_instance.get_turnover(positions, transactions)
    df_turnover_by_month = df_turnover.resample(get_month_end_freq()).mean()
    if hasattr(df_turnover_by_month.index, "to_timestamp"):
        df_turnover_by_month.index = df_turnover_by_month.index.to_timestamp()
    df_turnover.plot(color="steelblue", alpha=1.0, lw=0.5, ax=ax, **kwargs)
    df_turnover_by_month.plot(color="orangered", alpha=0.5, lw=2, ax=ax, **kwargs)
    ax.axhline(df_turnover.mean(), color="steelblue", linestyle="--", lw=3, alpha=1.0)
    ax.legend(
        ["Daily turnover", "Average daily turnover, by month", "Average daily turnover, net"],
        loc=legend_loc,
        frameon=True,
        framealpha=0.5,
    )
    ax.set_title("Daily turnover")
    ax.set_xlim((returns.index[0], returns.index[-1]))
    ax.set_ylim((0, 2))
    ax.set_ylabel("Turnover")
    ax.set_xlabel("")
    return ax


def plot_daily_volume(empyrical_instance, returns, transactions, ax=None, **kwargs):
    """
    Plots trading volume per day vs. date.

    Also displays all-time daily average.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()
    daily_txn = empyrical_instance.get_txn_vol(transactions)
    daily_txn.txn_shares.plot(alpha=1.0, lw=0.5, ax=ax, **kwargs)
    ax.axhline(daily_txn.txn_shares.mean(), color="steelblue", linestyle="--", lw=3, alpha=1.0)
    ax.set_title("Daily trading volume")
    ax.set_xlim((returns.index[0], returns.index[-1]))
    ax.set_ylabel("Amount of shares traded")
    ax.set_xlabel("")
    return ax


def plot_daily_turnover_hist(empyrical_instance, transactions, positions, ax=None, **kwargs):
    """
    Plots a histogram of daily turnover rates.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    positions : pd.DataFrame
        Daily net position values.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **kwargs
        Passed to seaborn plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()
    turnover = empyrical_instance.get_turnover(positions, transactions)
    sns.histplot(turnover, ax=ax, kde=True, **kwargs)
    ax.set_title("Distribution of daily turnover rates")
    ax.set_xlabel("Turnover rate")
    return ax


def plot_txn_time_hist(transactions, bin_minutes=5, tz="America/New_York", ax=None, **kwargs):
    """
    Plots a histogram of transaction times, binning the times into
    buckets of a given duration.

    Parameters
    ----------
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    bin_minutes : float, optional
        Sizes of the bins in minutes, defaults to 5 minutes.
    tz : str, optional
        Time zone to plot against.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    txn_time = transactions.copy()

    # tz_convert accepts a timezone string (e.g. "America/New_York") in pandas.
    txn_time.index = txn_time.index.tz_convert(tz)
    txn_time.index = txn_time.index.map(lambda x: x.hour * 60 + x.minute)
    txn_time["trade_value"] = (txn_time.amount * txn_time.price).abs()
    txn_time = txn_time.groupby(level=0).sum().reindex(index=range(570, 961))
    txn_time.index = (txn_time.index / bin_minutes).astype(int) * bin_minutes
    txn_time = txn_time.groupby(level=0).sum()

    txn_time["time_str"] = txn_time.index.map(lambda x: str(datetime.time(int(x / 60), x % 60))[:-3])

    trade_value_sum = txn_time.trade_value.sum()
    txn_time.trade_value = txn_time.trade_value.fillna(0) / trade_value_sum

    ax.bar(txn_time.index, txn_time.trade_value, width=bin_minutes, **kwargs)

    ax.set_xlim(570, 960)
    ax.set_xticks(txn_time.index[:: int(30 / bin_minutes)])
    ax.set_xticklabels(txn_time.time_str[:: int(30 / bin_minutes)])
    ax.set_title("Transaction time distribution")
    ax.set_ylabel("Proportion")
    ax.set_xlabel("")
    return ax


def plot_slippage_sweep(
    empyrical_instance, returns, positions, transactions, slippage_params=(3, 8, 10, 12, 15, 20, 50), ax=None, **_kwargs
):
    """
    Plots equity curves at different per-dollar slippage assumptions.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Timeseries of portfolio returns to be adjusted for various
        degrees of slippage.
    positions : pd.DataFrame
        Daily net position values.
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    slippage_params: tuple
        Slippage parameters to apply to the return time series (in
        basis points).
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **_kwargs
        Passed to seaborn plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    slippage_sweep = pd.DataFrame()
    for bps in slippage_params:
        adj_returns = empyrical_instance.adjust_returns_for_slippage(returns, positions, transactions, bps)
        label = str(bps) + " bps"
        slippage_sweep[label] = empyrical_instance.cum_returns(adj_returns, 1)

    slippage_sweep.plot(alpha=1.0, lw=0.5, ax=ax)

    ax.set_title("Cumulative returns given additional per-dollar slippage")
    ax.set_ylabel("")

    ax.legend(loc="center left", frameon=True, framealpha=0.5)

    return ax


def plot_slippage_sensitivity(empyrical_instance, returns, positions, transactions, ax=None, **_kwargs):
    """
    Plots curve relating per-dollar slippage to average annual returns.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Timeseries of portfolio returns to be adjusted for various
        degrees of slippage.
    positions : pd.DataFrame
        Daily net position values.
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **_kwargs
        Passed to seaborn plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    avg_returns_given_slippage = pd.Series()
    for bps in range(1, 100):
        adj_returns = empyrical_instance.adjust_returns_for_slippage(returns, positions, transactions, bps)
        avg_returns = empyrical_instance.annual_return(adj_returns)
        avg_returns_given_slippage.loc[bps] = avg_returns

    # Use matplotlib directly to avoid pandas timeseries date formatting on integer index
    ax.plot(avg_returns_given_slippage.index.astype(float), avg_returns_given_slippage.values, alpha=1.0, lw=2)

    ax.set_title("Average annual returns given additional per-dollar slippage")
    ax.set_xticks(np.arange(0, 100, 10))
    ax.set_ylabel("Average annual return")
    ax.set_xlabel("Per-dollar slippage (bps)")

    return ax
