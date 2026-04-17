#
# Copyright 2016 Quantopian, Inc.
# Copyright 2025 CloudQuant Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Round-trip trade metrics."""

import logging
from collections import deque

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "add_closing_transactions",
    "agg_all_long_short",
    "apply_sector_mappings_to_round_trips",
    "extract_round_trips",
    "gen_round_trip_stats",
    "groupby_consecutive",
]

_DEFAULT_MAX_DELTA = pd.Timedelta("8h")


def agg_all_long_short(
    round_trips: pd.DataFrame,
    col: str,
    stats_dict: dict,
    group_aware_stats: dict | None = None,
) -> pd.DataFrame:
    """Aggregate statistics for long and short round trips.

    Computes statistics separately for long trades, short trades, and
    all trades combined.

    Parameters
    ----------
    round_trips : pd.DataFrame
        DataFrame with one row per round-trip trade.
    col : str
        Column name to compute statistics on (e.g., 'pnl', 'duration').
    stats_dict : dict
        Dictionary mapping statistic names to functions or method names.
    group_aware_stats : dict, optional
        Optional dict of stats that receive (data, group) instead of just data.
        Used when stats need full group context (e.g. open_dt/close_dt for
        calendar span). Applied only when col has matching data.

    Returns
    -------
    pd.DataFrame
        DataFrame with statistics for 'All trades', 'long', and 'short'.
    """
    stats_all = []
    stats_long_short = []
    group_aware = group_aware_stats or {}

    for kind, group in round_trips.groupby("long"):
        label = "long" if kind else "short"

        stat = {}
        data = group[col]

        for name, func in stats_dict.items():
            try:
                if callable(func):
                    stat[name] = func(data)
                elif isinstance(func, str):
                    # Handle string method names like 'mean', 'sum', etc.
                    stat[name] = getattr(data, func)()
                else:
                    stat[name] = np.nan
            except (ValueError, TypeError, ZeroDivisionError, AttributeError) as e:
                logger.debug("round_trip stat %s failed for %s: %s", name, label, e)
                stat[name] = np.nan

        for name, func in group_aware.items():
            try:
                if callable(func):
                    stat[name] = func(data, group)
                else:
                    stat[name] = np.nan
            except (ValueError, TypeError, ZeroDivisionError, AttributeError) as e:
                logger.debug("round_trip group stat %s failed for %s: %s", name, label, e)
                stat[name] = np.nan

        stat_series = pd.Series(stat, name=label)
        stats_long_short.append(stat_series)

    # Compute 'All' statistics
    all_data = round_trips[col]
    all_stat = {}
    for name, func in stats_dict.items():
        try:
            if callable(func):
                all_stat[name] = func(all_data)
            elif isinstance(func, str):
                all_stat[name] = getattr(all_data, func)()
            else:
                all_stat[name] = np.nan
        except (ValueError, TypeError, ZeroDivisionError, AttributeError) as e:
            logger.debug("round_trip stat %s failed for All trades: %s", name, e)
            all_stat[name] = np.nan

    for name, func in group_aware.items():
        try:
            if callable(func):
                all_stat[name] = func(all_data, round_trips)
            else:
                all_stat[name] = np.nan
        except (ValueError, TypeError, ZeroDivisionError, AttributeError) as e:
            logger.debug("round_trip group stat %s failed for All trades: %s", name, e)
            all_stat[name] = np.nan

    all_series = pd.Series(all_stat, name="All trades")
    stats_all.append(all_series)

    # Combine into DataFrame
    df_long_short = pd.concat(stats_long_short, axis=1).T if stats_long_short else pd.DataFrame()

    df_all = pd.concat(stats_all, axis=1).T

    return pd.concat([df_all, df_long_short], axis=0)


def groupby_consecutive(txn, max_delta=_DEFAULT_MAX_DELTA):
    """Merge transactions of the same direction separated by less than max_delta time duration.

    Parameters
    ----------
    txn : pd.DataFrame
        Prices and amounts of executed round_trips. One row per trade.
    max_delta : pandas.Timedelta (optional)
        Merge transactions in the same direction separated by less
        than max_delta time duration.

    Returns
    -------
    transactions : pd.DataFrame
    """
    import warnings

    import numpy as np

    def vwap(transaction):
        """Calculate volume-weighted average price for a transaction.

        Parameters
        ----------
        transaction : pd.DataFrame
            Transaction data with 'amount' and 'price' columns.

        Returns
        -------
        float
            Volume-weighted average price.
        """
        if transaction.amount.sum() == 0:
            warnings.warn("Zero transacted shares, setting vwap to nan.", stacklevel=3)
            return np.nan
        return (transaction.amount * transaction.price).sum() / transaction.amount.sum()

    out = []
    for sym, t in txn.groupby("symbol"):
        t = t.sort_index()
        t.index.name = "dt"
        t.index = pd.to_datetime(t.index)
        t = t.reset_index()

        t["order_sign"] = t.amount > 0
        t["block_dir"] = (t.order_sign.shift(1) != t.order_sign).astype(int).cumsum()
        t["block_time"] = ((t.dt - t.dt.shift(1)) > max_delta).astype(int).cumsum()
        grouped_price = t.groupby(["block_dir", "block_time"])[["amount", "price"]].apply(vwap)
        grouped_price.name = "price"
        grouped_rest = t.groupby(["block_dir", "block_time"]).agg({"amount": "sum", "symbol": "first", "dt": "first"})

        grouped = grouped_rest.join(grouped_price)

        out.append(grouped)

    out = pd.concat(out)
    return out.set_index("dt")


def extract_round_trips(transactions, portfolio_value=None):
    """Group transactions into "round trips".

    First, transactions are grouped by day and directionality. Then, long and short
    transactions are matched to create round-trip round_trips for which
    PnL, duration and returns are computed. Crossings where a position
    changes from long to short and vice versa are handled correctly.

    Under the hood, we reconstruct the individual shares in a
    portfolio over time and match round_trips in a FIFO order.

    Parameters
    ----------
    transactions : pd.DataFrame
        Prices and amounts of executed round_trips. One row per trade.

    portfolio_value : pd.Series (optional)
        Portfolio value (all net assets including cash) over time.

    Returns
    -------
    round_trips : pd.DataFrame:
        DataFrame with one row per round trip.
    """
    import warnings

    transactions = groupby_consecutive(transactions)
    roundtrips = []

    for sym, trans_sym in transactions.groupby("symbol"):
        trans_sym = trans_sym.sort_index()
        # Use quantity-based stack: (price, qty, dt) instead of expanding individual shares
        qty_stack = deque()  # deque of (signed_price, quantity, dt)
        for row in trans_sym.itertuples():
            dt = row.Index
            if row.price < 0:
                warnings.warn("Negative price detected, ignoring for round-trip.", stacklevel=2)
                continue

            signed_price = row.price * np.sign(row.amount)
            remaining = abs(row.amount)
            if (len(qty_stack) == 0) or (np.copysign(1, qty_stack[-1][0]) == np.copysign(1, row.amount)):
                qty_stack.append((signed_price, remaining, dt))
            else:
                # Close round-trip(s)
                pnl = 0.0
                invested = 0.0
                first_open_dt = None

                while (
                    remaining > 0
                    and len(qty_stack) > 0
                    and (np.copysign(1, qty_stack[0][0]) != np.copysign(1, signed_price))
                ):
                    prev_price, prev_qty, prev_dt = qty_stack[0]
                    if first_open_dt is None:
                        first_open_dt = prev_dt
                    matched = min(remaining, prev_qty)
                    pnl += -(signed_price + prev_price) * matched
                    invested += abs(prev_price) * matched
                    remaining -= matched
                    if matched == prev_qty:
                        qty_stack.popleft()
                    else:
                        qty_stack[0] = (prev_price, prev_qty - matched, prev_dt)

                if first_open_dt is not None:
                    roundtrips.append(
                        {
                            "pnl": pnl,
                            "open_dt": first_open_dt,
                            "close_dt": dt,
                            "long": signed_price < 0,
                            "rt_returns": pnl / invested if invested != 0 else 0,
                            "symbol": sym,
                        }
                    )

                # Push leftover onto stack
                if remaining > 0:
                    qty_stack.append((signed_price, remaining, dt))

    roundtrips = pd.DataFrame(roundtrips)

    if len(roundtrips) == 0:
        return roundtrips

    roundtrips["duration"] = roundtrips["close_dt"].sub(roundtrips["open_dt"])

    if portfolio_value is not None:
        # Need to normalize so that we can join
        pv = pd.DataFrame(
            portfolio_value,
            columns=["portfolio_value"],
        ).assign(date=portfolio_value.index)

        roundtrips["date"] = roundtrips.close_dt.apply(lambda close_dt: close_dt.replace(hour=0, minute=0, second=0))
        # Convert 'roundtrips.date' to UTC to match 'portfolio_value.index'
        if pv.index.tz is not None:
            # Only localize if not already tz-aware
            if roundtrips["date"].dt.tz is None:
                roundtrips["date"] = roundtrips["date"].dt.tz_localize("UTC")
            else:
                roundtrips["date"] = roundtrips["date"].dt.tz_convert("UTC")

        tmp = roundtrips.join(pv, on="date", lsuffix="_")

        roundtrips["returns"] = tmp.pnl / tmp.portfolio_value
        roundtrips = roundtrips.drop("date", axis="columns")

    return roundtrips


def add_closing_transactions(positions, transactions):
    """Append transactions that close out all positions at the end of the timespan.

    Utilizes pricing information in the positions DataFrame to determine closing price.

    Parameters
    ----------
    positions : pd.DataFrame
        The positions that the strategy takes over time.
    transactions : pd.DataFrame
        Prices and amounts of executed round_trips. One row per trade.

    Returns
    -------
    pd.DataFrame
        Transactions with closing transactions appended.
    """
    closed_txns = transactions[["symbol", "amount", "price"]]

    pos_at_end = positions.drop("cash", axis=1).iloc[-1]
    open_pos = pos_at_end.replace(0, np.nan).dropna()
    # Add closing transactions one second after the close to be sure
    # they don't conflict with other transactions executed at that time.
    end_dt = open_pos.name + pd.Timedelta(seconds=1)

    for sym, ending_val in open_pos.items():
        txn_sym = transactions[transactions.symbol == sym]

        ending_amount = txn_sym.amount.sum()

        if abs(ending_amount) < 1e-6:
            continue

        ending_price = ending_val / ending_amount
        closing_txn = {
            "symbol": sym,
            "amount": -ending_amount,
            "price": ending_price,
        }

        closing_txn = pd.DataFrame(closing_txn, index=[end_dt])
        closed_txns = pd.concat([closed_txns, closing_txn], ignore_index=False)

    return closed_txns[closed_txns.amount != 0]


def apply_sector_mappings_to_round_trips(round_trips, sector_mappings):
    """Translate round trip symbols to sectors.

    Parameters
    ----------
    round_trips : pd.DataFrame
        DataFrame with one row per-round-trip trade.
    sector_mappings : dict or pd.Series
        Mapping from symbol to sector.

    Returns
    -------
    pd.DataFrame
        A copy of round_trips with an additional 'sector' column.
    """
    round_trips = round_trips.copy()

    if "symbol" in round_trips.columns:
        round_trips["sector"] = round_trips["symbol"].map(sector_mappings)

    return round_trips


def gen_round_trip_stats(round_trips: pd.DataFrame) -> dict:
    """Generate various round-trip statistics.

    Parameters
    ----------
    round_trips : pd.DataFrame
        DataFrame with one row per-round-trip trade.

    Returns
    -------
    dict
        A dictionary where each value is a pandas DataFrame containing
        various round-trip statistics.
    """
    from fincore.constants.style import (
        DURATION_STATS,
        DURATION_STATS_GROUP,
        PNL_STATS,
        RETURN_STATS,
        SUMMARY_STATS,
    )

    if len(round_trips) == 0:
        return {
            "pnl": pd.DataFrame(),
            "summary": pd.DataFrame(),
            "duration": pd.DataFrame(),
            "returns": pd.DataFrame(),
            "symbols": pd.DataFrame(),
        }

    # Helper function to apply custom and built-in functions
    def apply_custom_and_built_in_funcs(grouped, stats_dict):
        """Apply custom and built-in aggregation functions to grouped data.

        Parameters
        ----------
        grouped : pd.core.groupby.GroupBy
            Grouped data to aggregate.
        stats_dict : dict
            Dictionary mapping stat names to either callables (custom functions)
            or strings (built-in aggregation functions).

        Returns
        -------
        pd.DataFrame
            Aggregated results.
        """
        # Separate custom functions from built-in functions
        custom_funcs = {k: v for k, v in stats_dict.items() if callable(v)}
        built_in_funcs = [v for k, v in stats_dict.items() if not callable(v)]

        # Apply custom functions manually
        custom_results = {}
        for func_name, func in custom_funcs.items():
            custom_results[func_name] = grouped.apply(func)
        custom_results = pd.DataFrame(custom_results)

        # Apply built-in functions
        if built_in_funcs:
            built_in_results = grouped.agg(built_in_funcs)
            # Combine results
            return pd.concat([custom_results, built_in_results], axis=1)
        return custom_results  # pragma: no cover -- Edge case when no built-in funcs

    # Check if 'returns' column exists, if not use 'rt_returns'
    returns_col = "returns" if "returns" in round_trips.columns else "rt_returns"

    # Generate statistics for pnl, summary, duration, and returns
    return {
        "pnl": agg_all_long_short(round_trips, "pnl", PNL_STATS),
        "summary": agg_all_long_short(round_trips, "pnl", SUMMARY_STATS),
        "duration": agg_all_long_short(round_trips, "duration", DURATION_STATS, group_aware_stats=DURATION_STATS_GROUP),
        "returns": agg_all_long_short(round_trips, returns_col, RETURN_STATS),
        "symbols": apply_custom_and_built_in_funcs(round_trips.groupby("symbol")[returns_col], RETURN_STATS).T,
    }
