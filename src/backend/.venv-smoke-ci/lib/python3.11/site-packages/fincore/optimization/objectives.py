"""Constrained portfolio optimization with multiple objective functions.

Supports:
- max_sharpe: maximise risk-adjusted return
- min_variance: minimise portfolio variance
- target_return: minimise variance for a given target return
- target_risk: maximise return for a given target volatility
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import optimize as sp_opt

from fincore.optimization._utils import validate_result

__all__ = ["optimize"]


def optimize(
    returns: pd.DataFrame,
    objective: str = "max_sharpe",
    risk_free_rate: float = 0.0,
    target_return: float | None = None,
    target_volatility: float | None = None,
    short_allowed: bool = False,
    max_weight: float = 1.0,
    min_weight: float | None = None,
    sector_constraints: dict[str, tuple[float, float]] | None = None,
    sector_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Solve a constrained portfolio optimisation problem.

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (T x N).
    objective : str
        One of 'max_sharpe', 'min_variance', 'target_return', 'target_risk'.
    risk_free_rate : float, default 0.0
        Annual risk-free rate.
    target_return : float, optional
        Required for ``objective='target_return'``. Annualised target.
    target_volatility : float, optional
        Required for ``objective='target_risk'``. Annualised target.
    short_allowed : bool, default False
        Allow negative weights.
    max_weight : float, default 1.0
        Upper bound per asset.
    min_weight : float, optional
        Lower bound per asset. Defaults to 0 (or ``-max_weight`` if shorts allowed).
    sector_constraints : dict, optional
        ``{sector_name: (min_alloc, max_alloc)}`` pairs.
    sector_map : dict, optional
        ``{asset_name: sector_name}`` mapping (needed with ``sector_constraints``).

    Returns
    -------
    dict
        - 'weights': optimal weight array
        - 'return': annualised expected return
        - 'volatility': annualised volatility
        - 'sharpe': Sharpe ratio
        - 'asset_names': list
        - 'objective': objective used
    """
    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError("returns must be a non-empty DataFrame.")

    if returns.shape[0] < 2:
        raise ValueError("At least 2 observations are required for optimization.")

    if not np.isfinite(returns.to_numpy(dtype=float)).all():
        raise ValueError("returns contains NaN or infinite values.")

    if max_weight <= 0:
        raise ValueError("max_weight must be > 0.")

    if min_weight is not None and min_weight > max_weight:
        raise ValueError("min_weight must be <= max_weight.")

    if sector_constraints is not None and sector_map is None:
        raise ValueError("sector_map is required when sector_constraints is provided.")

    mu = returns.mean().values * 252
    cov = returns.cov().values * 252
    n = len(mu)
    asset_names = list(returns.columns)

    lb = min_weight if min_weight is not None else (-max_weight if short_allowed else 0.0)
    bounds = [(lb, max_weight)] * n
    constraints: list[dict] = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    # Sector constraints
    if sector_constraints and sector_map:
        for sector, (lo, hi) in sector_constraints.items():
            idx = [i for i, a in enumerate(asset_names) if sector_map.get(a) == sector]
            if idx:
                constraints.append({"type": "ineq", "fun": lambda w, ix=idx, lo=lo: np.sum(w[ix]) - lo})
                constraints.append({"type": "ineq", "fun": lambda w, ix=idx, hi=hi: hi - np.sum(w[ix])})

    def _vol(w: np.ndarray) -> float:
        return float(np.sqrt(w @ cov @ w))

    def _ret(w: np.ndarray) -> float:
        return float(w @ mu)

    w0 = np.ones(n) / n

    if objective == "max_sharpe":

        def _neg_sharpe(w):
            v = _vol(w)
            return -(_ret(w) - risk_free_rate) / v if v > 1e-12 else 1e6

        res = sp_opt.minimize(
            _neg_sharpe,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )

    elif objective == "min_variance":
        res = sp_opt.minimize(
            _vol,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )

    elif objective == "target_return":
        if target_return is None:
            raise ValueError("target_return must be specified for objective='target_return'")
        constraints.append({"type": "eq", "fun": lambda w: _ret(w) - target_return})
        res = sp_opt.minimize(
            _vol,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )

    elif objective == "target_risk":
        if target_volatility is None:
            raise ValueError("target_volatility must be specified for objective='target_risk'")
        constraints.append({"type": "eq", "fun": lambda w: _vol(w) - target_volatility})

        def _neg_ret(w):
            return -_ret(w)

        res = sp_opt.minimize(
            _neg_ret,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )

    else:
        raise ValueError(
            f"Unknown objective: {objective!r}. "
            "Choose from: 'max_sharpe', 'min_variance', 'target_return', 'target_risk'."
        )

    w = validate_result(res, context=f"optimize_{objective}")
    port_ret = _ret(w)
    port_vol = _vol(w)
    sharpe = (port_ret - risk_free_rate) / port_vol if port_vol > 1e-12 else 0.0

    return {
        "weights": w,
        "return": port_ret,
        "volatility": port_vol,
        "sharpe": sharpe,
        "asset_names": asset_names,
        "objective": objective,
    }
