"""Risk-related plotting functions.

Includes style factor exposures, sector exposures, cap exposures, and volume
exposures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
import numpy as np

from fincore.constants import CAP_BUCKETS, SECTORS

if TYPE_CHECKING:
    import pandas as pd

__all__ = [
    "plot_cap_exposures_gross",
    "plot_cap_exposures_longshort",
    "plot_cap_exposures_net",
    "plot_sector_exposures_gross",
    "plot_sector_exposures_longshort",
    "plot_sector_exposures_net",
    "plot_style_factor_exposures",
    "plot_volume_exposures_gross",
    "plot_volume_exposures_longshort",
]


# Get a categorical colormap.
cmap = plt.get_cmap("gist_rainbow")


def plot_style_factor_exposures(
    tot_style_factor_exposure: pd.Series,
    factor_name: str | None = None,
    ax: Any = None,
) -> Any:
    """
    Plots DataFrame output of compute_style_factor_exposures as a line graph.

    Parameters
    ----------
    tot_style_factor_exposure : pd.Series
        Daily style factor exposures (output of compute_style_factor_exposures)
    factor_name : string, optional
        Name of a style factor, for use in graph title
        - Defaults to tot_style_factor_exposure.name
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    if factor_name is None:
        factor_name = tot_style_factor_exposure.name

    ax.plot(tot_style_factor_exposure.index, tot_style_factor_exposure, label=factor_name)
    avg = tot_style_factor_exposure.mean()
    ax.axhline(avg, linestyle="-.", label=f"Mean = {avg:.3}")
    ax.axhline(0, color="k", linestyle="-")
    _, _, y1, y2 = plt.axis()
    lim = max(abs(y1), abs(y2))
    ax.set(title=f"Exposure to {factor_name}", ylabel=f"{factor_name} \n weighted exposure", ylim=(-lim, lim))
    ax.legend(frameon=True, framealpha=0.5)

    return ax


def plot_sector_exposures_longshort(
    long_exposures: Any,
    short_exposures: Any,
    sector_dict: dict[str, str] | None = None,
    ax: Any = None,
) -> Any:
    """
    Plots outputs of compute_sector_exposures as area charts.

    Parameters
    ----------
    long_exposures, short_exposures : arrays
        Arrays of long and short sector exposures (output of
        compute_sector_exposures).
    sector_dict : dict or OrderedDict, optional
        Dictionary of all sectors
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    sector_names = list(SECTORS.values()) if sector_dict is None else list(sector_dict.values())

    color_list = cmap(np.linspace(0, 1, 11))

    ax.stackplot(
        long_exposures[0].index, long_exposures, labels=sector_names, colors=color_list, alpha=0.8, baseline="zero"
    )
    ax.stackplot(long_exposures[0].index, short_exposures, colors=color_list, alpha=0.8, baseline="zero")
    ax.axhline(0, color="k", linestyle="-")
    ax.set(title="Long and short exposures to sectors", ylabel="Proportion of long/short exposure in sectors")
    ax.legend(loc="upper left", frameon=True, framealpha=0.5)

    return ax


def plot_sector_exposures_gross(
    gross_exposures: Any,
    sector_dict: dict[str, str] | None = None,
    ax: Any = None,
) -> Any:
    """
    Plots output of compute_sector_exposures as area charts.

    Parameters
    ----------
    gross_exposures : arrays
        Arrays of gross sector exposures (output of compute_sector_exposures).
    sector_dict : dict or OrderedDict, optional
        Dictionary of all sectors
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    sector_names = list(SECTORS.values()) if sector_dict is None else list(sector_dict.values())

    color_list = cmap(np.linspace(0, 1, 11))

    ax.stackplot(
        gross_exposures[0].index, gross_exposures, labels=sector_names, colors=color_list, alpha=0.8, baseline="zero"
    )
    ax.axhline(0, color="k", linestyle="-")
    ax.set(title="Gross exposure to sectors", ylabel="Proportion of gross exposure \n in sectors")

    return ax


def plot_sector_exposures_net(
    net_exposures: Any,
    sector_dict: dict[str, str] | None = None,
    ax: Any = None,
) -> Any:
    """
    Plots output of compute_sector_exposures as line graphs.

    Parameters
    ----------
    net_exposures : arrays
        Arrays of net sector exposures (output of compute_sector_exposures).
    sector_dict : dict or OrderedDict, optional
        Dictionary of all sectors
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    sector_names = list(SECTORS.values()) if sector_dict is None else list(sector_dict.values())

    color_list = cmap(np.linspace(0, 1, 11))

    for i in range(len(net_exposures)):
        ax.plot(net_exposures[i], color=color_list[i], alpha=0.8, label=sector_names[i])
    ax.set(title="Net exposures to sectors", ylabel="Proportion of net exposure \n in sectors")

    return ax


def plot_cap_exposures_longshort(
    long_exposures: Any,
    short_exposures: Any,
    ax: Any = None,
) -> Any:
    """
    Plots outputs of compute_cap_exposures as area charts.

    Parameters
    ----------
    long_exposures, short_exposures : arrays
        Arrays of long and short market cap exposures (output of
        compute_cap_exposures).
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    color_list = cmap(np.linspace(0, 1, 5))

    ax.stackplot(
        long_exposures[0].index,
        long_exposures,
        labels=CAP_BUCKETS.keys(),
        colors=color_list,
        alpha=0.8,
        baseline="zero",
    )
    ax.stackplot(long_exposures[0].index, short_exposures, colors=color_list, alpha=0.8, baseline="zero")
    ax.axhline(0, color="k", linestyle="-")
    ax.set(
        title="Long and short exposures to market caps",
        ylabel="Proportion of long/short exposure in market cap buckets",
    )
    ax.legend(loc="upper left", frameon=True, framealpha=0.5)

    return ax


def plot_cap_exposures_gross(
    gross_exposures: Any,
    ax: Any = None,
) -> Any:
    """
    Plots outputs of compute_cap_exposures as area charts.

    Parameters
    ----------
    gross_exposures : array
        Arrays of gross market cap exposures (output of compute_cap_exposures).
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    color_list = cmap(np.linspace(0, 1, 5))

    ax.stackplot(
        gross_exposures[0].index,
        gross_exposures,
        labels=CAP_BUCKETS.keys(),
        colors=color_list,
        alpha=0.8,
        baseline="zero",
    )
    ax.axhline(0, color="k", linestyle="-")
    ax.set(title="Gross exposure to market caps", ylabel="Proportion of gross exposure \n in market cap buckets")

    return ax


def plot_cap_exposures_net(
    net_exposures: Any,
    ax: Any = None,
) -> Any:
    """
    Plots outputs of compute_cap_exposures as line graphs.

    Parameters
    ----------
    net_exposures : array
        Arrays of gross market cap exposures (output of compute_cap_exposures).
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    color_list = cmap(np.linspace(0, 1, 5))

    cap_names = list(CAP_BUCKETS.keys())
    for i in range(len(net_exposures)):
        ax.plot(net_exposures[i], color=color_list[i], alpha=0.8, label=cap_names[i])
    ax.axhline(0, color="k", linestyle="-")
    ax.set(title="Net exposure to market caps", ylabel="Proportion of net exposure \n in market cap buckets")

    return ax


def plot_volume_exposures_longshort(
    longed_threshold: pd.Series,
    shorted_threshold: pd.Series,
    percentile: float,
    ax: Any = None,
) -> Any:
    """
    Plots outputs of compute_volume_exposures as line graphs.

    Parameters
    ----------
    longed_threshold, shorted_threshold : pd.Series
        Series of longed and shorted volume exposures (output of
        compute_volume_exposures).
    percentile : float
        Percentile to use when computing and plotting volume exposures.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    ax.plot(longed_threshold.index, longed_threshold, color="b", label="long")
    ax.plot(shorted_threshold.index, shorted_threshold, color="r", label="short")
    ax.axhline(0, color="k")
    ax.set(
        title="Long and short exposures to ill_liquidity",
        ylabel=f"{100 * percentile}th percentile of proportion of volume (%)",
    )
    ax.legend(frameon=True, framealpha=0.5)

    return ax


def plot_volume_exposures_gross(
    grossed_threshold: pd.Series,
    percentile: float,
    ax: Any = None,
) -> Any:
    """
    Plots outputs of compute_volume_exposures as line graphs.

    Parameters
    ----------
    grossed_threshold : pd.Series
        Series of grossed volume exposures (output of
        compute_volume_exposures).
    percentile : float
        Percentile to use when computing and plotting volume exposures.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.gca()

    ax.plot(grossed_threshold.index, grossed_threshold, color="b", label="gross")
    ax.axhline(0, color="k")
    ax.set(
        title="Gross exposure to ill_liquidity",
        ylabel=f"{100 * percentile}th percentile of \n proportion of volume (%)",
    )
    ax.legend(frameon=True, framealpha=0.5)

    return ax
