"""Utility functions for optimization module.

Provides common error handling and result validation for scipy.optimize
results across the optimization module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from scipy import optimize


class OptimizationError(Exception):
    """Raised when optimization fails to converge or finds invalid solution."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        solver_message: str | None = None,
    ) -> None:
        self.status = status
        self.solver_message = solver_message
        super().__init__(message)


def validate_result(
    res: optimize.OptimizeResult,
    context: str,
    allow_nan: bool = False,
) -> NDArray[np.float64]:
    """Validate scipy.optimize result and return weights.

    Parameters
    ----------
    res : OptimizeResult
        Result from scipy.optimize.minimize.
    context : str
        Description of optimization context (e.g., "max_sharpe", "risk_parity").
    allow_nan : bool, default False
        Whether to allow NaN/inf weights (useful for frontier computation).

    Returns
    -------
    NDArray[np.float64]
        Validated weight array.

    Raises
    ------
    OptimizationError
        If optimization failed or returned invalid weights.
    """
    if not res.success:
        msg = f"Optimization failed for {context}: status={res.status}, message={res.message!r}"
        raise OptimizationError(
            msg,
            status=res.status,
            solver_message=str(res.message),
        )

    weights: NDArray[np.float64] = res.x

    # Check for NaN/inf
    if not allow_nan and np.any(~np.isfinite(weights)):
        msg = f"Optimization for {context} returned invalid weights (NaN/inf detected): {weights}"
        raise OptimizationError(
            msg,
            status=res.status,
            solver_message=str(res.message),
        )

    return weights


def normalize_weights(
    weights: NDArray[np.float64],
    epsilon: float = 1e-12,
) -> NDArray[np.float64]:
    """Normalize weights to sum to 1, handling near-zero cases.

    Parameters
    ----------
    weights : NDArray[np.float64]
        Raw weight array.
    epsilon : float, default 1e-12
        Threshold for treating sum as zero.

    Returns
    -------
    NDArray[np.float64]
        Normalized weights summing to 1.

    Raises
    ------
    OptimizationError
        If weights sum is too small or negative.
    """
    total = float(weights.sum())
    if abs(total) < epsilon:
        raise OptimizationError(f"Cannot normalize weights: sum ({total}) is too close to zero")
    if total < 0:
        raise OptimizationError(f"Cannot normalize weights: sum ({total}) is negative")
    return weights / total
