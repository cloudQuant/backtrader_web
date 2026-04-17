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

"""Transaction analysis functions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "adjust_returns_for_slippage",
    "apply_slippage_penalty",
    "daily_txns_with_bar_data",
    "days_to_liquidate_positions",
    "get_low_liquidity_transactions",
    "get_max_days_to_liquidate_by_ticker",
    "get_turnover",
    "get_txn_vol",
    "make_transaction_frame",
    "map_transaction",
]


def daily_txns_with_bar_data(
    transactions: pd.DataFrame,
    market_data: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Sum the absolute value of shares traded in each name on each day.

    Add columns containing the closing price and total daily volume for
    each day-ticker combination.

    Parameters
    ----------
    transactions : pd.DataFrame
        Prices and amounts of executed trades. One row per trade.
    market_data : dict
        Contains "volume" and "price" DataFrames for the tickers.

    Returns
    -------
    pd.DataFrame
        Daily totals for transacted shares in each traded name.
        Price and volume columns for close price and daily volume for
        the corresponding ticker, respectively.
    """
    transactions.index.name = "date"
    txn_daily = pd.DataFrame(
        transactions.assign(amount=abs(transactions.amount)).groupby(["symbol", pd.Grouper(freq="D")]).sum()["amount"]
    )
    txn_daily["price"] = market_data["price"].unstack()
    txn_daily["volume"] = market_data["volume"].unstack()

    return txn_daily.reset_index().set_index("date")


def days_to_liquidate_positions(
    positions: pd.DataFrame,
    market_data: dict[str, pd.DataFrame],
    max_bar_consumption: float = 0.2,
    capital_base: float = 1e6,
    mean_volume_window: int = 5,
) -> pd.DataFrame:
    """Compute the number of days required to fully liquidate each position.

    Parameters
    ----------
    positions : pd.DataFrame
        Contains daily position values including cash.
    market_data : dict
        Dict with keys 'price' and 'volume' DataFrames.
    max_bar_consumption : float
        Max proportion of a daily bar that can be consumed.
    capital_base : int
        Capital base for position value calculation.
    mean_volume_window : int
        Trailing window to use in mean volume calculation.

    Returns
    -------
    pd.DataFrame
        Number of days required to fully liquidate daily positions.
    """
    dv = market_data["volume"] * market_data["price"]
    roll_mean_dv = dv.rolling(window=mean_volume_window, center=False).mean().shift()
    roll_mean_dv = roll_mean_dv.replace(0, np.nan)

    positions_alloc = get_percent_alloc(positions)
    if "cash" in positions_alloc.columns:
        positions_alloc = positions_alloc.drop("cash", axis=1)

    days_to_liquidate = (positions_alloc * capital_base) / (max_bar_consumption * roll_mean_dv)

    return days_to_liquidate.iloc[mean_volume_window:]


def get_max_days_to_liquidate_by_ticker(
    positions: pd.DataFrame,
    market_data: dict[str, pd.DataFrame],
    max_bar_consumption: float = 0.2,
    capital_base: float = 1e6,
    mean_volume_window: int = 5,
    last_n_days: int | None = None,
) -> pd.DataFrame:
    """Find the longest estimated liquidation time for each traded name.

    Parameters
    ----------
    positions : pd.DataFrame
        Contains daily position values including cash.
    market_data : dict
        Dict with keys 'price' and 'volume' DataFrames.
    max_bar_consumption : float
        Max proportion of a daily bar that can be consumed.
    capital_base : int
        Capital base for position value calculation.
    mean_volume_window : int
        Trailing window to use in mean volume calculation.
    last_n_days : int, optional
        Compute for only the last n days.

    Returns
    -------
    pd.DataFrame
        Max number of days required to fully liquidate each traded name.
    """
    dtlp = days_to_liquidate_positions(
        positions,
        market_data,
        max_bar_consumption=max_bar_consumption,
        capital_base=capital_base,
        mean_volume_window=mean_volume_window,
    )

    if last_n_days is not None:
        dtlp = dtlp.loc[dtlp.index.max() - pd.Timedelta(days=last_n_days) :]

    pos_alloc = get_percent_alloc(positions)
    if "cash" in pos_alloc.columns:
        pos_alloc = pos_alloc.drop("cash", axis=1)

    liq_desc = pd.DataFrame()
    liq_desc["days_to_liquidate"] = dtlp.unstack()
    liq_desc["pos_alloc_pct"] = pos_alloc.unstack() * 100
    liq_desc.index = liq_desc.index.set_names(["symbol", "date"])

    return liq_desc.reset_index().sort_values("days_to_liquidate", ascending=False).groupby("symbol").first()


def get_low_liquidity_transactions(
    transactions: pd.DataFrame,
    market_data: dict[str, pd.DataFrame],
    last_n_days: int | None = None,
) -> pd.DataFrame:
    """Find the daily transaction consuming the most bar volume.

    Parameters
    ----------
    transactions : pd.DataFrame
        Prices and amounts of executed trades.
    market_data : dict
        Dict with keys 'price' and 'volume' DataFrames.
    last_n_days : int, optional
        Compute for only the last n days.

    Returns
    -------
    pd.DataFrame
        Max bar consumption per symbol.
    """
    txn_daily_w_bar = daily_txns_with_bar_data(transactions, market_data)
    txn_daily_w_bar.index.name = "date"
    txn_daily_w_bar = txn_daily_w_bar.reset_index()

    if last_n_days is not None:
        md = txn_daily_w_bar.date.max() - pd.Timedelta(days=last_n_days)
        txn_daily_w_bar = txn_daily_w_bar[txn_daily_w_bar.date > md]

    bar_consumption = txn_daily_w_bar.assign(
        max_pct_bar_consumed=(txn_daily_w_bar.amount / txn_daily_w_bar.volume) * 100
    ).sort_values("max_pct_bar_consumed", ascending=False)
    max_bar_consumption = bar_consumption.groupby("symbol").first()

    return max_bar_consumption[["date", "max_pct_bar_consumed"]]


def apply_slippage_penalty(
    returns: pd.Series,
    txn_daily: pd.DataFrame,
    simulate_starting_capital: float,
    backtest_starting_capital: float,
    impact: float = 0.1,
) -> pd.Series:
    """Apply a quadratic volume share slippage model to daily returns.

    Parameters
    ----------
    returns : pd.Series
        Time series of daily returns.
    txn_daily : pd.DataFrame
        Daily transaction totals with 'amount', 'price', 'volume' columns.
    simulate_starting_capital : int
        Capital at which we want to test.
    backtest_starting_capital : int
        Capital base at which the backtest was originally run.
    impact : float
        Scales the size of the slippage penalty.

    Returns
    -------
    pd.Series
        Slippage penalty adjusted daily returns.
    """
    from fincore.metrics.returns import cum_returns

    mult = simulate_starting_capital / backtest_starting_capital
    simulate_traded_shares = abs(mult * txn_daily.amount)
    simulate_traded_dollars = txn_daily.price * simulate_traded_shares
    simulate_pct_volume_used = simulate_traded_shares / txn_daily.volume

    penalties = simulate_pct_volume_used**2 * impact * simulate_traded_dollars

    daily_penalty = penalties.resample("D").sum()
    daily_penalty = daily_penalty.reindex(returns.index)
    daily_penalty = pd.to_numeric(daily_penalty, errors="coerce").fillna(0)

    portfolio_value = cum_returns(returns, starting_value=backtest_starting_capital)
    portfolio_value = portfolio_value * mult
    portfolio_value = portfolio_value.replace(0, np.nan)  # type: ignore[union-attr]

    adj_returns = returns - (daily_penalty / portfolio_value)
    return adj_returns.fillna(returns)


def get_percent_alloc(values: pd.DataFrame) -> pd.DataFrame:
    """Determine a portfolio's allocations.

    Delegates to :func:`fincore.metrics.positions.get_percent_alloc`.

    Parameters
    ----------
    values : pd.DataFrame
        Contains position values or amounts.

    Returns
    -------
    pd.DataFrame
        Positions and their allocations.
    """
    from fincore.metrics.positions import get_percent_alloc as _gpa

    return _gpa(values)


def map_transaction(txn: dict[str, Any]) -> dict[str, Any]:
    """Map a single transaction to a standardized format.

    Parameters
    ----------
    txn : dict
        Transaction dictionary with keys like 'amount', 'price', 'sid', 'symbol', 'dt'.

    Returns
    -------
    dict
        Standardized transaction dictionary.
    """
    return {
        "amount": txn.get("amount", 0),
        "price": txn.get("price", 0),
        "sid": txn.get("sid"),
        "symbol": txn.get("symbol", ""),
        "dt": txn.get("dt"),
    }


def make_transaction_frame(
    transactions: list[dict[str, Any]] | pd.DataFrame,
) -> pd.DataFrame:
    """Convert transactions to a DataFrame.

    Parameters
    ----------
    transactions : list of dict or pd.DataFrame
        List of transaction dictionaries or existing DataFrame.

    Returns
    -------
    pd.DataFrame
        DataFrame with transaction data indexed by datetime.
    """
    if isinstance(transactions, pd.DataFrame):
        return transactions

    txns = [map_transaction(t) for t in transactions]
    df = pd.DataFrame(txns)

    if "dt" in df.columns:
        df = df.set_index("dt")

    return df


def get_txn_vol(transactions: pd.DataFrame) -> pd.DataFrame:
    """Extract daily transaction data from a set of transaction objects.

    Parameters
    ----------
    transactions : pd.DataFrame
        Time series containing one row per symbol (and potentially
        duplicate datetime indices) and columns for amount and price.

    Returns
    -------
    pd.DataFrame
        Daily transaction volume and number of shares.
    """
    txn_norm = transactions.copy()
    txn_norm.index = txn_norm.index.normalize()
    amounts = txn_norm.amount.abs()
    prices = txn_norm.price
    values = amounts * prices
    daily_amounts = amounts.groupby(amounts.index).sum()
    daily_values = values.groupby(values.index).sum()
    daily_amounts.name = "txn_shares"
    daily_values.name = "txn_volume"
    return pd.concat([daily_values, daily_amounts], axis=1)


def adjust_returns_for_slippage(
    returns: pd.Series,
    positions: pd.DataFrame,
    transactions: pd.DataFrame,
    slippage_bps: float,
) -> pd.Series:
    """Apply a slippage penalty for every dollar traded.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    positions : pd.DataFrame
        Daily net position values.
    transactions : pd.DataFrame
        Prices and amounts of executed trades. One row per trade.
    slippage_bps : int/float
        Basis points of slippage to apply.

    Returns
    -------
    pd.Series
        Time series of daily returns, adjusted for slippage.
    """
    slippage = 0.0001 * slippage_bps
    portfolio_value = positions.sum(axis=1)
    pnl = portfolio_value * returns
    traded_value = get_txn_vol(transactions).txn_volume
    slippage_dollars = traded_value * slippage
    adjusted_pnl = pnl.add(-slippage_dollars, fill_value=0)
    pnl_safe = pnl.replace(0, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        adjusted_returns = returns * adjusted_pnl / pnl_safe
    return adjusted_returns.fillna(0)


def get_turnover(
    positions: pd.DataFrame,
    transactions: pd.DataFrame,
    denominator: str = "AGB",
) -> pd.Series:
    """Calculate value of purchases and sales divided by either the actual gross book or the portfolio value.

    Parameters
    ----------
    positions : pd.DataFrame
        Contains daily position values including cash.
    transactions : pd.DataFrame
        Prices and amounts of executed trades. One row per trade.
    denominator : str, optional
        Either 'AGB' or 'portfolio_value', default AGB.

    Returns
    -------
    pd.Series
        Timeseries of portfolio turnover rates.
    """
    import warnings

    txn_vol = get_txn_vol(transactions)
    traded_value = txn_vol.txn_volume

    if denominator == "AGB":
        # Actual gross book is the same thing as the algo's GMV
        # We want our denom to be avg(AGB previous, AGB current)
        agb = positions.drop("cash", axis=1).abs().sum(axis=1)
        denom = agb.rolling(2).mean()

        # Since the first value of pd.rolling returns NaN, we
        # set our "day 0" AGB to 0.
        denom.iloc[0] = agb.iloc[0] / 2
    elif denominator == "portfolio_value":
        denom = positions.sum(axis=1)
    else:
        raise ValueError(
            f"Unexpected value for denominator '{denominator}'. The "
            "denominator parameter must be either 'AGB'"
            " or 'portfolio_value'."
        )

    denom.index = denom.index.normalize()
    turnover = traded_value.div(denom, axis="index")
    # Sanitize inf values to avoid downstream plotting/rendering errors.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        turnover = turnover.replace([np.inf, -np.inf], np.nan).infer_objects()
    turnover = turnover.fillna(0)
    return turnover.astype("float")
