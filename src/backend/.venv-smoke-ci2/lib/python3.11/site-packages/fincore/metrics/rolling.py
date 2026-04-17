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

"""Rolling-window metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fincore.constants import DAILY
from fincore.metrics.alpha_beta import alpha_aligned, alpha_beta_aligned
from fincore.metrics.basic import aligned_series, annualization_factor
from fincore.metrics.ratios import down_capture, up_capture

__all__ = [
    "roll_alpha",
    "roll_alpha_beta",
    "roll_beta",
    "roll_down_capture",
    "roll_max_drawdown",
    "roll_sharpe_ratio",
    "roll_up_capture",
    "roll_up_down_capture",
    "rolling_beta",
    "rolling_regression",
    "rolling_sharpe",
    "rolling_volatility",
]


def roll_alpha(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    window: int = 252,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Calculate rolling alpha over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns to calculate alpha against.
    window : int, optional
        Length of the rolling window (default 252).
    risk_free : float, optional
        Risk-free rate (default 0.0).
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Rolling alpha values.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    is_series = isinstance(returns_aligned, pd.Series)

    if len(returns_aligned) < window:
        if isinstance(returns_aligned, pd.Series):
            if isinstance(returns_aligned.index, pd.DatetimeIndex):
                return pd.Series([], dtype=float, index=returns_aligned.index[:0])
            return pd.Series([], dtype=float)
        return np.array([], dtype=float)

    if not is_series:
        returns_aligned = pd.Series(returns_aligned)
        factor_aligned = pd.Series(factor_aligned)

    assert isinstance(returns_aligned, pd.Series) and isinstance(factor_aligned, pd.Series)
    n = len(returns_aligned) - window + 1
    out = np.empty(n, dtype=float)
    ret_arr = np.asanyarray(returns_aligned)
    fac_arr = np.asanyarray(factor_aligned)
    for i in range(n):
        out[i] = alpha_aligned(ret_arr[i : i + window], fac_arr[i : i + window], risk_free, period, annualization)

    if is_series:
        return pd.Series(out, index=returns_aligned.index[window - 1 :])
    return out


def roll_beta(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    window: int = 252,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Calculate rolling beta over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns to calculate beta against.
    window : int, optional
        Length of the rolling window (default 252).
    risk_free : float, optional
        Risk-free rate (default 0.0).
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Rolling beta values.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    is_series = isinstance(returns_aligned, pd.Series)

    if len(returns_aligned) < window:
        if isinstance(returns_aligned, pd.Series):
            if isinstance(returns_aligned.index, pd.DatetimeIndex):
                return pd.Series([], dtype=float, index=returns_aligned.index[:0])
            return pd.Series([], dtype=float)
        return np.array([], dtype=float)

    if not is_series:
        returns_aligned = pd.Series(returns_aligned)
        factor_aligned = pd.Series(factor_aligned)

    assert isinstance(returns_aligned, pd.Series) and isinstance(factor_aligned, pd.Series)
    ret_adj = returns_aligned - risk_free
    fac_adj = factor_aligned - risk_free
    rolling_cov = ret_adj.rolling(window).cov(fac_adj)
    rolling_var = fac_adj.rolling(window).var()
    with np.errstate(divide="ignore", invalid="ignore"):
        result = rolling_cov / rolling_var
    result = result.iloc[window - 1 :]

    if is_series:
        return result
    return result.values


def roll_alpha_beta(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    window: int = 252,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.DataFrame | np.ndarray:
    """Calculate rolling alpha and beta over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns to calculate alpha and beta against.
    window : int, optional
        Length of the rolling window (default 252).
    risk_free : float, optional
        Risk-free rate (default 0.0).
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.DataFrame or np.ndarray
        Rolling alpha and beta values with columns ['alpha', 'beta'].
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    is_series = isinstance(returns_aligned, pd.Series)

    if len(returns_aligned) < window:
        if isinstance(returns_aligned, pd.Series):
            if isinstance(returns_aligned.index, pd.DatetimeIndex):
                return pd.DataFrame(columns=["alpha", "beta"], index=returns_aligned.index[:0])
            return pd.DataFrame(columns=["alpha", "beta"])
        return pd.DataFrame(columns=["alpha", "beta"])

    if not is_series:
        returns_aligned = pd.Series(returns_aligned)
        factor_aligned = pd.Series(factor_aligned)

    assert isinstance(returns_aligned, pd.Series) and isinstance(factor_aligned, pd.Series)
    n = len(returns_aligned) - window + 1
    out_alpha = np.empty(n, dtype=float)
    out_beta = np.empty(n, dtype=float)
    ret_arr = np.asanyarray(returns_aligned)
    fac_arr = np.asanyarray(factor_aligned)
    for i in range(n):
        ab = alpha_beta_aligned(ret_arr[i : i + window], fac_arr[i : i + window], risk_free, period, annualization)
        out_alpha[i] = ab[0]
        out_beta[i] = ab[1]

    idx = returns_aligned.index[window - 1 :]
    if is_series:
        return pd.DataFrame({"alpha": out_alpha, "beta": out_beta}, index=idx)
    return pd.DataFrame({"alpha": out_alpha, "beta": out_beta})


def roll_sharpe_ratio(
    returns: pd.Series | np.ndarray,
    window: int = 252,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series | np.ndarray:
    """Calculate rolling Sharpe ratio over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    window : int, optional
        Length of the rolling window (default 252).
    risk_free : float, optional
        Risk-free rate (default 0.0).
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    pd.Series or np.ndarray
        Rolling Sharpe ratio values.
    """
    is_series = isinstance(returns, pd.Series)

    if len(returns) < window:
        if isinstance(returns, pd.Series):
            if isinstance(returns.index, pd.DatetimeIndex):
                return pd.Series([], dtype=float, index=returns.index[:0])
            return pd.Series([], dtype=float)
        return np.array([], dtype=float)

    if not is_series:
        returns = pd.Series(returns)

    assert isinstance(returns, pd.Series)
    ann_factor = annualization_factor(period, annualization)
    sqrt_ann = np.sqrt(ann_factor)

    ret_adj = returns - risk_free
    rolling_mean = ret_adj.rolling(window, min_periods=1).mean()
    rolling_std = ret_adj.rolling(window, min_periods=1).std(ddof=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        result = (rolling_mean / rolling_std) * sqrt_ann

    result = result.iloc[window - 1 :]

    if is_series:
        return result
    return result.values


def roll_max_drawdown(
    returns: pd.Series | np.ndarray,
    window: int = 252,
) -> pd.Series | np.ndarray:
    """Calculate rolling maximum drawdown over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    window : int, optional
        Length of the rolling window (default 252).

    Returns
    -------
    pd.Series or np.ndarray
        Rolling maximum drawdown values.
    """
    if len(returns) < window:
        if isinstance(returns, pd.Series):
            if isinstance(returns.index, pd.DatetimeIndex):
                return pd.Series([], dtype=float, index=returns.index[:0])
            return pd.Series([], dtype=float)
        return np.array([], dtype=float)

    ret_arr = np.asanyarray(returns, dtype=np.float64)
    n = len(ret_arr) - window + 1

    # --- vectorised path using sliding_window_view ---
    from numpy.lib.stride_tricks import sliding_window_view

    windows = sliding_window_view(ret_arr, window)  # (n, window) — view, no copy

    # Build cumulative product with starting value 1.0 in a single allocation
    cum = np.empty((n, window + 1), dtype=np.float64)
    cum[:, 0] = 1.0
    np.cumprod(1.0 + windows, axis=1, out=cum[:, 1:])

    # running maximum along each window row
    run_max = np.maximum.accumulate(cum, axis=1)

    # drawdown at every point inside every window (in-place to reduce allocation)
    with np.errstate(divide="ignore", invalid="ignore"):
        cum -= run_max
        cum /= run_max

    # max drawdown per window (most negative value)
    out = np.nanmin(cum, axis=1)  # (n,)

    if isinstance(returns, pd.Series):
        return pd.Series(out, index=returns.index[window - 1 :])
    return out


def roll_up_capture(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    window: int = 252,
) -> pd.Series | np.ndarray:
    """Calculate rolling up capture over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns.
    window : int, optional
        Length of the rolling window (default 252).

    Returns
    -------
    pd.Series or np.ndarray
        Rolling up capture values.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    is_series = isinstance(returns_aligned, pd.Series)

    if len(returns_aligned) < window:
        if isinstance(returns_aligned, pd.Series):
            if isinstance(returns_aligned.index, pd.DatetimeIndex):
                return pd.Series([], dtype=float, index=returns_aligned.index[:0])
            return pd.Series([], dtype=float)
        return np.array([], dtype=float)

    if not is_series:
        returns_aligned = pd.Series(returns_aligned)
        factor_aligned = pd.Series(factor_aligned)

    assert isinstance(returns_aligned, pd.Series) and isinstance(factor_aligned, pd.Series)
    n = len(returns_aligned) - window + 1
    out = np.empty(n, dtype=float)
    for i in range(n):
        out[i] = up_capture(returns_aligned.iloc[i : i + window], factor_aligned.iloc[i : i + window])

    if is_series:
        return pd.Series(out, index=returns_aligned.index[window - 1 :])
    return out


def roll_down_capture(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    window: int = 252,
) -> pd.Series | np.ndarray:
    """Calculate rolling down capture over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns.
    window : int, optional
        Length of the rolling window (default 252).

    Returns
    -------
    pd.Series or np.ndarray
        Rolling down capture values.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    is_series = isinstance(returns_aligned, pd.Series)

    if len(returns_aligned) < window:
        if isinstance(returns_aligned, pd.Series):
            if isinstance(returns_aligned.index, pd.DatetimeIndex):
                return pd.Series([], dtype=float, index=returns_aligned.index[:0])
            return pd.Series([], dtype=float)
        return np.array([], dtype=float)

    if not is_series:
        returns_aligned = pd.Series(returns_aligned)
        factor_aligned = pd.Series(factor_aligned)

    assert isinstance(returns_aligned, pd.Series) and isinstance(factor_aligned, pd.Series)
    n = len(returns_aligned) - window + 1
    out = np.empty(n, dtype=float)
    for i in range(n):
        out[i] = down_capture(returns_aligned.iloc[i : i + window], factor_aligned.iloc[i : i + window])

    if is_series:
        return pd.Series(out, index=returns_aligned.index[window - 1 :])
    return out


def roll_up_down_capture(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    window: int = 252,
) -> pd.Series | np.ndarray:
    """Calculate rolling up/down capture ratio over a specified window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Non-cumulative returns of the strategy.
    factor_returns : pd.Series or np.ndarray
        Non-cumulative benchmark returns.
    window : int, optional
        Length of the rolling window (default 252).

    Returns
    -------
    pd.Series or np.ndarray
        Rolling up/down capture ratio values.
    """
    up_caps = roll_up_capture(returns, factor_returns, window)
    down_caps = roll_down_capture(returns, factor_returns, window)

    with np.errstate(divide="ignore", invalid="ignore"):
        return up_caps / down_caps


def rolling_volatility(
    returns: pd.Series,
    rolling_vol_window: int,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series:
    """Determine the rolling volatility of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative returns of the strategy.
    rolling_vol_window : int
        Length of the rolling window.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : float, optional
        Custom annualization factor.

    Returns
    -------
    pd.Series
        Rolling volatility, annualized.
    """
    ann_factor = annualization_factor(period, annualization)
    return returns.rolling(window=rolling_vol_window).std() * np.sqrt(ann_factor)


def rolling_sharpe(
    returns: pd.Series,
    rolling_sharpe_window: int,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series:
    """Determine the rolling Sharpe ratio of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative returns of the strategy.
    rolling_sharpe_window : int
        Length of the rolling window.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : float, optional
        Custom annualization factor.

    Returns
    -------
    pd.Series
        Rolling Sharpe ratio, annualized.
    """
    ann_factor = annualization_factor(period, annualization)
    rolling_mean = returns.rolling(window=rolling_sharpe_window).mean()
    rolling_std = returns.rolling(window=rolling_sharpe_window).std()

    with np.errstate(divide="ignore", invalid="ignore"):
        return rolling_mean / rolling_std * np.sqrt(ann_factor)


def rolling_beta(
    returns: pd.Series,
    factor_returns: pd.Series | pd.DataFrame,
    rolling_window: int = 126,
) -> pd.Series | pd.DataFrame:
    """Calculate rolling beta.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series or pd.DataFrame
        Daily noncumulative returns of the benchmark factor.
    rolling_window : int, optional
        The size of the rolling window, in days (default 126).

    Returns
    -------
    pd.Series
        Rolling beta.
    """
    from functools import partial

    if factor_returns.ndim > 1:
        return factor_returns.apply(partial(rolling_beta, returns), rolling_window=rolling_window)
    returns_aligned, factor_aligned = returns.align(factor_returns, join="inner")
    rolling_cov = returns_aligned.rolling(rolling_window).cov(factor_aligned)
    rolling_var = factor_aligned.rolling(rolling_window).var()
    with np.errstate(divide="ignore", invalid="ignore"):
        return rolling_cov / rolling_var


def rolling_regression(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    rolling_window: int = 126,
) -> pd.DataFrame:
    """Calculate rolling regression alpha and beta.

    Note: The alpha returned here is the **non-annualized** (daily-frequency)
    regression intercept, unlike ``roll_alpha`` which returns annualized alpha.
    To annualize, multiply by the appropriate annualization factor
    (e.g. 252 for daily data).

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series
        Daily returns of the benchmark factor.
    rolling_window : int, optional
        Length of the rolling window (default 126).

    Returns
    -------
    pd.DataFrame
        Rolling alpha (non-annualized) and beta values with columns
        ['alpha', 'beta'].
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    if len(returns_aligned) < rolling_window:
        return pd.DataFrame(columns=["alpha", "beta"])

    if not isinstance(returns_aligned, pd.Series):
        returns_aligned = pd.Series(returns_aligned)
        factor_aligned = pd.Series(factor_aligned)

    assert isinstance(returns_aligned, pd.Series) and isinstance(factor_aligned, pd.Series)
    rolling_cov = returns_aligned.rolling(rolling_window).cov(factor_aligned)
    rolling_var = factor_aligned.rolling(rolling_window).var()
    with np.errstate(divide="ignore", invalid="ignore"):
        rolling_beta_vals = rolling_cov / rolling_var
    rolling_mean_ret = returns_aligned.rolling(rolling_window).mean()
    rolling_mean_fac = factor_aligned.rolling(rolling_window).mean()
    rolling_alpha_vals = rolling_mean_ret - rolling_beta_vals * rolling_mean_fac

    result = pd.DataFrame({"alpha": rolling_alpha_vals, "beta": rolling_beta_vals})
    return result.dropna()
