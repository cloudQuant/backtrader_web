"""GARCH models for conditional volatility estimation.

Provides GARCH family models for time-varying volatility estimation:
- GARCH(p, q): Generalized Autoregressive Conditional Heteroskedasticity
- EGARCH: Exponential GARCH (asymmetric effects)
- GJR-GARCH: Glosten-Jagannathan-Runkle GARCH (leverage effect)

References
----------
Engle, R. F. (1982). Autoregressive Conditional Heteroscedasticity.
Bollerslev, T. (1986). Generalized Autoregressive Conditional Heteroscedasticity.
Nelson, D. B. (1991). Conditional Heteroskedasticity in Asset Returns.
Glosten, L. R., Jagannathan, R., & Runkle, D. E. (1993). On the Relation
Between the Expected Value and the Volatility of the Nominal Excess Return on Stocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy import optimize

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["EGARCH", "GARCH", "GJRGARCH", "GARCHResult", "conditional_var", "forecast_volatility"]


@dataclass
class GARCHResult:
    """Result of GARCH model fitting.

    Attributes
    ----------
    params : dict
        Fitted parameters (omega, alpha, beta, etc.).
    conditional_var : ndarray
        Fitted conditional variances.
    residuals : ndarray
        Standardized residuals.
    log_likelihood : float
        Maximized log-likelihood value.
    """

    params: dict[str, float]
    conditional_var: np.ndarray
    residuals: np.ndarray
    log_likelihood: float

    def forecast(self, horizon: int = 1) -> np.ndarray:
        """Forecast future conditional variances.

        Parameters
        ----------
        horizon : int, default 1
            Number of steps ahead to forecast.

        Returns
        -------
        ndarray
            Forecasted variances.
        """
        if horizon < 1:
            raise ValueError("horizon must be >= 1")

        forecasts = np.zeros(horizon)
        omega = self.params["omega"]
        alpha = self.params.get("alpha", 0.0)
        beta = self.params.get("beta", 0.0)
        persistence = alpha + beta

        # Last conditional variance and shock (epsilon_t)
        last_var = self.conditional_var[-1]
        last_eps = self.residuals[-1] * np.sqrt(last_var)

        for h in range(horizon):
            if h == 0:
                # One-step ahead GARCH(1,1): E_t[sigma_{t+1}^2]
                forecasts[h] = omega + alpha * (last_eps**2) + beta * last_var
            else:
                # Multi-step recursion: E_t[sigma_{t+h+1}^2] = omega + (alpha+beta) * E_t[sigma_{t+h}^2]
                forecasts[h] = omega + persistence * forecasts[h - 1]

        return forecasts


class GARCH:
    """GARCH(p, q) model for conditional volatility.

    The standard GARCH(p, q) model:
    sigma_t^2 = omega + sum(alpha_i * epsilon_{t-i}^2) + sum(beta_j * sigma_{t-j}^2)

    Parameters
    ----------
    p : int, default 1
        Order of ARCH terms (past squared shocks).
    q : int, default 1
        Order of GARCH terms (past conditional variances).
    mean_model : str, default 'zero'
        Mean model: 'zero' (zero mean), 'constant' (constant mean).

    Examples
    --------
    >>> returns = pd.Series(np.random.randn(1000) * 0.02)
    >>> model = GARCH(p=1, q=1)
    >>> result = model.fit(returns)
    >>> forecasts = result.forecast(horizon=10)
    """

    def __init__(
        self,
        p: int = 1,
        q: int = 1,
        mean_model: str = "zero",
    ):
        self.p = p
        self.q = q
        self.mean_model = mean_model

    def fit(
        self,
        returns: pd.Series | np.ndarray,
        method: str = "MLE",
    ) -> GARCHResult:
        """Fit GARCH model to returns.

        Parameters
        ----------
        returns : Series or ndarray
            Return series (not prices!).
        method : str, default 'MLE'
            Estimation method: 'MLE' (max likelihood) or 'OLS'.

        Returns
        -------
        GARCHResult
            Fitted model result.
        """
        y = np.asarray(returns).flatten()
        y = y[~np.isnan(y)]
        T = len(y)

        if max(self.p, self.q) + 10 > T:
            raise ValueError("Insufficient data for GARCH estimation")

        # Initialize parameters
        omega_init = np.var(y) * 0.1
        alpha_init = 0.1
        beta_init = 0.85

        if self.mean_model == "constant":
            mu_init = np.mean(y)
            init_params = [mu_init, omega_init, alpha_init, beta_init]
        else:
            init_params = [omega_init, alpha_init, beta_init]

        # Define bounds
        bounds = [
            (None, None),  # mu or omega
            (1e-6, None),  # omega
            (1e-6, 1.0),  # alpha (sum <= 1 for stability)
            (1e-6, 1.0),  # beta (sum <= 1 for stability)
        ]

        if self.mean_model == "zero":
            bounds = bounds[1:]

        # Optimize log-likelihood
        result = optimize.minimize(
            self._neg_log_likelihood,
            init_params,
            args=(y,),
            bounds=bounds,
            method="L-BFGS-B",
        )

        # Extract parameters
        params_opt = result.x

        if self.mean_model == "constant":
            mu, omega, alpha, beta = params_opt
        else:
            mu = 0
            omega, alpha, beta = params_opt

        # Compute conditional variances
        cond_var = self._compute_conditional_var(y - mu, omega, alpha, beta)

        # Standardized residuals
        residuals = (y - mu) / np.sqrt(cond_var)

        return GARCHResult(
            params={"mu": mu, "omega": omega, "alpha": alpha, "beta": beta},
            conditional_var=cond_var,
            residuals=residuals,
            log_likelihood=-result.fun,
        )

    def _neg_log_likelihood(
        self,
        params: np.ndarray,
        y: np.ndarray,
    ) -> float:
        """Negative log-likelihood function."""
        if self.mean_model == "constant":
            mu, omega, alpha, beta = params
            eps = y - mu
        else:
            mu = 0
            omega, alpha, beta = params
            eps = y

        # Compute conditional variances
        sigma2 = self._compute_conditional_var(eps, omega, alpha, beta)

        # Remove first p+q values (burn-in)
        burn = max(self.p, self.q)
        sigma2_valid = sigma2[burn:]
        eps_valid = eps[burn:]

        # Log-likelihood (assuming normal innovations)
        loglik = -0.5 * np.sum(np.log(2 * np.pi * sigma2_valid) + eps_valid**2 / sigma2_valid)

        return float(-loglik)

    def _compute_conditional_var(
        self,
        eps: np.ndarray,
        omega: float,
        alpha: float,
        beta: float,
    ) -> np.ndarray:
        """Compute conditional variances."""
        T = len(eps)
        sigma2 = np.ones(T) * float(np.var(eps))

        for t in range(1, T):
            # GARCH(1,1): sigma2[t] = omega + alpha*eps[t-1]^2 + beta*sigma2[t-1]
            sigma2[t] = omega + alpha * eps[t - 1] ** 2 + beta * sigma2[t - 1]

        return sigma2


class EGARCH:
    """Exponential GARCH model for asymmetric volatility.

    EGARCH models the log of variance, allowing for:
    - Leverage effects (negative shocks have different impact)
    - Guaranteed positive variance

    The EGARCH(1,1) model:
    log(sigma_t^2) = omega + alpha * |z_{t-1}| + gamma * z_{t-1} + beta * log(sigma_{t-1}^2)

    where z_t = epsilon_t / sigma_t are standardized shocks.

    Parameters
    ----------
    p : int, default 1
        Order of asymmetric terms.
    q : int, default 1
        Order of GARCH terms.

    Examples
    --------
    >>> returns = pd.Series(np.random.randn(1000) * 0.02)
    >>> model = EGARCH()
    >>> result = model.fit(returns)
    >>> forecasts = result.forecast(horizon=10)
    """

    def __init__(self, p: int = 1, q: int = 1):
        self.p = p
        self.q = q

    def fit(
        self,
        returns: pd.Series | np.ndarray,
    ) -> GARCHResult:
        """Fit EGARCH model to returns.

        Parameters
        ----------
        returns : Series or ndarray
            Return series.

        Returns
        -------
        GARCHResult
            Fitted model result.
        """
        y = np.asarray(returns).flatten()
        y = y[~np.isnan(y)]
        T = len(y)

        if T < 10:
            raise ValueError("Insufficient data for EGARCH estimation")

        # Initialize EGARCH params: omega, alpha, gamma, beta
        init_params = [0.01, 0.1, -0.1, 0.95]

        bounds = [
            (None, None),  # omega
            (1e-6, None),  # alpha
            (-1.0, 1.0),  # gamma (asymmetry)
            (1e-6, 1.0),  # beta
        ]

        result = optimize.minimize(
            self._neg_log_likelihood,
            init_params,
            args=(y,),
            bounds=bounds,
            method="L-BFGS-B",
        )

        omega, alpha, gamma, beta = result.x

        # Compute conditional variances
        log_var = np.zeros(T)
        eps = y / np.std(y)  # Initial standardization

        for t in range(1, T):
            z_prev = eps[t - 1]
            log_var[t] = omega + alpha * np.abs(z_prev) + gamma * z_prev + beta * log_var[t - 1]

        cond_var = np.exp(log_var)
        residuals = y / np.sqrt(cond_var)

        return GARCHResult(
            params={
                "omega": omega,
                "alpha": alpha,
                "gamma": gamma,
                "beta": beta,
            },
            conditional_var=cond_var,
            residuals=residuals,
            log_likelihood=-result.fun,
        )

    def _neg_log_likelihood(
        self,
        params: np.ndarray,
        y: np.ndarray,
    ) -> float:
        """Negative log-likelihood for EGARCH."""
        omega, alpha, gamma, beta = params
        T = len(y)

        # Compute log variances
        log_var = np.zeros(T)
        eps = y / np.std(y)  # Standardize

        for t in range(1, T):
            z_prev = eps[t - 1]
            log_var[t] = omega + alpha * np.abs(z_prev) + gamma * z_prev + beta * log_var[t - 1]

        sigma2 = np.exp(log_var)

        # Suppress numerical warnings during optimization
        # These warnings are expected during early iterations and don't affect final results
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            eps_valid = y[1:] / np.sqrt(sigma2[1:])
            sigma2_valid = sigma2[1:]
            loglik = -0.5 * np.sum(np.log(2 * np.pi * sigma2_valid) + eps_valid**2)

        return float(-loglik)


class GJRGARCH:
    """GJR-GARCH model with leverage effect.

    GJR-GARCH adds a term to capture asymmetric response to shocks:
    - Negative shocks (bad news) increase volatility more than positive shocks

    The GJR-GARCH(1,1) model:
    sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + gamma * I_{t-1} * epsilon_{t-1}^2 + beta * sigma_{t-1}^2

    where I_t = 1 if epsilon_t < 0 else 0.

    Parameters
    ----------
    p : int, default 1
        Order of ARCH terms.
    q : int, default 1
        Order of GARCH terms.

    Examples
    --------
    >>> returns = pd.Series(np.random.randn(1000) * 0.02)
    >>> model = GJRGARCH()
    >>> result = model.fit(returns)
    >>> print(f"Leverage gamma: {result.params['gamma']:.3f}")
    """

    def __init__(self, p: int = 1, q: int = 1):
        self.p = p
        self.q = q

    def fit(
        self,
        returns: pd.Series | np.ndarray,
    ) -> GARCHResult:
        """Fit GJR-GARCH model to returns.

        Parameters
        ----------
        returns : Series or ndarray
            Return series.

        Returns
        -------
        GARCHResult
            Fitted model result including leverage parameter gamma.
        """
        y = np.asarray(returns).flatten()
        y = y[~np.isnan(y)]
        T = len(y)

        if T < 10:
            raise ValueError("Insufficient data for GJR-GARCH estimation")

        # Initialize parameters: omega, alpha, gamma (leverage), beta
        init_params = [0.01, 0.05, 0.05, 0.9]

        bounds = [
            (1e-6, None),  # omega
            (1e-6, 1.0),  # alpha
            (0.0, 1.0),  # gamma (leverage, >= 0)
            (1e-6, 1.0),  # beta
        ]

        result = optimize.minimize(
            self._neg_log_likelihood,
            init_params,
            args=(y,),
            bounds=bounds,
            method="L-BFGS-B",
        )

        omega, alpha, gamma, beta = result.x

        # Compute conditional variances
        cond_var = self._compute_conditional_var(y, omega, alpha, gamma, beta)

        residuals = y / np.sqrt(cond_var)

        return GARCHResult(
            params={
                "omega": omega,
                "alpha": alpha,
                "gamma": gamma,  # Leverage effect
                "beta": beta,
            },
            conditional_var=cond_var,
            residuals=residuals,
            log_likelihood=-result.fun,
        )

    def _neg_log_likelihood(
        self,
        params: np.ndarray,
        y: np.ndarray,
    ) -> float:
        """Negative log-likelihood for GJR-GARCH."""
        omega, alpha, gamma, beta = params

        cond_var = self._compute_conditional_var(y, omega, alpha, gamma, beta)

        # Skip initial values
        burn = 1
        var_valid = cond_var[burn:]
        y_valid = y[burn:]

        loglik = -0.5 * np.sum(np.log(2 * np.pi * var_valid) + y_valid**2 / var_valid)

        return float(-loglik)

    def _compute_conditional_var(
        self,
        y: np.ndarray,
        omega: float,
        alpha: float,
        gamma: float,
        beta: float,
    ) -> np.ndarray:
        """Compute conditional variances with leverage effect."""
        T = len(y)
        sigma2 = np.ones(T) * float(np.var(y))

        for t in range(1, T):
            # Indicator for negative shock
            indicator = 1 if y[t - 1] < 0 else 0

            # GJR-GARCH variance recursion
            sigma2[t] = omega + alpha * y[t - 1] ** 2 + gamma * indicator * y[t - 1] ** 2 + beta * sigma2[t - 1]

        return sigma2


def forecast_volatility(
    returns: pd.Series | np.ndarray,
    model: str = "GARCH",
    horizon: int = 1,
    **kwargs,
) -> tuple[np.ndarray, GARCHResult]:
    """Forecast future volatility using GARCH models.

    Convenience function for volatility forecasting.

    Parameters
    ----------
    returns : Series or ndarray
        Historical returns.
    model : str, default 'GARCH'
        Model type: 'GARCH', 'EGARCH', 'GJRGARCH'.
    horizon : int, default 1
        Forecast horizon.
    **kwargs
        Additional model parameters (p, q, etc.).

    Returns
    -------
    forecasts : ndarray
        Forecasted conditional variances.
    result : GARCHResult
        Fitted model result.

    Examples
    --------
    >>> returns = pd.Series(np.random.randn(1000) * 0.02)
    >>> forecasts, result = forecast_volatility(returns, model="EGARCH", horizon=5)
    >>> print(f"5-day volatility forecast: {np.sqrt(forecasts)}")
    """
    models = {
        "GARCH": GARCH,
        "EGARCH": EGARCH,
        "GJRGARCH": GJRGARCH,
    }

    if model not in models:
        raise ValueError(f"Unknown model: {model}. Available: {list(models.keys())}")

    model_class = models[model]
    model_instance = model_class(**kwargs)
    result = model_instance.fit(returns)
    forecasts = result.forecast(horizon=horizon)

    return forecasts, result


def conditional_var(
    returns: pd.Series | np.ndarray,
    model: str = "GARCH",
    alpha: float = 0.05,
    **kwargs,
) -> dict[str, float | np.ndarray | GARCHResult]:
    """Calculate conditional VaR using GARCH models.

    Parameters
    ----------
    returns : Series or ndarray
        Historical returns.
    model : str, default 'GARCH'
        Model type.
    alpha : float, default 0.05
        Significance level.
    **kwargs
        Additional model parameters.

    Returns
    -------
    dict
        Contains 'var' (VaR estimate), 'cond_var' (conditional variances),
        and 'result' (full model fit).

    Examples
    --------
    >>> returns = pd.Series(np.random.randn(1000) * 0.02)
    >>> risk = conditional_var(returns, model="GJRGARCH", alpha=0.01)
    >>> print(f"Conditional VaR (99%): {risk['var']:.2%}")
    """
    forecasts, result = forecast_volatility(returns, model, horizon=1, **kwargs)

    # Forecasted variance
    forecast_var = forecasts[-1]

    # VaR using normal quantile
    from scipy import stats

    z_alpha = stats.norm.ppf(alpha)
    var = z_alpha * np.sqrt(forecast_var)

    return {
        "var": var,
        "cond_var": forecast_var,
        "result": result,
    }
