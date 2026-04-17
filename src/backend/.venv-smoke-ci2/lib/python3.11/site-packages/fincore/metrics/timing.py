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

"""Market timing metrics."""

from __future__ import annotations

import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd

from fincore.constants.interesting_periods import PERIODS
from fincore.metrics.basic import aligned_series

__all__ = [
    "cornell_timing",
    "extract_interesting_date_ranges",
    "henriksson_merton_timing",
    "market_timing_return",
    "treynor_mazuy_timing",
]


def treynor_mazuy_timing(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
) -> float:
    """Calculate the Treynor–Mazuy market timing coefficient (gamma).

    This fits a quadratic regression of excess strategy returns on excess
    factor returns and uses the coefficient on the squared factor term as
    a measure of market timing ability.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or market returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.

    Returns
    -------
    float
        Treynor–Mazuy timing coefficient (gamma), or ``NaN`` if there is
        insufficient data.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    ret_arr = np.asanyarray(returns_aligned, dtype=float)
    fac_arr = np.asanyarray(factor_aligned, dtype=float)
    valid_mask = ~(np.isnan(ret_arr) | np.isnan(fac_arr))
    ret_clean = ret_arr[valid_mask]
    fac_clean = fac_arr[valid_mask]

    if len(ret_clean) < 10:
        return np.nan

    excess_returns = ret_clean - risk_free
    excess_factor = fac_clean - risk_free

    factor_squared = excess_factor**2

    try:
        design_matrix = np.column_stack([np.ones(len(excess_factor)), excess_factor, factor_squared])
        coeffs = np.linalg.lstsq(design_matrix, excess_returns, rcond=None)[0]
        return coeffs[2]  # gamma coefficient
    except (np.linalg.LinAlgError, ValueError, FloatingPointError) as e:
        logger.debug("treynor_mazuy_timing failed: %s", e)
        return np.nan


def henriksson_merton_timing(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
) -> float:
    """Calculate the Henriksson–Merton market timing coefficient.

    This fits a regression of excess strategy returns on excess factor
    returns and a down-market dummy, using the coefficient on the dummy
    as a measure of market timing.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or market returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.

    Returns
    -------
    float
        Henriksson–Merton timing coefficient, or ``NaN`` if there is
        insufficient data.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    ret_arr = np.asanyarray(returns_aligned, dtype=float)
    fac_arr = np.asanyarray(factor_aligned, dtype=float)
    valid_mask = ~(np.isnan(ret_arr) | np.isnan(fac_arr))
    ret_clean = ret_arr[valid_mask]
    fac_clean = fac_arr[valid_mask]

    if len(ret_clean) < 10:
        return np.nan

    excess_returns = ret_clean - risk_free
    excess_factor = fac_clean - risk_free

    down_market = (excess_factor < 0).astype(float)

    try:
        design_matrix = np.column_stack([np.ones(len(excess_factor)), excess_factor, down_market])
        coeffs = np.linalg.lstsq(design_matrix, excess_returns, rcond=None)[0]
        return coeffs[2]  # gamma coefficient
    except (np.linalg.LinAlgError, ValueError, FloatingPointError) as e:
        logger.debug("henriksson_merton_timing failed: %s", e)
        return np.nan


def market_timing_return(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
) -> float:
    """Calculate the market timing return component.

    Given the Treynor–Mazuy timing coefficient, this computes the portion
    of returns attributable to market timing as ``gamma * E[(R_m - R_f)^2]``.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or market returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.

    Returns
    -------
    float
        Estimated contribution of market timing to returns, or ``NaN`` if
        the timing coefficient cannot be estimated.
    """
    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    gamma = treynor_mazuy_timing(returns_aligned, factor_aligned, risk_free)

    if np.isnan(gamma):
        return np.nan

    excess_factor = factor_aligned - risk_free

    return float(gamma * np.mean(excess_factor**2))


def cornell_timing(
    returns: pd.Series | np.ndarray,
    factor_returns: pd.Series | np.ndarray,
    risk_free: float = 0.0,
) -> float:
    """Calculate the Cornell timing model coefficient.

    The Cornell timing model decomposes market returns into positive and
    negative components and estimates different betas in up and down
    markets. The timing coefficient is the difference between these two
    betas.

    Parameters
    ----------
    returns : array-like or pd.Series
        Non-cumulative strategy returns.
    factor_returns : array-like or pd.Series
        Non-cumulative benchmark or market returns.
    risk_free : float, optional
        Risk-free rate used when computing excess returns. Default is 0.0.

    Returns
    -------
    float
        Cornell timing coefficient (beta_up - beta_down), or ``NaN`` if
        there is insufficient data.
    """
    if len(returns) < 10 or len(factor_returns) < 10:
        return np.nan

    returns_aligned, factor_aligned = aligned_series(returns, factor_returns)

    returns_array = np.asanyarray(returns_aligned)
    factor_array = np.asanyarray(factor_aligned)

    valid_mask = ~(np.isnan(returns_array) | np.isnan(factor_array))
    returns_clean = returns_array[valid_mask]
    factor_clean = factor_array[valid_mask]

    if len(returns_clean) < 10:
        return np.nan

    try:
        excess_returns = returns_clean - risk_free
        excess_market = factor_clean - risk_free

        excess_market_positive = np.maximum(0, excess_market)
        excess_market_negative = np.minimum(0, excess_market)

        design_matrix = np.column_stack(
            [
                np.ones(len(excess_market)),
                excess_market_positive,
                excess_market_negative,
            ]
        )

        coeffs = np.linalg.lstsq(design_matrix, excess_returns, rcond=None)[0]

        beta_up = coeffs[1]
        beta_down = coeffs[2]

        timing_coef = beta_up - beta_down

        return float(timing_coef)

    except (np.linalg.LinAlgError, ValueError, FloatingPointError) as e:
        logger.debug("cornell_timing failed: %s", e)
        return np.nan


def extract_interesting_date_ranges(returns: pd.Series) -> OrderedDict[str, pd.Series]:
    """Extract returns based on interesting events.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.

    Returns
    -------
    ranges : OrderedDict
        Date ranges, with returns, of all valid events.
    """
    returns_dupe = returns.copy()
    returns_dupe.index = returns_dupe.index.map(pd.Timestamp)
    ranges = OrderedDict()
    for name, (start, end) in PERIODS.items():
        try:
            period = returns_dupe.loc[start:end]
            if len(period) == 0:
                continue
            ranges[name] = period
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("extract_interesting_date_ranges skipped %s: %s", name, e)
            continue

    return ranges
