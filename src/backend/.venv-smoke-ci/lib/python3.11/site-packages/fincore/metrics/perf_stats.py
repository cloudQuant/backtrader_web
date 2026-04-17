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

"""Performance statistics (summary tables, bootstrap stats, etc.)."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

import numpy as np
import pandas as pd

from fincore.constants import DAILY
from fincore.metrics.basic import annualization_factor
from fincore.metrics.drawdown import max_drawdown
from fincore.metrics.ratios import calmar_ratio, omega_ratio, sharpe_ratio, sortino_ratio, stability_of_timeseries
from fincore.metrics.returns import cum_returns_final
from fincore.metrics.risk import annual_volatility, tail_ratio, value_at_risk
from fincore.metrics.stats import kurtosis, skewness
from fincore.metrics.yearly import annual_return
from fincore.utils import nanmean, nanstd

__all__ = [
    "calc_bootstrap",
    "calc_distribution_stats",
    "perf_stats",
    "perf_stats_bootstrap",
]


def perf_stats(
    returns: pd.Series,
    factor_returns: pd.Series | None = None,
    positions: pd.DataFrame | None = None,
    transactions: pd.DataFrame | None = None,
    turnover_denom: str = "AGB",
    period: str = DAILY,
) -> pd.Series:
    """Calculate various performance metrics of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor to which betas are
        computed. Usually a benchmark such as market returns.
    positions : pd.DataFrame, optional
        Daily net position values.
    transactions : pd.DataFrame, optional
        Prices and amounts of executed trades. One row per trade.
    turnover_denom : str, optional
        Either 'AGB' or 'portfolio_value', default 'AGB'.
    period : str, optional
        Frequency of the input data (for example ``DAILY``).

    Returns
    -------
    pd.Series
        Performance metrics.
    """
    stats = OrderedDict()

    # Pre-compute shared intermediate results
    mdd = max_drawdown(returns)
    ann_ret = annual_return(returns, period=period)
    ann_factor = annualization_factor(period, None)
    returns_arr = np.asanyarray(returns)
    std_ret = nanstd(returns_arr, ddof=1, axis=0)
    mean_ret = nanmean(returns_arr, axis=0)
    sqrt_ann = np.sqrt(ann_factor)

    stats["Annual return"] = ann_ret
    stats["Cumulative returns"] = cum_returns_final(returns, starting_value=0)
    stats["Annual volatility"] = std_ret * sqrt_ann
    with np.errstate(divide="ignore", invalid="ignore"):
        stats["Sharpe ratio"] = (mean_ret / std_ret) * sqrt_ann if len(returns) >= 2 else np.nan
    stats["Calmar ratio"] = calmar_ratio(returns, period=period)
    stats["Stability"] = stability_of_timeseries(returns)
    stats["Max drawdown"] = mdd
    stats["Omega ratio"] = omega_ratio(returns)
    stats["Sortino ratio"] = sortino_ratio(returns, period=period)
    stats["Skew"] = skewness(returns)
    stats["Kurtosis"] = kurtosis(returns)
    stats["Tail ratio"] = tail_ratio(returns)
    stats["Daily value at risk"] = value_at_risk(returns)

    if factor_returns is not None:
        from fincore.metrics.alpha_beta import alpha_beta

        ab = alpha_beta(returns, factor_returns)
        stats["Alpha"] = ab[0]
        stats["Beta"] = ab[1]

    return pd.Series(stats)


def perf_stats_bootstrap(returns, factor_returns=None, return_stats=True, **_kwargs):
    """Calculate various bootstrapped performance metrics of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor to which betas are
        computed. Usually a benchmark such as market returns.
    return_stats : bool, optional
        If True, returns a DataFrame of mean, median, 5 and 95 percentiles
        for each perf metric.
        If False, return a DataFrame with the bootstrap samples for
        each perf metric.

    Returns
    -------
    pd.DataFrame
        if return_stats is True:
        - Distributional statistics of bootstrapped sampling
        distribution of performance metrics.
        If return_stats is False:
        - Bootstrap samples for each performance metric.
    """
    from scipy import stats as scipy_stats

    from fincore.constants.style import FACTOR_STAT_FUNCS, SIMPLE_STAT_FUNCS, STAT_FUNC_NAMES
    from fincore.metrics.alpha_beta import alpha, beta
    from fincore.metrics.ratios import omega_ratio, stability_of_timeseries
    from fincore.metrics.risk import tail_ratio, value_at_risk

    bootstrap_values = OrderedDict()

    def _resolve_stat_func(stat_entry):
        """Apply same resolution logic as in perf_stats for bootstrap case."""
        if callable(stat_entry):
            stat_func = stat_entry
            stat_key = getattr(stat_entry, "__name__", str(stat_entry))
            return stat_func, stat_key

        if isinstance(stat_entry, str):
            if stat_entry.startswith("stats."):
                func_name = stat_entry.split(".", 1)[1]
                stat_func = getattr(scipy_stats, func_name)
                return stat_func, func_name

            # Map to local functions
            func_map = {
                "annual_return": annual_return,
                "cum_returns_final": cum_returns_final,
                "annual_volatility": annual_volatility,
                "sharpe_ratio": sharpe_ratio,
                "calmar_ratio": calmar_ratio,
                "stability_of_timeseries": stability_of_timeseries,
                "max_drawdown": max_drawdown,
                "omega_ratio": omega_ratio,
                "sortino_ratio": sortino_ratio,
                "tail_ratio": tail_ratio,
                "value_at_risk": value_at_risk,
                "alpha": alpha,
                "beta": beta,
            }
            stat_func = func_map.get(stat_entry)
            if stat_func is not None:
                return stat_func, stat_entry

        return stat_entry, str(stat_entry)

    # Bootstrap for simple statistics
    for entry in SIMPLE_STAT_FUNCS:
        stat_func, stat_key = _resolve_stat_func(entry)
        if stat_func is None:
            continue
        stat_name = STAT_FUNC_NAMES.get(stat_key, stat_key)
        bootstrap_values[stat_name] = calc_bootstrap(stat_func, returns)

    # Bootstrap for factor-based statistics, if provided
    if factor_returns is not None:
        for entry in FACTOR_STAT_FUNCS:
            stat_func, stat_key = _resolve_stat_func(entry)
            if stat_func is None:
                continue
            stat_name = STAT_FUNC_NAMES.get(stat_key, stat_key)
            bootstrap_values[stat_name] = calc_bootstrap(stat_func, returns, factor_returns=factor_returns)

    bootstrap_values = pd.DataFrame(bootstrap_values)

    if return_stats:
        stats_df = bootstrap_values.apply(calc_distribution_stats)
        return stats_df.T[["mean", "median", "5%", "95%"]]
    return bootstrap_values


def calc_bootstrap(func, returns, *args, **kwargs):
    """Perform a bootstrap analysis on a user-defined function returning a summary statistic.

    Parameters
    ----------
    func : callable
        Function that either takes a single array (commonly ``returns``)
        or two arrays (for example ``returns`` and ``factor_returns``) and
        returns a single summary value.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
    n_samples : int, optional
        Number of bootstrap samples to draw. Default is 1000.
    random_seed : int, optional
        Seed for the pseudorandom number generator to make results
        reproducible. Default is ``None`` (non-deterministic).
    kwargs : dict, optional
        Additional keyword arguments forwarded to ``func``. For
        factor-based statistics this often includes ``factor_returns``.

    Returns
    -------
    numpy.ndarray
        Bootstrapped sampling distribution of passed in func.
    """
    n_samples = kwargs.pop("n_samples", 1000)
    random_seed = kwargs.pop("random_seed", None)
    out = np.empty(n_samples)

    factor_returns = kwargs.pop("factor_returns", None)
    rng = np.random.RandomState(seed=random_seed)

    for i in range(n_samples):
        idx = rng.randint(len(returns), size=len(returns))
        returns_i = returns.iloc[idx].reset_index(drop=True)
        if factor_returns is not None:
            factor_returns_i = factor_returns.iloc[idx].reset_index(drop=True)
            out[i] = func(returns_i, factor_returns_i, *args, **kwargs)
        else:
            out[i] = func(returns_i, *args, **kwargs)

    return out


def calc_distribution_stats(x: np.ndarray | pd.Series) -> pd.Series:
    """Calculate various summary statistics of data.

    Parameters
    ----------
    x : numpy.ndarray or pandas.Series
        Array to compute summary statistics for.

    Returns
    -------
    pandas.Series
        Series containing mean, median, std, as well as 5, 25, 75 and
        95 percentiles of passed in values.
    """
    return pd.Series(
        {
            "mean": np.mean(x),
            "median": np.median(x),
            "std": np.std(x),
            "5%": np.percentile(x, 5),
            "25%": np.percentile(x, 25),
            "75%": np.percentile(x, 75),
            "95%": np.percentile(x, 95),
            "IQR": np.subtract.reduce(np.percentile(x, [75, 25])),
        }
    )
