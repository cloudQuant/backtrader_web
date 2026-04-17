#
# Copyright 2018 Quantopian, Inc.
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

"""Data processing utilities.

Includes helpers for rolling-window computations and small array utilities.
"""

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import as_strided


def rolling_window(array, length):
    """
    Creates a rolling window of length from array.

    Parameters
    ----------
    array : array-like
        The array to create rolling windows from.
    length : int
        Length of the rolling window.

    Returns
    -------
    rolling_windows : np.ndarray
        Rolling windows of the input array.
    """
    # Make sure the array is a numpy array
    array = np.asarray(array)

    if array.ndim != 1:
        raise ValueError("Rolling window only supports 1D arrays")

    if length > len(array):
        raise ValueError("Window length cannot be greater than array length")

    # Create the rolling window using stride tricks
    shape = (array.size - length + 1, length)
    strides = (array.strides[0], array.strides[0])

    return as_strided(array, shape=shape, strides=strides)


def _roll_pandas(func, window, *args, **kwargs):
    """
    Pandas-based rolling calculation.
    """
    data = args[0]

    # When window is larger than the data length, return an empty Series
    # with the same index type so that index comparisons in tests pass.
    if len(data) < window:
        return pd.Series([], dtype=float, index=data.index[:0])

    n = len(data) - window + 1
    out = np.empty(n, dtype=float)
    result_index = data.index[window - 1 :]

    if len(args) == 1:
        for i in range(n):
            out[i] = func(data.iloc[i : i + window], **kwargs)
    else:
        factor_returns = args[1]
        for i in range(n):
            out[i] = func(data.iloc[i : i + window], factor_returns.iloc[i : i + window], **kwargs)

    return pd.Series(out, index=result_index, dtype=float)


def _roll_ndarray(func, window, *args, **kwargs):
    """
    NumPy array-based rolling calculation.
    """
    data = args[0]

    # Match original empyrical.utils.roll semantics: if window is larger
    # than the data length, return an empty array.
    if len(data) < window:
        return np.array([], dtype=float)

    n = len(data) - window + 1
    out = np.empty(n, dtype=float)

    if len(args) == 1:
        for i in range(n):
            out[i] = func(data[i : i + window], **kwargs)
    else:
        factor_returns = args[1]
        for i in range(n):
            out[i] = func(data[i : i + window], factor_returns[i : i + window], **kwargs)

    return out


def roll(*args, **kwargs):
    """
    Calculates a given statistic across a rolling time period.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
    factor_returns: float / series, optional
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    window (keyword): int
        the number of periods included in each calculation.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns
    -------
    np.ndarray or pd.Series
        depends on input type
        ndarray(s) ==> ndarray
        Series(s) ==> pd.Series

        A Series or ndarray of the results.
    """
    func = kwargs.pop("function")
    window = kwargs.pop("window")

    if len(args) > 2:
        raise ValueError("Cannot pass more than 2 return sets")

    if len(args) == 2 and not isinstance(args[0], type(args[1])):
        raise ValueError("The two returns arguments are not the same.")

    if isinstance(args[0], np.ndarray):
        return _roll_ndarray(func, window, *args, **kwargs)
    return _roll_pandas(func, window, *args, **kwargs)


def up(returns, factor_returns, **kwargs):
    """
    Calculates a given statistic filtering only positive factor return periods.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
    factor_returns: float / series
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns
    -------
    Same as the return of the function
    """
    func = kwargs.pop("function")
    returns = returns[factor_returns > 0]
    factor_returns = factor_returns[factor_returns > 0]
    return func(returns, factor_returns, **kwargs)


def down(returns, factor_returns, **kwargs):
    """
    Calculates a given statistic filtering only negative factor return periods.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
    factor_returns: float / series
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns
    -------
    Same as the return of the function
    """
    func = kwargs.pop("function")
    returns = returns[factor_returns < 0]
    factor_returns = factor_returns[factor_returns < 0]
    return func(returns, factor_returns, **kwargs)


__all__ = ["down", "roll", "rolling_window", "up"]
