"""Round-trip trade plotting and display functions.

Includes round-trip lifetimes and probability-of-profit plots.
"""

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from fincore.utils import format_asset, print_table

__all__ = [
    "plot_prob_profit_trade",
    "plot_round_trip_lifetimes",
    "print_round_trip_stats",
    "show_profit_attribution",
]


def plot_round_trip_lifetimes(round_trips, disp_amount=16, lsize=18, ax=None):
    """
    Plots timespans and directions of a sample of round trip trades.

    Parameters
    ----------
    round_trips : pd.DataFrame
        DataFrame with one row per-round-trip trade.
    disp_amount : int, optional
        Number of round trips to display.
    lsize : int, optional
        Line size for the plot.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    if ax is None:
        ax = plt.subplot()

    symbols_sample = round_trips.symbol.unique()
    rng = np.random.default_rng(1)
    sample = rng.choice(symbols_sample, replace=False, size=min(disp_amount, len(symbols_sample)))
    sample_round_trips = round_trips[round_trips.symbol.isin(sample)]

    import pandas as pd

    symbol_idx = pd.Series(np.arange(len(sample)), index=sample)

    for symbol, sym_round_trips in sample_round_trips.groupby("symbol"):
        for _, row in sym_round_trips.iterrows():
            c = "b" if row.long else "r"
            y_ix = symbol_idx[symbol] + 0.05
            ax.plot([row["open_dt"], row["close_dt"]], [y_ix, y_ix], color=c, linewidth=lsize, solid_capstyle="butt")

    # Adjust the number of y-ticks to match the number of symbols in the sample
    num_ticks = len(sample)
    ax.set_yticks(range(num_ticks))
    ax.set_yticklabels([format_asset(s) for s in sample])

    ax.set_ylim((-0.5, num_ticks - 0.5))
    blue = patches.Rectangle([0, 0], 1, 1, color="b", label="Long")
    red = patches.Rectangle([0, 0], 1, 1, color="r", label="Short")
    leg = ax.legend(handles=[blue, red], loc="lower left", frameon=True, framealpha=0.5)
    leg.get_frame().set_edgecolor("black")
    ax.grid(False)

    return ax


def plot_prob_profit_trade(round_trips, ax=None):
    """
    Plots a probability distribution for the event of making
    a profitable trade.

    Parameters
    ----------
    round_trips : pd.DataFrame
        DataFrame with one row per-round-trip trade.
    ax : matplotlib.Axes, optional
        Axes upon which to plot.

    Returns
    -------
    ax : matplotlib.Axes
        The axes that were plotted on.
    """
    x = np.linspace(0, 1.0, 500)

    round_trips["profitable"] = round_trips.pnl > 0

    dist = stats.beta(round_trips.profitable.sum(), (~round_trips.profitable).sum())
    y = dist.pdf(x)
    lower_perc = dist.ppf(0.025)
    upper_perc = dist.ppf(0.975)

    lower_plot = dist.ppf(0.001)
    upper_plot = dist.ppf(0.999)

    if ax is None:
        ax = plt.subplot()

    ax.plot(x, y)
    ax.axvline(lower_perc, color="0.5")
    ax.axvline(upper_perc, color="0.5")

    ax.set_xlabel("Probability of making a profitable decision")
    ax.set_ylabel("Belief")
    ax.set_xlim(lower_plot, upper_plot)
    ax.set_ylim((0, y.max() + 1.0))

    return ax


def print_round_trip_stats(empyrical_instance, round_trips, hide_pos=False, run_flask_app=False):
    """
    Print various round-trip statistics.

    Parameters
    ----------
    empyrical_instance : Empyrical
        Empyrical instance used to compute metrics.
    round_trips : pd.DataFrame
        DataFrame with one row per-round-trip trade.
    hide_pos : bool, optional, default: False
        Whether to hide the position-based statistics.
    run_flask_app : bool, optional, default: False
        Whether to run a Flask app to serve the round-trip statistics.
    """
    stats = empyrical_instance.gen_round_trip_stats(round_trips)

    print_table(stats["summary"], float_format="{:.2f}".format, name="Summary stats", run_flask_app=run_flask_app)
    print_table(stats["pnl"], float_format="${:.2f}".format, name="PnL stats", run_flask_app=run_flask_app)
    print_table(stats["duration"], float_format="{:.2f}".format, name="Duration stats", run_flask_app=run_flask_app)
    print_table(stats["returns"] * 100, float_format="{:.2f}%".format, name="Return stats", run_flask_app=run_flask_app)

    if not hide_pos:
        stats["symbols"].columns = stats["symbols"].columns.map(format_asset)
        print_table(
            stats["symbols"] * 100, float_format="{:.2f}%".format, name="Symbol stats", run_flask_app=run_flask_app
        )


def show_profit_attribution(round_trips, run_flask_app=False):
    """
    Prints the share of total PnL contributed by each traded name.

    Parameters
    ----------
    round_trips : pd.DataFrame
        DataFrame with one row per-round-trip trade.
    run_flask_app : bool, optional, default=False
        Whether to run the flask app to display the plot.
    """
    total_pnl = round_trips["pnl"].sum()
    pnl_attribution = round_trips.groupby("symbol")["pnl"].sum() / total_pnl
    pnl_attribution.name = ""

    pnl_attribution.index = pnl_attribution.index.map(format_asset)
    print_table(
        pnl_attribution.sort_values(
            inplace=False,
            ascending=False,
        ),
        name="Profitability (PnL / PnL total) per name",
        float_format="{:.2%}".format,
        run_flask_app=run_flask_app,
    )
