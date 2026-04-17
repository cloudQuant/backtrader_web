"""RollingEngine — batch rolling metric computation.

Computes multiple rolling metrics in a single pass where possible,
avoiding redundant rolling-window iteration.

Usage::

    from fincore.core.engine import RollingEngine
    engine = RollingEngine(returns, window=60)
    results = engine.compute(['sharpe', 'volatility', 'max_drawdown'])
    # results is a dict[str, pd.Series]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from fincore.constants import DAILY
from fincore.metrics.basic import annualization_factor as _ann_factor

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["RollingEngine"]


# Registry of available rolling metric names
_AVAILABLE_METRICS = frozenset(
    {
        "sharpe",
        "volatility",
        "max_drawdown",
        "beta",
        "sortino",
        "mean_return",
    }
)


class RollingEngine:
    """Batch rolling metric computation engine.

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative simple returns with a DatetimeIndex.
    factor_returns : pd.Series, optional
        Benchmark returns (required for ``beta``).
    window : int, optional
        Rolling window size.  Default 252 (approx. 1 year of daily data).
    period : str, optional
        Data frequency.  Default ``DAILY``.
    """

    def __init__(
        self,
        returns: pd.Series,
        *,
        factor_returns: pd.Series | None = None,
        window: int = 252,
        period: str = DAILY,
    ) -> None:
        self._returns = returns
        self._factor_returns = factor_returns
        self._window = window
        self._period = period
        self._ann = _ann_factor(period, None)
        self._sqrt_ann = float(np.sqrt(self._ann))

    @property
    def available_metrics(self) -> frozenset:
        """Return the set of metric names supported by this engine."""
        return _AVAILABLE_METRICS

    # ------------------------------------------------------------------
    # Core compute
    # ------------------------------------------------------------------

    def compute(
        self,
        metrics: list[str] | str = "all",
    ) -> dict[str, pd.Series]:
        """Compute the requested rolling metrics.

        Parameters
        ----------
        metrics : list of str or ``'all'``
            Which metrics to compute.  Pass ``'all'`` to compute every
            available metric.

        Returns
        -------
        dict[str, pd.Series]
            Mapping from metric name to rolling values.
        """
        if metrics == "all":
            metrics = list(_AVAILABLE_METRICS)

        results: dict[str, pd.Series] = {}
        for name in metrics:
            fn = getattr(self, f"_compute_{name}", None)
            if fn is None:
                raise ValueError(f"Unknown metric {name!r}. Available: {sorted(_AVAILABLE_METRICS)}")
            results[name] = fn()
        return results

    # ------------------------------------------------------------------
    # Individual metric implementations
    # ------------------------------------------------------------------

    def _compute_sharpe(self) -> pd.Series:
        w = self._window
        ret = self._returns
        rolling_mean = ret.rolling(w, min_periods=w).mean()
        rolling_std = ret.rolling(w, min_periods=w).std(ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = (rolling_mean / rolling_std) * self._sqrt_ann
        return result.dropna()

    def _compute_volatility(self) -> pd.Series:
        w = self._window
        result = self._returns.rolling(w, min_periods=w).std(ddof=1) * self._sqrt_ann
        return result.dropna()

    def _compute_max_drawdown(self) -> pd.Series:
        from fincore.metrics.rolling import roll_max_drawdown

        return roll_max_drawdown(self._returns, window=self._window)

    def _compute_beta(self) -> pd.Series:
        if self._factor_returns is None:
            raise ValueError("factor_returns required to compute 'beta'")
        from fincore.metrics.rolling import roll_beta

        return roll_beta(self._returns, self._factor_returns, window=self._window)

    def _compute_sortino(self) -> pd.Series:
        w = self._window
        ret = self._returns
        rolling_mean = ret.rolling(w, min_periods=w).mean()
        # downside deviation: std of returns below 0
        downside = ret.copy()
        downside[downside > 0] = 0.0
        rolling_downside_std = downside.rolling(w, min_periods=w).std(ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = (rolling_mean / rolling_downside_std) * self._sqrt_ann
        return result.dropna()

    def _compute_mean_return(self) -> pd.Series:
        w = self._window
        result = self._returns.rolling(w, min_periods=w).mean() * self._ann
        return result.dropna()
