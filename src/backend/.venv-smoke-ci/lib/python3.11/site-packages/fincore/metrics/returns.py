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

"""Return calculation utilities.

This module provides core functions for return analytics, including:
- simple returns from prices
- cumulative return series and final cumulative return
- return aggregation (e.g. weekly/monthly/yearly)
- normalization of a value series to a starting value
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from fincore.constants import MONTHLY, QUARTERLY, WEEKLY, YEARLY

__all__ = [
    "aggregate_returns",
    "cum_returns",
    "cum_returns_final",
    "normalize",
    "simple_returns",
]


def _get_annual_return():
    """Lazily import ``annual_return`` to avoid circular dependencies.

    Returns
    -------
    function
        The ``annual_return`` function.
    """
    from fincore.metrics.yearly import annual_return

    return annual_return


# Re-export annual_return for backwards compatibility
def annual_return(*args: object, **kwargs: object) -> float | np.ndarray | pd.Series:
    """Backwards-compatible wrapper for computing annual return (CAGR).

    The implementation lives in :func:`fincore.metrics.yearly.annual_return`.

    Parameters
    ----------
    *args : tuple
        Positional arguments forwarded to ``yearly.annual_return``.
    **kwargs : dict
        Keyword arguments forwarded to ``yearly.annual_return``.

    Returns
    -------
    float
        Annual return.

    See Also
    --------
    fincore.metrics.yearly.annual_return : Implementation.
    """
    return _get_annual_return()(*args, **kwargs)


def simple_returns(
    prices: pd.Series | pd.DataFrame | np.ndarray,
) -> pd.Series | pd.DataFrame | np.ndarray:
    """Compute simple returns from a time series of prices.

    Parameters
    ----------
    prices : array-like or pd.Series or pd.DataFrame
        Time series of prices.

    Returns
    -------
    array-like or pd.Series or pd.DataFrame
        Simple returns computed as ``(price[t] - price[t-1])`` divided by
        ``price[t-1]``. The first observation is dropped. For pandas
        inputs, the index is preserved (excluding the first element).
    """
    if isinstance(prices, (pd.DataFrame, pd.Series)):
        out = prices.pct_change().iloc[1:]
    else:
        # Assume np.ndarray
        out = np.diff(prices, axis=0)
        # Avoid division by zero warning
        with np.errstate(divide="ignore", invalid="ignore"):
            np.divide(out, prices[:-1], out=out)

    return out


def cum_returns(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    starting_value: float = 0,
    out: np.ndarray | None = None,
) -> pd.Series | pd.DataFrame | np.ndarray:
    """Compute cumulative returns from simple returns.

    This compounds the input returns and optionally scales by an initial
    ``starting_value``.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative simple returns.
    starting_value : float, optional
        Initial portfolio value. If ``0`` (default), the result is
        returned as a pure cumulative return. Otherwise, the result is
        scaled so that ``starting_value * cumprod(1 + returns)`` is
        returned.
    out : np.ndarray, optional
        pre-allocated output array. If given, the result is
        written in-place into this array.

    Returns
    -------
    array-like or pd.Series or pd.DataFrame
        Cumulative returns. The type mirrors the input type.
    """
    if len(returns) < 1:
        return returns.copy()

    nanmask = np.isnan(returns)
    if np.any(nanmask):
        returns = returns.copy()
        returns[nanmask] = 0

    allocated_output = out is None
    if allocated_output:
        out = np.empty_like(returns)

    assert out is not None  # for type checking
    np.add(returns, 1, out=out)
    out.cumprod(axis=0, out=out)

    if starting_value == 0:
        np.subtract(out, 1, out=out)
    else:
        np.multiply(out, starting_value, out=out)

    if allocated_output:
        if returns.ndim == 1 and isinstance(returns, pd.Series):
            out = pd.Series(out, index=returns.index)
        elif isinstance(returns, pd.DataFrame):
            out = pd.DataFrame(
                out,
                index=returns.index,
                columns=returns.columns,
            )

    return out


def cum_returns_final(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    starting_value: float = 0,
) -> float | np.ndarray | pd.Series:
    """Compute total cumulative return from a series of simple returns.

    This computes the cumulative return by compounding simple period
    returns and optionally scaling by an initial ``starting_value``.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative simple returns. For a DataFrame, the computation is
        performed column-wise.
    starting_value : float, optional
        Initial portfolio value. If ``0`` (default), the result is
        returned as a pure return (ending_value - 1). Otherwise, the result
        is scaled so that ``starting_value * cumprod(1 + returns)`` is
        returned.

    Returns
    -------
    float or np.ndarray or pd.Series or pd.DataFrame
        Final cumulative return (or value, depending on
        ``starting_value``). The type mirrors the input type.
    """
    if len(returns) == 0:
        return np.nan

    result = (returns + 1).prod() if isinstance(returns, pd.DataFrame) else np.nanprod(returns + 1, axis=0)

    if starting_value == 0:
        result -= 1
    else:
        result *= starting_value

    return result


def aggregate_returns(
    returns: pd.Series,
    convert_to: str = "monthly",
) -> pd.Series:
    """Aggregate returns at a weekly/monthly/quarterly/yearly frequency.

    The function groups the input return series by calendar period and
    compounds the returns within each group using
    :func:`cum_returns`.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative returns with a ``DatetimeIndex``.
    convert_to : {"weekly", "monthly", "quarterly", "yearly"}, optional
        Target aggregation frequency. Case-insensitive. Default is
        ``"monthly"``.

    Returns
    -------
    pd.Series
        Aggregated returns at the requested frequency, indexed by
        (year, period) where period is week number, month, quarter, or
        year depending on ``convert_to``.
    """

    def cumulate_returns(ret: pd.Series) -> float:
        """Compute cumulative returns for a period.

        Parameters
        ----------
        ret : pd.Series
            Non-cumulative returns.

        Returns
        -------
        float
            The last value of the cumulative returns series.
        """
        return cum_returns(ret).iloc[-1]  # type: ignore[union-attr]

    if not isinstance(returns.index, pd.DatetimeIndex):
        raise ValueError(
            f"aggregate_returns requires returns with a DatetimeIndex, got {type(returns.index).__name__} instead."
        )

    if convert_to == WEEKLY:
        grouping = [lambda dt: dt.year, lambda dt: dt.isocalendar()[1]]
    elif convert_to == MONTHLY:
        grouping = [lambda dt: dt.year, lambda dt: dt.month]
    elif convert_to == QUARTERLY:
        grouping = [lambda dt: dt.year, lambda dt: math.ceil(dt.month / 3.0)]
    elif convert_to == YEARLY:
        grouping = [lambda dt: dt.year]
    else:
        raise ValueError(f"convert_to must be {WEEKLY}, {MONTHLY}, {QUARTERLY} or {YEARLY}")

    return returns.groupby(grouping).apply(cumulate_returns)


def normalize(
    returns: pd.Series,
    starting_value: float = 1,
) -> pd.Series:
    """Normalize a value series to start at ``starting_value``.

    This scales the input series by its first value so that the resulting series
    starts at ``starting_value``. This is commonly used to align equity curves
    from different strategies for comparison.

    Parameters
    ----------
    returns : pd.Series
        Value series (typically cumulative returns or prices).
    starting_value : float, optional
        Starting value after normalization. Default is 1.

    Returns
    -------
    pd.Series
        Normalized series whose first value equals ``starting_value``.

    Examples
    --------
    >>> import pandas as pd
    >>> returns = pd.Series([100, 110, 105, 115])
    >>> normalize(returns, starting_value=1)
    0    1.00
    1    1.10
    2    1.05
    3    1.15
    dtype: float64
    """
    if len(returns) < 1:
        return returns.copy()

    first_value = returns.iloc[0]
    if first_value == 0:
        import warnings

        warnings.warn(
            "First value of returns is 0, normalization will produce inf/nan values.",
            stacklevel=2,
        )
        return returns * np.nan
    return starting_value * (returns / first_value)
