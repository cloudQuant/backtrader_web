"""Base classes and utility functions for Monte Carlo simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "SimResult",
    "annualize",
    "compute_statistics",
    "estimate_parameters",
    "validate_returns",
]


def validate_returns(returns: pd.Series | np.ndarray) -> np.ndarray:
    """Validate and convert returns to numpy array.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Return series to validate.

    Returns
    -------
    np.ndarray
        Validated returns as numpy array.

    Raises
    ------
    ValueError
        If returns contain NaN or are empty.
    """
    arr = np.asarray(returns)
    if arr.size == 0:
        raise ValueError("Returns cannot be empty")
    if np.any(np.isnan(arr)):
        raise ValueError("Returns cannot contain NaN values")
    return arr


def annualize(
    daily_value: float,
    period: str = "daily",
) -> float:
    """Annualize a daily value.

    Parameters
    ----------
    daily_value : float
        Daily value to annualize.
    period : str, default "daily"
        Input period. One of: daily, weekly, monthly, yearly.

    Returns
    -------
    float
        Annualized value.
    """
    factors = {
        "daily": 252,
        "weekly": 52,
        "monthly": 12,
        "yearly": 1,
    }
    factor = factors.get(period.lower(), 252)
    return float(daily_value * np.sqrt(factor))


def compute_statistics(
    paths: np.ndarray,
) -> dict:
    """Compute statistics from simulated paths.

    Parameters
    ----------
    paths : np.ndarray, shape (n_paths, horizon)
        Simulated price or return paths.

    Returns
    -------
    dict
        Dictionary containing:
        - mean: Mean terminal value
        - std: Standard deviation of terminal values
        - median: Median terminal value
        - percentiles: Selected percentiles [1, 5, 25, 50, 75, 95, 99]
    """
    terminal_values = paths[:, -1] if paths.ndim > 1 else paths

    return {
        "mean": float(np.mean(terminal_values)),
        "std": float(np.std(terminal_values, ddof=1)),
        "median": float(np.median(terminal_values)),
        "percentiles": {
            1: float(np.percentile(terminal_values, 1)),
            5: float(np.percentile(terminal_values, 5)),
            25: float(np.percentile(terminal_values, 25)),
            50: float(np.percentile(terminal_values, 50)),
            75: float(np.percentile(terminal_values, 75)),
            95: float(np.percentile(terminal_values, 95)),
            99: float(np.percentile(terminal_values, 99)),
        },
    }


def estimate_parameters(
    returns: np.ndarray,
    frequency: int = 252,
) -> tuple[float, float]:
    """Estimate drift and volatility from historical returns.

    Uses maximum likelihood estimation for GBM parameters.

    Parameters
    ----------
    returns : np.ndarray
        Historical returns (not prices).
    frequency : int, default 252
        Number of periods per year for annualization.

    Returns
    -------
    tuple (drift, volatility)
        drift : Annualized drift rate (mu)
        volatility : Annualized volatility (sigma)
    """
    # Remove any NaN values
    clean_returns = returns[~np.isnan(returns)]

    if len(clean_returns) == 0:
        raise ValueError("No valid returns for parameter estimation")

    # Daily statistics
    daily_mean = float(np.mean(clean_returns))
    daily_std = float(np.std(clean_returns, ddof=1))

    # Annualize
    drift = daily_mean * frequency
    volatility = daily_std * np.sqrt(frequency)

    return drift, volatility


class SimResult:
    """Container for simulation results.

    Attributes
    ----------
    paths : np.ndarray
        Simulated paths, shape (n_paths, horizon).
    statistics : dict
        Computed statistics from paths.
    """

    def __init__(
        self,
        paths: np.ndarray,
        statistics: dict | None = None,
    ):
        self.paths = paths
        self.statistics = statistics or compute_statistics(paths)

    @property
    def n_paths(self) -> int:
        """Number of simulated paths."""
        return self.paths.shape[0] if self.paths.ndim > 1 else 1

    @property
    def horizon(self) -> int:
        """Simulation horizon (number of steps)."""
        return self.paths.shape[1] if self.paths.ndim > 1 else len(self.paths)

    def var(
        self,
        alpha: float = 0.05,
    ) -> float:
        """Value at Risk from simulation.

        Parameters
        ----------
        alpha : float, default 0.05
            Significance level (0.05 = 95% VaR). Must be in (0, 1).

        Returns
        -------
        float
            VaR at the specified significance level. Returns NaN if alpha
            is outside (0, 1).
        """
        if not (0 < alpha < 1):
            return float("nan")
        terminal = self.paths[:, -1] if self.paths.ndim > 1 else self.paths
        return float(np.percentile(terminal, alpha * 100))

    def cvar(
        self,
        alpha: float = 0.05,
    ) -> float:
        """Conditional Value at Risk (Expected Shortfall).

        Parameters
        ----------
        alpha : float, default 0.05
            Significance level (0.05 = 95% CVaR). Must be in (0, 1).

        Returns
        -------
        float
            CVaR at the specified significance level. Returns NaN if alpha
            is outside (0, 1).
        """
        if not (0 < alpha < 1):
            return float("nan")
        terminal = self.paths[:, -1] if self.paths.ndim > 1 else self.paths
        var = self.var(alpha)
        # Mean of values below VaR
        tail_values = terminal[terminal <= var]
        return float(np.mean(tail_values)) if len(tail_values) > 0 else var

    def to_dataframe(self) -> pd.DataFrame:
        """Convert paths to pandas DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with path simulations as rows.
        """
        return pd.DataFrame(self.paths)

    def __repr__(self) -> str:
        return f"SimResult(n_paths={self.n_paths}, horizon={self.horizon})"
