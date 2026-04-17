# =============================================================================
# Tear sheet creation functions
# =============================================================================
#
# This module contains 11 ``create_*_tear_sheet`` functions organized by domain:
#
# 1. Full tear sheet: create_full_tear_sheet (aggregates multiple sub tear sheets)
# 2. Returns tear sheet: create_returns_tear_sheet (returns analysis)
# 3. Risk tear sheet: create_risk_tear_sheet (risk metrics analysis)
# 4. Transactions tear sheet: create_txn_tear_sheet (transactions analysis)
# 5. Simple tear sheet: create_simple_tear_sheet (simplified full tear sheet)
# 6. Interesting times tear sheet: create_interesting_times_tear_sheet (stress/interesting periods)
# 7. Performance attribution tear sheet: create_perf_attribution_tear_sheet (attribution)
# 8. Round trip tear sheet: create_round_trip_tear_sheet (round-trip analysis)
# 9. Bayesian tear sheet: create_bayesian_tear_sheet (Bayesian analysis)
# 10. Capacity tear sheet: create_capacity_tear_sheet (capacity constraints)
# 11. Positions tear sheet: create_position_tear_sheet (positions analysis)
#
# =============================================================================


"""
Tear sheet creation functions.
Contains functions for creating various analysis tear sheets.
"""

import importlib
import time
import warnings
from collections.abc import Callable
from typing import Any

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

from fincore.constants import (
    APPROX_BDAYS_PER_MONTH,
    CAPACITY_CAPITAL_BASE,
    CAPACITY_SWEEP_MAX_PV,
    CAPACITY_SWEEP_MIN_PV,
    CAPACITY_SWEEP_STEP,
    FACTOR_PARTITIONS,
    LIQUIDATION_DAILY_VOL_LIMIT,
    TRADE_DAILY_VOL_LIMIT,
)
from fincore.empyrical import Empyrical
from fincore.utils import (
    check_intraday,
    clip_returns_to_benchmark,
    format_asset,
    get_utc_timestamp,
    make_timezone_aware,
    print_table,
    timer,
)

__all__ = [
    "DisplayFunc",
    "MarkdownFunc",
    "create_bayesian_tear_sheet",
    "create_capacity_tear_sheet",
    "create_full_tear_sheet",
    "create_interesting_times_tear_sheet",
    "create_perf_attrib_tear_sheet",
    "create_position_tear_sheet",
    "create_returns_tear_sheet",
    "create_risk_tear_sheet",
    "create_round_trip_tear_sheet",
    "create_simple_tear_sheet",
    "create_txn_tear_sheet",
]


DisplayFunc = Callable[..., Any]
MarkdownFunc = Callable[[str], Any]


def _fallback_display(*objs: Any, **_kwargs: Any) -> None:
    print(*objs)


def _fallback_markdown(text: str) -> str:
    return text


display: DisplayFunc = _fallback_display
Markdown: MarkdownFunc = _fallback_markdown

try:
    _ipy_display_mod = importlib.import_module("IPython.display")
except ModuleNotFoundError:  # pragma: no cover
    pass
else:
    display = getattr(_ipy_display_mod, "display", _fallback_display)
    Markdown = getattr(_ipy_display_mod, "Markdown", _fallback_markdown)


# # Full tear sheet
# ==============
def create_full_tear_sheet(
    pyfolio_instance,
    returns,
    positions=None,
    transactions=None,
    market_data=None,
    benchmark_rets=None,
    slippage=None,
    live_start_date=None,
    sector_mappings=None,
    bayesian=False,
    round_trips=False,
    estimate_intraday="infer",
    hide_positions=False,
    cone_std=(1.0, 1.5, 2.0),
    bootstrap=False,
    unadjusted_returns=None,
    style_factor_panel=None,
    sectors=None,
    caps=None,
    shares_held=None,
    volumes=None,
    percentile=None,
    turnover_denom="AGB",
    set_context=True,
    factor_returns=None,
    factor_loadings=None,
    pos_in_dollars=True,
    header_rows=None,
    factor_partitions=FACTOR_PARTITIONS,
):
    """
    Generate a number of tear sheets that are useful for analyzing a strategy's performance.
    """
    if (unadjusted_returns is None) and (slippage is not None) and (transactions is not None):
        unadjusted_returns = returns.copy()
        returns = pyfolio_instance.adjust_returns_for_slippage(returns, positions, transactions, slippage)

    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    pyfolio_instance.create_returns_tear_sheet(
        returns,
        positions=positions,
        transactions=transactions,
        live_start_date=live_start_date,
        cone_std=cone_std,
        benchmark_rets=benchmark_rets,
        bootstrap=bootstrap,
        turnover_denom=turnover_denom,
        header_rows=header_rows,
        set_context=set_context,
    )

    pyfolio_instance.create_interesting_times_tear_sheet(
        returns, benchmark_rets=benchmark_rets, set_context=set_context
    )

    if positions is not None:
        pyfolio_instance.create_position_tear_sheet(
            returns,
            positions,
            hide_positions=hide_positions,
            set_context=set_context,
            sector_mappings=sector_mappings,
            estimate_intraday=False,
        )

        if transactions is not None:
            pyfolio_instance.create_txn_tear_sheet(
                returns,
                positions,
                transactions,
                unadjusted_returns=unadjusted_returns,
                estimate_intraday=False,
                set_context=set_context,
            )
            if round_trips:
                pyfolio_instance.create_round_trip_tear_sheet(
                    returns=returns,
                    positions=positions,
                    transactions=transactions,
                    sector_mappings=sector_mappings,
                    estimate_intraday=False,
                )

            if market_data is not None:
                pyfolio_instance.create_capacity_tear_sheet(
                    returns,
                    positions,
                    transactions,
                    market_data,
                    liquidation_daily_vol_limit=0.2,
                    last_n_days=125,
                    estimate_intraday=False,
                )

        if style_factor_panel is not None:
            pyfolio_instance.create_risk_tear_sheet(
                positions, style_factor_panel, sectors, caps, shares_held, volumes, percentile
            )

        if factor_returns is not None and factor_loadings is not None:
            pyfolio_instance.create_perf_attrib_tear_sheet(
                returns,
                positions,
                factor_returns,
                factor_loadings,
                transactions,
                pos_in_dollars=pos_in_dollars,
                factor_partitions=factor_partitions,
            )

    if bayesian:
        pyfolio_instance.create_bayesian_tear_sheet(
            returns, live_start_date=live_start_date, benchmark_rets=benchmark_rets, set_context=set_context
        )


# # Simple tear sheet
# ==============
def create_simple_tear_sheet(
    pyfolio_instance,
    returns,
    positions=None,
    transactions=None,
    benchmark_rets=None,
    slippage=None,
    estimate_intraday="infer",
    live_start_date=None,
    turnover_denom="AGB",
    header_rows=None,
):
    """
    Simpler version of create_full_tear_sheet.
    """
    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    if (slippage is not None) and (transactions is not None):
        returns = pyfolio_instance.adjust_returns_for_slippage(returns, positions, transactions, slippage)

    always_sections = 4
    positions_sections = 4 if positions is not None else 0
    transactions_sections = 2 if transactions is not None else 0
    live_sections = 1 if live_start_date is not None else 0
    benchmark_sections = 1 if benchmark_rets is not None else 0

    vertical_sections = sum(
        [
            always_sections,
            positions_sections,
            transactions_sections,
            live_sections,
            benchmark_sections,
        ]
    )

    if live_start_date is not None:
        live_start_date = get_utc_timestamp(live_start_date)

    pyfolio_instance.show_perf_stats(
        returns,
        benchmark_rets,
        positions=positions,
        transactions=transactions,
        turnover_denom=turnover_denom,
        live_start_date=live_start_date,
        header_rows=header_rows,
    )

    fig = plt.figure(figsize=(14, vertical_sections * 6))
    gs = gridspec.GridSpec(vertical_sections, 3, wspace=0.5, hspace=0.5)

    ax_rolling_returns = fig.add_subplot(gs[:2, :])
    i = 2
    if benchmark_rets is not None:
        ax_rolling_beta = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
        i += 1
    ax_rolling_sharpe = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_underwater = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1

    pyfolio_instance.plot_rolling_returns(
        returns,
        factor_returns=benchmark_rets,
        live_start_date=live_start_date,
        cone_std=(1.0, 1.5, 2.0),
        ax=ax_rolling_returns,
    )
    ax_rolling_returns.set_title("Cumulative returns")

    if benchmark_rets is not None:
        pyfolio_instance.plot_rolling_beta(returns, benchmark_rets, ax=ax_rolling_beta)

    pyfolio_instance.plot_rolling_sharpe(returns, ax=ax_rolling_sharpe)

    pyfolio_instance.plot_drawdown_underwater(returns, ax=ax_underwater)

    if positions is not None:
        ax_exposures = fig.add_subplot(gs[i, :])
        i += 1
        ax_top_positions = fig.add_subplot(gs[i, :], sharex=ax_exposures)
        i += 1
        ax_holdings = fig.add_subplot(gs[i, :], sharex=ax_exposures)
        i += 1
        ax_long_short_holdings = fig.add_subplot(gs[i, :])
        i += 1

        positions_alloc = pyfolio_instance.get_percent_alloc(positions)

        pyfolio_instance.plot_exposures(returns, positions, ax=ax_exposures)

        pyfolio_instance.show_and_plot_top_positions(
            returns, positions_alloc, show_and_plot=0, hide_positions=False, ax=ax_top_positions
        )

        pyfolio_instance.plot_holdings(returns, positions_alloc, ax=ax_holdings)

        pyfolio_instance.plot_long_short_holdings(returns, positions_alloc, ax=ax_long_short_holdings)

        if transactions is not None:
            ax_turnover = fig.add_subplot(gs[i, :])
            i += 1
            ax_txn_timings = fig.add_subplot(gs[i, :])
            i += 1

            pyfolio_instance.plot_turnover(returns, transactions, positions, ax=ax_turnover)

            pyfolio_instance.plot_txn_time_hist(transactions, ax=ax_txn_timings)

    for ax in fig.axes:
        plt.setp(ax.get_xticklabels(), visible=True)


# # Returns tear sheet
# ==============
def create_returns_tear_sheet(
    pyfolio_instance,
    returns,
    positions=None,
    transactions=None,
    live_start_date=None,
    cone_std=(1.0, 1.5, 2.0),
    benchmark_rets=None,
    bootstrap=False,
    turnover_denom="AGB",
    header_rows=None,
    run_flask_app=False,
):
    """
    Generate a number of plots for analyzing a strategy's returns.
    """
    if benchmark_rets is not None:
        returns = clip_returns_to_benchmark(returns, benchmark_rets)

    pyfolio_instance.show_perf_stats(
        returns,
        benchmark_rets,
        positions=positions,
        transactions=transactions,
        turnover_denom=turnover_denom,
        bootstrap=bootstrap,
        live_start_date=live_start_date,
        header_rows=header_rows,
        run_flask_app=run_flask_app,
    )

    pyfolio_instance.show_worst_drawdown_periods(returns, run_flask_app=run_flask_app)

    vertical_sections = 11

    if live_start_date is not None:
        vertical_sections += 1
        live_start_date = get_utc_timestamp(live_start_date)

    if benchmark_rets is not None:
        vertical_sections += 1

    if bootstrap:
        vertical_sections += 1

    fig = plt.figure(figsize=(14, vertical_sections * 6))
    gs = gridspec.GridSpec(vertical_sections, 3, wspace=0.5, hspace=0.5)
    ax_rolling_returns = fig.add_subplot(gs[:2, :])

    i = 2
    ax_rolling_returns_vol_match = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_rolling_returns_log = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_returns = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    if benchmark_rets is not None:
        ax_rolling_beta = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
        i += 1
    ax_rolling_volatility = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_rolling_sharpe = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_drawdown = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_underwater = fig.add_subplot(gs[i, :], sharex=ax_rolling_returns)
    i += 1
    ax_monthly_heatmap = fig.add_subplot(gs[i, 0])
    ax_annual_returns = fig.add_subplot(gs[i, 1])
    ax_monthly_dist = fig.add_subplot(gs[i, 2])
    i += 1
    ax_return_quantiles = fig.add_subplot(gs[i, :])
    i += 1

    pyfolio_instance.plot_rolling_returns(
        returns,
        factor_returns=benchmark_rets,
        live_start_date=live_start_date,
        cone_std=cone_std,
        ax=ax_rolling_returns,
    )
    ax_rolling_returns.set_title("Cumulative returns")

    pyfolio_instance.plot_rolling_returns(
        returns,
        factor_returns=benchmark_rets,
        live_start_date=live_start_date,
        cone_std=None,
        volatility_match=(benchmark_rets is not None),
        legend_loc=None,
        ax=ax_rolling_returns_vol_match,
    )
    ax_rolling_returns_vol_match.set_title("Cumulative returns volatility matched to benchmark")

    pyfolio_instance.plot_rolling_returns(
        returns,
        factor_returns=benchmark_rets,
        logy=True,
        live_start_date=live_start_date,
        cone_std=cone_std,
        ax=ax_rolling_returns_log,
    )
    ax_rolling_returns_log.set_title("Cumulative returns on logarithmic scale")

    pyfolio_instance.plot_returns(returns, live_start_date=live_start_date, ax=ax_returns)
    ax_returns.set_title("Returns")

    if benchmark_rets is not None:
        pyfolio_instance.plot_rolling_beta(returns, benchmark_rets, ax=ax_rolling_beta)

    pyfolio_instance.plot_rolling_volatility(returns, factor_returns=benchmark_rets, ax=ax_rolling_volatility)

    pyfolio_instance.plot_rolling_sharpe(returns, ax=ax_rolling_sharpe)

    pyfolio_instance.plot_drawdown_periods(returns, top=5, ax=ax_drawdown)

    pyfolio_instance.plot_drawdown_underwater(returns=returns, ax=ax_underwater)

    pyfolio_instance.plot_monthly_returns_heatmap(returns, ax=ax_monthly_heatmap)
    pyfolio_instance.plot_annual_returns(returns, ax=ax_annual_returns)
    pyfolio_instance.plot_monthly_returns_dist(returns, ax=ax_monthly_dist)

    pyfolio_instance.plot_return_quantiles(returns, live_start_date=live_start_date, ax=ax_return_quantiles)

    if bootstrap and (benchmark_rets is not None):
        ax_bootstrap = fig.add_subplot(gs[i, :])
        pyfolio_instance.plot_perf_stats(returns, benchmark_rets, ax=ax_bootstrap)
    elif bootstrap:
        raise ValueError("bootstrap requires passing of benchmark_rets.")

    for ax in fig.axes:
        plt.setp(ax.get_xticklabels(), visible=True)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Positions tear sheet
# ==============
def create_position_tear_sheet(
    pyfolio_instance,
    returns,
    positions,
    show_and_plot_top_pos=2,
    hide_positions=False,
    run_flask_app=False,
    sector_mappings=None,
    transactions=None,
    estimate_intraday="infer",
):
    """
    Generate a number of plots for analyzing a strategy's positions and holdings.
    """
    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    if hide_positions:
        show_and_plot_top_pos = 0
    vertical_sections = 7 if sector_mappings is not None else 6

    fig = plt.figure(figsize=(14, vertical_sections * 6))
    gs = gridspec.GridSpec(vertical_sections, 3, wspace=0.5, hspace=0.5)
    ax_exposures = fig.add_subplot(gs[0, :])
    ax_top_positions = fig.add_subplot(gs[1, :], sharex=ax_exposures)
    ax_max_median_pos = fig.add_subplot(gs[2, :], sharex=ax_exposures)
    ax_holdings = fig.add_subplot(gs[3, :], sharex=ax_exposures)
    ax_long_short_holdings = fig.add_subplot(gs[4, :])
    ax_gross_leverage = fig.add_subplot(gs[5, :], sharex=ax_exposures)

    positions_alloc = pyfolio_instance.get_percent_alloc(positions)

    pyfolio_instance.plot_exposures(returns, positions, ax=ax_exposures)

    pyfolio_instance.show_and_plot_top_positions(
        returns,
        positions_alloc,
        show_and_plot=show_and_plot_top_pos,
        hide_positions=hide_positions,
        ax=ax_top_positions,
        run_flask_app=run_flask_app,
    )

    pyfolio_instance.plot_max_median_position_concentration(positions, ax=ax_max_median_pos)

    pyfolio_instance.plot_holdings(returns, positions_alloc, ax=ax_holdings)

    pyfolio_instance.plot_long_short_holdings(returns, positions_alloc, ax=ax_long_short_holdings)

    pyfolio_instance.plot_gross_leverage(returns, positions, ax=ax_gross_leverage)

    if sector_mappings is not None:
        sector_exposures = pyfolio_instance.get_sector_exposures(positions, sector_mappings)
        if len(sector_exposures.columns) > 1:
            sector_alloc = pyfolio_instance.get_percent_alloc(sector_exposures)
            sector_alloc = sector_alloc.drop("cash", axis="columns")
            ax_sector_alloc = fig.add_subplot(gs[6, :], sharex=ax_exposures)
            pyfolio_instance.plot_sector_allocations(returns, sector_alloc, ax=ax_sector_alloc)

    for ax in fig.axes:
        plt.setp(ax.get_xticklabels(), visible=True)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Transactions tear sheet
# ==============
def create_txn_tear_sheet(
    pyfolio_instance,
    returns,
    positions,
    transactions,
    unadjusted_returns=None,
    estimate_intraday="infer",
    run_flask_app=False,
):
    """
    Generate a number of plots for analyzing a strategy's transactions.
    """
    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    vertical_sections = 6 if unadjusted_returns is not None else 4

    fig = plt.figure(figsize=(14, vertical_sections * 6))
    gs = gridspec.GridSpec(vertical_sections, 3, wspace=0.5, hspace=0.5)
    ax_turnover = fig.add_subplot(gs[0, :])
    ax_daily_volume = fig.add_subplot(gs[1, :], sharex=ax_turnover)
    ax_turnover_hist = fig.add_subplot(gs[2, :])
    ax_txn_timings = fig.add_subplot(gs[3, :])

    pyfolio_instance.plot_turnover(returns, transactions, positions, ax=ax_turnover)

    pyfolio_instance.plot_daily_volume(returns, transactions, ax=ax_daily_volume)

    try:
        pyfolio_instance.plot_daily_turnover_hist(transactions, positions, ax=ax_turnover_hist)
    except ValueError:
        warnings.warn("Unable to generate turnover plot.", UserWarning, stacklevel=2)

    pyfolio_instance.plot_txn_time_hist(transactions, ax=ax_txn_timings)

    if unadjusted_returns is not None:
        ax_slippage_sweep = fig.add_subplot(gs[4, :])
        pyfolio_instance.plot_slippage_sweep(unadjusted_returns, positions, transactions, ax=ax_slippage_sweep)
        ax_slippage_sensitivity = fig.add_subplot(gs[5, :])
        pyfolio_instance.plot_slippage_sensitivity(
            unadjusted_returns, positions, transactions, ax=ax_slippage_sensitivity
        )

    for ax in fig.axes:
        plt.setp(ax.get_xticklabels(), visible=True)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Round trip tear sheet
# ================
def create_round_trip_tear_sheet(
    pyfolio_instance,
    returns,
    positions,
    transactions,
    sector_mappings=None,
    estimate_intraday="infer",
    run_flask_app=False,
):
    """
    Generate a number of figures and plots describing trade round trips.
    """
    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    transactions_closed = Empyrical.add_closing_transactions(positions, transactions)
    trades = Empyrical.extract_round_trips(
        transactions_closed,
        portfolio_value=positions.sum(axis="columns") / (1 + returns),
    )

    if len(trades) < 5:
        warnings.warn(
            """Fewer than 5 round-trip trades made.
               Skipping round trip tearsheet.""",
            UserWarning,
            stacklevel=2,
        )
        return None

    pyfolio_instance.print_round_trip_stats(trades, run_flask_app=run_flask_app)

    pyfolio_instance.show_profit_attribution(trades, run_flask_app=run_flask_app)

    if sector_mappings is not None:
        sector_trades = Empyrical.apply_sector_mappings_to_round_trips(trades, sector_mappings)
        pyfolio_instance.show_profit_attribution(sector_trades, run_flask_app=run_flask_app)

    fig = plt.figure(figsize=(14, 3 * 6))

    gs = gridspec.GridSpec(3, 2, wspace=0.5, hspace=0.5)

    ax_trade_lifetimes = fig.add_subplot(gs[0, :])
    ax_prob_profit_trade = fig.add_subplot(gs[1, 0])
    ax_holding_time = fig.add_subplot(gs[1, 1])
    ax_pnl_per_round_trip_dollars = fig.add_subplot(gs[2, 0])
    ax_pnl_per_round_trip_pct = fig.add_subplot(gs[2, 1])

    pyfolio_instance.plot_round_trip_lifetimes(trades, ax=ax_trade_lifetimes)

    pyfolio_instance.plot_prob_profit_trade(trades, ax=ax_prob_profit_trade)

    trade_holding_times = [x.days for x in trades["duration"]]
    sns.histplot(trade_holding_times, kde=False, ax=ax_holding_time)
    ax_holding_time.set(xlabel="Holding time in days")

    sns.histplot(trades.pnl, kde=False, ax=ax_pnl_per_round_trip_dollars)
    ax_pnl_per_round_trip_dollars.set(xlabel="PnL per round-trip trade in $")

    sns.histplot(trades.returns.dropna() * 100, kde=False, ax=ax_pnl_per_round_trip_pct)
    ax_pnl_per_round_trip_pct.set(xlabel="Round-trip returns in %")

    gs.tight_layout(fig)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Interesting times tear sheet
def create_interesting_times_tear_sheet(
    pyfolio_instance, returns, benchmark_rets=None, legend_loc="best", run_flask_app=False
):
    """
    Generate a number of returns plots around interesting points in time.
    """
    rets_interesting = pyfolio_instance.extract_interesting_date_ranges(returns)

    if not rets_interesting:
        warnings.warn("Passed returns do not overlap with any interesting times.", UserWarning, stacklevel=2)
        return None

    print_table(
        pd.DataFrame(rets_interesting).describe().transpose().loc[:, ["mean", "min", "max"]] * 100,
        name="Stress Events",
        float_format="{:.2f}%".format,
        run_flask_app=run_flask_app,
    )

    if benchmark_rets is not None:
        returns = clip_returns_to_benchmark(returns, benchmark_rets)
        bmark_interesting = pyfolio_instance.extract_interesting_date_ranges(benchmark_rets)

    num_plots = len(rets_interesting)
    num_rows = int((num_plots + 1) / 2.0)
    fig = plt.figure(figsize=(14, num_rows * 6.0))
    gs = gridspec.GridSpec(num_rows, 2, wspace=0.5, hspace=0.5)

    for i, (name, rets_period) in enumerate(rets_interesting.items()):
        ax = fig.add_subplot(gs[int(i / 2.0), i % 2])

        pyfolio_instance.cum_returns(rets_period).plot(ax=ax, color="forestgreen", label="algo", alpha=0.7, lw=2)

        if benchmark_rets is not None:
            pyfolio_instance.cum_returns(bmark_interesting[name]).plot(
                ax=ax, color="gray", label="benchmark", alpha=0.6
            )
            ax.legend(["Algo", "benchmark"], loc=legend_loc, frameon=True, framealpha=0.5)
        else:
            ax.legend(["Algo"], loc=legend_loc, frameon=True, framealpha=0.5)

        ax.set_title(name)
        ax.set_ylabel("Returns")
        ax.set_xlabel("")

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Capacity tear sheet
# ==============
def create_capacity_tear_sheet(
    pyfolio_instance,
    returns,
    positions,
    transactions,
    market_data,
    liquidation_daily_vol_limit=LIQUIDATION_DAILY_VOL_LIMIT,
    trade_daily_vol_limit=TRADE_DAILY_VOL_LIMIT,
    last_n_days=APPROX_BDAYS_PER_MONTH * 6,
    days_to_liquidate_limit=1,
    estimate_intraday="infer",
    run_flask_app=False,
):
    """
    Generates a report detailing portfolio size constraints.
    """
    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    print(
        "Max days to liquidation is computed for each traded name "
        "assuming a 20% limit on daily bar consumption \n"
        "and trailing 5 day mean volume as the available bar volume.\n\n"
        "Tickers with >1 day liquidation time at a"
        " constant $1m capital base:"
    )

    max_days_by_ticker = pyfolio_instance.get_max_days_to_liquidate_by_ticker(
        positions,
        market_data,
        max_bar_consumption=liquidation_daily_vol_limit,
        capital_base=CAPACITY_CAPITAL_BASE,
        mean_volume_window=5,
    )
    max_days_by_ticker.index = max_days_by_ticker.index.map(format_asset)

    print("Whole backtest:")
    print_table(
        max_days_by_ticker[max_days_by_ticker.days_to_liquidate > days_to_liquidate_limit], run_flask_app=run_flask_app
    )

    max_days_by_ticker_lnd = pyfolio_instance.get_max_days_to_liquidate_by_ticker(
        positions,
        market_data,
        max_bar_consumption=liquidation_daily_vol_limit,
        capital_base=CAPACITY_CAPITAL_BASE,
        mean_volume_window=5,
        last_n_days=last_n_days,
    )
    max_days_by_ticker_lnd.index = max_days_by_ticker_lnd.index.map(format_asset)

    print(f"Last {last_n_days} trading days:")
    print_table(max_days_by_ticker_lnd[max_days_by_ticker_lnd.days_to_liquidate > 1], run_flask_app=run_flask_app)

    llt = pyfolio_instance.get_low_liquidity_transactions(transactions, market_data)
    llt.index = llt.index.map(format_asset)

    print(f"Tickers with daily transactions consuming >{trade_daily_vol_limit * 100}% of daily bar \nall backtest:")
    print_table(llt[llt["max_pct_bar_consumed"] > trade_daily_vol_limit * 100], run_flask_app=run_flask_app)

    llt = pyfolio_instance.get_low_liquidity_transactions(transactions, market_data, last_n_days=last_n_days)

    print(f"Last {last_n_days} trading days:")
    print_table(llt[llt["max_pct_bar_consumed"] > trade_daily_vol_limit * 100], run_flask_app=run_flask_app)

    bt_starting_capital = positions.iloc[0].sum() / (1 + returns.iloc[0])
    fig, ax_capacity_sweep = plt.subplots(figsize=(14, 6))
    pyfolio_instance.plot_capacity_sweep(
        returns,
        transactions,
        market_data,
        bt_starting_capital,
        min_pv=CAPACITY_SWEEP_MIN_PV,
        max_pv=CAPACITY_SWEEP_MAX_PV,
        step_size=CAPACITY_SWEEP_STEP,
        ax=ax_capacity_sweep,
    )
    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Bayesian tear sheet
# ===============
def create_bayesian_tear_sheet(
    pyfolio_instance,
    returns,
    benchmark_rets=None,
    live_start_date=None,
    samples=2000,
    run_flask_app=False,
    stoch_vol=False,
    progressbar=True,
):
    """
    Generate a number of Bayesian distributions and a Bayesian cone plot of returns.
    """
    if live_start_date is None:
        raise NotImplementedError("Bayesian tear sheet requires setting of live_start_date")

    live_start_date = get_utc_timestamp(live_start_date)
    live_start_date = make_timezone_aware(live_start_date, returns.index[0].tz)
    df_train = returns.loc[returns.index < live_start_date]
    df_test = returns.loc[returns.index >= live_start_date]

    print("Running T model")
    previous_time = time.time()
    start_time = previous_time

    _trace_t, ppc_t = pyfolio_instance.run_model(
        "t", df_train, returns_test=df_test, samples=samples, ppc=True, progressbar=progressbar
    )
    previous_time = timer("T model", previous_time)

    print("\nRunning BEST model")
    trace_best = pyfolio_instance.run_model(
        "best", df_train, returns_test=df_test, samples=samples, progressbar=progressbar
    )
    previous_time = timer("BEST model", previous_time)

    fig = plt.figure(figsize=(14, 10 * 2))
    gs = gridspec.GridSpec(9, 2, wspace=0.3, hspace=0.3)

    axs = []
    row = 0

    ax_cone = fig.add_subplot(gs[row, :])
    pyfolio_instance.plot_bayes_cone(df_train, df_test, ppc_t, ax=ax_cone)
    previous_time = timer("plotting Bayesian cone", previous_time)

    row += 1
    axs.append(fig.add_subplot(gs[row, 0]))
    axs.append(fig.add_subplot(gs[row, 1]))
    row += 1
    axs.append(fig.add_subplot(gs[row, 0]))
    axs.append(fig.add_subplot(gs[row, 1]))
    row += 1
    axs.append(fig.add_subplot(gs[row, 0]))
    axs.append(fig.add_subplot(gs[row, 1]))
    row += 1
    axs.append(fig.add_subplot(gs[row, :]))

    pyfolio_instance.plot_best(trace=trace_best, axs=axs)
    previous_time = timer("plotting BEST results", previous_time)

    row += 1
    ax_ret_pred_day = fig.add_subplot(gs[row, 0])
    ax_ret_pred_week = fig.add_subplot(gs[row, 1])
    day_pred = ppc_t[:, 0]
    p5 = stats.scoreatpercentile(day_pred, 5)
    sns.histplot(day_pred, ax=ax_ret_pred_day)
    ax_ret_pred_day.axvline(p5, linestyle="--", linewidth=3.0)
    ax_ret_pred_day.set_xlabel("Predicted returns 1 day")
    ax_ret_pred_day.set_ylabel("Frequency")
    ax_ret_pred_day.text(
        0.4,
        0.9,
        "Bayesian VaR = %.2f" % p5,
        verticalalignment="bottom",
        horizontalalignment="right",
        transform=ax_ret_pred_day.transAxes,
    )
    previous_time = timer("computing Bayesian predictions", previous_time)

    week_pred = (np.cumprod(ppc_t[:, :5] + 1, 1) - 1)[:, -1]
    p5 = stats.scoreatpercentile(week_pred, 5)
    sns.histplot(week_pred, ax=ax_ret_pred_week)
    ax_ret_pred_week.axvline(p5, linestyle="--", linewidth=3.0)
    ax_ret_pred_week.set_xlabel("Predicted cum returns 5 days")
    ax_ret_pred_week.set_ylabel("Frequency")
    ax_ret_pred_week.text(
        0.4,
        0.9,
        "Bayesian VaR = %.2f" % p5,
        verticalalignment="bottom",
        horizontalalignment="right",
        transform=ax_ret_pred_week.transAxes,
    )
    previous_time = timer("plotting Bayesian VaRs estimate", previous_time)

    if benchmark_rets is not None:
        print("\nRunning alpha beta model")
        benchmark_rets = benchmark_rets.loc[df_train.index]
        trace_alpha_beta = pyfolio_instance.run_model(
            "alpha_beta", df_train, bmark=benchmark_rets, samples=samples, progressbar=progressbar
        )
        previous_time = timer("running alpha beta model", previous_time)

        row += 1
        ax_alpha = fig.add_subplot(gs[row, 0])
        ax_beta = fig.add_subplot(gs[row, 1])
        sns.histplot((1 + trace_alpha_beta["alpha"][100:]) ** 252 - 1, ax=ax_alpha)
        sns.histplot(trace_alpha_beta["beta"][100:], ax=ax_beta)
        ax_alpha.set_xlabel("Annual Alpha")
        ax_alpha.set_ylabel("Belief")
        ax_beta.set_xlabel("Beta")
        ax_beta.set_ylabel("Belief")
        previous_time = timer("plotting alpha beta model", previous_time)

    if stoch_vol:
        returns_cutoff = 400
        print(f"\nRunning stochastic volatility model on most recent {returns_cutoff} days of returns.")
        df_train_truncated = df_train[-returns_cutoff:] if df_train.size > returns_cutoff else df_train
        _, trace_stoch_vol = pyfolio_instance.model_stoch_vol(df_train_truncated)
        previous_time = timer("running stochastic volatility model", previous_time)

        row += 1
        ax_volatility = fig.add_subplot(gs[row, :])
        pyfolio_instance.plot_stoch_vol(df_train_truncated, trace=trace_stoch_vol, ax=ax_volatility)
        previous_time = timer("plotting stochastic volatility model", previous_time)

    total_time = time.time() - start_time
    print(f"\nTotal runtime was {total_time:.2f} seconds.")

    gs.tight_layout(fig)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


# # Risk tear sheet
# ==============
def create_risk_tear_sheet(
    pyfolio_instance,
    positions,
    style_factor_panel=None,
    sectors=None,
    caps=None,
    shares_held=None,
    volumes=None,
    percentile=None,
    returns=None,
    transactions=None,
    estimate_intraday="infer",
    run_flask_app=False,
):
    """
    Creates risk tear sheet.
    """
    positions = check_intraday(estimate_intraday, returns, positions, transactions)

    # Align inputs on the overlapping time index. Most upstream implementations
    # expect these inputs to be time-indexed.
    idx = positions.index
    if style_factor_panel is not None:
        for df in style_factor_panel.values():
            idx = idx.intersection(df.index)
    for maybe_panel in (sectors, caps, shares_held, volumes):
        if maybe_panel is not None:
            idx = idx.intersection(maybe_panel.index)

    if len(idx) == 0:
        warnings.warn("No overlapping index across risk tear sheet inputs; nothing to plot.", UserWarning, stacklevel=2)
        return None

    positions = positions.loc[idx]
    if style_factor_panel is not None:
        style_factor_panel = {k: v.loc[idx] for k, v in style_factor_panel.items()}
    if sectors is not None:
        sectors = sectors.loc[idx]
    if caps is not None:
        caps = caps.loc[idx]
    if shares_held is not None:
        shares_held = shares_held.loc[idx]  # pragma: no cover -- Edge case
    if volumes is not None:
        volumes = volumes.loc[idx]

    if percentile is None:
        percentile = 0.1

    vertical_sections = 0
    if style_factor_panel is not None:
        vertical_sections += len(style_factor_panel)
    if sectors is not None:
        vertical_sections += 4
    if caps is not None:
        vertical_sections += 4
    if volumes is not None:
        vertical_sections += 3

    if vertical_sections == 0:
        raise ValueError(
            "create_risk_tear_sheet requires at least one of style_factor_panel, sectors, caps, or volumes."
        )

    fig = plt.figure(figsize=[14, vertical_sections * 6])
    gs = gridspec.GridSpec(vertical_sections, 3, wspace=0.5, hspace=0.5)

    row = 0
    sharex_ax = None

    if style_factor_panel is not None:
        style_axes = []
        for k in range(len(style_factor_panel)):
            ax = fig.add_subplot(gs[row + k, :], sharex=style_axes[0] if k > 0 else None)
            style_axes.append(ax)

        for j, (name, df) in enumerate(style_factor_panel.items()):
            sfe = pyfolio_instance.compute_style_factor_exposures(positions, df)
            pyfolio_instance.plot_style_factor_exposures(sfe, name, style_axes[j])

        sharex_ax = style_axes[0]
        row += len(style_factor_panel)

    if sectors is not None:
        ax_sector_longshort = fig.add_subplot(gs[row : row + 2, :], sharex=sharex_ax)
        ax_sector_gross = fig.add_subplot(gs[row + 2, :], sharex=sharex_ax or ax_sector_longshort)
        ax_sector_net = fig.add_subplot(gs[row + 3, :], sharex=sharex_ax or ax_sector_longshort)
        long_exposures, short_exposures, gross_exposures, net_exposures = pyfolio_instance.compute_sector_exposures(
            positions, sectors
        )
        pyfolio_instance.plot_sector_exposures_longshort(long_exposures, short_exposures, ax=ax_sector_longshort)
        pyfolio_instance.plot_sector_exposures_gross(gross_exposures, ax=ax_sector_gross)
        pyfolio_instance.plot_sector_exposures_net(net_exposures, ax=ax_sector_net)
        sharex_ax = sharex_ax or ax_sector_longshort
        row += 4

    if caps is not None:
        ax_cap_longshort = fig.add_subplot(gs[row : row + 2, :], sharex=sharex_ax)
        ax_cap_gross = fig.add_subplot(gs[row + 2, :], sharex=sharex_ax or ax_cap_longshort)
        ax_cap_net = fig.add_subplot(gs[row + 3, :], sharex=sharex_ax or ax_cap_longshort)
        long_exposures, short_exposures, gross_exposures, net_exposures = pyfolio_instance.compute_cap_exposures(
            positions, caps
        )
        pyfolio_instance.plot_cap_exposures_longshort(long_exposures, short_exposures, ax_cap_longshort)
        pyfolio_instance.plot_cap_exposures_gross(gross_exposures, ax_cap_gross)
        pyfolio_instance.plot_cap_exposures_net(net_exposures, ax_cap_net)
        sharex_ax = sharex_ax or ax_cap_longshort
        row += 4

    if volumes is not None:
        ax_vol_longshort = fig.add_subplot(gs[row : row + 2, :], sharex=sharex_ax)
        ax_vol_gross = fig.add_subplot(gs[row + 2, :], sharex=sharex_ax or ax_vol_longshort)
        longed_threshold, shorted_threshold, grossed_threshold = pyfolio_instance.compute_volume_exposures(
            positions, volumes, percentile
        )
        pyfolio_instance.plot_volume_exposures_longshort(
            longed_threshold, shorted_threshold, percentile, ax_vol_longshort
        )
        pyfolio_instance.plot_volume_exposures_gross(grossed_threshold, percentile, ax_vol_gross)

    for ax in fig.axes:
        plt.setp(ax.get_xticklabels(), visible=True)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None


def create_perf_attrib_tear_sheet(
    pyfolio_instance,
    returns,
    positions,
    factor_returns,
    factor_loadings,
    transactions=None,
    pos_in_dollars=True,
    run_flask_app=False,
    factor_partitions=FACTOR_PARTITIONS,
):
    """
    Generate plots and tables for analyzing a strategy's performance.
    """
    portfolio_exposures, perf_attrib_data = pyfolio_instance.perf_attrib(
        returns, positions, factor_returns, factor_loadings, transactions, pos_in_dollars=pos_in_dollars
    )

    display(Markdown("## Performance Relative to Common Risk Factors"))

    pyfolio_instance.show_perf_attrib_stats(
        returns, positions, factor_returns, factor_loadings, transactions, pos_in_dollars
    )

    num_partitions = len(factor_partitions) if factor_partitions else 1
    vertical_sections = 1 + 2 * max(num_partitions, 1)
    current_section = 0

    fig = plt.figure(figsize=[14, vertical_sections * 6])

    gs = gridspec.GridSpec(vertical_sections, 1, wspace=0.5, hspace=0.5)

    pyfolio_instance.plot_perf_attrib_returns(perf_attrib_data, ax=fig.add_subplot(gs[current_section]))
    current_section += 1

    if factor_partitions is not None:
        for factor_type, partitions in factor_partitions.items():
            columns_to_select = perf_attrib_data.columns.intersection(partitions)

            pyfolio_instance.plot_factor_contribution_to_perf(
                perf_attrib_data[columns_to_select],
                ax=fig.add_subplot(gs[current_section]),
                title=f"Cumulative common {factor_type} returns attribution",
            )
            current_section += 1

        for factor_type, partitions in factor_partitions.items():
            pyfolio_instance.plot_risk_exposures(
                portfolio_exposures[portfolio_exposures.columns.intersection(partitions)],
                ax=fig.add_subplot(gs[current_section]),
                title=f"Daily {factor_type} factor exposures",
            )
            current_section += 1
    else:
        pyfolio_instance.plot_factor_contribution_to_perf(perf_attrib_data, ax=fig.add_subplot(gs[current_section]))
        current_section += 1

        pyfolio_instance.plot_risk_exposures(portfolio_exposures, ax=fig.add_subplot(gs[current_section]))

    gs.tight_layout(fig)

    if run_flask_app:
        return fig  # pragma: no cover -- Flask app mode
    return None
