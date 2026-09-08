"""Fail-closed statistical primitives for trusted AI research promotion gates."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from purgedcv import deflated_sharpe_ratio


def calculate_deflated_sharpe(
    returns: Sequence[float],
    *,
    trial_sharpes: Sequence[float],
    bars_per_year: int = 252,
) -> float:
    """Calculate DSR from the full cross-trial Sharpe distribution.

    ``var_sharpe`` is deliberately derived from the recorded Sharpe values of
    all market trials.  Using the variance of one candidate's return series
    would have incompatible units and silently discard multiple-testing data.
    """

    if len(returns) < 2:
        raise ValueError("EVALUATION_RETURNS_INSUFFICIENT")
    if not trial_sharpes:
        raise ValueError("EVALUATION_TRIAL_SHARPES_REQUIRED")
    values = np.asarray(returns, dtype=float)
    sharpes = np.asarray(trial_sharpes, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("EVALUATION_RETURNS_NOT_FINITE")
    if not np.isfinite(sharpes).all():
        raise ValueError("EVALUATION_TRIAL_SHARPES_NOT_FINITE")
    if bars_per_year < 1:
        raise ValueError("EVALUATION_BARS_PER_YEAR_INVALID")

    variance = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    return float(
        deflated_sharpe_ratio(
            values,
            n_trials=len(sharpes),
            var_sharpe=variance,
            bars_per_year=bars_per_year,
        )
    )
