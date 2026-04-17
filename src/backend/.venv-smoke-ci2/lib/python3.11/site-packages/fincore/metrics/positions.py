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

"""Position and holdings metrics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "compute_cap_exposures",
    "compute_sector_exposures",
    "compute_style_factor_exposures",
    "compute_volume_exposures",
    "extract_pos",
    "get_long_short_pos",
    "get_max_median_position_concentration",
    "get_percent_alloc",
    "get_sector_exposures",
    "get_top_long_short_abs",
    "gross_lev",
    "stack_positions",
]


def get_percent_alloc(values: pd.DataFrame) -> pd.DataFrame:
    """Determine a portfolio's allocations.

    Parameters
    ----------
    values : pd.DataFrame
        Contains position values or amounts.

    Returns
    -------
    pd.DataFrame
        Positions and their allocations.
    """
    result = values.divide(values.sum(axis="columns"), axis="rows")
    return result.replace([np.inf, -np.inf], np.nan)


def get_top_long_short_abs(
    positions: pd.DataFrame,
    top: int = 10,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Find the top long, short, and absolute positions.

    Parameters
    ----------
    positions : pd.DataFrame
        The positions that the strategy takes over time.
    top : int, optional
        How many of each to find (default 10).

    Returns
    -------
    df_top_long : pd.DataFrame
        Top long positions.
    df_top_short : pd.DataFrame
        Top short positions.
    df_top_abs : pd.DataFrame
        Top absolute positions.
    """
    positions = positions.drop("cash", axis="columns")
    df_max = positions.max()
    df_min = positions.min()
    df_abs_max = positions.abs().max()
    df_top_long = df_max[df_max > 0].nlargest(top)
    df_top_short = df_min[df_min < 0].nsmallest(top)
    df_top_abs = df_abs_max.nlargest(top)
    return df_top_long, df_top_short, df_top_abs


def get_max_median_position_concentration(positions: pd.DataFrame) -> pd.DataFrame:
    """Find the max and median long and short position concentrations.

    Parameters
    ----------
    positions : pd.DataFrame
        The positions that the strategy takes over time.

    Returns
    -------
    pd.DataFrame
        Columns are the max long, max short, median long, and median short
        position concentrations. Rows are time periods.
    """
    expos = get_percent_alloc(positions)
    expos = expos.drop("cash", axis=1)

    longs = expos.where(expos > 0)
    shorts = expos.where(expos < 0)

    alloc_summary = pd.DataFrame()
    alloc_summary["max_long"] = longs.max(axis=1)
    alloc_summary["median_long"] = longs.median(axis=1)
    alloc_summary["median_short"] = shorts.median(axis=1)
    alloc_summary["max_short"] = shorts.min(axis=1)

    return alloc_summary


def extract_pos(positions: pd.DataFrame, cash: pd.Series) -> pd.DataFrame:
    """Extract position values from get_backtest() output.

    Convert the backtest object's positions and cash series into a
    DataFrame of daily net position values (one column per symbol).

    Parameters
    ----------
    positions : pd.DataFrame
        timeseries containing one row per symbol (and potentially
        duplicate datetime indices) and columns for amount and
        last_sale_price.
    cash : pd.Series
        timeseries containing cash in the portfolio.

    Returns
    -------
    pd.DataFrame
        Daily net position values.
    """
    positions = positions.copy()
    positions["values"] = positions.amount * positions.last_sale_price

    cash.name = "cash"

    values = positions.reset_index().pivot_table(
        index="index",
        columns="sid",
        values="values",
    )

    values = values.join(cash).fillna(0)

    # NOTE: Set the name of DataFrame.columns to sid, to match the behavior
    # of DataFrame.join in earlier versions of pandas.
    values.columns.name = "sid"

    return values


def get_sector_exposures(
    positions: pd.DataFrame,
    symbol_sector_map: dict[Any, Any] | pd.Series,
) -> pd.DataFrame:
    """Sum position exposures by sector.

    Parameters
    ----------
    positions : pd.DataFrame
        Contains position values or amounts.
    symbol_sector_map : dict or pd.Series
        Security identifier to sector mapping.

    Returns
    -------
    pd.DataFrame
        Sectors and their allocations.
    """
    import warnings

    cash = positions["cash"]
    positions = positions.drop("cash", axis=1)

    unmapped_pos = np.setdiff1d(
        positions.columns.values,
        list(symbol_sector_map.keys()),
    )
    if len(unmapped_pos) > 0:
        warn_message = (
            "Warning: Symbols {} have no sector mapping. They will not be included in sector allocations"
        ).format(", ".join(map(str, unmapped_pos)))
        warnings.warn(warn_message, UserWarning, stacklevel=2)

    sector_exp = positions.T.groupby(by=symbol_sector_map).sum().T

    sector_exp["cash"] = cash

    return sector_exp


def get_long_short_pos(positions: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Determine the long and short allocations in a portfolio.

    Parameters
    ----------
    positions : pd.DataFrame
        The positions that the strategy takes over time.

    Returns
    -------
    tuple of pd.Series
        (longs, shorts) - Long and short position sums.
    """
    positions = positions.copy()

    if "cash" in positions.columns:
        positions = positions.drop("cash", axis=1)

    longs = positions.where(positions > 0, 0).sum(axis=1)
    shorts = positions.where(positions < 0, 0).abs().sum(axis=1)

    return longs, shorts


def compute_style_factor_exposures(
    positions: pd.DataFrame,
    risk_factor: pd.DataFrame,
) -> pd.Series:
    """Return style factor exposure of an algorithm's positions.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily equity positions of algorithm, in dollars.
    risk_factor : pd.DataFrame
        Daily risk factor per asset.

    Returns
    -------
    pd.Series
        Total style factor exposure over time.
    """
    positions = positions.copy()

    aligned = positions.align(risk_factor, axis=0, join="inner")[0]
    risk_factor_aligned = risk_factor.loc[aligned.index]

    return aligned.mul(risk_factor_aligned, axis=0).sum(axis=1)


def compute_sector_exposures(
    positions: pd.DataFrame,
    sectors: list[str],
    sector_dict: dict[Any, str] | None = None,
) -> pd.DataFrame:
    """Return sector exposures of an algorithm's positions.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily equity positions of algorithm, in dollars.
    sectors : list
        List of sector names or codes.
    sector_dict : dict, optional
        Dictionary mapping security identifiers to sectors.

    Returns
    -------
    pd.DataFrame
        Sector exposures over time.
    """
    positions = positions.copy()

    if sector_dict is None:
        sector_dict = {}

    exposures = {}
    for sector in sectors:
        sector_stocks = [s for s, sec in sector_dict.items() if sec == sector]
        sector_pos = positions[[c for c in positions.columns if c in sector_stocks]]
        exposures[sector] = sector_pos.sum(axis=1)

    return pd.DataFrame(exposures)


def compute_cap_exposures(
    positions: pd.DataFrame,
    caps: dict[str, list[Any]],
) -> pd.DataFrame:
    """Compute market capitalization exposures.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily equity positions of algorithm, in dollars.
    caps : dict
        Dictionary mapping cap categories to lists of securities.

    Returns
    -------
    pd.DataFrame
        Market cap exposures over time.
    """
    positions = positions.copy()

    exposures = {}
    for cap_category, cap_stocks in caps.items():
        cap_pos = positions[[c for c in positions.columns if c in cap_stocks]]
        exposures[cap_category] = cap_pos.sum(axis=1)

    return pd.DataFrame(exposures)


def compute_volume_exposures(
    shares_held: pd.DataFrame,
    volumes: pd.DataFrame,
    percentile: float,
) -> pd.Series:
    """Compute volume-based liquidity exposures.

    Parameters
    ----------
    shares_held : pd.DataFrame
        Number of shares held per security.
    volumes : pd.DataFrame
        Daily trading volumes per security.
    percentile : float
        Threshold percentile for days-to-liquidate.

    Returns
    -------
    pd.Series
        Count of positions exceeding the liquidity threshold.
    """
    days_to_liquidate = shares_held.abs() / volumes

    return (days_to_liquidate > percentile).sum(axis=1)


def gross_lev(positions: pd.DataFrame) -> pd.Series:
    """Calculate the gross leverage of a strategy.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily net position values.

    Returns
    -------
    pd.Series
        Gross leverage.
    """
    exposure = positions.drop("cash", axis=1).abs().sum(axis=1)
    total = positions.sum(axis=1)
    result = exposure / total
    return result.replace([np.inf, -np.inf], np.nan)


def stack_positions(
    positions: pd.DataFrame,
    pos_in_dollars: bool = True,
) -> pd.Series:
    """Stack positions into a multi-index Series.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily positions with tickers as columns.
    pos_in_dollars : bool, optional
        Whether positions are in dollars (default True).

    Returns
    -------
    pd.Series
        Stacked positions with MultiIndex (dt, ticker).
    """
    positions = positions.copy()

    if "cash" in positions.columns:
        positions = positions.drop("cash", axis=1)

    stacked = positions.stack()
    stacked.index.names = ["dt", "ticker"]

    return stacked
