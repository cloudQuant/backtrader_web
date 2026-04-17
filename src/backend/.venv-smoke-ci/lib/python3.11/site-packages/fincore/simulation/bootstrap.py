"""Bootstrap methods for statistical inference.

Provides non-parametric statistical inference using resampling techniques.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

__all__ = ["bootstrap", "bootstrap_ci", "bootstrap_summary"]


def bootstrap(
    returns: pd.Series | np.ndarray,
    n_samples: int = 10000,
    statistic: str | Callable = "mean",
    seed: int | None = None,
) -> np.ndarray:
    """Bootstrap resampling for statistical inference.

    Resamples the returns with replacement and computes a statistic
    on each resample to build its distribution.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Input returns data.
    n_samples : int, default 10000
        Number of bootstrap resamples.
    statistic : str or callable, default "mean"
        Statistic to compute. Can be:
        - String: 'mean', 'std', 'sharpe', 'median'
        - Callable: Custom function taking array and returning scalar
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray, shape (n_samples,)
        Bootstrap distribution of the statistic.

    Examples
    --------
    >>> import numpy as np
    >>> from fincore.simulation import bootstrap
    >>> returns = np.random.normal(0.001, 0.02, 252)
    >>> boot_mean = bootstrap(returns, n_samples=10000, statistic="mean")
    >>> np.percentile(boot_mean, [2.5, 97.5])  # 95% CI
    """
    arr = np.asarray(returns)
    arr = arr[~np.isnan(arr)]

    if len(arr) == 0:
        raise ValueError("Cannot bootstrap empty returns")

    rng = np.random.default_rng(seed)

    # Map string statistic to function
    statistic_fn = _get_statistic_fn(statistic) if isinstance(statistic, str) else statistic

    # Bootstrap resampling
    boot_stats = np.zeros(n_samples)
    n = len(arr)

    for i in range(n_samples):
        # Resample with replacement
        sample = rng.choice(arr, size=n, replace=True)
        boot_stats[i] = statistic_fn(sample)

    return boot_stats


def bootstrap_ci(
    returns: pd.Series | np.ndarray,
    n_samples: int = 10000,
    alpha: float = 0.05,
    statistic: str | Callable = "mean",
    method: str = "percentile",
    seed: int | None = None,
) -> tuple[float, float]:
    """Calculate bootstrap confidence interval.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Input returns data.
    n_samples : int, default 10000
        Number of bootstrap resamples.
    alpha : float, default 0.05
        Significance level (0.05 = 95% confidence interval).
    statistic : str or callable, default "mean"
        Statistic to compute.
    method : str, default "percentile"
        Method for CI calculation:
        - 'percentile': Simple percentile method
        - 'bc': Bias-corrected (not implemented)
        - 'bca': BCa method (not implemented)
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    tuple (lower, upper)
        Lower and upper bounds of the confidence interval.

    Examples
    --------
    >>> from fincore.simulation import bootstrap_ci
    >>> import numpy as np
    >>> returns = np.random.normal(0.001, 0.02, 252)
    >>> ci = bootstrap_ci(returns, alpha=0.05)
    >>> print(f"95% CI: [{ci[0]:.4f}, {ci[1]:.4f}]")
    """
    if not (0 < alpha < 1):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    boot_stats = bootstrap(
        returns=returns,
        n_samples=n_samples,
        statistic=statistic,
        seed=seed,
    )

    if method == "percentile":
        lower = np.percentile(boot_stats, alpha / 2 * 100)
        upper = np.percentile(boot_stats, (1 - alpha / 2) * 100)
    else:
        raise ValueError(f"Method '{method}' not implemented. Use 'percentile'.")

    return float(lower), float(upper)


def _get_statistic_fn(name: str) -> Callable[[np.ndarray], float]:
    """Map statistic name to function."""
    statistics = {
        "mean": lambda x: float(np.mean(x)),
        "std": lambda x: float(np.std(x, ddof=1)),
        "median": lambda x: float(np.median(x)),
        "sharpe": _sharpe_statistic,
        "sortino": _sortino_statistic,
        "min": lambda x: float(np.min(x)),
        "max": lambda x: float(np.max(x)),
    }

    if name not in statistics:
        available = ", ".join(statistics.keys())
        raise ValueError(f"Unknown statistic '{name}'. Available: {available}")

    return statistics[name]


def _sharpe_statistic(returns: np.ndarray) -> float:
    """Calculate Sharpe ratio for bootstrap."""
    if len(returns) < 2:
        return np.nan
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std == 0:
        return np.nan if mean == 0 else np.inf
    return float(mean / std * np.sqrt(252))


def _sortino_statistic(returns: np.ndarray) -> float:
    """Calculate Sortino ratio for bootstrap."""
    if len(returns) < 2:
        return np.nan
    mean = np.mean(returns)

    # Downside deviation
    downside = returns.copy()
    downside[downside > 0] = 0
    downside_std = np.std(downside, ddof=1)

    if downside_std == 0:
        return np.nan if mean == 0 else np.inf
    return float(mean / downside_std * np.sqrt(252))


def bootstrap_summary(
    returns: pd.Series | np.ndarray,
    n_samples: int = 10000,
    alpha: float = 0.05,
    seed: int | None = None,
) -> dict:
    """Compute comprehensive bootstrap statistics summary.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Input returns data.
    n_samples : int, default 10000
        Number of bootstrap resamples.
    alpha : float, default 0.05
        Significance level for confidence intervals.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    dict
        Dictionary containing bootstrap statistics for multiple metrics.
    """
    result = {}

    for stat_name in ["mean", "std", "sharpe", "sortino"]:
        boot_dist = bootstrap(returns, n_samples=n_samples, statistic=stat_name, seed=seed)
        result[stat_name] = {
            "value": float(_get_statistic_fn(stat_name)(returns)),
            "se": float(np.std(boot_dist, ddof=1)),  # Standard error
            "ci_lower": float(np.percentile(boot_dist, alpha / 2 * 100)),
            "ci_upper": float(np.percentile(boot_dist, (1 - alpha / 2) * 100)),
        }

    return result
