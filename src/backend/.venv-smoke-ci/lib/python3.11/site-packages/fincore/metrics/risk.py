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

"""Risk metrics."""

from __future__ import annotations

import logging
from sys import float_info

import numpy as np
import pandas as pd

from fincore.constants import DAILY
from fincore.metrics.basic import adjust_returns, aligned_series, annualization_factor
from fincore.utils import nanmean, nanstd

logger = logging.getLogger(__name__)

__all__ = [
    "annual_volatility",
    "beta_fragility_heuristic",
    "beta_fragility_heuristic_aligned",
    "conditional_value_at_risk",
    "downside_risk",
    "gpd_risk_estimates",
    "gpd_risk_estimates_aligned",
    "residual_risk",
    "tail_ratio",
    "tracking_error",
    "trading_value_at_risk",
    "value_at_risk",
    "var_cov_var_normal",
    "var_excess_return",
]


def annual_volatility(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    period: str = DAILY,
    volatility_power: float = 2.0,
    annualization: float | None = None,
    out: np.ndarray | None = None,
    *,
    alpha_: float | None = None,
) -> float | np.ndarray:
    """Determine the annualized volatility of a return series.

    Volatility is computed as the standard deviation of returns scaled by
    an annualization factor based on ``period`` or ``annualization``.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative simple returns.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    volatility_power : float, optional
        Power used when scaling volatility (for example 2.0 for variance,
        1.0 for standard deviation). Defaults to 2.0 to match the
        original empyrical implementation. Named to avoid confusion with
        alpha (excess return) in finance.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        pre-allocated output array. If provided, the result is
        written in-place into this array.
    alpha_ : float, optional
        Deprecated. Use ``volatility_power`` instead. If provided, takes
        precedence over ``volatility_power`` for backward compatibility.

    Returns
    -------
    float or np.ndarray or pd.Series
        Annualized volatility. For 1D input a scalar is returned; for 2D
        input one value is returned per column.
    """
    import warnings

    if alpha_ is not None:
        warnings.warn(
            "The parameter 'alpha_' is deprecated. Use 'volatility_power' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        volatility_power = alpha_
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])
    assert out is not None

    returns_1d = returns.ndim == 1

    if len(returns) < 2:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out  # type: ignore[return-value]

    ann_factor = annualization_factor(period, annualization)
    nanstd(returns, ddof=1, axis=0, out=out)
    out = np.multiply(out, ann_factor ** (1.0 / volatility_power), out=out)
    if returns_1d:
        out = out.item()  # type: ignore[union-attr]
    return out  # type: ignore[return-value]


def downside_risk(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    required_return: float = 0,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> float | np.ndarray | pd.Series:
    """Determine the annualized downside deviation below a threshold.

    Downside risk is computed as the annualized standard deviation of
    returns that fall below ``required_return``.

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative strategy returns.
    required_return : float, optional
        Minimum acceptable return threshold. Only returns below this
        value contribute to the downside risk. Default is 0.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        Optional pre-allocated output array. If given, the result is
        written in-place into this array.

    Returns
    -------
    float or np.ndarray or pd.Series
        Annualized downside risk. For 1D input a scalar is returned; for
        2D input one value is returned per column. Returns 0 when all
        returns are above ``required_return`` (no downside component).
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])
    assert out is not None

    returns_1d = returns.ndim == 1

    if len(returns) < 1:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out  # type: ignore[return-value]
    # Reject scalar required_return that is nan/inf (array required_return may have NaN per-period)
    req_arr = np.asarray(required_return)
    if req_arr.ndim == 0 and not np.isfinite(req_arr.item()):
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        elif isinstance(returns, pd.DataFrame):
            out = pd.Series(out, index=returns.columns)
        return out  # type: ignore[return-value]

    ann_factor = annualization_factor(period, annualization)

    downside_diff = np.clip(
        adjust_returns(np.asanyarray(returns), np.asanyarray(required_return)),
        -np.inf,
        0,
    )

    np.square(downside_diff, out=downside_diff)
    nanmean(downside_diff, axis=0, out=out)
    np.sqrt(out, out=out)
    np.multiply(out, np.sqrt(ann_factor), out=out)

    if returns_1d:
        out = out.item()
    elif isinstance(returns, pd.DataFrame):
        out = pd.Series(out, index=returns.columns)
    return out


def value_at_risk(returns: pd.Series | np.ndarray, cutoff: float = 0.05) -> float:
    """Calculate the (historical) value at risk (VaR) of returns.

    VaR is estimated as the ``cutoff``-percentile of the return
    distribution.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    cutoff : float, optional
        Left-tail probability level in [0, 1]. For example ``0.05``
        selects the 5th percentile. Values outside [0, 1] return NaN.
        Default is 0.05.

    Returns
    -------
    float
        Historical VaR at the given confidence level, or ``NaN`` if there
        are no observations or cutoff is invalid.
    """
    if len(returns) < 1:
        return np.nan
    if not (0 <= cutoff <= 1):
        return np.nan
    arr = np.asanyarray(returns)
    if not np.all(np.isfinite(arr)):
        return np.nan
    return float(np.percentile(arr, cutoff * 100))


def conditional_value_at_risk(returns: pd.Series | np.ndarray, cutoff: float = 0.05) -> float:
    """Calculate the conditional value at risk (CVaR) of returns.

    CVaR (also known as Expected Shortfall) is the expected return
    conditional on the return being at or below the VaR threshold.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    cutoff : float, optional
        Left-tail probability level in [0, 1]. Values outside [0, 1]
        return NaN. Default is 0.05.

    Returns
    -------
    float
        Conditional VaR (expected shortfall) at the given confidence
        level, or ``NaN`` if there are no observations or cutoff is invalid.
    """
    if len(returns) < 1:
        return np.nan
    if not (0 <= cutoff <= 1):
        return np.nan
    arr = np.asanyarray(returns)
    if not np.all(np.isfinite(arr)):
        return np.nan
    cutoff_index = value_at_risk(returns, cutoff=cutoff)
    return np.mean(returns[returns <= cutoff_index])


def tail_ratio(returns: pd.Series | np.ndarray) -> float:
    """Determine the ratio of right- to left-tail percentiles of returns.

    The tail ratio is defined as the absolute value of the 95th
    percentile divided by the absolute value of the 5th percentile.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.

    Returns
    -------
    float
        Tail ratio, or ``NaN`` if there are no valid observations.
    """
    if len(returns) < 1:
        return np.nan

    returns = np.asanyarray(returns)
    returns = returns[~np.isnan(returns)]
    if len(returns) < 1:
        return np.nan

    left_tail = np.abs(np.percentile(returns, 5))
    if left_tail == 0:
        return np.nan
    return np.abs(np.percentile(returns, 95)) / left_tail


def tracking_error(
    returns: pd.Series | pd.DataFrame | np.ndarray,
    factor_returns: pd.Series | pd.DataFrame | np.ndarray,
    period: str = DAILY,
    annualization: float | None = None,
    out: np.ndarray | None = None,
) -> float | np.ndarray:
    """Determine the annualized tracking error versus a benchmark.

    Tracking error is defined as the annualized standard deviation of
    the active returns (strategy minus benchmark).

    Parameters
    ----------
    returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series or pd.DataFrame
        Non-cumulative benchmark or factor returns.
    period : str, optional
        Frequency of the input data (for example ``DAILY``). Used to
        infer the annualization factor when ``annualization`` is ``None``.
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.
    out : np.ndarray, optional
        Optional pre-allocated output array. If given, the result is
        written in-place into this array.

    Returns
    -------
    float or np.ndarray
        Annualized tracking error. For 1D input a scalar is returned; for
        2D input one value is returned per column.
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])
    assert out is not None

    returns_1d = returns.ndim == 1

    if len(returns) < 2:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out  # type: ignore[return-value]

    returns, factor_returns = aligned_series(returns, factor_returns)
    active_return = adjust_returns(returns, factor_returns)
    ann_factor = annualization_factor(period, annualization)

    nanstd(active_return, ddof=1, axis=0, out=out)
    np.multiply(out, np.sqrt(ann_factor), out=out)

    if returns_1d:
        out = out.item()

    return out  # type: ignore[return-value]


def residual_risk(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> float:
    """Calculate annualized residual risk (idiosyncratic risk).

    Residual risk is the standard deviation of regression residuals
    from a single-factor regression of excess returns on benchmark
    excess returns.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.
    period : str, optional
        Frequency of the returns (default 'daily').
    annualization : float, optional
        Custom annualization factor. If provided, this value is used
        directly instead of inferring it from ``period``.

    Returns
    -------
    float
        Annualized residual risk, or ``NaN`` if there are fewer than two
        aligned observations.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    # `aligned_series` may return a union index for Series inputs; ensure we only
    # compute the regression on paired, finite observations.
    if isinstance(returns_aligned, (pd.Series, pd.DataFrame)) or isinstance(factor_aligned, (pd.Series, pd.DataFrame)):
        df = pd.concat([pd.Series(returns_aligned), pd.Series(factor_aligned)], axis=1, sort=False)
        df = df.dropna()
        if len(df) < 2:
            return np.nan
        excess_returns = df.iloc[:, 0] - risk_free
        excess_factor = df.iloc[:, 1] - risk_free
    else:
        ret_arr = np.asanyarray(returns_aligned, dtype=float)
        fac_arr = np.asanyarray(factor_aligned, dtype=float)
        mask = np.isfinite(ret_arr) & np.isfinite(fac_arr)
        if mask.sum() < 2:
            return np.nan
        excess_returns = ret_arr[mask] - risk_free
        excess_factor = fac_arr[mask] - risk_free

    from fincore.metrics.alpha_beta import beta_aligned

    beta_val = beta_aligned(np.asanyarray(excess_returns), np.asanyarray(excess_factor))
    predicted_returns = beta_val * excess_factor
    residuals = excess_returns - predicted_returns

    ann_factor = annualization_factor(period, annualization)
    return np.std(residuals, ddof=1) * np.sqrt(ann_factor)


def var_excess_return(
    returns: pd.Series | np.ndarray,
    cutoff: float = 0.05,
    risk_free: float = 0.0,
    period: str = DAILY,
    annualization: float | None = None,
) -> float:
    """Calculate the excess-return-on-VaR ratio.

    Defined as ``(annualized_return - risk_free) / abs(VaR)``, where VaR
    is the historical Value at Risk at the given cutoff level.

    Reference: ER-VaR = (r_annual - rf) / |VaR|

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    cutoff : float, optional
        Left-tail probability level in (0, 1). Default is 0.05.
    risk_free : float, optional
        Annual risk-free rate. Default is 0.0.
    period : str, optional
        Frequency of the input data. Default is ``DAILY``.
    annualization : float, optional
        Custom annualization factor.

    Returns
    -------
    float
        Excess-return-on-VaR ratio, or ``NaN`` if there are fewer than
        two observations or VaR is zero.
    """
    if len(returns) < 2:
        return np.nan

    from fincore.metrics.yearly import annual_return

    ann_ret = annual_return(returns, period=period, annualization=annualization)
    var_value = value_at_risk(returns, cutoff=cutoff)

    if var_value == 0 or np.isnan(var_value) or np.isnan(ann_ret):
        return np.nan

    return (ann_ret - risk_free) / abs(var_value)  # type: ignore[return-value]


def var_cov_var_normal(p: float, c: float, mu: float = 0, sigma: float = 1) -> float:
    """Calculate parametric Value at Risk using the normal distribution.

    Parameters
    ----------
    p : float
        Portfolio value.
    c : float
        Confidence level (e.g., 0.99 for 99% VaR).
    mu : float, optional
        Expected return. Default is 0.
    sigma : float, optional
        Standard deviation of returns. Default is 1.

    Returns
    -------
    float
        Parametric VaR at the given confidence level.
    """
    from scipy import stats as _stats

    alpha = _stats.norm.ppf(1 - c, mu, sigma)
    return float(p - p * (alpha + 1))


def _gpd_loglikelihood_scale_and_shape(scale: float, shape: float, price_data: np.ndarray) -> float:
    """GPD log-likelihood when both scale and shape are non-zero."""
    n = len(price_data)
    result = -1 * float_info.max
    if scale != 0:
        param_factor = shape / scale
        if shape != 0 and param_factor >= 0 and scale >= 0:
            result = (-n * np.log(scale)) - (((1 / shape) + 1) * (np.log((shape / scale * price_data) + 1)).sum())
    return result


def _gpd_loglikelihood_scale_only(scale: float, price_data: np.ndarray) -> float:
    """GPD log-likelihood when shape is zero (exponential tail)."""
    n = len(price_data)
    data_sum = price_data.sum()
    result = -1 * float_info.max
    if scale >= 0:
        result = (-n * np.log(scale)) - (data_sum / scale)
    return result


def _gpd_var_calculator(
    threshold: float,
    scale_param: float,
    shape_param: float,
    probability: float,
    total_n: int,
    exceedance_n: int,
) -> float:
    """Compute VaR from GPD parameters."""
    result = 0.0
    if exceedance_n > 0 and shape_param > 0:
        param_ratio = scale_param / shape_param
        prob_ratio = (total_n / exceedance_n) * probability
        result = threshold + (param_ratio * (pow(prob_ratio, -shape_param) - 1))
    return result


def _gpd_es_calculator(
    var_estimate: float,
    threshold: float,
    scale_param: float,
    shape_param: float,
) -> float:
    """Compute Expected Shortfall from GPD parameters."""
    result = 0.0
    if (1 - shape_param) != 0:
        var_ratio = var_estimate / (1 - shape_param)
        param_ratio = (scale_param - (shape_param * threshold)) / (1 - shape_param)
        result = var_ratio + param_ratio
    return result


def _gpd_loglikelihood(params: np.ndarray, price_data: np.ndarray) -> float:
    """Negative log-likelihood for GPD, used by scipy.optimize.minimize."""
    if params[1] != 0:
        return -_gpd_loglikelihood_scale_and_shape(params[0], params[1], price_data)
    return -_gpd_loglikelihood_scale_only(params[0], price_data)


def trading_value_at_risk(
    returns: pd.Series | np.ndarray,
    period: str | None = None,
    sigma: float = 2.0,
) -> float:
    """Calculate trading Value at Risk.

    This computes a simplified VaR as ``mean - sigma * std``.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    period : str, optional
        Frequency of the input data. Currently unused.
    sigma : float, optional
        Number of standard deviations to subtract from the mean.
        Default is 2.0.

    Returns
    -------
    float
        Trading VaR, or ``NaN`` if there are fewer than two observations.
    """
    if len(returns) < 2:
        return np.nan

    mean_ret = np.mean(returns)
    std_ret = np.std(returns, ddof=1)

    return mean_ret - sigma * std_ret


def gpd_risk_estimates(
    returns: pd.Series | np.ndarray,
    var_p: float = 0.01,
) -> np.ndarray | pd.Series:
    """Estimate VaR and ES using the Generalized Pareto Distribution (GPD).

    This fits a GPD to the tail of the loss distribution and estimates
    VaR and Expected Shortfall (ES).

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    var_p : float, optional
        Probability level for VaR/ES estimation. Default is 0.01.

    Returns
    -------
    np.ndarray or pd.Series
        Array of length 5 containing:
        ``[threshold, scale_param, shape_param, var_estimate, es_estimate]``.
        Returns zeros if the estimation fails.
    """
    from scipy import optimize

    if len(returns) < 3:
        result = np.zeros(5)
        if isinstance(returns, pd.Series):
            result = pd.Series(result)
        return result

    result = np.zeros(5)
    default_threshold = 0.2
    minimum_threshold = 0.000000001

    try:
        returns_array = pd.Series(returns).to_numpy()
    except AttributeError:
        returns_array = pd.Series(returns).values

    flipped_returns = -1 * returns_array
    losses = flipped_returns[flipped_returns > 0]
    threshold = default_threshold
    finished = False
    scale_param = 0.0
    shape_param = 0.0
    var_estimate = 0.0

    while not finished and threshold > minimum_threshold:
        losses_beyond_threshold = losses[losses >= threshold]
        if len(losses_beyond_threshold) > 0:
            try:
                optimization_results = optimize.minimize(
                    lambda params: _gpd_loglikelihood(params, losses_beyond_threshold),
                    np.array([1, 1]),
                    method="Nelder-Mead",
                )
                if optimization_results.success:
                    resulting_params = optimization_results.x
                    if len(resulting_params) == 2:
                        scale_param = resulting_params[0]
                        shape_param = resulting_params[1]
                        var_estimate = _gpd_var_calculator(
                            threshold, scale_param, shape_param, var_p, len(losses), len(losses_beyond_threshold)
                        )
                        if shape_param > 0 and var_estimate > 0:
                            finished = True
            except (ValueError, RuntimeError, FloatingPointError) as e:
                logger.debug("gpd_risk_estimates optimization failed at threshold %.6e: %s", threshold, e)
        if not finished:
            threshold = threshold / 2

    if finished:
        es_estimate = _gpd_es_calculator(var_estimate, threshold, scale_param, shape_param)
        result = np.array([threshold, scale_param, shape_param, var_estimate, es_estimate])

    if isinstance(returns, pd.Series):
        result = pd.Series(result)
    return result


def gpd_risk_estimates_aligned(
    returns: pd.Series | np.ndarray,
    var_p: float = 0.01,
) -> np.ndarray | pd.Series:
    """Calculate GPD risk estimates (aligned version for compatibility).

    This is a wrapper around :func:`gpd_risk_estimates` for API
    compatibility.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    var_p : float, optional
        Probability level for VaR/ES estimation. Default is 0.01.

    Returns
    -------
    np.ndarray or pd.Series
        Array of length 5 containing GPD risk estimates.
    """
    return gpd_risk_estimates(returns, var_p)


def beta_fragility_heuristic(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
) -> float:
    """Estimate fragility to a drop in beta.

    This heuristic measures how fragile a strategy's returns are to changes
    in market conditions by comparing returns at different points in the
    factor return distribution.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.

    Returns
    -------
    float
        Beta fragility heuristic, or ``NaN`` if there is insufficient data.
    """
    if len(returns) < 3 or len(factor_returns) < 3:
        return np.nan

    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    if len(returns_aligned) < 3 or len(factor_aligned) < 3:
        return np.nan

    returns_series = pd.Series(np.asanyarray(returns_aligned))
    factor_returns_series = pd.Series(np.asanyarray(factor_aligned))
    pairs = pd.concat([returns_series, factor_returns_series], axis=1)
    pairs.columns = ["returns", "factor_returns"]
    pairs = pairs.dropna()
    pairs = pairs.sort_values(by=["factor_returns"], kind="mergesort")

    start_index = 0
    mid_index = int(np.around(len(pairs) / 2, 0))
    end_index = len(pairs) - 1

    (start_returns, start_factor_returns) = pairs.iloc[start_index]
    (mid_returns, mid_factor_returns) = pairs.iloc[mid_index]
    (end_returns, end_factor_returns) = pairs.iloc[end_index]

    factor_returns_range = end_factor_returns - start_factor_returns
    start_returns_weight = 0.5
    end_returns_weight = 0.5

    if factor_returns_range != 0:
        start_returns_weight = (mid_factor_returns - start_factor_returns) / factor_returns_range
        end_returns_weight = (end_factor_returns - mid_factor_returns) / factor_returns_range

    return (start_returns_weight * start_returns) + (end_returns_weight * end_returns) - mid_returns


def beta_fragility_heuristic_aligned(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
) -> float:
    """Calculate the beta fragility heuristic with aligned series.

    This is a wrapper around :func:`beta_fragility_heuristic` for API
    compatibility.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or factor returns.

    Returns
    -------
    float
        Beta fragility heuristic, or ``NaN`` if there is insufficient data.
    """
    return beta_fragility_heuristic(returns, factor_returns)
