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

"""Statistical metrics."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from fincore.constants import DAILY
from fincore.metrics.basic import aligned_series

__all__ = [
    "bond_market_correlation",
    "capm_r_squared",
    "common_sense_ratio",
    "futures_market_correlation",
    "hurst_exponent",
    "kurtosis",
    "loss_rate",
    "normalize",
    "r_cubed",
    "r_cubed_turtle",
    "relative_win_rate",
    "serial_correlation",
    "skewness",
    "stock_market_correlation",
    "stutzer_index",
    "tracking_difference",
    "var_cov_var_normal",
    "win_rate",
]


def _safe_correlation(x, y):
    """Compute Pearson correlation safely without emitting runtime warnings.

    Returns ``NaN`` for insufficient data or constant series.
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    valid_mask = ~(np.isnan(x_arr) | np.isnan(y_arr))
    if valid_mask.sum() < 2:
        return np.nan

    x_clean = x_arr[valid_mask]
    y_clean = y_arr[valid_mask]

    if np.std(x_clean) < 1e-15 or np.std(y_clean) < 1e-15:
        return np.nan

    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(x_clean, y_clean)[0, 1]

    return float(corr) if np.isfinite(corr) else np.nan


def skewness(returns: pd.Series | np.ndarray) -> float:
    """Calculate the skewness of a return series.

    This is a thin wrapper around :func:`scipy.stats.skew` with
    ``nan_policy="omit"``.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative returns.

    Returns
    -------
    float
        Sample skewness of the return distribution, or ``NaN`` if there
        are fewer than three observations.
    """
    from scipy import stats as _stats

    if len(returns) < 3:
        return np.nan
    return _stats.skew(returns, nan_policy="omit")


def kurtosis(returns: pd.Series | np.ndarray) -> float:
    """Calculate the kurtosis of a return series.

    This is a thin wrapper around :func:`scipy.stats.kurtosis` with
    ``nan_policy="omit"``.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative returns.

    Returns
    -------
    float
        Sample excess kurtosis of the return distribution, or ``NaN`` if
        there are fewer than four observations.
    """
    from scipy import stats as _stats

    if len(returns) < 4:
        return np.nan
    return _stats.kurtosis(returns, nan_policy="omit")


def hurst_exponent(returns: pd.Series | np.ndarray) -> float:
    """Estimate the Hurst exponent of a return series.

    The Hurst exponent is estimated via a rescaled range (R/S) analysis
    with safeguards for short and noisy series. Values near 0.5 indicate
    a random walk; values above 0.5 suggest persistence; values below 0.5
    suggest mean reversion.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative returns.

    Returns
    -------
    float
        Estimated Hurst exponent in the interval [0, 1], or ``NaN`` when
        there is insufficient data.
    """
    min_length = 8
    if len(returns) < min_length:
        return np.nan

    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)

    returns_array = returns.values
    returns_clean = returns_array[~np.isnan(returns_array)]

    if len(returns_clean) < min_length:
        return np.nan

    try:
        mean_return = np.mean(returns_clean)
        y_cumsum = np.cumsum(returns_clean - mean_return)
        r_range = np.max(y_cumsum) - np.min(y_cumsum)
        s_std = np.std(returns_clean, ddof=1)

        if s_std == 0 or r_range == 0:
            return np.nan

        n = len(returns_clean)
        max_lag = max(n // 3, 3)
        min_lag = 2

        max_points = 30
        if max_lag - min_lag + 1 > max_points:
            lags = np.unique(np.geomspace(min_lag, max_lag, num=max_points).astype(int))
        else:
            lags = range(min_lag, max_lag + 1)  # type: ignore[assignment]
        rs_values = []

        for lag in lags:
            n_subseries = n // lag
            if n_subseries < 1:
                continue

            # Vectorized: reshape into (n_subseries, lag) matrix
            block = returns_clean[: n_subseries * lag].reshape(n_subseries, lag)
            means = block.mean(axis=1, keepdims=True)
            cumdevs = np.cumsum(block - means, axis=1)
            r_sub = cumdevs.max(axis=1) - cumdevs.min(axis=1)
            s_sub = block.std(axis=1, ddof=1)

            valid = (s_sub > 0) & (r_sub > 0)
            if valid.any():
                rs_values.append((lag, float(np.mean(r_sub[valid] / s_sub[valid]))))

        if len(rs_values) < 2:
            if s_std > 0 and r_range > 0:
                hurst = 0.5 + np.log(r_range / s_std) / np.log(2.0 * n)
                hurst = max(0.0, min(1.0, hurst))
                return float(hurst)
            return np.nan  # pragma: no cover -- Defensive edge case

        lags_array = np.array([item[0] for item in rs_values])
        rs_array = np.array([item[1] for item in rs_values])

        valid_mask = (lags_array > 0) & (rs_array > 0)
        lags_array = lags_array[valid_mask]
        rs_array = rs_array[valid_mask]

        if len(lags_array) < 2:
            return np.nan

        log_lags = np.log(lags_array)
        log_rs = np.log(rs_array)

        poly = np.polyfit(log_lags, log_rs, 1)
        hurst = poly[0]

        hurst = max(0.0, min(1.0, hurst))

        return float(hurst)

    except (ValueError, FloatingPointError, ZeroDivisionError, RuntimeError) as e:
        logger.debug("hurst_exponent failed: %s", e)
        return np.nan


def stutzer_index(returns: pd.Series | np.ndarray, target_return: float = 0.0) -> float:
    """Calculate the Stutzer index.

    The Stutzer index is a downside-risk-adjusted performance measure
    based on an exponential tilting of the return distribution.

    Formula
    -------
    I_P = max_θ { -log(mean(exp(θ × r_t))) }
    Stutzer = (|r̄| / r̄) × sqrt(2 × I_P)

    where r_t are the excess returns and r̄ is their mean.

    Reference: Stutzer, M. (2000). "A Portfolio Performance Index."
    Financial Analysts Journal, 56(3), 52-61.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    target_return : float, optional
        Target or benchmark return used to compute excess returns.

    Returns
    -------
    float
        Stutzer index estimate, or ``NaN`` if the optimization fails or
        there is insufficient data.
    """
    if len(returns) < 2:
        return np.nan

    excess_returns = np.asanyarray(returns) - target_return
    excess_returns = excess_returns[~np.isnan(excess_returns)]

    if len(excess_returns) < 2:
        return np.nan

    mean_excess = np.mean(excess_returns)

    if abs(mean_excess) < 1e-15:
        return 0.0

    try:
        from scipy.optimize import minimize_scalar

        def neg_ip(theta):
            """Negative of I_P: we minimize -I_P to find max I_P."""
            exp_theta_r = np.exp(theta * excess_returns)
            if np.any(np.isinf(exp_theta_r)) or np.any(np.isnan(exp_theta_r)):
                return 0.0
            return np.log(exp_theta_r.mean())

        if mean_excess > 0:
            result = minimize_scalar(neg_ip, bounds=(-50, -1e-10), method="bounded")
        else:
            result = minimize_scalar(neg_ip, bounds=(1e-10, 50), method="bounded")

        if result.success:
            ip = -result.fun
            if ip < 0:
                ip = 0.0
            sign = 1.0 if mean_excess > 0 else -1.0
            return sign * np.sqrt(2 * ip)
        return np.nan
    except (ValueError, FloatingPointError, ZeroDivisionError, RuntimeError) as e:
        logger.debug("stutzer_index failed: %s", e)
        return np.nan


def serial_correlation(returns: pd.Series | np.ndarray, lag: int = 1) -> float:
    """Determine the serial correlation of returns.

    This computes the correlation between ``r[t]`` and ``r[t-lag]``.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    lag : int, optional
        Number of periods to lag. Default is 1.

    Returns
    -------
    float
        Pearson correlation coefficient between returns and lagged returns,
        or ``NaN`` if there are fewer than ``lag + 1`` valid observations.
    """
    if returns is None:
        return np.nan

    if lag is None or lag < 1:
        return np.nan

    arr = np.asarray(returns, dtype=float)
    if arr.size == 0:
        return np.nan

    mask = ~np.isnan(arr)
    arr = arr[mask]

    if arr.size <= lag:
        return np.nan

    arr_lagged = arr[lag:]
    arr_early = arr[:-lag]

    if arr_lagged.size < 2:
        return np.nan

    return _safe_correlation(arr_lagged, arr_early)


def _market_correlation(returns, benchmark_returns):
    """Compute Pearson correlation between strategy and benchmark returns.

    Shared implementation for stock/bond/futures market correlation.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    benchmark_returns : array-like or pd.Series
        Non-cumulative benchmark returns.

    Returns
    -------
    float
        Pearson correlation coefficient in ``[-1, 1]``, or ``NaN`` if
        there are fewer than two valid observations.
    """
    if returns is None or benchmark_returns is None:
        return np.nan

    if isinstance(returns, pd.Series) and isinstance(benchmark_returns, pd.Series):
        returns, benchmark_returns = returns.align(benchmark_returns, join="inner")

    if len(returns) < 2 or len(benchmark_returns) < 2:
        return np.nan

    return _safe_correlation(returns, benchmark_returns)


def stock_market_correlation(returns: pd.Series | np.ndarray, market_returns: pd.Series | np.ndarray) -> float:
    """Determine the correlation between strategy and stock market returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    market_returns : array-like or pd.Series
        Non-cumulative stock market (benchmark) returns.

    Returns
    -------
    float
        Pearson correlation coefficient in ``[-1, 1]`` between strategy
        and market returns, or ``NaN`` if there are fewer than two valid
        observations.
    """
    return _market_correlation(returns, market_returns)


def bond_market_correlation(returns: pd.Series | np.ndarray, bond_returns: pd.Series | np.ndarray) -> float:
    """Determine the correlation between strategy and bond market returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    bond_returns : array-like or pd.Series
        Non-cumulative bond market benchmark returns.

    Returns
    -------
    float
        Pearson correlation coefficient in ``[-1, 1]`` between strategy
        and bond market returns, or ``NaN`` if there are fewer than two
        valid observations.
    """
    return _market_correlation(returns, bond_returns)


def futures_market_correlation(returns: pd.Series | np.ndarray, futures_returns: pd.Series | np.ndarray) -> float:
    """Determine the correlation between strategy and futures market returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    futures_returns : array-like or pd.Series
        Non-cumulative futures market benchmark returns.

    Returns
    -------
    float
        Pearson correlation coefficient in ``[-1, 1]`` between strategy
        and futures market returns, or ``NaN`` if there are fewer than two
        valid observations.
    """
    return _market_correlation(returns, futures_returns)


def win_rate(returns: pd.Series | np.ndarray) -> float:
    """Calculate the percentage of positive return observations.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.

    Returns
    -------
    float
        Fraction of observations with strictly positive returns in
        ``[0, 1]``, or ``NaN`` if there are no valid observations.
    """
    if len(returns) < 1:
        return np.nan

    returns_array = np.asanyarray(returns)

    positive_count = np.sum(returns_array > 0)
    total_count = np.sum(~np.isnan(returns_array))

    if total_count == 0:
        return np.nan

    win_rate_value = positive_count / total_count

    if returns_array.ndim == 1:
        val = win_rate_value.item() if isinstance(win_rate_value, np.ndarray) else win_rate_value
        return float(val)
    return float(win_rate_value)


def loss_rate(returns: pd.Series | np.ndarray) -> float:
    """Calculate the percentage of negative return observations.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.

    Returns
    -------
    float
        Fraction of observations with strictly negative returns in
        ``[0, 1]``, or ``NaN`` if there are no valid observations.
    """
    if len(returns) < 1:
        return np.nan

    returns_array = np.asanyarray(returns)

    negative_count = np.sum(returns_array < 0)
    total_count = np.sum(~np.isnan(returns_array))

    if total_count == 0:
        return np.nan

    loss_rate_value = negative_count / total_count

    if returns_array.ndim == 1:
        val = loss_rate_value.item() if isinstance(loss_rate_value, np.ndarray) else loss_rate_value
        return float(val)
    return float(loss_rate_value)


def relative_win_rate(returns: pd.Series | np.ndarray, factor_returns: pd.Series | np.ndarray) -> float:
    """Calculate the win rate of strategy returns relative to a benchmark.

    The relative win rate is the fraction of periods where the strategy
    return exceeds the benchmark return.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark returns.

    Returns
    -------
    float
        Fraction of observations where ``returns > factor_returns`` in
        ``[0, 1]``, or ``NaN`` if there are no valid observations.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    ret_arr = np.asarray(returns_aligned, dtype=float)
    fac_arr = np.asarray(factor_aligned, dtype=float)
    mask = ~(np.isnan(ret_arr) | np.isnan(fac_arr))

    total = mask.sum()
    if total == 0:
        return np.nan

    win_count = np.sum(ret_arr[mask] > fac_arr[mask])
    return float(win_count / total)


def r_cubed(returns: pd.Series | np.ndarray, factor_returns: pd.Series | np.ndarray) -> float:
    """Calculate the R-cubed (R³) measure.

    R³ is defined as the cube of the correlation between strategy returns
    and benchmark returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.

    Returns
    -------
    float
        Cube of the Pearson correlation coefficient, or ``NaN`` if there
        is insufficient data.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    ret_arr = np.asarray(returns_aligned, dtype=float)
    fac_arr = np.asarray(factor_aligned, dtype=float)
    mask = ~(np.isnan(ret_arr) | np.isnan(fac_arr))
    if mask.sum() < 2:
        return np.nan

    correlation = _safe_correlation(ret_arr[mask], fac_arr[mask])
    return correlation**3 if not np.isnan(correlation) else np.nan


def r_cubed_turtle(returns: pd.Series | np.ndarray, period: str = DAILY, annualization: float | None = None) -> float:
    """Calculate the R-cubed measure from the Turtle Trading system.

    R³ (turtle) is defined as the Regression Annual Return (RAR) divided
    by the average maximum annual drawdown.

    RAR is the slope of a linear regression of cumulative NAV against time,
    annualized.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    period : str, optional
        Frequency of the input data. Default is ``DAILY``.
    annualization : float, optional
        Custom annualization factor.

    Returns
    -------
    float
        R³ turtle measure, or ``NaN`` if insufficient data.
    """
    from fincore.metrics.basic import annualization_factor
    from fincore.metrics.returns import cum_returns

    if len(returns) < 2:
        return np.nan

    ann_factor = annualization_factor(period, annualization)
    nav = cum_returns(returns, starting_value=1.0)
    nav_arr = np.asarray(nav, dtype=float)
    t = np.arange(len(nav_arr), dtype=float)

    mask = ~np.isnan(nav_arr)
    if mask.sum() < 2:
        return np.nan

    from scipy import stats as _stats

    slope, _, _, _, _ = _stats.linregress(t[mask], nav_arr[mask])
    rar = slope * ann_factor

    if isinstance(returns, pd.Series) and hasattr(returns.index, "year"):
        years = returns.index.year.unique()
    else:
        n_obs = len(returns)
        n_years = max(1, round(n_obs / ann_factor))
        years = range(n_years)

    if len(years) < 1:
        return np.nan

    from fincore.metrics.drawdown import max_drawdown

    max_dds = []
    if isinstance(returns, pd.Series) and hasattr(returns.index, "year"):
        for yr in years:
            yr_returns = returns[returns.index.year == yr]
            if len(yr_returns) > 0:
                dd = max_drawdown(yr_returns)
                max_dds.append(abs(dd))
    else:
        returns_arr = np.asanyarray(returns)
        chunk_size = max(1, int(ann_factor))
        for i in range(0, len(returns_arr), chunk_size):
            chunk = returns_arr[i : i + chunk_size]
            if len(chunk) > 0:
                dd = max_drawdown(pd.Series(chunk))
                max_dds.append(abs(dd))

    if len(max_dds) == 0:
        return np.nan

    avg_max_dd = np.mean(max_dds)
    if avg_max_dd < 1e-15:
        return np.inf if rar > 0 else np.nan

    return rar / avg_max_dd


def capm_r_squared(returns: pd.Series | np.ndarray, factor_returns: pd.Series | np.ndarray) -> float:
    """Calculate the CAPM R-squared.

    R² = (β × σ_B / σ_P)², measuring the proportion of strategy return
    variance explained by market (systematic) risk.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.

    Returns
    -------
    float
        CAPM R-squared in ``[0, 1]``, or ``NaN`` if insufficient data.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    ret_arr = np.asarray(returns_aligned, dtype=float)
    fac_arr = np.asarray(factor_aligned, dtype=float)
    mask = ~(np.isnan(ret_arr) | np.isnan(fac_arr))
    if mask.sum() < 2:
        return np.nan

    ret_clean = ret_arr[mask]
    fac_clean = fac_arr[mask]

    sigma_p = np.std(ret_clean, ddof=1)
    sigma_b = np.std(fac_clean, ddof=1)

    if sigma_p < 1e-15:
        return np.nan

    cov = np.cov(ret_clean, fac_clean, ddof=1)[0, 1]
    var_b = sigma_b**2
    if var_b < 1e-30:
        return np.nan
    beta = cov / var_b

    r_sq = (beta * sigma_b / sigma_p) ** 2
    return float(np.clip(r_sq, 0.0, 1.0))


def tracking_difference(returns: pd.Series | np.ndarray, factor_returns: pd.Series | np.ndarray) -> float:
    """Calculate tracking difference in cumulative returns.

    Tracking difference is defined as the cumulative strategy return minus
    the cumulative benchmark return over the full sample.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.

    Returns
    -------
    float
        Difference between cumulative strategy and benchmark returns.
    """
    from fincore.metrics.returns import cum_returns_final

    if len(returns) < 1:
        return np.nan

    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    cum_strategy = cum_returns_final(returns_aligned, starting_value=0)
    cum_benchmark = cum_returns_final(factor_aligned, starting_value=0)

    result = cum_strategy - cum_benchmark
    if not isinstance(result, (float, np.floating)):
        result = result.item()
    return result  # type: ignore[return-value]


def common_sense_ratio(returns: pd.Series | np.ndarray) -> float:
    """Calculate the common sense ratio.

    Delegates to :func:`fincore.metrics.ratios.common_sense_ratio`.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.

    Returns
    -------
    float
        Common sense ratio, or ``NaN`` if there is insufficient data.
    """
    from fincore.metrics.ratios import common_sense_ratio as _csr

    return _csr(returns)


def var_cov_var_normal(p: float, c: float, mu: float = 0, sigma: float = 1) -> float:
    """Calculate variance-covariance of daily Value-at-Risk in a portfolio.

    Delegates to :func:`fincore.metrics.risk.var_cov_var_normal`.

    Parameters
    ----------
    p : float
        Portfolio value.
    c : float
        Confidence level.
    mu : float, optional
        Mean. Default is 0.
    sigma : float, optional
        Standard deviation. Default is 1.

    Returns
    -------
    float
        Value-at-Risk.
    """
    from fincore.metrics.risk import var_cov_var_normal as _vcv

    return _vcv(p, c, mu, sigma)


def normalize(returns: pd.Series | np.ndarray, starting_value: float = 1) -> pd.Series | np.ndarray:
    """Normalize a returns series to start at a given value.

    Delegates to :func:`fincore.metrics.returns.normalize`.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    starting_value : float, optional
        Starting value for the normalized series. Default is 1.

    Returns
    -------
    pd.Series or np.ndarray
        Normalized cumulative returns starting at ``starting_value``.
    """
    from fincore.metrics.returns import normalize as _normalize

    return _normalize(returns, starting_value=starting_value)
