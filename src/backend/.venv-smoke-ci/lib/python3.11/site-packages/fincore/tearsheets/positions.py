"""Position-related plotting and display functions.

Includes exposure, leverage, and holdings charts.
"""

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

from fincore.utils import format_asset, get_month_end_freq, print_table

__all__ = [
    "plot_exposures",
    "plot_gross_leverage",
    "plot_holdings",
    "plot_long_short_holdings",
    "plot_max_median_position_concentration",
    "plot_sector_allocations",
    "show_and_plot_top_positions",
]


def plot_holdings(empyrical_instance, returns, positions, legend_loc="best", ax=None, **kwargs):
    """
    Plots total amount of stocks with an active position, either short
    or long. Displays daily total, daily average per month, and
    all-time daily average.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    positions : pd.DataFrame, optional
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

    positions = positions.copy().drop("cash", axis="columns")
    df_holdings = positions.replace(0, np.nan).count(axis=1)
    df_holdings_by_month = df_holdings.resample(get_month_end_freq()).mean()
    if hasattr(df_holdings_by_month.index, "to_timestamp"):
        df_holdings_by_month.index = df_holdings_by_month.index.to_timestamp()
    df_holdings.plot(color="steelblue", alpha=0.6, lw=0.5, ax=ax, **kwargs)
    df_holdings_by_month.plot(color="orangered", lw=2, ax=ax, **kwargs)
    ax.axhline(df_holdings.values.mean(), color="steelblue", ls="--", lw=3)

    ax.set_xlim((returns.index[0], returns.index[-1]))

    leg = ax.legend(
        ["Daily holdings", "Average daily holdings, by month", "Average daily holdings, overall"],
        loc=legend_loc,
        frameon=True,
        framealpha=0.5,
    )
    leg.get_frame().set_edgecolor("black")

    ax.set_title("Total holdings")
    ax.set_ylabel("Holdings")
    ax.set_xlabel("")
    return ax


def plot_long_short_holdings(returns, positions, legend_loc="upper left", ax=None, **_kwargs):
    """
    Plots total amount of stocks with an active position, breaking out
    short and long into transparent-filled regions.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    positions : pd.DataFrame, optional
        Daily net position values.
    legend_loc : matplotlib.loc, optional
        The location of the legend on the plot.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **_kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    positions = positions.drop("cash", axis="columns")
    positions = positions.replace(0, np.nan)
    df_longs = positions[positions > 0].count(axis=1)
    df_shorts = positions[positions < 0].count(axis=1)
    lf = ax.fill_between(df_longs.index, 0, df_longs.values, color="g", alpha=0.5, lw=2.0)
    sf = ax.fill_between(df_shorts.index, 0, df_shorts.values, color="r", alpha=0.5, lw=2.0)

    bf = patches.Rectangle([0, 0], 1, 1, color="darkgoldenrod")
    leg = ax.legend(
        [lf, sf, bf],
        [
            f"Long (max: {df_longs.max()}, min: {df_longs.min()})",
            f"Short (max: {df_shorts.max()}, min: {df_shorts.min()})",
            "Overlap",
        ],
        loc=legend_loc,
        frameon=True,
        framealpha=0.5,
    )
    leg.get_frame().set_edgecolor("black")

    ax.set_xlim((returns.index[0], returns.index[-1]))
    ax.set_title("Long and short holdings")
    ax.set_ylabel("Holdings")
    ax.set_xlabel("")
    return ax


def plot_exposures(returns, positions, ax=None, **_kwargs):
    """
    Plots a cake chart of the long and short exposure.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    positions: pd.DataFrame
        Portfolio allocation of positions.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **_kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    pos_no_cash = positions.drop("cash", axis=1)
    l_exp = pos_no_cash[pos_no_cash > 0].sum(axis=1) / positions.sum(axis=1)
    s_exp = pos_no_cash[pos_no_cash < 0].sum(axis=1) / positions.sum(axis=1)
    net_exp = pos_no_cash.sum(axis=1) / positions.sum(axis=1)

    ax.fill_between(l_exp.index, 0, l_exp.values, label="Long", color="green", alpha=0.5)
    ax.fill_between(s_exp.index, 0, s_exp.values, label="Short", color="red", alpha=0.5)
    ax.plot(net_exp.index, net_exp.values, label="Net", color="black", linestyle="dotted")

    ax.set_xlim((returns.index[0], returns.index[-1]))
    ax.set_title("Exposure")
    ax.set_ylabel("Exposure")
    ax.legend(loc="lower left", frameon=True, framealpha=0.5)
    ax.set_xlabel("")
    return ax


def plot_gross_leverage(empyrical_instance, _returns, positions, ax=None, **kwargs):
    """
    Plots gross leverage versus date.

    Gross leverage is the sum of long and short exposure per share
    divided by net asset value.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    _returns : pd.Series
        Daily returns of the strategy, noncumulative.
    positions : pd.DataFrame
        Daily net position values.
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
    gl = empyrical_instance.gross_lev(positions)
    gl.plot(lw=0.5, color="limegreen", legend=False, ax=ax, **kwargs)

    ax.axhline(gl.mean(), color="g", linestyle="--", lw=3)

    ax.set_title("Gross leverage")
    ax.set_ylabel("Gross leverage")
    ax.set_xlabel("")
    return ax


def plot_max_median_position_concentration(empyrical_instance, positions, ax=None, **_kwargs):
    """
    Plots the max and median of long and short position concentrations
    over the time.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    positions : pd.DataFrame
        The positions that the strategy takes over time.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    alloc_summary = empyrical_instance.get_max_median_position_concentration(positions)
    colors = ["mediumblue", "steelblue", "tomato", "firebrick"]
    alloc_summary.plot(linewidth=1, color=colors, alpha=0.6, ax=ax)

    ax.legend(loc="center left", frameon=True, framealpha=0.5)
    ax.set_ylabel("Exposure")
    ax.set_title("Long/short max and median position concentration")

    return ax


def plot_sector_allocations(_returns, sector_alloc, ax=None, **kwargs):
    """
    Plots the sector exposures of the portfolio over time.

    Parameters
    ----------
    _returns : pd.Series
        Daily returns of the strategy, noncumulative.
    sector_alloc : pd.DataFrame
        Portfolio allocation of positions. See pos.get_sector_alloc.
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

    sector_alloc.plot(title="Sector allocation over time", alpha=0.5, ax=ax, **kwargs)

    box = ax.get_position()
    ax.set_position([box.x0, box.y0 + box.height * 0.1, box.width, box.height * 0.9])

    # Put a legend below current axis
    ax.legend(loc="upper center", frameon=True, framealpha=0.5, bbox_to_anchor=(0.5, -0.14), ncol=5)

    ax.set_xlim((sector_alloc.index[0], sector_alloc.index[-1]))
    ax.set_ylabel("Exposure by sector")
    ax.set_xlabel("")

    return ax


def show_and_plot_top_positions(
    empyrical_instance,
    returns,
    positions_alloc,
    show_and_plot=2,
    hide_positions=False,
    legend_loc="real_best",
    ax=None,
    run_flask_app=False,
    **kwargs,
):
    """
    Prints and/or plots the exposures of the top 10 held positions of
    all time.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    positions_alloc : pd.DataFrame
        Portfolio allocation of positions. See pos.get_percent_alloc.
    show_and_plot : int, optional
        By default, this is 2, and both prints and plots.
        If this is 0, it will only plot; if 1, it will only print.
    hide_positions : bool, optional
        If True, will not output any symbol names.
    legend_loc : matplotlib.loc, optional
        The location of the legend on the plot.
        By default, the legend will display below the plot.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    run_flask_app : bool, optional, default False
        If True, will run a Flask app to display the plot in a web browser.
    **kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes, conditional
        The axes that were plotted on.
    """
    import pandas as pd

    positions_alloc = positions_alloc.copy()
    positions_alloc.columns = positions_alloc.columns.map(format_asset)

    df_top_long, df_top_short, df_top_abs = empyrical_instance.get_top_long_short_abs(positions_alloc)

    if show_and_plot == 1 or show_and_plot == 2:
        print_table(
            pd.DataFrame(df_top_long * 100, columns=["max"]),
            float_format="{:.2f}%".format,
            name="Top 10 long positions of all time",
            run_flask_app=run_flask_app,
        )

        print_table(
            pd.DataFrame(df_top_short * 100, columns=["max"]),
            float_format="{:.2f}%".format,
            name="Top 10 short positions of all time",
            run_flask_app=run_flask_app,
        )

        print_table(
            pd.DataFrame(df_top_abs * 100, columns=["max"]),
            float_format="{:.2f}%".format,
            name="Top 10 positions of all time",
            run_flask_app=run_flask_app,
        )

    if show_and_plot == 0 or show_and_plot == 2:
        if ax is None:
            ax = plt.gca()

        positions_alloc[df_top_abs.index].plot(
            title="Portfolio allocation over time, only top 10 holdings", alpha=0.5, ax=ax, **kwargs
        )

        # Place legend below plot, shrink plot by 20%
        if legend_loc == "real_best":
            box = ax.get_position()
            ax.set_position([box.x0, box.y0 + box.height * 0.1, box.width, box.height * 0.9])

            # Put a legend below current axis
            ax.legend(loc="upper center", frameon=True, framealpha=0.5, bbox_to_anchor=(0.5, -0.14), ncol=5)
        else:
            ax.legend(loc=legend_loc)

        ax.set_xlim((returns.index[0], returns.index[-1]))
        ax.set_ylabel("Exposure by holding")

        if hide_positions:
            ax.legend_.remove()

        return ax
    return None
