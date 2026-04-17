"""Path generation methods for Monte Carlo simulation.

Implements various stochastic processes for generating price/return paths:
- Geometric Brownian Motion (GBM)
- Jump Diffusion
- Heston Stochastic Volatility (future)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from fincore.simulation.base import estimate_parameters

if TYPE_CHECKING:
    import pandas as pd

__all__ = [
    "antithetic_variates",
    "gbm_from_returns",
    "geometric_brownian_motion",
    "latin_hypercube_sampling",
]


def geometric_brownian_motion(
    S0: float,
    mu: float,
    sigma: float,
    T: float,
    dt: float,
    n_paths: int,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Generate price paths using Geometric Brownian Motion.

    The GBM model is:
        dS = mu * S * dt + sigma * S * dW

    Discrete form:
        S(t+dt) = S(t) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)

    where Z ~ N(0,1).

    Parameters
    ----------
    S0 : float
        Initial asset price.
    mu : float
        Annualized drift rate.
    sigma : float
        Annualized volatility.
    T : float
        Total time in years.
    dt : float
        Time step size in years.
    n_paths : int
        Number of paths to simulate.
    rng : np.random.Generator, optional
        Random number generator.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray, shape (n_paths, n_steps)
        Simulated price paths.
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    elif rng is None:
        rng = np.random.default_rng()

    n_steps = int(T / dt)
    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = S0

    # Pre-compute constants
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt)

    # Generate all random numbers at once (vectorized)
    Z = rng.standard_normal((n_paths, n_steps))

    # Simulate paths
    for t in range(1, n_steps + 1):
        paths[:, t] = paths[:, t - 1] * np.exp(drift + diffusion * Z[:, t - 1])

    return paths


def gbm_from_returns(
    returns: pd.Series | np.ndarray,
    horizon: int = 252,
    n_paths: int = 1000,
    frequency: int = 252,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Generate GBM paths estimated from historical returns.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Historical returns to estimate parameters from.
    horizon : int, default 252
        Number of time steps to simulate.
    n_paths : int, default 1000
        Number of paths to generate.
    frequency : int, default 252
        Number of periods per year (for parameter estimation).
    rng : np.random.Generator, optional
        Random number generator.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray, shape (n_paths, horizon)
        Simulated cumulative return paths.
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    elif rng is None:
        rng = np.random.default_rng()

    # Convert to numpy array and clean
    ret_arr = np.asarray(returns)
    ret_arr = ret_arr[~np.isnan(ret_arr)]

    if len(ret_arr) == 0:
        raise ValueError("No valid returns for simulation")

    # Estimate parameters
    mu, sigma = estimate_parameters(ret_arr, frequency)

    # Convert to daily parameters
    dt = 1.0 / frequency
    mu_daily = mu / frequency
    sigma_daily = sigma / np.sqrt(frequency)

    # Start from 1 (for returns) or 0 (for log returns)
    S0 = 1.0

    # Generate price paths
    price_paths = geometric_brownian_motion(
        S0=S0,
        mu=mu_daily,
        sigma=sigma_daily,
        T=horizon / frequency,
        dt=dt,
        n_paths=n_paths,
        rng=rng,
        seed=seed,
    )

    # Convert to cumulative returns and remove initial point
    return price_paths[:, 1:] - 1.0


def antithetic_variates(
    paths: np.ndarray,
) -> np.ndarray:
    """Generate antithetic variates for variance reduction.

    Creates mirror paths using -Z instead of Z, which reduces
    Monte Carlo variance by approximately half.

    Parameters
    ----------
    paths : np.ndarray
        Original paths generated with random variates Z.

    Returns
    -------
    np.ndarray
        Original paths concatenated with antithetic paths.
    """
    # Antithetic paths are mirrored around the initial value
    antithetic = 2 * paths[0, 0] - paths
    return np.vstack([paths, antithetic])


def latin_hypercube_sampling(
    n_samples: int,
    n_dimensions: int,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Generate Latin Hypercube samples for quasi-Monte Carlo.

    LHS provides better coverage of the sample space than
    pure random sampling, often reducing required samples.

    Parameters
    ----------
    n_samples : int
        Number of samples to generate.
    n_dimensions : int
        Number of dimensions (time steps).
    rng : np.random.Generator, optional
        Random number generator.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray, shape (n_samples, n_dimensions)
        LHS samples in [0, 1].
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    elif rng is None:
        rng = np.random.default_rng()

    samples = np.zeros((n_samples, n_dimensions))

    # Generate random permutations for each dimension
    for i in range(n_dimensions):
        # Random permutation
        perm = rng.permutation(n_samples)
        # Uniform random within each interval
        samples[:, i] = (perm + rng.uniform(0, 1, n_samples)) / n_samples

    return samples
