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

"""Basic metric utilities (alignment, annualization, helpers)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from fincore.constants import ANNUALIZATION_FACTORS, DAILY, PERIOD_TO_FREQ

__all__ = [
    "adjust_returns",
    "aligned_series",
    "annualization_factor",
    "ensure_datetime_index_series",
    "flatten",
    "to_pandas",
]


def ensure_datetime_index_series(
    data: pd.Series | np.ndarray | list,
    period: str = DAILY,
) -> pd.Series:
    """Return a Series indexed by dates regardless of the input type.

    If the input is already a datetime-indexed Series, it is returned as
    is. Otherwise, a synthetic datetime index is generated based on the
    specified ``period``.

    Parameters
    ----------
    data : array-like or pd.Series
        Input data to be converted.
    period : str, optional
        Frequency of the data (for example ``DAILY``, ``WEEKLY``). Used
        to generate the synthetic datetime index when needed. Default is
        ``DAILY``.

    Returns
    -------
    pd.Series
        with a ``DatetimeIndex``. Empty input returns an empty
        Series.
    """
    if isinstance(data, pd.Series) and isinstance(data.index, pd.DatetimeIndex):
        return data

    values = data.values if isinstance(data, pd.Series) else np.asarray(data)

    if values.size == 0:
        return pd.Series(values)

    freq = PERIOD_TO_FREQ.get(period, "D")
    index = pd.date_range("1970-01-01", periods=values.size, freq=freq)
    return pd.Series(values, index=index)


def flatten(arr: pd.Series | np.ndarray) -> np.ndarray:
    """Flatten a pandas Series to a NumPy array.

    Parameters
    ----------
    arr : array-like or pd.Series
        Input array or Series.

    Returns
    -------
    np.ndarray or original type
        If the input is a Series, returns its underlying values as a
        NumPy array; otherwise returns the input unchanged.
    """
    return arr if not isinstance(arr, pd.Series) else arr.values


def adjust_returns(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    adjustment_factor: float | pd.Series | pd.DataFrame | np.ndarray,
) -> pd.Series | pd.DataFrame | np.ndarray:
    """Adjust returns by subtracting an adjustment factor.

    This is a convenience helper for computing excess returns or active
    returns. If the adjustment factor is zero, the original returns are
    returned unchanged.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative returns.
    adjustment_factor : float or array-like or pd.Series or pd.DataFrame
        Value(s) to subtract from ``returns``. Can be a scalar (for
        example a risk-free rate) or an array-like of the same shape as
        ``returns`` (for example benchmark returns).

    Returns
    -------
    array-like or pd.Series or pd.DataFrame
        Adjusted returns ``returns - adjustment_factor``, or the original
        ``returns`` if ``adjustment_factor`` is zero.
    """
    if isinstance(adjustment_factor, (float, int)) and adjustment_factor == 0:
        return returns
    return returns - adjustment_factor


@lru_cache(maxsize=32)
def annualization_factor(period: str, annualization: float | None = None) -> float:
    """Return the annualization factor for a given period.

    If a custom ``annualization`` value is provided, it is returned
    directly. Otherwise, the factor is looked up from a predefined
    mapping based on ``period``.

    Parameters
    ----------
    period : str
        Frequency of the data (for example ``DAILY``, ``WEEKLY``,
        ``MONTHLY``, ``YEARLY``).
    annualization : float or None
        Custom annualization factor. If provided (not ``None``), this
        value is returned directly.

    Returns
    -------
    float
        Annualization factor corresponding to ``period`` or the custom
        value if provided.

    Raises
    ------
    ValueError
        If ``period`` is not recognized and ``annualization`` is ``None``.
    """
    if annualization is None:
        try:
            factor = float(ANNUALIZATION_FACTORS[period])
        except KeyError as e:
            raise ValueError(
                "Period cannot be '{}'. Can be '{}'.".format(period, "', '".join(ANNUALIZATION_FACTORS.keys()))
            ) from e
    else:
        factor = float(annualization)
    return factor


def to_pandas(ob: np.ndarray | pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Convert an array-like to a pandas object.

    Parameters
    ----------
    ob : np.ndarray or pd.Series or pd.DataFrame
        Input array or pandas object.

    Returns
    -------
    pd.Series or pd.DataFrame
        If the input is already a pandas object, it is returned as-is.
        Otherwise, 1D arrays are converted to Series and 2D arrays to
        DataFrame.

    Raises
    ------
    ValueError
        If the input has more than two dimensions.
    """
    if isinstance(ob, (pd.Series, pd.DataFrame)):
        return ob

    if ob.ndim == 1:
        return pd.Series(ob)
    if ob.ndim == 2:
        return pd.DataFrame(ob)
    raise ValueError(
        "cannot convert array of dim > 2 to a pandas structure",
    )


def aligned_series(
    *many_series: pd.Series | pd.DataFrame | np.ndarray,
) -> tuple[pd.Series | pd.DataFrame | np.ndarray, ...]:
    """Return a new tuple of series with their indices aligned.

    This helper aligns multiple return series by their common index,
    dropping observations that are not present in all series. If all
    inputs are NumPy arrays of the same length, they are assumed to be
    already aligned and returned unchanged.

    Parameters
    ----------
    *many_series : sequence of array-like or pd.Series or pd.DataFrame
        Two or more return series to align.

    Returns
    -------
    tuple of pd.Series or pd.DataFrame
        Aligned series with a common index. If the inputs were NumPy
        arrays of the same length, they are returned unchanged.
    """
    head = many_series[0]
    tail = many_series[1:]
    n = len(head)
    if isinstance(head, np.ndarray) and all(len(s) == n and isinstance(s, np.ndarray) for s in tail):
        # optimization: ndarrays of the same length are already aligned
        return many_series

    if len(many_series) == 2 and isinstance(head, pd.Series) and isinstance(tail[0], pd.Series):
        if head.index.equals(tail[0].index):
            return many_series
        combined = pd.concat([head, tail[0]], axis=1, sort=False)
        return tuple(combined.iloc[:, i] for i in range(2))

    if len(many_series) == 2 and isinstance(head, pd.DataFrame) and isinstance(tail[0], pd.DataFrame):
        if head.index.equals(tail[0].index):
            return many_series
        left, right = head.align(tail[0], join="inner", axis=0)
        return left, right

    if len(many_series) == 2 and isinstance(head, pd.DataFrame) and isinstance(tail[0], pd.Series):
        if head.index.equals(tail[0].index):
            return many_series
        idx = head.index.intersection(tail[0].index)
        return head.loc[idx], tail[0].loc[idx]

    if len(many_series) == 2 and isinstance(head, pd.Series) and isinstance(tail[0], pd.DataFrame):
        if head.index.equals(tail[0].index):
            return many_series
        idx = head.index.intersection(tail[0].index)
        return head.loc[idx], tail[0].loc[idx]

    # dataframe has no ``itervalues``
    return tuple(v for _, v in pd.concat(map(to_pandas, many_series), axis=1, sort=False).items())
