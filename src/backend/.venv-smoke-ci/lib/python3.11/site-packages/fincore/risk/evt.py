"""Extreme Value Theory (EVT) models for tail risk estimation.

EVT provides better estimates of extreme losses than normal
distribution assumptions, particularly for:

- Tail index estimation (Hill estimator)
- Peaks-over-threshold (POT) with Generalized Pareto Distribution (GPD)
- Block maxima with Generalized Extreme Value (GEV) distribution

References
----------
Embrechts, P., Klüppelberg, C., & Mikosch, T. (1997).
Modelling Extremal Events for Insurance and Finance.
McNeil, A. J., Frey, R., & Embrechts, P. (2015).
Quantitative Risk Management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

import numpy as np
import pandas as pd
from scipy import optimize, stats

__all__ = ["evt_cvar", "evt_var", "extreme_risk", "gev_fit", "gpd_fit", "hill_estimator"]


if TYPE_CHECKING:
    ArrayLike = Union[np.ndarray, pd.Series, pd.DataFrame]


def hill_estimator(
    data: ArrayLike,
    threshold: float | None = None,
    tail: str = "upper",
) -> tuple[float, np.ndarray]:
    """Estimate tail index using Hill estimator.

    The Hill estimator is a popular method for estimating the
    tail index (extreme value index) of heavy-tailed distributions.

    Parameters
    ----------
    data : array-like
        Input data (returns or losses).
    threshold : float, optional
        Threshold for selecting tail data.
        If None, uses 90th percentile for upper tail.
    tail : str, default 'upper'
        Which tail to estimate: 'upper' (right/gains) or 'lower' (left/losses).

    Returns
    -------
    xi : float
        Estimated tail index (shape parameter).
        xi > 0: Heavy-tailed (Pareto, Student-t)
        xi = 0: Exponential tail
        xi < 0: Bounded tail (Beta, Uniform)
    excesses : ndarray
        Data above threshold.

    Examples
    --------
    >>> returns = np.random.standard_t(3, 10000)
    >>> xi, excesses = hill_estimator(returns, tail="lower")
    >>> print(f"Tail index: {xi:.3f}")
    """
    data = np.asarray(data).flatten()
    data = data[~np.isnan(data)]

    # Select tail based on sign
    if tail == "upper":
        tail_data = data[data > 0]
    elif tail == "lower":
        tail_data = -data[data < 0]  # Convert losses to positive
    else:
        raise ValueError("tail must be 'upper' or 'lower'")

    # Set threshold if not provided
    if threshold is None:
        threshold = np.percentile(tail_data, 90)

    # Get exceedances
    excesses = tail_data[tail_data > threshold] - threshold

    if len(excesses) < 10:
        raise ValueError("Not enough exceedances for Hill estimation (need >= 10)")

    # Sort log exceedances
    log_excess = np.log(excesses)
    log_excess = np.sort(log_excess)

    # Hill estimator
    k = len(log_excess)
    xi = 1 / k * np.sum(log_excess - log_excess[0])

    return xi, excesses + threshold


def gpd_fit(
    data: ArrayLike,
    threshold: float | None = None,
    method: str = "mle",
) -> dict[str, float]:
    """Fit Generalized Pareto Distribution (GPD) to exceedances.

    GPD is used in Peaks-Over-Threshold (POT) method for modeling
    tail exceedances above a threshold.

    Parameters
    ----------
    data : array-like
        Input data (returns or losses).
    threshold : float, optional
        Threshold for POT. If None, uses 90th percentile.
    method : str, default 'mle'
        Estimation method: 'mle' (maximum likelihood) or 'pwm' (probability weighted moments).

    Returns
    -------
    dict
        Fitted parameters:
        - 'xi' (shape): Tail index
        - 'beta' (scale): Scale parameter
        - 'threshold': Fitted threshold
        - 'n_exceed': Number of exceedances

    Examples
    --------
    >>> returns = np.random.standard_t(4, 10000)
    >>> params = gpd_fit(returns, tail="lower")
    >>> print(f"xi={params['xi']:.3f}, beta={params['beta']:.3f}")
    """
    data = np.asarray(data).flatten()
    data = data[~np.isnan(data)]

    # Use losses (positive tail of negative returns)
    tail_data = -data[data < 0]

    if len(tail_data) == 0:
        raise ValueError("No negative returns in data; need at least some losses for GPD fitting")

    # Set threshold
    if threshold is None:
        threshold = np.percentile(tail_data, 90)

    # Get exceedances
    excesses = tail_data[tail_data > threshold] - threshold

    if len(excesses) < 10:
        raise ValueError("Not enough exceedances for GPD fitting (need >= 10)")

    if method == "mle":
        # Maximum likelihood estimation
        def neg_loglik(params):
            xi, beta = params
            beta = np.abs(beta)

            # Avoid invalid parameter combinations
            if beta <= 0:
                return 1e10  # pragma: no cover -- Edge case for optimization

            z = 1 + xi * excesses / beta

            if np.any(z <= 0):
                return 1e10

            # Log-likelihood for GPD
            if np.abs(xi) < 1e-10:
                # Exponential case (xi -> 0)
                ll = np.sum(np.log(beta) + excesses / beta)  # pragma: no cover -- Rare edge case
            else:
                ll = np.sum(np.log(beta) + (1 + 1 / xi) * np.log(z))

            return ll

        # Optimize
        result = optimize.minimize(
            neg_loglik,
            x0=[0.1, np.std(excesses)],
            bounds=[(-0.5, 1.0), (1e-6, None)],
            method="L-BFGS-B",
        )

        xi, beta = result.x
        beta = np.abs(beta)

    elif method == "pwm":
        # Probability weighted moments
        n = len(excesses)
        excesses_sorted = np.sort(excesses)

        # L-moments estimators
        m1 = np.mean(excesses)
        m2 = 2 / n * np.sum([(i + 1) * excesses_sorted[i] / n for i in range(n)])

        # PWM estimators
        xi = (m1 / (m1 - 2 * m2) - 2) / 3
        beta = (2 * m1 * m2) / (m1 - 2 * m2)

    else:
        raise ValueError(f"Unknown method: {method}")

    return {
        "xi": xi,
        "beta": beta,
        "threshold": threshold,
        "n_exceed": len(excesses),
    }


def gev_fit(
    data: ArrayLike,
    block_size: int | None = None,
) -> dict[str, float]:
    """Fit Generalized Extreme Value (GEV) distribution to block maxima.

    GEV is used for modeling maximum values over fixed time blocks
    (e.g., monthly maximum losses).

    Parameters
    ----------
    data : array-like
        Input data (returns or losses).
    block_size : int, optional
        Size of each block for extracting maxima.
        If None, uses sqrt(n) blocks.

    Returns
    -------
    dict
        Fitted parameters:
        - 'xi' (shape): Tail index
        - 'mu' (location): Location parameter
        - 'sigma' (scale): Scale parameter

    Examples
    --------
    >>> returns = np.random.standard_t(4, 10000)
    >>> params = gev_fit(returns, block_size=252)  # Annual maxima
    >>> print(f"xi={params['xi']:.3f}")
    """
    data = np.asarray(data).flatten()
    data = data[~np.isnan(data)]

    n = len(data)

    if block_size is None:
        block_size = int(np.sqrt(n))

    # Split into blocks and get maxima
    n_blocks = n // block_size
    trimmed_data = data[: n_blocks * block_size]
    block_maxima = trimmed_data.reshape(-1, block_size)

    # For risk analysis, we want minimum (most negative) returns
    block_minima = np.min(block_maxima, axis=1)

    # Fit GEV to minima (negate to use standard GEV)
    neg_minima = -block_minima

    # Use scipy's genextreme fit
    # Note: scipy uses different parameterization
    xi, mu, sigma = stats.genextreme.fit(neg_minima)

    # Convert to standard GEV parameters
    return {
        "xi": xi,
        "mu": -mu,  # Flip back for minima
        "sigma": sigma,
        "n_blocks": n_blocks,
    }


def evt_var(
    data: ArrayLike,
    alpha: float = 0.05,
    model: str = "gpd",
    tail: str = "lower",
    threshold: float | None = None,
    block_size: int | None = None,
) -> float:
    """Calculate VaR using Extreme Value Theory.

    EVT-based VaR provides better tail risk estimates than
    normal distribution assumptions.

    Parameters
    ----------
    data : array-like
        Input return data.
    alpha : float, default 0.05
        Significance level (e.g., 0.05 for 95% VaR).
    model : str, default 'gpd'
        EVT model: 'gpd' (POT) or 'gev' (block maxima).
    tail : str, default 'lower'
        Tail to estimate: 'lower' for losses, 'upper' for gains.
    threshold : float, optional
        Threshold for GPD fitting.
    block_size : int, optional
        Block size for GEV fitting.

    Returns
    -------
    float
        EVT-based VaR estimate (negative value for losses).

    Examples
    --------
    >>> returns = np.random.standard_t(4, 1000)
    >>> var_95 = evt_var(returns, alpha=0.05, model="gpd")
    >>> print(f"95% EVT-VaR: {var_95:.2%}")
    """
    data = np.asarray(data).flatten()
    data = data[~np.isnan(data)]

    var: float = np.nan  # Initialize var

    if model == "gpd":
        # For GPD, we fit to losses (negative returns converted to positive)
        # The result needs to be negated to return to return-space
        params = gpd_fit(data, threshold=threshold)

        xi = params["xi"]
        beta = params["beta"]
        u = params["threshold"]

        # Number of exceedances
        n_exceed = params["n_exceed"]
        n_total = len(data)
        exceed_prob = n_exceed / n_total

        # GPD-based VaR (in loss space, positive)
        # Formula: VaR = u + (β/ξ) * [((α/F_u))^(-ξ) - 1)]
        # where F_u = n_exceed/n is the empirical exceedance probability
        # Reference: McNeil, Frey, Embrechts - Quantitative Risk Management
        ratio = alpha / exceed_prob
        var = u - beta * np.log(ratio) if np.abs(xi) < 1e-10 else u + (beta / xi) * (ratio ** (-xi) - 1)

        # Convert to return-space (negative for losses)
        var = -var

    elif model == "gev":
        # Fit GEV
        params = gev_fit(data, block_size=block_size)

        xi = params["xi"]
        mu = params["mu"]
        sigma = params["sigma"]

        # GEV quantile function (already in return-space)
        if np.abs(xi) < 1e-10:
            # Gumbel case
            var = mu - sigma * np.log(-np.log(alpha))
        else:
            # General case
            var = mu + (sigma / xi) * ((-np.log(alpha)) ** (-xi) - 1)
    else:
        raise ValueError(f"Unknown model: {model}")  # pragma: no cover -- Invalid input

    return var


def evt_cvar(
    data: ArrayLike,
    alpha: float = 0.05,
    model: str = "gpd",
    tail: str = "lower",
    threshold: float | None = None,
    block_size: int | None = None,
) -> float:
    """Calculate CVaR (Expected Shortfall) using EVT.

    EVT-based CVaR provides better average tail loss estimates.

    Parameters
    ----------
    data : array-like
        Input return data.
    alpha : float, default 0.05
        Significance level.
    model : str, default 'gpd'
        EVT model: 'gpd' or 'gev'.
    tail : str, default 'lower'
        Tail to estimate.
    threshold : float, optional
        Threshold for GPD fitting.
    block_size : int, optional
        Block size for GEV fitting.

    Returns
    -------
    float
        EVT-based CVaR estimate (negative value for losses).

    Examples
    --------
    >>> returns = np.random.standard_t(4, 1000)
    >>> cvar_95 = evt_cvar(returns, alpha=0.05, model="gpd")
    >>> print(f"95% EVT-CVaR: {cvar_95:.2%}")
    """
    data = np.asarray(data).flatten()
    data = data[~np.isnan(data)]

    var = evt_var(data, alpha, model, tail, threshold=threshold, block_size=block_size)

    if model == "gpd":
        params = gpd_fit(data, threshold=threshold)
        xi = params["xi"]
        beta = params["beta"]
        u = params["threshold"]

        # For GPD CVaR, we work in loss space (positive values)
        # then convert back to return-space (negative)
        var_loss = -var  # Convert back to loss space

        # GPD-based CVaR (in loss space)
        if np.abs(xi) < 1e-10:
            # Exponential case
            cvar_loss = var_loss + beta
        elif xi < 1:
            # General case
            cvar_loss = var_loss + (beta + xi * (var_loss - u)) / (1 - xi)
        else:
            raise ValueError("CVaR infinite for xi >= 1")

        # Convert to return-space (negative for losses)
        cvar = -cvar_loss

    elif model == "gev":
        params = gev_fit(data, block_size=block_size)
        xi = params["xi"]
        sigma = params["sigma"]

        # GEV-based CVaR (mu already incorporated via var)
        t = -np.log(alpha)

        if np.abs(xi) < 1e-10:
            # Gumbel case
            cvar = var - sigma * (1 + np.euler_gamma)
        elif xi < 1:
            # General case
            cvar = var + (sigma / xi) * (1 - 1 / (1 - xi) + t ** (-xi) / (1 - xi))
        else:
            raise ValueError("CVaR infinite for xi >= 1")
    else:
        raise ValueError(f"Unknown model: {model}")  # pragma: no cover -- Invalid input

    return cvar


def extreme_risk(
    returns: pd.Series,
    alpha: float = 0.05,
    tail: str = "lower",
    model: str = "gpd",
    threshold: float | None = None,
    block_size: int | None = None,
) -> pd.DataFrame:
    """Calculate comprehensive EVT-based risk measures.

    Parameters
    ----------
    returns : pd.Series
        Return series.
    alpha : float, default 0.05
        Significance level.
    tail : str, default 'lower'
        Tail to estimate.
    model : str, default 'gpd'
        EVT model.
    threshold : float, optional
        Threshold for GPD fitting.
    block_size : int, optional
        Block size for GEV fitting.

    Returns
    -------
    pd.DataFrame
        Risk measures including VaR, CVaR, tail index,
        and threshold.

    Examples
    --------
    >>> returns = pd.Series(np.random.standard_t(4, 1000))
    >>> risk = extreme_risk(returns, alpha=0.05)
    >>> print(risk)
    """
    data = returns.values

    # Fit model
    if model == "gpd":
        params = gpd_fit(data, threshold=threshold)

        var = evt_var(data, alpha, model, tail, threshold=params["threshold"])
        cvar = evt_cvar(data, alpha, model, tail, threshold=params["threshold"])

        return pd.DataFrame(
            {
                "VaR": [var],
                "CVaR": [cvar],
                "tail_index": [params["xi"]],
                "threshold": [params["threshold"]],
                "n_exceedances": [params["n_exceed"]],
            },
            index=[alpha],
        )

    if model == "gev":
        params = gev_fit(data, block_size=block_size)
        var = evt_var(data, alpha, model, tail, block_size=block_size)
        cvar = evt_cvar(data, alpha, model, tail, block_size=block_size)

        return pd.DataFrame(
            {
                "VaR": [var],
                "CVaR": [cvar],
                "tail_index": [params["xi"]],
                "location": [params["mu"]],
                "scale": [params["sigma"]],
            },
            index=[alpha],
        )
    raise ValueError(f"Unknown model: {model}")  # pragma: no cover -- Invalid input
