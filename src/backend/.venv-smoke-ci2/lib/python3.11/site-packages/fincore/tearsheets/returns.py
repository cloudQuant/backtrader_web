"""Return-related plotting and display functions.

Includes charts such as monthly return heatmaps, annual returns, rolling metrics,
and drawdown visualizations.
"""

from collections import OrderedDict

import matplotlib
import matplotlib.lines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from fincore.constants import APPROX_BDAYS_PER_MONTH, STAT_FUNCS_PCT
from fincore.empyrical import Empyrical
from fincore.utils import (
    get_month_end_freq,
    make_timezone_aware,
    percentage,
    print_table,
    two_dec_places,
)

__all__ = [
    "plot_annual_returns",
    "plot_drawdown_periods",
    "plot_drawdown_underwater",
    "plot_monthly_returns_dist",
    "plot_monthly_returns_heatmap",
    "plot_monthly_returns_timeseries",
    "plot_perf_stats",
    "plot_return_quantiles",
    "plot_returns",
    "plot_rolling_beta",
    "plot_rolling_returns",
    "plot_rolling_sharpe",
    "plot_rolling_volatility",
    "show_perf_stats",
    "show_worst_drawdown_periods",
]


def plot_monthly_returns_heatmap(empyrical_instance, returns, ax=None, **kwargs):
    """
    Plots a heatmap of returns by month.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
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

    monthly_ret_table = empyrical_instance.aggregate_returns(returns, "monthly")
    monthly_ret_table = monthly_ret_table.unstack().round(3)

    sns.heatmap(
        monthly_ret_table.fillna(0) * 100.0,
        annot=True,
        annot_kws={"size": 9},
        alpha=1.0,
        center=0.0,
        cbar=False,
        cmap=matplotlib.cm.RdYlGn,
        ax=ax,
        **kwargs,
    )
    ax.set_ylabel("Year")
    ax.set_xlabel("Month")
    ax.set_title("Monthly returns (%)")
    return ax


def plot_annual_returns(empyrical_instance, returns, ax=None, **kwargs):
    """
    Plots a bar graph of returns by year.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
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

    x_axis_formatter = FuncFormatter(percentage)
    ax.xaxis.set_major_formatter(FuncFormatter(x_axis_formatter))
    ax.tick_params(axis="x", which="major")

    ann_ret_df = pd.DataFrame(empyrical_instance.aggregate_returns(returns, "yearly"))

    ax.axvline(100 * ann_ret_df.values.mean(), color="steelblue", linestyle="--", lw=4, alpha=0.7)
    plot_df = 100 * ann_ret_df.sort_index(ascending=False)
    # Use matplotlib barh directly: pandas DataFrame.plot(barh) accesses index.freq,
    # which fails for non-DatetimeIndex (yearly aggregates use Int64Index).
    vals = plot_df.iloc[:, 0].values if plot_df.ndim == 2 else plot_df.values
    y_pos = np.arange(len(vals))
    ax.barh(y_pos, vals, tick_label=plot_df.index.astype(str), alpha=0.70, **kwargs)
    ax.axvline(0.0, color="black", linestyle="-", lw=3)

    ax.set_ylabel("Year")
    ax.set_xlabel("Returns")
    ax.set_title("Annual returns")
    ax.legend(["Mean"], frameon=True, framealpha=0.5)
    return ax


def plot_monthly_returns_dist(empyrical_instance, returns, ax=None, **kwargs):
    """
    Plots a distribution of monthly returns.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
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

    x_axis_formatter = FuncFormatter(percentage)
    ax.xaxis.set_major_formatter(FuncFormatter(x_axis_formatter))
    ax.tick_params(axis="x", which="major")

    monthly_ret_table = empyrical_instance.aggregate_returns(returns, "monthly")

    ax.hist(100 * monthly_ret_table, color="orangered", alpha=0.80, bins=20, **kwargs)

    ax.axvline(100 * monthly_ret_table.mean(), color="gold", linestyle="--", lw=4, alpha=1.0)

    ax.axvline(0.0, color="black", linestyle="-", lw=3, alpha=0.75)
    ax.legend(["Mean"], frameon=True, framealpha=0.5)
    ax.set_ylabel("Number of months")
    ax.set_xlabel("Returns")
    ax.set_title("Distribution of monthly returns")
    return ax


def plot_returns(returns, live_start_date=None, ax=None):
    """
    Plots raw returns over time.

    Backtest returns are in green, and out-of-sample (live trading)
    returns are in red.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    live_start_date : datetime, optional
        The date when the strategy began to live trading, after
        its backtest period. This date should be normalized.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    ax.set_label("")
    ax.set_ylabel("Returns")

    if live_start_date is not None:
        if isinstance(live_start_date, str):
            live_start_date = pd.to_datetime(live_start_date)
        live_start_date = make_timezone_aware(live_start_date, returns.index[0].tz)
        is_returns = returns.loc[returns.index < live_start_date]
        oos_returns = returns.loc[returns.index >= live_start_date]
        is_returns.plot(ax=ax, color="g")
        oos_returns.plot(ax=ax, color="r")
    else:
        returns.plot(ax=ax, color="g")

    return ax


def plot_rolling_returns(
    empyrical_instance,
    returns,
    factor_returns=None,
    live_start_date=None,
    logy=False,
    cone_std=None,
    legend_loc="best",
    volatility_match=False,
    cone_function=None,
    ax=None,
    **kwargs,
):
    """
    Plots cumulative rolling returns versus some benchmarks'.

    Backtest returns are in green, and out-of-sample (live trading)
    returns are in red.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor.
    live_start_date : datetime, optional
        The date when the strategy began to live trading.
    logy : bool, optional
        Whether to log-scale the y-axis.
    cone_std : float, or tuple, optional
        Standard deviation to use for the cone plots.
    legend_loc : matplotlib.loc, optional
        The location of the legend on the plot.
    volatility_match : bool, optional
        Whether to normalize the volatility of the returns.
    cone_function : function, optional
        Function to use when generating forecast probability cone.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **kwargs
        Passed to plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if cone_function is None:
        cone_function = Empyrical.forecast_cone_bootstrap

    if ax is None:
        ax = plt.gca()

    ax.set_xlabel("")
    ax.set_ylabel("Cumulative returns")
    ax.set_yscale("log" if logy else "linear")

    if volatility_match and factor_returns is None:
        raise ValueError("volatility_match requires passing of factor_returns.")
    if volatility_match and factor_returns is not None:
        bmark_vol = factor_returns.loc[returns.index].std()
        returns = (returns / returns.std()) * bmark_vol

    cum_rets = empyrical_instance.cum_returns(returns, 1.0)

    y_axis_formatter = FuncFormatter(two_dec_places)
    ax.yaxis.set_major_formatter(FuncFormatter(y_axis_formatter))

    if factor_returns is not None:
        cum_factor_returns = empyrical_instance.cum_returns(factor_returns[cum_rets.index], 1.0)
        cum_factor_returns.plot(lw=2, color="gray", label=factor_returns.name, alpha=0.60, ax=ax, **kwargs)

    if live_start_date is not None:
        if isinstance(live_start_date, str):
            live_start_date = pd.to_datetime(live_start_date)
        live_start_date = make_timezone_aware(live_start_date, cum_rets.index[0].tz)
        is_cum_returns = cum_rets.loc[cum_rets.index < live_start_date]
        oos_cum_returns = cum_rets.loc[cum_rets.index >= live_start_date]
    else:
        is_cum_returns = cum_rets
        oos_cum_returns = pd.Series([])

    is_cum_returns.plot(lw=3, color="forestgreen", alpha=0.6, label="Backtest", ax=ax, **kwargs)

    if len(oos_cum_returns) > 0:
        oos_cum_returns.plot(lw=4, color="red", alpha=0.6, label="Live", ax=ax, **kwargs)

        if cone_std is not None:
            if isinstance(cone_std, (float, int)):
                cone_std = [cone_std]

            is_returns = returns.loc[returns.index < live_start_date]
            cone_bounds = cone_function(
                is_returns, len(oos_cum_returns), cone_std=cone_std, starting_value=is_cum_returns.iloc[-1]
            )

            cone_bounds = cone_bounds.set_index(oos_cum_returns.index)
            for std in cone_std:
                ax.fill_between(
                    cone_bounds.index, cone_bounds[float(std)], cone_bounds[float(-std)], color="steelblue", alpha=0.5
                )

    if legend_loc is not None:
        ax.legend(loc=legend_loc, frameon=True, framealpha=0.5)
    ax.axhline(1.0, linestyle="--", color="black", lw=2)

    return ax


def plot_rolling_beta(empyrical_instance, returns, factor_returns, legend_loc="best", ax=None, **kwargs):
    """
    Plots the rolling 6-month and 12-month beta versus date.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series
        Daily noncumulative returns of the benchmark factor.
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

    ax.set_title("Rolling portfolio beta to " + str(factor_returns.name))
    ax.set_ylabel("Beta")
    rb_1 = empyrical_instance.rolling_beta(returns, factor_returns, rolling_window=APPROX_BDAYS_PER_MONTH * 6)
    rb_1.plot(color="steelblue", lw=3, alpha=0.6, ax=ax, **kwargs)
    rb_2 = empyrical_instance.rolling_beta(returns, factor_returns, rolling_window=APPROX_BDAYS_PER_MONTH * 12)
    rb_2.plot(color="grey", lw=3, alpha=0.4, ax=ax, **kwargs)
    ax.axhline(rb_1.mean(), color="steelblue", linestyle="--", lw=3)
    ax.axhline(0.0, color="black", linestyle="-", lw=2)

    ax.set_xlabel("")
    ax.legend(["6-mo", "12-mo"], loc=legend_loc, frameon=True, framealpha=0.5)
    ax.set_ylim((-1.0, 1.0))
    return ax


def plot_rolling_volatility(
    empyrical_instance, returns, factor_returns=None, rolling_window=None, legend_loc="best", ax=None, **kwargs
):
    """
    Plots the rolling volatility versus date.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor.
    rolling_window : int, optional
        The day window over which to compute the volatility.
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
    if rolling_window is None:
        rolling_window = APPROX_BDAYS_PER_MONTH * 6

    if ax is None:
        ax = plt.gca()

    y_axis_formatter = FuncFormatter(two_dec_places)
    ax.yaxis.set_major_formatter(FuncFormatter(y_axis_formatter))

    rolling_vol_ts = empyrical_instance.rolling_volatility(returns, rolling_window)
    rolling_vol_ts.plot(alpha=0.7, lw=3, color="orangered", ax=ax, **kwargs)
    if factor_returns is not None:
        rolling_vol_ts_factor = empyrical_instance.rolling_volatility(factor_returns, rolling_window)
        rolling_vol_ts_factor.plot(alpha=0.7, lw=3, color="grey", ax=ax, **kwargs)

    ax.set_title("Rolling volatility (6-month)")
    ax.axhline(rolling_vol_ts.mean(), color="steelblue", linestyle="--", lw=3)
    ax.axhline(0.0, color="black", linestyle="-", lw=2)

    ax.set_ylabel("Volatility")
    ax.set_xlabel("")
    if factor_returns is None:
        ax.legend(["Volatility", "Average volatility"], loc=legend_loc, frameon=True, framealpha=0.5)
    else:
        ax.legend(
            ["Volatility", "Benchmark volatility", "Average volatility"], loc=legend_loc, frameon=True, framealpha=0.5
        )
    return ax


def plot_rolling_sharpe(
    empyrical_instance, returns, factor_returns=None, rolling_window=None, legend_loc="best", ax=None, **kwargs
):
    """
    Plots the rolling Sharpe ratio versus date.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor.
    rolling_window : int, optional
        The day window over which to compute the sharpe ratio.
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
    if rolling_window is None:
        rolling_window = APPROX_BDAYS_PER_MONTH * 6

    if ax is None:
        ax = plt.gca()

    y_axis_formatter = FuncFormatter(two_dec_places)
    ax.yaxis.set_major_formatter(FuncFormatter(y_axis_formatter))

    rolling_sharpe_ts = empyrical_instance.rolling_sharpe(returns, rolling_window)
    rolling_sharpe_ts.plot(alpha=0.7, lw=3, color="orangered", ax=ax, **kwargs)

    if factor_returns is not None:
        rolling_sharpe_ts_factor = empyrical_instance.rolling_sharpe(factor_returns, rolling_window)
        rolling_sharpe_ts_factor.plot(alpha=0.7, lw=3, color="grey", ax=ax, **kwargs)

    ax.set_title("Rolling Sharpe ratio (6-month)")
    ax.axhline(rolling_sharpe_ts.mean(), color="steelblue", linestyle="--", lw=3)
    ax.axhline(0.0, color="black", linestyle="-", lw=3)

    ax.set_ylabel("Sharpe ratio")
    ax.set_xlabel("")
    if factor_returns is None:
        ax.legend(["Sharpe", "Average"], loc=legend_loc, frameon=True, framealpha=0.5)
    else:
        ax.legend(["Sharpe", "Benchmark Sharpe", "Average"], loc=legend_loc, frameon=True, framealpha=0.5)

    return ax


def plot_drawdown_periods(empyrical_instance, returns, top=10, ax=None, **kwargs):
    """
    Plots cumulative returns highlighting top drawdown periods.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    top : int, optional
        Amount of top drawdowns periods to plot (default 10).
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

    df_cum_rets = empyrical_instance.cum_returns(returns, starting_value=1.0)
    df_drawdowns = empyrical_instance.gen_drawdown_table(returns, top=top)

    df_cum_rets.plot(ax=ax, **kwargs)

    lim = ax.get_ylim()
    colors = sns.cubehelix_palette(len(df_drawdowns))[::-1]
    for i, (peak, recovery) in df_drawdowns[["Peak date", "Recovery date"]].iterrows():
        if pd.isnull(recovery):
            recovery = returns.index[-1]
        ax.fill_between((peak, recovery), lim[0], lim[1], alpha=0.4, color=colors[i])
    ax.set_ylim(lim)
    ax.set_title("Top %i drawdown periods" % top)
    ax.set_ylabel("Cumulative returns")
    ax.legend(["Portfolio"], loc="upper left", frameon=True, framealpha=0.5)
    ax.set_xlabel("")
    return ax


def plot_drawdown_underwater(empyrical_instance, returns, ax=None, **kwargs):
    """
    Plots how far underwater returns are over time, or plots current
    drawdown vs. date.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
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

    y_axis_formatter = FuncFormatter(percentage)
    ax.yaxis.set_major_formatter(FuncFormatter(y_axis_formatter))

    df_cum_rets = empyrical_instance.cum_returns(returns, starting_value=1.0)
    running_max = np.maximum.accumulate(df_cum_rets)
    underwater = -100 * ((running_max - df_cum_rets) / running_max)
    underwater.plot(ax=ax, kind="area", color="coral", alpha=0.7, **kwargs)
    ax.set_ylabel("Drawdown")
    ax.set_title("Underwater plot")
    ax.set_xlabel("")
    return ax


def plot_return_quantiles(empyrical_instance, returns, live_start_date=None, ax=None, **kwargs):
    """
    Creates a box plot of daily, weekly, and monthly return distributions.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    live_start_date : datetime, optional
        The point in time when the strategy began to live trading.
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
    if live_start_date is None:
        is_returns = returns
    else:
        if isinstance(live_start_date, str):
            live_start_date = pd.to_datetime(live_start_date)
        live_start_date = make_timezone_aware(live_start_date, returns.index[0].tz)
        is_returns = returns.loc[returns.index < live_start_date]
    is_weekly = empyrical_instance.aggregate_returns(is_returns, "weekly")
    is_monthly = empyrical_instance.aggregate_returns(is_returns, "monthly")
    data = pd.concat(
        [
            pd.DataFrame({"value": is_returns, "category": "returns"}),
            pd.DataFrame({"value": is_weekly, "category": "weekly"}),
            pd.DataFrame({"value": is_monthly, "category": "monthly"}),
        ]
    )
    data = data.dropna()
    sns.boxplot(
        data=data, x="category", y="value", palette=["#4c72B0", "#55A868", "#CCB974"], ax=ax, hue="category", **kwargs
    )

    if live_start_date is not None:
        oos_returns = returns.loc[returns.index >= live_start_date]
        oos_weekly = empyrical_instance.aggregate_returns(oos_returns, "weekly")
        oos_monthly = empyrical_instance.aggregate_returns(oos_returns, "monthly")

        sns.swarmplot(data=[oos_returns, oos_weekly, oos_monthly], ax=ax, color="red", marker="d", **kwargs)
        red_dots = matplotlib.lines.Line2D([], [], color="red", marker="d", label="Out-of-sample data", linestyle="")
        ax.legend(handles=[red_dots], frameon=True, framealpha=0.5)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Daily", "Weekly", "Monthly"])
    ax.set_title("Return quantiles")

    return ax


def plot_monthly_returns_timeseries(empyrical_instance, returns, ax=None, **_kwargs):
    """
    Plots monthly returns as a timeseries.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.
    **_kwargs
        Passed to seaborn plotting function.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """

    def cumulate_returns(x):
        # ``Series[-1]`` is label-based for most indexes; use positional access.
        return empyrical_instance.cum_returns(x).iloc[-1]

    if ax is None:
        ax = plt.gca()

    monthly_rets = returns.resample(get_month_end_freq()).apply(lambda x: cumulate_returns(x))
    # ``to_period`` drops timezone information; avoid emitting a warning in
    # tz-aware series by stripping tz explicitly first (labels only).
    if getattr(monthly_rets.index, "tz", None) is not None:
        monthly_rets.index = monthly_rets.index.tz_localize(None)
    monthly_rets = monthly_rets.to_period()

    sns.barplot(x=monthly_rets.index, y=monthly_rets.values, color="steelblue")

    _locs, labels = plt.xticks()
    plt.setp(labels, rotation=90)

    # only show x-labels on year boundary
    xticks_coord = []
    xticks_label = []
    for count, i in enumerate(monthly_rets.index):
        if i.month == 1:
            xticks_label.append(i)
            xticks_coord.append(count)
            # plot yearly boundary line
            ax.axvline(count, color="gray", ls="--", alpha=0.3)

    ax.axhline(0.0, color="darkgray", ls="-")
    ax.set_xticks(xticks_coord)
    ax.set_xticklabels(xticks_label)

    return ax


def plot_perf_stats(empyrical_instance, returns, factor_returns, ax=None):
    """
    Create a box plot of some performance metrics of the strategy.
    The width of the box whiskers is determined by a bootstrap.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series
        Daily noncumulative returns of the benchmark factor.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    bootstrap_values = empyrical_instance.perf_stats_bootstrap(returns, factor_returns, return_stats=False)
    bootstrap_values = bootstrap_values.drop("Kurtosis", axis="columns")

    sns.boxplot(data=bootstrap_values, orient="h", ax=ax)

    return ax


def show_perf_stats(
    empyrical_instance,
    returns,
    factor_returns=None,
    positions=None,
    transactions=None,
    turnover_denom="AGB",
    live_start_date=None,
    bootstrap=False,
    header_rows=None,
    run_flask_app=False,
):
    """
    Prints some performance metrics of the strategy.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor.
    positions : pd.DataFrame, optional
        Daily net position values.
    transactions : pd.DataFrame, optional
        Prices and amounts of executed trades.
    turnover_denom : str, optional
        Either AGB or portfolio_value, default AGB.
    live_start_date : datetime, optional
        The point in time when the strategy began to live trading.
    bootstrap : boolean, optional
        Whether to perform bootstrap analysis for the performance metrics.
    header_rows : dict or OrderedDict, optional
        Extra rows to display at the top of the displayed table.
    run_flask_app : boolean, optional, default False
        Whether to run the flask app.
    """
    perf_func = empyrical_instance.perf_stats_bootstrap if bootstrap else empyrical_instance.perf_stats

    perf_stats_all = perf_func(
        returns,
        factor_returns=factor_returns,
        positions=positions,
        transactions=transactions,
        turnover_denom=turnover_denom,
    )

    date_rows = OrderedDict()
    if len(returns.index) > 0:
        date_rows["Start date"] = returns.index[0].strftime("%Y-%m-%d")
        date_rows["End date"] = returns.index[-1].strftime("%Y-%m-%d")

    if live_start_date is not None:
        # Convert string to datetime once
        if isinstance(live_start_date, str):
            live_start_date = pd.to_datetime(live_start_date)

        # Handle timezone for returns comparison
        live_start_date_for_returns = make_timezone_aware(live_start_date, returns.index[0].tz)
        returns_is = returns[returns.index < live_start_date_for_returns]
        returns_oos = returns[returns.index >= live_start_date_for_returns]

        positions_is = None
        positions_oos = None
        transactions_is = None
        transactions_oos = None

        if positions is not None:
            # Handle timezone for positions comparison
            live_start_date_for_positions = make_timezone_aware(live_start_date, positions.index[0].tz)
            positions_is = positions[positions.index < live_start_date_for_positions]
            positions_oos = positions[positions.index >= live_start_date_for_positions]

            if transactions is not None:
                # Handle timezone for transactions comparison
                live_start_date_for_txns = make_timezone_aware(live_start_date, transactions.index[0].tz)
                transactions_is = transactions[(transactions.index < live_start_date_for_txns)]
                transactions_oos = transactions[(transactions.index > live_start_date_for_txns)]

        perf_stats_is = perf_func(
            returns_is,
            factor_returns=factor_returns,
            positions=positions_is,
            transactions=transactions_is,
            turnover_denom=turnover_denom,
        )

        perf_stats_oos = perf_func(
            returns_oos,
            factor_returns=factor_returns,
            positions=positions_oos,
            transactions=transactions_oos,
            turnover_denom=turnover_denom,
        )
        if len(returns.index) > 0:
            date_rows["In-sample months"] = int(len(returns_is) / APPROX_BDAYS_PER_MONTH)
            date_rows["Out-of-sample months"] = int(len(returns_oos) / APPROX_BDAYS_PER_MONTH)

        perf_stats = pd.concat(
            OrderedDict(
                [
                    ("In-sample", perf_stats_is),
                    ("Out-of-sample", perf_stats_oos),
                    ("All", perf_stats_all),
                ]
            ),
            axis=1,
        )
    else:
        if len(returns.index) > 0:
            date_rows["Total months"] = int(len(returns) / APPROX_BDAYS_PER_MONTH)
        perf_stats = pd.DataFrame(perf_stats_all, columns=["Backtest"])

    for column in perf_stats.columns:
        perf_stats[column] = perf_stats[column].astype(object)
        for stat, value in perf_stats[column].items():
            if stat in STAT_FUNCS_PCT:
                if np.isnan(value):
                    perf_stats.loc[stat, column] = np.nan
                else:
                    perf_stats.loc[stat, column] = str(np.round(value * 100, 1)) + "%"
    if header_rows is None:
        header_rows = date_rows
    else:
        header_rows = OrderedDict(header_rows)
        header_rows.update(date_rows)

    print_table(perf_stats, float_format="{:.2f}".format, header_rows=header_rows, run_flask_app=run_flask_app)


def show_worst_drawdown_periods(empyrical_instance, returns, top=5, run_flask_app=False):
    """
    Prints information about the worst drawdown periods.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    top : int, optional
        Amount of top drawdowns periods to plot (default 5).
    run_flask_app : bool, optional, default=False
        Whether to run the flask app to display the plot.
    """
    drawdown_df = empyrical_instance.gen_drawdown_table(returns, top=top)
    print_table(
        drawdown_df.sort_values("Net drawdown in %", ascending=False),
        name="Worst drawdown periods",
        float_format="{:.2f}".format,
        run_flask_app=run_flask_app,
    )
