"""Type definitions for fincore.

Provides type aliases and structured return types used across the library.
All NamedTuple types are backward-compatible with plain tuple unpacking.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Union

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Input type aliases
# ---------------------------------------------------------------------------
ArrayLike = Union[pd.Series, np.ndarray, Sequence[float]]
ReturnSeries = Union[pd.Series, np.ndarray]
ReturnOrDataFrame = Union[pd.Series, pd.DataFrame, np.ndarray]

# ---------------------------------------------------------------------------
# Structured return types (backward-compatible with tuple unpacking)
# ---------------------------------------------------------------------------


class DrawdownPeriod(NamedTuple):
    """A single drawdown period with peak, valley and optional recovery."""

    peak: pd.Timestamp
    valley: pd.Timestamp
    recovery: pd.Timestamp | None


class AlphaBeta(NamedTuple):
    """Alpha and beta from a regression of returns on a factor."""

    alpha: float
    beta: float


class BootstrapResult(NamedTuple):
    """Result of a bootstrap analysis."""

    samples: np.ndarray
    mean: float
    median: float
    ci_lower: float
    ci_upper: float


# ---------------------------------------------------------------------------
# Metric result types (scalar or per-column)
# ---------------------------------------------------------------------------
# Return type for metrics that yield one value per input column (or scalar for 1D).
MetricResult = Union[float, np.ndarray, pd.Series]

# ---------------------------------------------------------------------------
# Constant type aliases
# ---------------------------------------------------------------------------
Period = str  # 'daily', 'weekly', 'monthly', 'yearly'
