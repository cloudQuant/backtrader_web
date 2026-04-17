"""Fama-French multi-factor model implementation.

Provides factor model estimation and attribution using the Fama-French
multi-factor framework:
- 3-Factor model: Market (MKT), Size (SMB), Value (HML)
- 5-Factor model: MKT, SMB, HML, Profitability (RMW), Investment (CMA)
- Momentum: Fama-French-Carhart 4-factor model
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, TypedDict

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "FF3_FACTORS",
    "FF4MOM_FACTORS",
    "FF5_FACTORS",
    "FamaFrenchFitResult",
    "FamaFrenchModel",
    "FamaFrenchProvider",
    "calculate_idiosyncratic_risk",
    "clear_ff_factor_cache",
    "fetch_ff_factors",
    "set_ff_provider",
]


# Standard Fama-French factor definitions
FF3_FACTORS = ["MKT", "SMB", "HML"]
FF5_FACTORS = ["MKT", "SMB", "HML", "RMW", "CMA"]
FF4MOM_FACTORS = ["MKT", "SMB", "HML", "MOM"]

# Minimum std threshold for near-zero variance (avoids div-by-zero in autocorrelation)
_MIN_STD = 1e-15


class FamaFrenchFitResult(TypedDict):
    """Result of Fama-French factor model regression.

    Attributes
    ----------
    alpha : float
        Intercept (alpha) of the regression.
    betas : dict[str, float]
        Factor loadings for each factor.
    r_squared : float
        R-squared of the regression.
    std_errors : np.ndarray
        Standard errors of coefficients.
    p_values : np.ndarray
        P-values for coefficient significance tests.
    residuals : np.ndarray
        Residuals from the regression.
    """

    alpha: float
    betas: dict[str, float]
    r_squared: float
    std_errors: np.ndarray
    p_values: np.ndarray
    residuals: np.ndarray


class FamaFrenchModel:
    """Fama-French multi-factor model estimator.

    Supports OLS regression with Newey-West standard errors
    and various factor model specifications.
    """

    def __init__(
        self,
        model_type: str = "5factor",
        risk_free_rate: float = 0.0,
    ):
        """Initialize Fama-French model.

        Parameters
        ----------
        model_type : str, default "5factor"
            Factor model specification.
            Options: '3factor', '5factor', '4factor_mom'
        risk_free_rate : float, default 0.0
            Risk-free rate for excess returns calculation.
        """
        self.model_type = model_type
        self.risk_free_rate = risk_free_rate
        self._alpha: float | None = None
        self._betas: dict[str, float] | None = None
        self._set_factors()

    def _set_factors(self) -> None:
        """Set factor list based on model type."""
        if self.model_type == "3factor":
            self.factors = FF3_FACTORS
        elif self.model_type == "5factor":
            self.factors = FF5_FACTORS
        elif self.model_type == "4factor_mom":
            self.factors = FF4MOM_FACTORS
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}. Use: '3factor', '5factor', '4factor_mom'")

    def fit(
        self,
        returns: pd.Series | pd.DataFrame,
        factor_data: pd.DataFrame,
        method: str = "ols",
        newey_west_lags: int = 1,
    ) -> FamaFrenchFitResult:
        """Estimate factor model using OLS regression.

        Parameters
        ----------
        returns : pd.Series or pd.DataFrame
            Asset or portfolio returns to explain.
        factor_data : pd.DataFrame
            Factor returns with columns matching factor definitions.
        method : str, default "ols"
            Estimation method. Options: 'ols', 'wls', 'gls'.
        newey_west_lags : int, default 1
            Number of lags for Newey-West standard errors.

        Returns
        -------
        dict
            Dictionary containing:
            - 'alpha': Intercept (alpha)
            - 'betas': Factor loadings
            - 'r_squared': R-squared of regression
            - 'std_errors': Standard errors (Newey-West if lags > 0)
            - 'p_values': P-values for coefficients
            - 'residuals': Regression residuals
        """
        # Prepare data — when a multi-column DataFrame is passed, use the
        # first column as the dependent variable (single-asset regression).
        if isinstance(returns, pd.DataFrame) and returns.shape[1] > 1:
            y = returns.iloc[:, 0].values.ravel()
        elif isinstance(returns, pd.DataFrame):
            y = returns.values.ravel()
        else:
            y = np.asarray(returns).ravel()
        X = factor_data[self.factors].values

        # Add constant for intercept  — shape (N, K+1)
        X_with_const = np.column_stack([np.ones(X.shape[0]), X])

        # OLS / WLS regression
        if method in ("ols", "wls"):
            beta_coeffs, _ss_res, _, _ = np.linalg.lstsq(X_with_const, y, rcond=None)

            # Compute residuals explicitly (lstsq only returns ss_res for overdetermined systems)
            y_pred = X_with_const @ beta_coeffs
            residuals = y - y_pred

            # Calculate R-squared
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            ss_res = np.sum(residuals**2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        else:
            raise ValueError(f"Unknown method: {method}")

        # Extract alpha and betas
        alpha: float = float(beta_coeffs[0])
        betas: dict[str, float] = dict(zip(self.factors, beta_coeffs[1:].tolist(), strict=False))

        # Calculate standard errors
        n = len(y)
        k = len(beta_coeffs)
        resid_var = np.sum(residuals**2) / max(n - k, 1)

        # Newey-West standard errors
        if newey_west_lags > 0:
            acorr_vals: list[float] = []
            for lag in range(1, newey_west_lags + 1):
                if len(residuals) > lag:
                    resid_prev = residuals[:-lag]
                    resid_next = residuals[lag:]
                    if np.std(resid_prev) < _MIN_STD or np.std(resid_next) < _MIN_STD:
                        acorr_vals.append(0.0)
                    else:
                        with np.errstate(invalid="ignore", divide="ignore"):
                            corr = np.corrcoef(resid_prev, resid_next)[0, 1]
                        acorr_vals.append(float(corr) if np.isfinite(corr) else 0.0)
                else:
                    acorr_vals.append(0.0)

            # Newey-West HAC adjustment factor
            nw_factor = 1.0
            for j, rho_j in enumerate(acorr_vals):
                weight = 1 - (j + 1) / (newey_west_lags + 1)
                nw_factor += 2 * weight * rho_j

            std_errors = np.sqrt(resid_var * nw_factor / n) * np.ones(k)
        else:
            # Simple OLS standard errors
            std_errors = np.sqrt(np.diag(resid_var * np.linalg.inv(X_with_const.T @ X_with_const)))

        # Calculate t-statistics and p-values
        t_stats = beta_coeffs / np.where(std_errors > 0, std_errors, 1e-10)
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), max(n - k, 1)))

        # Store alpha and betas for later use
        self._alpha = alpha
        self._betas = betas

        return {
            "alpha": float(alpha),
            "betas": betas,
            "r_squared": float(r_squared),
            "std_errors": std_errors,
            "p_values": p_values,
            "residuals": residuals,
        }

    def predict(
        self,
        factor_data: pd.DataFrame,
    ) -> np.ndarray:
        """Predict returns using estimated model.

        Parameters
        ----------
        factor_data : pd.DataFrame
            Factor returns with columns matching factor definitions.

        Returns
        -------
        np.ndarray
            Predicted returns.
        """
        coeffs = self._get_regression_coeffs()
        X = factor_data[self.factors].values

        # Add constant — shape (N, K+1)
        X_with_const = np.column_stack([np.ones(X.shape[0]), X])
        # numpy typing for matmul can degrade to Any; force ndarray
        return np.asarray(X_with_const @ coeffs, dtype=float)

    def _get_regression_coeffs(self) -> np.ndarray:
        """Get concatenated alpha and betas from last fit."""
        if self._betas is None or self._alpha is None:
            raise RuntimeError("Model must be fit before prediction")

        coeffs_list = [self._alpha] + [self._betas[f] for f in self.factors]
        return np.asarray(coeffs_list, dtype=float)

    def get_factor_exposures(
        self,
        returns: pd.DataFrame,
        factor_data: pd.DataFrame,
        rolling_window: int | None = None,
    ) -> pd.DataFrame:
        """Calculate rolling factor exposures (betas).

        Parameters
        ----------
        returns : pd.DataFrame
            Asset returns (T x N).
        factor_data : pd.DataFrame
            Factor returns (T x K factors).
        rolling_window : int, optional
            Rolling window size. If None, full sample.

        Returns
        -------
        pd.DataFrame
            Rolling factor exposures (T x K).
        """
        exposures = []

        for t in range(len(returns)):
            if rolling_window is None:
                # Use full history up to time t
                start = 0
                end = t + 1
            else:
                # Use rolling window
                start = max(0, t - rolling_window + 1)
                end = min(t + 1, len(returns))

            window_returns = returns.iloc[start:end]
            window_factors = factor_data.iloc[start:end]

            if end > start and len(window_returns) > len(self.factors):
                # Fit model on window (first column as proxy)
                result = self.fit(
                    window_returns.iloc[:, 0],
                    window_factors,
                )
                result_alpha = result["alpha"]
                result_betas = result["betas"]
                exposures.append([result_alpha] + [result_betas.get(f, np.nan) for f in self.factors])
            else:
                # Not enough data - use NaN
                exposures.append([np.nan] * (len(self.factors) + 1))

        # Create column names
        column_names = ["alpha", *self.factors]
        return pd.DataFrame(exposures, index=returns.index, columns=column_names)

    def attribution_decomposition(
        self,
        returns: pd.Series,
        factor_data: pd.DataFrame,
    ) -> dict[str, float]:
        """Decompose returns using factor model.

        Parameters
        ----------
        returns : pd.Series
            Portfolio returns to attribute.
        factor_data : pd.DataFrame
            Factor returns.

        Returns
        -------
        dict
            Factor attribution breakdown.
        """
        # Fit model
        result = self.fit(returns, factor_data)

        # Calculate average factor returns
        avg_factor_returns = factor_data[self.factors].mean()

        # Factor contributions
        factor_contribs: dict[str, float] = {}
        result_betas = result["betas"]
        for factor, beta in result_betas.items():
            factor_contribs[factor] = beta * avg_factor_returns[factor]

        # Calculate contributions
        total_return = float(np.mean(returns)) - self.risk_free_rate
        alpha_contrib = float(result["alpha"])
        specific_contrib = sum(factor_contribs.values())

        return {
            "alpha": alpha_contrib,
            **{f"{factor}_attribution": contrib for factor, contrib in factor_contribs.items()},
            "specific_return": float(specific_contrib),
            "common_return": total_return,
            "unexplained": total_return - alpha_contrib - specific_contrib,
        }


def fetch_ff_factors(
    start: str,
    end: str,
    library: str = "french",
    *,
    provider: FamaFrenchProvider | None = None,
    copy: bool = True,
) -> pd.DataFrame:
    """Fetch Fama-French factors.

    .. note::

       A concrete data provider must be configured before calling this
       function.  Pass a ``provider`` that implements the
       ``FamaFrenchProvider`` protocol, or set a module-level provider
       via :func:`set_ff_provider`.

    Parameters
    ----------
    start : str
        Start date (YYYY-MM-DD).
    end : str
        End date (YYYY-MM-DD).
    library : str, default "french"
        Data source. Options: 'french', 'chinese'.

    Returns
    -------
    pd.DataFrame
        DataFrame with factor returns. Columns depend on library.

    Raises
    ------
    NotImplementedError
        Raised when no provider is configured.
    """
    if provider is not None:
        df = provider(start, end, library)
        if not isinstance(df, pd.DataFrame):
            raise TypeError("Fama-French provider must return a pandas DataFrame")
        return df.copy(deep=True) if copy else df

    df_cached = _fetch_ff_factors_cached(start, end, library)
    return df_cached.copy(deep=True) if copy else df_cached


class FamaFrenchProvider(Protocol):
    """Protocol for Fama-French factor data providers.

    A provider function that takes date range and library name,
    and returns a DataFrame of factor returns.
    """

    def __call__(self, start: str, end: str, library: str) -> pd.DataFrame:
        """Fetch Fama-French factor data.

        Parameters
        ----------
        start : str
            Start date (YYYY-MM-DD format).
        end : str
            End date (YYYY-MM-DD format).
        library : str
            Data library identifier.

        Returns
        -------
        pd.DataFrame
            Factor returns with columns for each factor.
        """


_ff_provider: FamaFrenchProvider | None = None


def set_ff_provider(provider: FamaFrenchProvider | None) -> None:
    """Set the module-level Fama-French factor provider and clear cache."""
    global _ff_provider
    _ff_provider = provider
    _fetch_ff_factors_cached.cache_clear()


def clear_ff_factor_cache() -> None:
    """Clear the in-process factor cache used by :func:`fetch_ff_factors`."""
    _fetch_ff_factors_cached.cache_clear()


@lru_cache(maxsize=128)
def _fetch_ff_factors_cached(start: str, end: str, library: str) -> pd.DataFrame:
    provider = _ff_provider
    if provider is None:
        raise NotImplementedError(
            "No Fama-French data provider is configured. "
            "Pass `provider=` to fetch_ff_factors(), or set a module provider via set_ff_provider()."
        )
    df = provider(start, end, library)
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Fama-French provider must return a pandas DataFrame")
    # Freeze the cached value against accidental mutation; callers get copies by default.
    return df.copy(deep=True)


def calculate_idiosyncratic_risk(
    returns: pd.DataFrame,
    factor_data: pd.DataFrame,
    model: FamaFrenchModel | None = None,
) -> pd.Series:
    """Calculate idiosyncratic volatility (asset-specific risk).

    Measures risk that cannot be diversified away:
    VAR(asset) - cov(asset, market) * var(market) / cov(market, market)

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (N assets x T).
    factor_data : pd.DataFrame
        Market factor returns (T x K).
    model : FamaFrenchModel, optional
        Pre-fitted model. If None, fits new model.

    Returns
    -------
    pd.Series
        Idiosyncratic volatility for each asset.
    """
    n_assets = returns.shape[1]

    if model is None:
        model = FamaFrenchModel()
        model.fit(returns.iloc[:, 0], factor_data)

    # Calculate systematic and specific returns
    market_returns = factor_data["MKT"].values
    rf = model.risk_free_rate

    specific_volatilities = []

    for i in range(n_assets):
        asset_returns = returns.iloc[:, i].values

        if model._betas is not None:
            beta = model._betas.get("MKT", 1.0)  # Default to market beta

            # Total return variance
            total_return = asset_returns - rf
            total_var = np.var(total_return)

            # Systematic variance
            systematic_var = (beta**2) * np.var(market_returns - rf)

            # Idiosyncratic variance
            idio_var = total_var - systematic_var

            specific_volatilities.append(np.sqrt(idio_var) if idio_var > 0 else 0)

    return pd.Series(specific_volatilities, index=returns.columns)
