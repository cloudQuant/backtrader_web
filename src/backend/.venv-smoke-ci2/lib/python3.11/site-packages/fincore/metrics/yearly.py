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

"""Yearly aggregation metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fincore.constants import DAILY
from fincore.metrics.basic import aligned_series, annualization_factor, ensure_datetime_index_series
from fincore.metrics.drawdown import max_drawdown
from fincore.metrics.ratios import sharpe_ratio
from fincore.metrics.returns import cum_returns_final
from fincore.metrics.risk import annual_volatility

__all__ = [
    "annual_active_return",
    "annual_active_return_by_year",
    "annual_return",
    "annual_return_by_year",
    "annual_volatility_by_year",
    "information_ratio_by_year",
    "max_drawdown_by_year",
    "sharpe_ratio_by_year",
]


def annual_return(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    period: str = DAILY,
    annualization: float | None = None,
) -> float | np.ndarray | pd.Series:
    """Determine the mean annual growth rate of returns (CAGR).

    This is effectively the compound annual growth rate assuming
    reinvestment of returns.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative simple returns.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.

    Returns
    -------
    float or np.ndarray or pd.Series
        Annualized return. For 1D input a scalar is returned; for 2D input
        one value is returned per column.
    """
    if len(returns) < 1:
        return np.nan

    ann_factor = annualization_factor(period, annualization)
    num_years = len(returns) / ann_factor
    ending_value = cum_returns_final(returns, starting_value=1)
    if isinstance(ending_value, (pd.Series, np.ndarray)):
        result = np.asarray(ending_value, dtype=float).copy()
        mask = result <= 0
        result[mask] = -1.0
        result[~mask] = result[~mask] ** (1 / num_years) - 1
        if isinstance(ending_value, pd.Series):
            return pd.Series(result, index=ending_value.index)
        return result
    if ending_value <= 0:
        return -1.0
    return ending_value ** (1 / num_years) - 1


def annual_return_by_year(
    returns: pd.Series | np.ndarray,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Determine the annual return for each calendar year.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns indexed by date.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Annual return for each calendar year.
    """
    if len(returns) < 1:
        return_as_array = isinstance(returns, np.ndarray)
        if return_as_array:
            return np.array([])
        return pd.Series(dtype="float64")

    return_as_array = isinstance(returns, np.ndarray)

    returns = ensure_datetime_index_series(returns, period=period)

    annual_returns = returns.groupby(returns.index.year).apply(
        lambda ret: annual_return(ret, period=period, annualization=annualization)
    )

    return annual_returns.values if return_as_array else annual_returns


def sharpe_ratio_by_year(
    returns: pd.Series | np.ndarray,
    risk_free: float = 0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Determine the Sharpe ratio for each calendar year.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns indexed by date.
    risk_free : float, optional
        Risk-free rate (default 0).
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Sharpe ratio for each calendar year.
    """
    if len(returns) < 1:
        return_as_array = isinstance(returns, np.ndarray)
        return np.array([]) if return_as_array else pd.Series(dtype="float64")

    return_as_array = isinstance(returns, np.ndarray)

    returns = ensure_datetime_index_series(returns, period=period)

    sharpe_by_year = returns.groupby(returns.index.year).apply(
        lambda ret: sharpe_ratio(ret, risk_free=risk_free, period=period, annualization=annualization)
    )

    return sharpe_by_year.values if return_as_array else sharpe_by_year


def max_drawdown_by_year(returns: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
    """Determine the maximum drawdown for each calendar year.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns indexed by date.

    Returns
    -------
    pd.Series or np.ndarray
        Maximum drawdown for each calendar year.
    """
    if len(returns) < 1:
        return_as_array = isinstance(returns, np.ndarray)
        return np.array([]) if return_as_array else pd.Series(dtype="float64")

    return_as_array = isinstance(returns, np.ndarray)

    returns = ensure_datetime_index_series(returns, period=DAILY)

    max_dd_by_year = returns.groupby(returns.index.year).apply(lambda ret: max_drawdown(ret))
    return max_dd_by_year.values if return_as_array else max_dd_by_year


def annual_volatility_by_year(
    returns: pd.Series | np.ndarray,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Determine the annual volatility for each calendar year.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns indexed by date.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Annualized volatility for each calendar year.
    """
    if len(returns) < 1:
        return_as_array = isinstance(returns, np.ndarray)
        return np.array([]) if return_as_array else pd.Series(dtype="float64")

    return_as_array = isinstance(returns, np.ndarray)

    returns = ensure_datetime_index_series(returns, period=period)

    annual_vol_by_year = returns.groupby(returns.index.year).apply(
        lambda ret: annual_volatility(ret, period=period, annualization=annualization)
    )

    return annual_vol_by_year.values if return_as_array else annual_vol_by_year


def annual_active_return(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    period: str = DAILY,
    annualization: float | None = None,
) -> float:
    """Calculate annual active return (strategy minus benchmark).

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative strategy returns.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    float
        Annual active return, or ``NaN`` if insufficient data.
    """
    if len(returns) < 1:
        return np.nan

    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    strategy_annual = annual_return(returns_aligned, period, annualization)
    benchmark_annual = annual_return(factor_aligned, period, annualization)

    if np.isnan(strategy_annual) or np.isnan(benchmark_annual):
        return np.nan  # pragma: no cover -- Defensive edge case

    return strategy_annual - benchmark_annual  # type: ignore[return-value]


def annual_active_return_by_year(
    returns: pd.Series,
    factor_returns: pd.Series,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series:
    """Determine the annual active return for each calendar year.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative strategy returns indexed by date.
    factor_returns : pd.Series
        Non-cumulative benchmark returns indexed by date.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series
        Annual active return for each calendar year.
    """
    if len(returns) < 1:
        return pd.Series([], dtype=float)

    if not isinstance(returns.index, pd.DatetimeIndex):
        return pd.Series([], dtype=float)

    grouped = returns.groupby(returns.index.year)
    factor_grouped = factor_returns.groupby(factor_returns.index.year)

    annual_active_returns = []
    for year in grouped.groups:
        if year in factor_grouped.groups:
            year_returns = grouped.get_group(year)
            year_factor = factor_grouped.get_group(year)
            active_return = annual_active_return(year_returns, year_factor, period, annualization)
            annual_active_returns.append((year, active_return))

    if not annual_active_returns:
        return pd.Series([], dtype=float)

    years, active_returns = zip(*annual_active_returns, strict=False)
    return pd.Series(active_returns, index=years)


def information_ratio_by_year(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Determine the information ratio for each calendar year.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative strategy returns indexed by date.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns indexed by date.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Information ratio for each calendar year.
    """
    from fincore.metrics.ratios import information_ratio as calc_ir

    if len(returns) < 1:
        return_as_array = isinstance(returns, np.ndarray)
        return np.array([]) if return_as_array else pd.Series(dtype="float64")

    return_as_array = isinstance(returns, np.ndarray)

    returns = ensure_datetime_index_series(returns, period=period)
    factor_returns = ensure_datetime_index_series(factor_returns, period=period)

    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    def calc_ir_for_year(returns_group: pd.Series) -> float:
        """Calculate Information Ratio for a specific year.

        Parameters
        ----------
        returns_group : pd.Series
            Returns for a specific year.

        Returns
        -------
        float
            Information Ratio for the year.
        """
        factor_group = factor_aligned.loc[returns_group.index]  # type: ignore[union-attr]
        return calc_ir(returns_group, factor_group, period, annualization)

    information_ratios = returns_aligned.groupby(returns_aligned.index.year).apply(calc_ir_for_year)  # type: ignore[union-attr]

    if hasattr(information_ratios, "name"):
        information_ratios.name = None

    if return_as_array:
        return information_ratios.values
    return information_ratios
