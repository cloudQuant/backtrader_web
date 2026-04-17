"""Efficient frontier computation.

Computes the mean-variance efficient frontier for a set of assets
using quadratic optimization (scipy.optimize).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import optimize as sp_opt

from fincore.optimization._utils import validate_result

__all__ = ["efficient_frontier"]


def efficient_frontier(
    returns: pd.DataFrame,
    n_points: int = 50,
    risk_free_rate: float = 0.0,
    short_allowed: bool = False,
    max_weight: float = 1.0,
) -> dict[str, Any]:
    """Compute the mean-variance efficient frontier.

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N). Columns = asset names.
    n_points : int, default 50
        Number of points on the frontier.
    risk_free_rate : float, default 0.0
        Annual risk-free rate (used for Sharpe calculation).
    short_allowed : bool, default False
        Whether short selling is allowed.
    max_weight : float, default 1.0
        Maximum weight per asset.

    Returns
    -------
    dict
        - 'frontier_returns': array of annualised portfolio returns
        - 'frontier_volatilities': array of annualised portfolio volatilities
        - 'frontier_sharpe': array of Sharpe ratios
        - 'frontier_weights': (n_points x N) weight matrix
        - 'min_variance': dict with keys 'weights', 'return', 'volatility'
        - 'max_sharpe': dict with keys 'weights', 'return', 'volatility', 'sharpe'
        - 'asset_names': list of asset names
    """
    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError("returns must be a non-empty DataFrame.")

    if returns.shape[0] < 2:
        raise ValueError("At least 2 observations are required for frontier computation.")

    if returns.shape[1] < 2:
        raise ValueError("At least 2 assets required for frontier computation.")

    if n_points < 2:
        raise ValueError("n_points must be >= 2.")

    if max_weight <= 0:
        raise ValueError("max_weight must be > 0.")

    if not np.isfinite(returns.values).all():
        raise ValueError("returns contains NaN or infinite values.")

    mu = returns.mean().values * 252  # annualised
    cov = returns.cov().values * 252
    n = len(mu)
    asset_names = list(returns.columns)

    # --- weight bounds ---
    lb = -max_weight if short_allowed else 0.0
    bounds = [(lb, max_weight)] * n

    # --- constraints: weights sum to 1 ---
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    # --- helper: portfolio stats ---
    def _port_vol(w: np.ndarray) -> float:
        return float(np.sqrt(w @ cov @ w))

    def _port_ret(w: np.ndarray) -> float:
        return float(w @ mu)

    # --- minimum-variance portfolio ---
    w0 = np.ones(n) / n
    res_mv = sp_opt.minimize(
        _port_vol,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 1000},
    )
    mv_w = validate_result(res_mv, context="min_variance")
    mv_ret = _port_ret(mv_w)
    mv_vol = _port_vol(mv_w)

    # --- max-Sharpe portfolio ---
    def _neg_sharpe(w: np.ndarray) -> float:
        vol = _port_vol(w)
        if vol < 1e-12:
            return 1e6  # pragma: no cover -- Edge case for optimization
        return -((_port_ret(w) - risk_free_rate) / vol)

    res_ms = sp_opt.minimize(
        _neg_sharpe,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 1000},
    )
    ms_w = validate_result(res_ms, context="max_sharpe")
    ms_ret = _port_ret(ms_w)
    ms_vol = _port_vol(ms_w)
    ms_sharpe = (ms_ret - risk_free_rate) / ms_vol if ms_vol > 1e-12 else 0.0

    # --- frontier points ---
    ret_min = mv_ret
    ret_max = float(mu.max()) * 1.05
    target_rets = np.linspace(ret_min, ret_max, n_points)

    frontier_vols = np.empty(n_points)
    frontier_rets = np.empty(n_points)
    frontier_weights = np.empty((n_points, n))

    for i, target in enumerate(target_rets):
        cons_i = [*constraints, {"type": "eq", "fun": lambda w, t=target: _port_ret(w) - t}]
        res = sp_opt.minimize(
            _port_vol,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons_i,
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        if res.success:
            w_valid = validate_result(res, context=f"frontier_point_{i}", allow_nan=False)
            frontier_weights[i] = w_valid
            frontier_rets[i] = _port_ret(w_valid)
            frontier_vols[i] = _port_vol(w_valid)
        else:
            frontier_weights[i] = np.nan
            frontier_rets[i] = np.nan
            frontier_vols[i] = np.nan

    frontier_sharpe = np.where(
        frontier_vols > 1e-12,
        (frontier_rets - risk_free_rate) / frontier_vols,
        0.0,
    )

    return {
        "frontier_returns": frontier_rets,
        "frontier_volatilities": frontier_vols,
        "frontier_sharpe": frontier_sharpe,
        "frontier_weights": frontier_weights,
        "min_variance": {
            "weights": mv_w,
            "return": mv_ret,
            "volatility": mv_vol,
        },
        "max_sharpe": {
            "weights": ms_w,
            "return": ms_ret,
            "volatility": ms_vol,
            "sharpe": ms_sharpe,
        },
        "asset_names": asset_names,
    }
