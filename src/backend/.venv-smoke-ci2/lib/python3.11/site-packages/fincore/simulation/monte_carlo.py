"""Monte Carlo simulation engine.

Main MonteCarlo class that orchestrates path generation and risk analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from fincore.simulation.base import SimResult, compute_statistics
from fincore.simulation.paths import gbm_from_returns, geometric_brownian_motion
from fincore.simulation.scenarios import scenario_table, stress_test

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["MonteCarlo"]


class MonteCarlo:
    """Monte Carlo simulation engine for financial risk analysis.

    Provides methods for:
    - Path simulation using Geometric Brownian Motion
    - Risk metric calculation (VaR, CVaR)
    - Stress testing scenarios

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Historical returns for parameter estimation.
    """

    def __init__(
        self,
        returns: pd.Series | np.ndarray,
    ):
        self.returns = np.asarray(returns)
        self.returns = self.returns[~np.isnan(self.returns)]

        if len(self.returns) == 0:
            raise ValueError("Returns cannot be empty or all NaN")

    def simulate(
        self,
        n_paths: int = 1000,
        horizon: int = 252,
        *,
        drift: float | None = None,
        volatility: float | None = None,
        antithetic: bool = False,
        seed: int | None = None,
    ) -> SimResult:
        """Simulate future return paths using Geometric Brownian Motion.

        Parameters
        ----------
        n_paths : int, default 1000
            Number of paths to simulate.
        horizon : int, default 252
            Number of time steps to simulate.
        drift : float, optional
            Annualized drift rate. If None, estimated from returns.
        volatility : float, optional
            Annualized volatility. If None, estimated from returns.
        antithetic : bool, default False
            Use antithetic variates for variance reduction.
        seed : int, optional
            Random seed for reproducibility.

        Returns
        -------
        SimResult
            Object containing simulated paths and statistics.

        Examples
        --------
        >>> import numpy as np
        >>> from fincore.simulation import MonteCarlo
        >>> returns = np.random.normal(0.001, 0.02, 252)
        >>> mc = MonteCarlo(returns)
        >>> result = mc.simulate(n_paths=10000, horizon=252)
        >>> print(f"95% VaR: {result.var(0.05):.2%}")
        """
        rng = np.random.default_rng(seed) if seed is not None else None

        # Generate paths
        paths = gbm_from_returns(
            returns=self.returns,
            horizon=horizon,
            n_paths=n_paths,
            frequency=252,
            rng=rng,
        )

        # Apply antithetic variates if requested
        if antithetic:
            from fincore.simulation.paths import antithetic_variates

            paths = antithetic_variates(paths)

        stats = compute_statistics(paths)
        return SimResult(paths, stats)

    def var(
        self,
        alpha: float = 0.05,
        n_paths: int = 10000,
        horizon: int = 252,
        seed: int | None = None,
    ) -> float:
        """Calculate Value at Risk using Monte Carlo simulation.

        Parameters
        ----------
        alpha : float, default 0.05
            Significance level (0.05 = 95% VaR).
        n_paths : int, default 10000
            Number of simulation paths.
        horizon : int, default 252
            Simulation horizon.

        Returns
        -------
        float
            VaR at the specified significance level.
        """
        result = self.simulate(n_paths=n_paths, horizon=horizon)
        return result.var(alpha)

    def cvar(
        self,
        alpha: float = 0.05,
        n_paths: int = 10000,
        horizon: int = 252,
        seed: int | None = None,
    ) -> float:
        """Calculate Conditional Value at Risk (Expected Shortfall).

        Parameters
        ----------
        alpha : float, default 0.05
            Significance level (0.05 = 95% CVaR).
        n_paths : int, default 10000
            Number of simulation paths.
        horizon : int, default 252
            Simulation horizon.

        Returns
        -------
        float
            CVaR at the specified significance level.
        """
        result = self.simulate(n_paths=n_paths, horizon=horizon)
        return result.cvar(alpha)

    def price_paths(
        self,
        S0: float,
        n_paths: int = 1000,
        horizon: int = 252,
        mu: float | None = None,
        sigma: float | None = None,
        seed: int | None = None,
    ) -> SimResult:
        """Simulate price paths starting from given initial price.

        Parameters
        ----------
        S0 : float
            Initial asset price.
        n_paths : int, default 1000
            Number of paths to simulate.
        horizon : int, default 252
            Number of trading days to simulate.
        mu : float, optional
            Annual drift. Estimated from returns if None.
        sigma : float, optional
            Annual volatility. Estimated from returns if None.
        seed : int, optional
            Random seed.

        Returns
        -------
        SimResult
            Simulated price paths.
        """
        rng = np.random.default_rng(seed) if seed is not None else None

        # Estimate parameters if not provided
        if mu is None or sigma is None:
            from fincore.simulation.base import estimate_parameters

            est_mu, est_sigma = estimate_parameters(self.returns)
            mu = mu if mu is not None else est_mu / 252
            sigma = sigma if sigma is not None else est_sigma / np.sqrt(252)

        # Generate price paths
        paths = geometric_brownian_motion(
            S0=S0,
            mu=mu,
            sigma=sigma,
            T=horizon / 252,
            dt=1 / 252,
            n_paths=n_paths,
            rng=rng,
        )

        stats = compute_statistics(paths)
        return SimResult(paths, stats)

    def stress(
        self,
        scenarios: list | None = None,
    ) -> dict:
        """Perform stress testing on historical returns.

        Parameters
        ----------
        scenarios : list of str, optional
            Scenarios to apply. Options: 'crash', 'spike',
            'vol_crush', 'vol_spike'. If None, applies all.

        Returns
        -------
        dict
            Stress test results for each scenario.
        """
        return stress_test(self.returns, scenarios=scenarios)

    def stress_table(self) -> pd.DataFrame:
        """Generate a summary table of stress test results.

        Returns
        -------
        pd.DataFrame
            Formatted stress test results.
        """
        results = self.stress()
        return scenario_table(results)

    @staticmethod
    def from_parameters(
        mu: float,
        sigma: float,
        S0: float = 1.0,
        n_paths: int = 1000,
        horizon: int = 252,
        seed: int | None = None,
    ) -> SimResult:
        """Create Monte Carlo simulation from known parameters.

        Parameters
        ----------
        mu : float
            Annual drift rate.
        sigma : float
            Annual volatility.
        S0 : float, default 1.0
            Initial price/return level.
        n_paths : int, default 1000
            Number of paths.
        horizon : int, default 252
            Simulation horizon in days.
        seed : int, optional
            Random seed.

        Returns
        -------
        SimResult
            Simulation result.
        """
        rng = np.random.default_rng(seed) if seed is not None else None

        # Convert daily parameters
        dt = 1 / 252
        mu_daily = mu / 252
        sigma_daily = sigma / np.sqrt(252)

        paths = geometric_brownian_motion(
            S0=S0,
            mu=mu_daily,
            sigma=sigma_daily,
            T=horizon / 252,
            dt=dt,
            n_paths=n_paths,
            rng=rng,
        )

        stats = compute_statistics(paths)
        return SimResult(paths, stats)
