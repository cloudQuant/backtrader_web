"""Risk parity (equal risk contribution) portfolio optimization.

Computes portfolio weights such that each asset contributes equally
to the total portfolio risk (variance).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize as sp_opt

from fincore.constants import APPROX_BDAYS_PER_YEAR
from fincore.optimization._utils import normalize_weights, validate_result

__all__ = ["risk_parity"]


def risk_parity(
    returns: pd.DataFrame,
    risk_budget: np.ndarray | None = None,
    max_iter: int = 1000,
) -> dict[str, np.ndarray | float | list[str]]:
    """Compute risk-parity portfolio weights.

    Each asset's marginal risk contribution is equalised (or matched
    to a user-supplied risk budget).

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N).
    risk_budget : np.ndarray, optional
        Target risk budget per asset (sums to 1).
        Defaults to equal budget ``1/N`` for each asset.
    max_iter : int, default 1000
        Maximum solver iterations.

    Returns
    -------
    dict
        - 'weights': optimal weight array (N,)
        - 'risk_contributions': risk contribution per asset (N,)
        - 'volatility': portfolio annualised volatility
        - 'asset_names': list of asset names
    """
    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError("returns must be a non-empty DataFrame.")

    if returns.shape[0] < 2:
        raise ValueError("At least 2 observations are required for risk parity.")

    if max_iter < 1:
        raise ValueError("max_iter must be >= 1.")

    if not np.isfinite(returns.to_numpy(dtype=float)).all():
        raise ValueError("returns contains NaN or infinite values.")

    cov = returns.cov().values * APPROX_BDAYS_PER_YEAR
    n = cov.shape[0]
    asset_names = list(returns.columns)

    if risk_budget is None:
        risk_budget = np.ones(n) / n
    risk_budget = np.asarray(risk_budget, dtype=float)
    if risk_budget.ndim != 1:
        raise ValueError("risk_budget must be a 1D array.")
    if len(risk_budget) != n:
        raise ValueError(f"risk_budget length ({len(risk_budget)}) must match number of assets ({n}).")
    if not np.isfinite(risk_budget).all():
        raise ValueError("risk_budget contains NaN or infinite values.")
    if np.any(risk_budget < 0):
        raise ValueError("risk_budget must be non-negative.")
    if np.sum(risk_budget) <= 0:
        raise ValueError("risk_budget must have a positive sum.")
    risk_budget = risk_budget / risk_budget.sum()

    def _risk_contrib(w: np.ndarray) -> np.ndarray:
        port_var = w @ cov @ w
        if port_var < 1e-16:
            return np.zeros(n, dtype=float)
        marginal: np.ndarray = cov @ w
        port_vol = float(np.sqrt(port_var))
        rc: np.ndarray = w * marginal / port_vol
        return rc

    def _objective(w: np.ndarray) -> float:
        rc = _risk_contrib(w)
        rc_total = rc.sum()
        if rc_total < 1e-16:
            return 1e6
        rc_pct = rc / rc_total
        return float(np.sum((rc_pct - risk_budget) ** 2))

    w0 = np.ones(n) / n
    bounds = [(1e-6, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    res = sp_opt.minimize(
        _objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-14, "maxiter": max_iter},
    )

    weights = normalize_weights(validate_result(res, context="risk_parity"))
    rc = _risk_contrib(weights)
    vol = float(np.sqrt(weights @ cov @ weights))

    return {
        "weights": weights,
        "risk_contributions": rc,
        "volatility": vol,
        "asset_names": asset_names,
    }
