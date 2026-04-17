"""Performance attribution plotting and display functions.

Includes attribution return series, factor contributions, and risk exposures.
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from fincore.utils import configure_legend, print_table

__all__ = [
    "plot_alpha_returns",
    "plot_factor_contribution_to_perf",
    "plot_perf_attrib_returns",
    "plot_risk_exposures",
    "show_perf_attrib_stats",
]


def plot_perf_attrib_returns(
    empyrical_instance: Any,
    perf_attrib_data: pd.DataFrame,
    cost: pd.Series | None = None,
    ax: Any = None,
) -> Any:
    """
    Plot total, specific, and common returns.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    perf_attrib_data : pd.DataFrame
        df with factors, common returns, and specific returns as columns,
        and datetimes as index. Assumes the `total_returns` column is NOT
        cost adjusted.
    cost : pd.Series, optional
        if present, gets subtracted from `perf_attrib_data['total_returns']`,
        and gets plotted separately
    ax : matplotlib.axes.Axes, optional
        axes on which plots are made. If None, current axes will be used

    Returns
    -------
    ax : matplotlib.axes.Axes
    """
    if ax is None:
        ax = plt.gca()

    returns = perf_attrib_data["total_returns"]
    total_returns_label = "Total returns"

    cumulative_returns_less_costs = empyrical_instance._cumulative_returns_less_costs(returns, cost)
    if cost is not None:
        total_returns_label += " (adjusted)"

    specific_returns = perf_attrib_data["specific_returns"]
    common_returns = perf_attrib_data["common_returns"]

    ax.plot(cumulative_returns_less_costs, color="b", label=total_returns_label)
    ax.plot(empyrical_instance.cum_returns(specific_returns), color="g", label="Cumulative specific returns")
    ax.plot(empyrical_instance.cum_returns(common_returns), color="r", label="Cumulative common returns")

    if cost is not None:
        ax.plot(-empyrical_instance.cum_returns(cost), color="k", label="Cumulative cost spent")

    ax.set_title("Time series of cumulative returns")
    ax.set_ylabel("Returns")

    configure_legend(ax)

    return ax


def plot_alpha_returns(
    alpha_returns: pd.Series,
    ax: Any = None,
) -> Any:
    """
    Plot histogram of daily multifactor alpha returns (specific returns).

    Parameters
    ----------
    alpha_returns : pd.Series
        series of daily alpha returns indexed by datetime
    ax : matplotlib.axes.Axes, optional
        axes on which plots are made. If None, current axes will be used

    Returns
    -------
    ax : matplotlib.axes.Axes
    """
    if ax is None:
        ax = plt.gca()

    ax.hist(alpha_returns, color="g", label="Multi-factor alpha")
    ax.set_title("Histogram of alphas")
    ax.axvline(0, color="k", linestyle="--", label="Zero")

    avg = alpha_returns.mean()
    ax.axvline(avg, color="b", label=f"Mean = {avg: 0.5f}")
    configure_legend(ax)

    return ax


def plot_factor_contribution_to_perf(
    empyrical_instance: Any,
    perf_attrib_data: pd.DataFrame,
    ax: Any = None,
    title: str = "Cumulative common returns attribution",
) -> Any:
    """
    Plot each factor's contribution to performance.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    perf_attrib_data : pd.DataFrame
        df with factors, common returns, and specific returns as columns,
        and datetimes as index
    ax : matplotlib.axes.Axes, optional
        axes on which plots are made. If None, current axes will be used
    title : str, optional
        title of plot

    Returns
    -------
    ax : matplotlib.axes.Axes
    """
    if ax is None:
        ax = plt.gca()

    factors_to_plot = perf_attrib_data.drop(["total_returns", "common_returns"], axis="columns", errors="ignore")

    factors_cumulative = pd.DataFrame()
    for factor in factors_to_plot:
        factors_cumulative[factor] = empyrical_instance.cum_returns(factors_to_plot[factor])

    for col in factors_cumulative:
        ax.plot(factors_cumulative[col])

    ax.axhline(0, color="k")
    configure_legend(ax, change_colors=True)

    ax.set_ylabel("Cumulative returns by factor")
    ax.set_title(title)

    return ax


def plot_risk_exposures(
    exposures: pd.DataFrame,
    ax: Any = None,
    title: str = "Daily risk factor exposures",
) -> Any:
    """
    Plot daily risk factor exposures.

    Parameters
    ----------
    exposures : pd.DataFrame
        df indexed by datetime, with factors as columns
    ax : matplotlib.axes.Axes, optional
        axes on which plots are made. If None, current axes will be used
    title: string, optional
        Title for the plot, default 'Daily risk factor exposures'

    Returns
    -------
    ax : matplotlib.axes.Axes
    """
    if ax is None:
        ax = plt.gca()

    for col in exposures:
        ax.plot(exposures[col])

    configure_legend(ax, change_colors=True)
    ax.set_ylabel("Factor exposures")
    ax.set_title(title)

    return ax


def show_perf_attrib_stats(
    empyrical_instance: Any,
    returns: pd.Series,
    positions: pd.DataFrame,
    factor_returns: pd.DataFrame,
    factor_loadings: pd.DataFrame,
    transactions: pd.DataFrame | None = None,
    pos_in_dollars: bool = True,
) -> None:
    """
    Calls `perf_attrib` using inputs, and displays outputs using
    `print_table`.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    returns : pd.Series
        Daily returns of the strategy.
    positions : pd.DataFrame
        Daily net position values.
    factor_returns : pd.DataFrame
        Returns by factor.
    factor_loadings : pd.DataFrame
        Factor loadings for all days.
    transactions : pd.DataFrame, optional
        Executed trade volumes and fill prices.
    pos_in_dollars : bool, optional
        Whether positions are in dollars.
    """
    risk_exposures, perf_attrib_data = empyrical_instance.perf_attrib(
        returns,
        positions,
        factor_returns,
        factor_loadings,
        transactions,
        pos_in_dollars=pos_in_dollars,
    )

    perf_attrib_stats, risk_exposure_stats = empyrical_instance.create_perf_attrib_stats(
        perf_attrib_data, risk_exposures
    )

    percentage_formatter = "{:.2%}".format
    float_formatter = "{:.2f}".format

    summary_stats = perf_attrib_stats.loc[
        ["Annualized Specific Return", "Annualized Common Return", "Annualized Total Return", "Specific Sharpe Ratio"]
    ]
    # Pandas (>= 2.0) may raise when assigning strings into a float Series.
    # Convert to object so we can format a subset of rows as percentages.
    summary_stats = summary_stats.astype(object)

    # Format return rows in summary stats table as percentages.
    for col_name in (
        "Annualized Specific Return",
        "Annualized Common Return",
        "Annualized Total Return",
    ):
        summary_stats[col_name] = percentage_formatter(summary_stats[col_name])

    # Display sharpe to two decimal places.
    summary_stats["Specific Sharpe Ratio"] = float_formatter(summary_stats["Specific Sharpe Ratio"])

    print_table(summary_stats, name="Summary Statistics")

    print_table(
        risk_exposure_stats,
        name="Exposures Summary",
        # In `exposures` table, format exposure column to 2 decimal places, and
        # return columns as percentages.
        formatters={
            "Average Risk Factor Exposure": float_formatter,
            "Annualized Return": percentage_formatter,
            "Cumulative Return": percentage_formatter,
        },
    )
