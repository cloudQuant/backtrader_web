"""Statistics computation engine for strategy reports.

Computes all metrics, time-series data, and summary text needed by the
HTML / PDF renderers.  This module has **no** rendering logic.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

import numpy as np
import pandas as pd

__all__ = ["compute_sections"]


# Module-level logger
logger = logging.getLogger(__name__)


def _compute_core_perf(Empyrical, returns, benchmark_rets, positions, transactions):
    """Compute core performance statistics."""
    perf = OrderedDict()
    perf["Annual Return"] = Empyrical.annual_return(returns)
    perf["Cumulative Returns"] = Empyrical.cum_returns_final(returns)
    perf["Annual Volatility"] = Empyrical.annual_volatility(returns)
    perf["Sharpe Ratio"] = Empyrical.sharpe_ratio(returns)
    perf["Calmar Ratio"] = Empyrical.calmar_ratio(returns)
    perf["Stability"] = Empyrical.stability_of_timeseries(returns)
    perf["Max Drawdown"] = Empyrical.max_drawdown(returns)
    perf["Omega Ratio"] = Empyrical.omega_ratio(returns)
    perf["Sortino Ratio"] = Empyrical.sortino_ratio(returns)
    perf["Skew"] = Empyrical.skewness(returns)
    perf["Kurtosis"] = Empyrical.kurtosis(returns)
    perf["Tail Ratio"] = Empyrical.tail_ratio(returns)
    perf["Daily Value at Risk"] = Empyrical.value_at_risk(returns)
    perf["Downside Risk"] = Empyrical.downside_risk(returns)

    perf["Daily Mean Return"] = float(np.nanmean(returns))
    perf["Daily Std Return"] = float(np.nanstd(returns, ddof=1))
    perf["Best Day"] = float(returns.max())
    perf["Worst Day"] = float(returns.min())

    if benchmark_rets is not None:
        a, b = Empyrical.alpha_beta(returns, benchmark_rets)
        perf["Alpha"] = a
        perf["Beta"] = b

    if positions is not None and transactions is not None:
        try:
            turnover = Empyrical.get_turnover(positions, transactions)
            perf["Avg Daily Turnover"] = float(turnover.mean())
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
            logger.warning("Failed to calculate turnover: %s", e)

    if positions is not None:
        try:
            gl = Empyrical.gross_lev(positions)
            perf["Avg Gross Leverage"] = float(gl.mean())
            perf["Max Gross Leverage"] = float(gl.max())
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
            logger.warning("Failed to calculate gross leverage: %s", e)

    return perf


def _compute_extended_stats(Empyrical, returns):
    """Compute extended strategy statistics."""
    ext = OrderedDict()
    emp = Empyrical(returns=returns)
    ext["Win Rate (daily)"] = emp.win_rate()
    ext["Loss Rate (daily)"] = emp.loss_rate()
    ext["Serial Correlation"] = emp.serial_correlation()
    ext["Common Sense Ratio"] = emp.common_sense_ratio()
    ext["Sterling Ratio"] = emp.sterling_ratio()
    ext["Burke Ratio"] = emp.burke_ratio()
    ext["Kappa Three Ratio"] = emp.kappa_three_ratio()
    ext["Max Drawdown Days"] = emp.max_drawdown_days()
    ext["Max Drawdown Recovery Days"] = emp.max_drawdown_recovery_days()
    ext["2nd Max Drawdown"] = emp.second_max_drawdown()
    ext["3rd Max Drawdown"] = emp.third_max_drawdown()
    ext["Max Consecutive Up Days"] = Empyrical.max_consecutive_up_days(returns)
    ext["Max Consecutive Down Days"] = Empyrical.max_consecutive_down_days(returns)
    ext["Max Single Day Gain"] = Empyrical.max_single_day_gain(returns)
    ext["Max Single Day Loss"] = Empyrical.max_single_day_loss(returns)
    ext["Hurst Exponent"] = Empyrical.hurst_exponent(returns)
    return ext


def _compute_time_series(Empyrical, returns, rolling_window):
    """Compute time-series data for charts."""
    ts = {}
    ts["returns"] = returns
    ts["cum_returns"] = Empyrical.cum_returns(returns, starting_value=1.0)
    cum_ret_0 = Empyrical.cum_returns(returns, starting_value=0)
    running_max = (1 + cum_ret_0).cummax()
    ts["drawdown"] = (1 + cum_ret_0) / running_max - 1
    ts["rolling_sharpe"] = Empyrical.rolling_sharpe(returns, rolling_sharpe_window=rolling_window)
    ts["rolling_volatility"] = Empyrical.rolling_volatility(returns, rolling_vol_window=rolling_window)
    ts["dd_table"] = Empyrical.gen_drawdown_table(returns, top=5)

    ts["yearly_stats"] = pd.DataFrame(
        {
            "Annual Return": Empyrical.annual_return_by_year(returns),
            "Sharpe Ratio": Empyrical.sharpe_ratio_by_year(returns),
            "Max Drawdown": Empyrical.max_drawdown_by_year(returns),
        }
    )
    ts["monthly_returns"] = Empyrical.aggregate_returns(returns, "monthly")
    monthly_rets = ts["monthly_returns"]
    ts["best_month"] = float(monthly_rets.max())
    ts["worst_month"] = float(monthly_rets.min())
    ts["avg_month"] = float(monthly_rets.mean())
    yearly_rets = Empyrical.aggregate_returns(returns, "yearly")
    ts["best_year"] = float(yearly_rets.max())
    ts["worst_year"] = float(yearly_rets.min())
    ts["return_quantiles"] = returns.quantile([0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
    return ts


def _compute_benchmark(Empyrical, returns, benchmark_rets, perf, rolling_window):
    """Compute benchmark comparison stats."""
    bm = OrderedDict()
    bm["Alpha"] = perf["Alpha"]
    bm["Beta"] = perf["Beta"]
    bm["Information Ratio"] = Empyrical.information_ratio(returns, benchmark_rets)
    bm["Tracking Error"] = Empyrical.tracking_error(returns, benchmark_rets)
    bm["Up Capture"] = Empyrical.up_capture(returns, benchmark_rets)
    bm["Down Capture"] = Empyrical.down_capture(returns, benchmark_rets)
    bm["Capture Ratio"] = bm["Up Capture"] / bm["Down Capture"] if bm["Down Capture"] != 0 else np.nan
    bm["Correlation"] = float(returns.corr(benchmark_rets))
    return {
        "benchmark_stats": bm,
        "benchmark_cum": Empyrical.cum_returns(benchmark_rets, starting_value=1.0),
        "rolling_beta": Empyrical.rolling_beta(returns, benchmark_rets, rolling_window=rolling_window),
    }


def _compute_positions(positions):
    """Compute position analysis."""
    s = {"has_positions": True}
    pos_no_cash = positions.drop("cash", axis=1, errors="ignore")
    s["positions"] = positions
    s["pos_no_cash"] = pos_no_cash
    s["pos_long"] = pos_no_cash.where(pos_no_cash > 0, 0).sum(axis=1)
    s["pos_short"] = pos_no_cash.where(pos_no_cash < 0, 0).sum(axis=1)
    total = positions.sum(axis=1).replace(0, np.nan)
    exposure = pos_no_cash.abs().sum(axis=1)
    s["gross_leverage"] = (exposure / total).replace([np.inf, -np.inf], np.nan)

    pos_abs = pos_no_cash.abs()
    pos_total = pos_abs.sum(axis=1).replace(0, np.nan)
    pos_pct = pos_abs.div(pos_total, axis=0).fillna(0)
    s["pos_max_concentration"] = pos_pct.max(axis=1)
    s["pos_median_concentration"] = pos_pct.median(axis=1)
    s["pos_alloc"] = pos_no_cash.div(total, axis=0).fillna(0)

    pos_summary = OrderedDict()
    pos_summary["Avg Gross Leverage"] = s["gross_leverage"].mean()
    pos_summary["Max Gross Leverage"] = s["gross_leverage"].max()
    pos_summary["Avg Long Exposure"] = s["pos_long"].mean()
    pos_summary["Avg Short Exposure"] = s["pos_short"].mean()
    pos_summary["Avg Max Position Concentration"] = s["pos_max_concentration"].mean()
    pos_summary["Number of Assets"] = len(pos_no_cash.columns)
    s["position_summary"] = pos_summary
    return s


def _compute_transactions(Empyrical, transactions, positions):
    """Compute transaction analysis."""
    s = {"has_transactions": True}
    txn = transactions.copy()
    txn_norm = txn.copy()
    txn_norm.index = txn_norm.index.normalize()
    s["daily_txn_count"] = txn_norm.groupby(txn_norm.index).size()
    s["daily_txn_value"] = (txn_norm["amount"].abs() * txn_norm["price"]).groupby(txn_norm.index).sum()

    if hasattr(txn.index, "hour"):
        s["txn_hours"] = txn.index.hour

    if positions is not None:
        try:
            s["turnover"] = Empyrical.get_turnover(positions, transactions)
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
            logger.warning("Failed to calculate turnover from transactions: %s", e)

    txn_summary = OrderedDict()
    txn_summary["Total Transactions"] = len(transactions)
    txn_summary["Total Transaction Days"] = len(s["daily_txn_count"])
    txn_summary["Avg Daily Trades"] = float(s["daily_txn_count"].mean())
    txn_summary["Max Daily Trades"] = int(s["daily_txn_count"].max())
    txn_summary["Avg Daily Volume"] = float(s["daily_txn_value"].mean())
    txn_summary["Max Daily Volume"] = float(s["daily_txn_value"].max())
    if "symbol" in transactions.columns:
        txn_summary["Unique Symbols Traded"] = int(transactions["symbol"].nunique())
    s["txn_summary"] = txn_summary
    return s


def _compute_trades(trades):
    """Compute trade-level statistics."""
    s = {}
    ts = OrderedDict()
    n_trades = len(trades)
    winners = trades[trades["pnlcomm"] > 0]
    losers = trades[trades["pnlcomm"] <= 0]
    n_win = len(winners)
    n_loss = len(losers)

    ts["Total Trades"] = n_trades
    ts["Winning Trades"] = n_win
    ts["Losing Trades"] = n_loss
    ts["Win Rate"] = n_win / n_trades if n_trades > 0 else 0
    ts["Total PnL"] = float(trades["pnlcomm"].sum())
    ts["Avg PnL per Trade"] = float(trades["pnlcomm"].mean())
    ts["Median PnL per Trade"] = float(trades["pnlcomm"].median())
    ts["PnL Std Dev"] = float(trades["pnlcomm"].std())
    ts["Avg Win"] = float(winners["pnlcomm"].mean()) if n_win > 0 else 0
    ts["Avg Loss"] = float(losers["pnlcomm"].mean()) if n_loss > 0 else 0
    ts["Max Win"] = float(winners["pnlcomm"].max()) if n_win > 0 else 0
    ts["Max Loss"] = float(losers["pnlcomm"].min()) if n_loss > 0 else 0
    avg_loss = ts["Avg Loss"]
    ts["Profit/Loss Ratio"] = abs(ts["Avg Win"] / avg_loss) if avg_loss != 0 else np.nan
    ts["Expectancy"] = ts["Win Rate"] * ts["Avg Win"] + (1 - ts["Win Rate"]) * ts["Avg Loss"]

    if "commission" in trades.columns:
        ts["Total Commission"] = float(trades["commission"].sum())
        ts["Avg Commission per Trade"] = float(trades["commission"].mean())

    if "long" in trades.columns:
        long_mask = trades["long"] == 1
        short_mask = ~long_mask
        ts["Long Trades"] = int(long_mask.sum())
        ts["Short Trades"] = int(short_mask.sum())
        if long_mask.sum() > 0:
            long_trades = trades[long_mask]
            ts["Long Win Rate"] = float((long_trades["pnlcomm"] > 0).sum() / len(long_trades))
            ts["Long Avg PnL"] = float(long_trades["pnlcomm"].mean())
            ts["Long Total PnL"] = float(long_trades["pnlcomm"].sum())
        if short_mask.sum() > 0:
            short_trades = trades[short_mask]
            ts["Short Win Rate"] = float((short_trades["pnlcomm"] > 0).sum() / len(short_trades))
            ts["Short Avg PnL"] = float(short_trades["pnlcomm"].mean())
            ts["Short Total PnL"] = float(short_trades["pnlcomm"].sum())

    if "barlen" in trades.columns:
        ts["Avg Holding Bars"] = float(trades["barlen"].mean())
        ts["Median Holding Bars"] = float(trades["barlen"].median())
        ts["Max Holding Bars"] = int(trades["barlen"].max())
        ts["Min Holding Bars"] = int(trades["barlen"].min())

    s["trade_stats"] = ts
    s["trade_pnl"] = trades["pnlcomm"].values
    if "long" in trades.columns:
        s["trade_pnl_long"] = trades.loc[trades["long"] == 1, "pnlcomm"].values
        s["trade_pnl_short"] = trades.loc[trades["long"] == 0, "pnlcomm"].values
    if "barlen" in trades.columns:
        s["trade_barlen"] = trades["barlen"].values
    return s


_PERIOD_DEFS = [
    ("1W", 5),
    ("1M", 21),
    ("3M", 63),
    ("6M", 126),
    ("1Y", 252),
    ("3Y", 756),
    ("5Y", 1260),
]


def _compute_period_returns(Empyrical, returns, benchmark_rets):
    """Compute period returns and win rates."""
    s = {}
    end_date = returns.index[-1]
    _tz = getattr(end_date, "tzinfo", None)
    _ytd_ts = pd.Timestamp(end_date.year, 1, 1, tz=_tz)
    ytd_mask = returns.index >= _ytd_ts

    pr = OrderedDict()
    for label, days in _PERIOD_DEFS:
        pr[label] = float(Empyrical.cum_returns_final(returns.iloc[-days:])) if len(returns) >= days else np.nan
    if ytd_mask.sum() > 0:
        pr["YTD"] = float(Empyrical.cum_returns_final(returns[ytd_mask]))
    pr["Since Inception"] = float(Empyrical.cum_returns_final(returns))
    s["period_returns"] = pr

    if benchmark_rets is not None:
        _bm_tz = getattr(benchmark_rets.index[-1], "tzinfo", None)
        _bm_ytd_ts = pd.Timestamp(end_date.year, 1, 1, tz=_bm_tz)
        bpr = OrderedDict()
        for label, days in _PERIOD_DEFS:
            bpr[label] = (
                float(Empyrical.cum_returns_final(benchmark_rets.iloc[-days:]))
                if len(benchmark_rets) >= days
                else np.nan
            )
        bm_ytd = benchmark_rets[benchmark_rets.index >= _bm_ytd_ts]
        if len(bm_ytd) > 0:
            bpr["YTD"] = float(Empyrical.cum_returns_final(bm_ytd))
        bpr["Since Inception"] = float(Empyrical.cum_returns_final(benchmark_rets))
        s["benchmark_period_returns"] = bpr

    wr = OrderedDict()
    for label, days in _PERIOD_DEFS:
        if len(returns) >= days:
            r = returns.iloc[-days:]
            wr[label] = float((r > 0).sum() / len(r))
        else:
            wr[label] = np.nan
    ytd_r = returns[ytd_mask]
    if len(ytd_r) > 0:
        wr["YTD"] = float((ytd_r > 0).sum() / len(ytd_r))
    wr["Since Inception"] = float((returns > 0).sum() / len(returns))
    s["period_win_rates"] = wr
    return s


def _perf_tag(sh):
    if np.isnan(sh):
        return "N/A"
    return "excellent" if sh > 1.5 else ("good" if sh > 1.0 else ("fair" if sh > 0.5 else "poor"))


def _risk_tag(dd):
    if np.isnan(dd):
        return "N/A"
    a = abs(dd)
    return (
        "risk control: excellent"
        if a < 0.1
        else ("risk control: good" if a < 0.2 else ("risk control: fair" if a < 0.3 else "risk control: poor"))
    )


def _compute_summary_text(perf, benchmark_rets):
    """Generate human-readable summary text."""
    _ann = perf.get("Annual Return", np.nan)
    _shp = perf.get("Sharpe Ratio", np.nan)
    _mdd = perf.get("Max Drawdown", np.nan)
    _vol = perf.get("Annual Volatility", np.nan)
    _sor = perf.get("Sortino Ratio", np.nan)
    _cal = perf.get("Calmar Ratio", np.nan)

    txt = (
        f"Over the report period, annual return is {_ann * 100:.2f}% ({_perf_tag(_shp)}). "
        f"Sharpe={_shp:.2f}, Sortino={_sor:.2f}, Calmar={_cal:.2f}. "
        f"Max drawdown={abs(_mdd) * 100:.2f}%, annual volatility={_vol * 100:.2f}%, {_risk_tag(_mdd)}."
    )
    if benchmark_rets is not None:
        _a = perf.get("Alpha", np.nan)
        _b = perf.get("Beta", np.nan)
        txt += f" Alpha={_a:.4f}, Beta={_b:.4f}."
    return txt


def compute_sections(
    returns,
    benchmark_rets,
    positions,
    transactions,
    trades,
    rolling_window,
):
    """Compute all statistics and time series needed by the report renderers.

    Returns
    -------
    dict
        A sections dictionary consumed by the HTML/PDF renderers.
    """
    from fincore import Empyrical

    sections = {}

    # ------ Basics ------
    sections["date_range"] = (
        returns.index[0].strftime("%Y-%m-%d"),
        returns.index[-1].strftime("%Y-%m-%d"),
    )
    sections["n_days"] = len(returns)
    sections["n_months"] = int(len(returns) / 21)

    # ------ Core performance ------
    perf = _compute_core_perf(Empyrical, returns, benchmark_rets, positions, transactions)
    sections["perf_stats"] = perf

    # ------ Extended stats ------
    sections["extended_stats"] = _compute_extended_stats(Empyrical, returns)

    # ------ Time series ------
    sections.update(_compute_time_series(Empyrical, returns, rolling_window))

    # ------ Benchmark ------
    if benchmark_rets is not None:
        sections.update(_compute_benchmark(Empyrical, returns, benchmark_rets, perf, rolling_window))

    # ------ Positions ------
    if positions is not None:
        sections.update(_compute_positions(positions))

    # ------ Transactions ------
    if transactions is not None:
        sections.update(_compute_transactions(Empyrical, transactions, positions))

    # ------ Trades ------
    if trades is not None and len(trades) > 0:
        sections.update(_compute_trades(trades))

    # ------ Period returns ------
    sections.update(_compute_period_returns(Empyrical, returns, benchmark_rets))

    # ------ Summary text ------
    sections["summary_text"] = _compute_summary_text(perf, benchmark_rets)

    return sections
