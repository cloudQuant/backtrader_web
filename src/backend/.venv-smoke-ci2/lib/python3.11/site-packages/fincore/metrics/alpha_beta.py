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

"""Alpha/beta related metrics."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Callable, cast

import numpy as np
import pandas as pd

from fincore.constants import DAILY
from fincore.metrics.basic import adjust_returns, aligned_series, annualization_factor
from fincore.utils import nanmean

if TYPE_CHECKING:
    from fincore._types import ReturnOrDataFrame

__all__ = [
    "alpha",
    "alpha_aligned",
    "alpha_beta",
    "alpha_beta_aligned",
    "alpha_percentile_rank",
    "annual_alpha",
    "annual_beta",
    "beta",
    "beta_aligned",
    "down_alpha_beta",
    "up_alpha_beta",
]


def beta_aligned(
    returns: np.ndarray,
    factor_returns: np.ndarray,
    risk_free: float = 0.0,
    out: np.ndarray | None = None,
) -> float | np.ndarray:
    """Calculate beta for already-aligned data.

    This function assumes that ``returns`` and ``factor_returns`` are
    already aligned NumPy arrays (or array-like) with matching shapes
    along the time dimension. Beta is estimated using the covariance of
    excess returns divided by the variance of excess factor returns.

    Parameters
    ----------
    returns : np.ndarray
        Array of non-cumulative strategy returns. The first dimension is
        interpreted as time; any remaining dimensions correspond to
        different assets/strategies.
    factor_returns : np.ndarray
        Array of non-cumulative benchmark or factor returns, aligned with
        ``returns`` along the time dimension.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    out : np.ndarray, optional
        pre-allocated output array. If given, the result is
        written in-place into this array.

    Returns
    -------
    float or np.ndarray
        Beta of the strategy versus the benchmark. For 1D input a scalar
        is returned; for 2D input one value is returned per column.
    """
    nanmean_local = np.nanmean
    nan = np.nan
    isnan = np.isnan

    returns_1d = returns.ndim == 1
    if returns_1d:
        returns = np.asanyarray(returns)[:, np.newaxis]

    if factor_returns.ndim == 1:
        factor_returns = np.asanyarray(factor_returns)[:, np.newaxis]

    _n, m = returns.shape

    if out is None:
        out = np.full(m, nan)
    elif out.ndim == 0:
        out = out[np.newaxis]
    assert out is not None  # Helps type checker

    if len(returns) < 2 or len(factor_returns) < 2:
        out[()] = nan
        if returns_1d:
            out = out.item()
        return cast("float | np.ndarray", out)

    if risk_free != 0.0:
        returns = returns - risk_free
        factor_returns = factor_returns - risk_free

    independent = np.where(isnan(returns), nan, factor_returns)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        ind_residual = independent - nanmean_local(independent, axis=0)
        covariances = nanmean_local(ind_residual * returns, axis=0)

        np.square(ind_residual, out=ind_residual)
        independent_variances = nanmean_local(ind_residual, axis=0)
    independent_variances[independent_variances < 1.0e-30] = np.nan

    np.divide(covariances, independent_variances, out=out)

    if returns_1d:
        out = out.item()

    return cast("float | np.ndarray", out)


def alpha_aligned(
    returns: np.ndarray,
    factor_returns: np.ndarray,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
    _beta: float | np.ndarray | None = None,
) -> float | np.ndarray | pd.Series:
    """Calculate annualized alpha for already-aligned series.

    This function assumes that ``returns`` and ``factor_returns`` are
    already aligned NumPy arrays (or array-like) with matching shapes
    along the time dimension.

    Parameters
    ----------
    returns : np.ndarray
        Array of non-cumulative strategy returns. The first dimension is
        interpreted as time; any remaining dimensions correspond to
        different assets/strategies.
    factor_returns : np.ndarray
        Array of non-cumulative benchmark or factor returns, aligned with
        ``returns`` along the time dimension.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated output array. If given, the result is
        written in-place into this array.
    _beta : float or np.ndarray, optional
        pre-computed beta used to avoid recomputing beta internally.

    Returns
    -------
    float or np.ndarray or pd.Series
        Annualized alpha of the strategy versus the benchmark. For 1D
        input a scalar is returned; for higher-dimensional input one value
        is returned per series.
    """
    # Preserve DataFrame status before conversion
    was_dataframe = isinstance(returns, pd.DataFrame)

    returns = np.asanyarray(returns)
    factor_returns = np.asanyarray(factor_returns)

    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:], dtype="float64")
    assert out is not None  # Set by allocation or caller; helps type checker

    if len(returns) < 2:
        out[()] = np.nan
        if returns.ndim == 1:
            out = out.item()
        return out

    ann_factor = annualization_factor(period, annualization)

    if _beta is None:
        _beta = beta_aligned(returns, factor_returns, risk_free)

    adj_returns = adjust_returns(returns, risk_free)
    adj_factor_returns = adjust_returns(factor_returns, risk_free)
    # Ensure adj_factor_returns broadcasts correctly with _beta
    if adj_factor_returns.ndim == 1 and hasattr(_beta, "ndim") and _beta.ndim > 0:
        adj_factor_returns = adj_factor_returns[:, np.newaxis]
    alpha_series = adj_returns - (_beta * adj_factor_returns)

    out = np.subtract(
        np.power(np.add(nanmean(alpha_series, axis=0, out=out), 1, out=out), ann_factor, out=out),
        1,
        out=out,
    )

    if allocated_output and was_dataframe:
        out = pd.Series(out)

    if returns.ndim == 1:
        out = out.item()  # type: ignore[union-attr]

    return out


def alpha_beta_aligned(
    returns: np.ndarray,
    factor_returns: np.ndarray,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate annualized alpha and beta for already-aligned series.

    This function assumes that ``returns`` and ``factor_returns`` are
    already aligned NumPy arrays (or array-like) with matching shapes
    along the time dimension.

    Parameters
    ----------
    returns : np.ndarray
        Array of non-cumulative strategy returns. The first dimension is
        interpreted as time; any remaining dimensions correspond to
        different assets/strategies.
    factor_returns : np.ndarray
        Array of non-cumulative benchmark or factor returns, aligned with
        ``returns`` along the time dimension.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated output array of shape ``returns.shape[1:] +
        (2),``. If given, the result is written in-place into this array.

    Returns
    -------
    np.ndarray
        Array of shape ``returns.shape[1:] + (2),`` whose last dimension
        contains ``[alpha, beta]``.
    """
    if out is None:
        out = np.empty((*returns.shape[1:], 2), dtype="float64")

    b = beta_aligned(returns, factor_returns, risk_free, out=out[..., 1])
    alpha_aligned(
        returns,
        factor_returns,
        risk_free=risk_free,
        period=period,
        annualization=annualization,
        out=out[..., 0],
        _beta=b,
    )

    return out


def beta(
    returns: ReturnOrDataFrame,
    factor_returns: ReturnOrDataFrame,
    risk_free: float = 0.0,
    _period: str = DAILY,
    _annualization: float | None = None,
    out: np.ndarray | None = None,
) -> float | np.ndarray | pd.Series:
    """Calculate beta versus a benchmark.

    This mirrors ``empyrical.stats.beta``: non-ndarray inputs are first
    aligned, then :func:`beta_aligned` is called to compute the beta.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative benchmark or factor returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    _period : str, optional
        Deprecated. Kept for API compatibility and ignored.
    _annualization : float, optional
        Deprecated. Kept for API compatibility and ignored.
    out : np.ndarray, optional
        pre-allocated output array. If given, the result is
        written in-place into this array.

    Returns
    -------
    float or np.ndarray or pd.Series
        Beta of the strategy versus the benchmark. For 1D input a scalar
        is returned; for 2D input one value is returned per column.
    """
    if not (isinstance(returns, np.ndarray) and isinstance(factor_returns, np.ndarray)):
        returns, factor_returns = aligned_series(returns, factor_returns)

    return beta_aligned(returns, factor_returns, risk_free=risk_free, out=out)


def alpha(
    returns: ReturnOrDataFrame,
    factor_returns: ReturnOrDataFrame,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
    _beta: float | np.ndarray | None = None,
) -> float | np.ndarray | pd.Series:
    """Calculate annualized alpha versus a benchmark.

    This mirrors ``empyrical.stats.alpha``: non-ndarray inputs are first
    aligned, then :func:`alpha_aligned` is called to compute the
    annualized alpha.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative benchmark or factor returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated output array. If given, the result is
        written in-place into this array.
    _beta : float or np.ndarray, optional
        pre-computed beta used to avoid recomputing beta
        internally. Primarily intended for internal reuse.

    Returns
    -------
    float or np.ndarray or pd.Series
        Annualized alpha of the strategy versus the benchmark. For 1D
        input a scalar is returned; for 2D input one value is returned
        per column.
    """
    if not (isinstance(returns, np.ndarray) and isinstance(factor_returns, np.ndarray)):
        returns, factor_returns = aligned_series(returns, factor_returns)

    return alpha_aligned(
        returns, factor_returns, risk_free=risk_free, period=period, annualization=annualization, out=out, _beta=_beta
    )


def alpha_beta(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    factor_returns: pd.Series | pd.DataFrame | np.ndarray,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate annualized alpha and beta versus a benchmark.

    This is a convenience wrapper that aligns ``returns`` and
    ``factor_returns`` (if they are not already NumPy arrays) and then
    delegates to :func:`alpha_beta_aligned`.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative benchmark or factor returns, aligned to
        ``returns`` after preprocessing.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated output array. If given, the result is
        written in-place into this array.

    Returns
    -------
    np.ndarray
        Array of shape ``(..., 2)`` containing annualized alpha and beta
        in the last dimension. For 1D inputs this is length-2; for 2D
        inputs it has one row per column of ``returns``.
    """
    if not (isinstance(returns, np.ndarray) and isinstance(factor_returns, np.ndarray)):
        returns, factor_returns = aligned_series(returns, factor_returns)

    return alpha_beta_aligned(
        returns, factor_returns, risk_free=risk_free, period=period, annualization=annualization, out=out
    )


def _conditional_alpha_beta(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    condition_func: Callable[[np.ndarray], np.ndarray],
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate alpha and beta for a conditional subset of market periods.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.
    condition_func : callable
        Function that takes a numpy array of factor returns and returns
        a boolean mask selecting the desired market regime.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``).
    annualization : float, optional
        Custom annualization factor.
    out : np.ndarray, optional
        pre-allocated array of length 2.

    Returns
    -------
    np.ndarray
        Array ``[alpha, beta]``. Elements are ``NaN`` if insufficient data.
    """
    if out is None:
        out = np.empty((2,), dtype="float64")

    if isinstance(returns, pd.Series) and isinstance(factor_returns, pd.Series):
        returns, factor_returns = returns.align(factor_returns, join="inner")

    returns_array = np.asanyarray(returns)
    factor_array = np.asanyarray(factor_returns)

    mask = condition_func(factor_array)
    masked_returns = returns_array[mask]
    masked_factor = factor_array[mask]

    if len(masked_returns) < 2:
        out[0] = np.nan
        out[1] = np.nan
        return out

    valid_mask = ~(np.isnan(masked_returns) | np.isnan(masked_factor))
    returns_clean = masked_returns[valid_mask]
    factor_clean = masked_factor[valid_mask]

    if len(returns_clean) < 2:
        out[0] = np.nan
        out[1] = np.nan
        return out

    ann_factor = annualization_factor(period, annualization)

    returns_adj = returns_clean - risk_free
    factor_returns_adj = factor_clean - risk_free

    factor_var = np.var(factor_returns_adj, ddof=1)
    if factor_var == 0 or np.isnan(factor_var):
        out[0] = np.nan
        out[1] = np.nan
        return out

    beta_val = np.cov(returns_adj, factor_returns_adj)[0, 1] / factor_var

    alpha_series = returns_adj - (beta_val * factor_returns_adj)
    mean_alpha = np.mean(alpha_series)
    alpha_val = (1 + mean_alpha) ** ann_factor - 1

    out[0] = alpha_val
    out[1] = beta_val
    return out


def up_alpha_beta(
    returns: ReturnOrDataFrame,
    factor_returns: ReturnOrDataFrame,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate alpha and beta for up-market periods only.

    This helper restricts the sample to periods where the benchmark
    (factor) return is positive and then estimates alpha and beta using
    a single-factor model on excess returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``).
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated array of length 2, where index 0 receives
        alpha and index 1 receives beta.

    Returns
    -------
    np.ndarray
        Array ``[alpha, beta]`` for up-market periods. Elements are
        ``NaN`` if there is insufficient data.
    """
    return _conditional_alpha_beta(returns, factor_returns, lambda f: f > 0, risk_free, period, annualization, out)


def down_alpha_beta(
    returns: ReturnOrDataFrame,
    factor_returns: ReturnOrDataFrame,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate alpha and beta for down-market periods only.

    This helper restricts the sample to periods where the benchmark
    (factor) return is non-positive and then estimates alpha and beta
    using a single-factor model on excess returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``).
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated array of length 2, where index 0 receives
        alpha and index 1 receives beta.

    Returns
    -------
    np.ndarray
        Array ``[alpha, beta]`` for down-market periods. Elements are
        ``NaN`` if there is insufficient data.
    """
    return _conditional_alpha_beta(returns, factor_returns, lambda f: f <= 0, risk_free, period, annualization, out)


def annual_alpha(
    returns: pd.Series,
    factor_returns: pd.Series,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series:
    """Determine the annual alpha for each calendar year.

    This groups aligned strategy and benchmark returns by calendar year
    and computes :func:`alpha` for each year.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative strategy returns indexed by date.
    factor_returns : pd.Series
        Non-cumulative benchmark or factor returns indexed by date.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``).
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.

    Returns
    -------
    pd.Series
        Annual alpha by calendar year.
    """
    if len(returns) < 1:
        return pd.Series([], dtype=float)

    if not isinstance(returns.index, pd.DatetimeIndex):
        return pd.Series([], dtype=float)

    returns, factor_returns = aligned_series(returns, factor_returns)
    if len(returns) < 1:
        return pd.Series([], dtype=float)

    grouped = returns.groupby(returns.index.year)
    factor_grouped = factor_returns.groupby(factor_returns.index.year)

    annual_alphas = []
    for year in grouped.groups:
        if year in factor_grouped.groups:
            returns_for_year = grouped.get_group(year)
            factor_for_year = factor_grouped.get_group(year)
            alpha_val = alpha(returns_for_year, factor_for_year, risk_free, period, annualization)
            annual_alphas.append((year, alpha_val))

    if not annual_alphas:
        return pd.Series([], dtype=float)

    years, alphas = zip(*annual_alphas, strict=False)
    return pd.Series(alphas, index=years)


def annual_beta(
    returns: pd.Series,
    factor_returns: pd.Series,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> pd.Series:
    """Determine the annual beta for each calendar year.

    This groups aligned strategy and benchmark returns by calendar year
    and computes :func:`beta` for each year.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative strategy returns indexed by date.
    factor_returns : pd.Series
        Non-cumulative benchmark or factor returns indexed by date.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``).
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.

    Returns
    -------
    pd.Series
        Annual beta by calendar year.
    """
    if len(returns) < 1:
        return pd.Series([], dtype=float)

    if not isinstance(returns.index, pd.DatetimeIndex):
        return pd.Series([], dtype=float)

    returns, factor_returns = aligned_series(returns, factor_returns)
    if len(returns) < 1:
        return pd.Series([], dtype=float)

    grouped = returns.groupby(returns.index.year)
    factor_grouped = factor_returns.groupby(factor_returns.index.year)

    annual_betas = []
    for year in grouped.groups:
        if year in factor_grouped.groups:
            year_returns = grouped.get_group(year)
            year_factor = factor_grouped.get_group(year)
            beta_val = beta(year_returns, year_factor, risk_free, period, annualization)
            annual_betas.append((year, beta_val))

    if not annual_betas:
        return pd.Series([], dtype=float)

    years, betas = zip(*annual_betas, strict=False)
    return pd.Series(betas, index=years)


def alpha_percentile_rank(
    strategy_returns: pd.Series,
    all_strategies_returns: list[pd.Series],
    factor_returns: pd.Series,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> float:
    """Calculate the percentile rank of alpha versus a peer universe.

    This computes the strategy's alpha and compares it to the alphas of
    all peer strategies, returning the percentile rank.

    Parameters
    ----------
    strategy_returns : pd.Series
        Non-cumulative returns of the strategy being evaluated.
    all_strategies_returns : list of pd.Series
        Non-cumulative returns of all peer strategies.
    factor_returns : pd.Series
        Non-cumulative benchmark or factor returns.
    risk_free : float, optional
        Risk-free rate (default 0.0).
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : int, optional
        Factor to convert period returns to yearly returns.

    Returns
    -------
    float
        Percentile rank of the strategy's alpha in [0, 1], or ``NaN``
        if insufficient data.
    """
    if len(strategy_returns) < 3:
        return np.nan

    strategy_alpha = alpha(strategy_returns, factor_returns, risk_free, period, annualization)

    if np.isnan(strategy_alpha):
        return np.nan

    all_alphas = []
    for other_returns in all_strategies_returns:
        if len(other_returns) < 3:
            continue
        other_alpha = alpha(other_returns, factor_returns, risk_free, period, annualization)
        if not np.isnan(other_alpha):
            all_alphas.append(other_alpha)

    if len(all_alphas) == 0:
        return np.nan

    rank = sum(1 for a in all_alphas if a < strategy_alpha)
    percentile = rank / len(all_alphas)

    return float(percentile)
