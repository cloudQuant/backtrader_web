"""AnalysisContext — cached, lazy performance analytics.

Usage::

    import fincore
    ctx = fincore.analyze(returns, factor_returns=benchmark)
    print(ctx.sharpe_ratio)
    print(ctx.perf_stats())
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fincore.constants import DAILY
from fincore.metrics.basic import annualization_factor as _ann_factor
from fincore.metrics.drawdown import max_drawdown
from fincore.metrics.ratios import (
    calmar_ratio as _calmar_ratio,
)
from fincore.metrics.ratios import (
    information_ratio as _information_ratio,
)
from fincore.metrics.ratios import (
    omega_ratio as _omega_ratio,
)
from fincore.metrics.ratios import (
    sortino_ratio as _sortino_ratio,
)
from fincore.metrics.ratios import stability_of_timeseries
from fincore.metrics.returns import cum_returns, cum_returns_final
from fincore.metrics.risk import (
    tail_ratio,
    value_at_risk,
)
from fincore.metrics.stats import (
    kurtosis,
    skewness,
)
from fincore.metrics.yearly import annual_return as _annual_return
from fincore.utils import nanmean, nanstd

__all__ = ["AnalysisContext", "analyze"]


class AnalysisContext:
    """Lazy, cached container for performance analytics.

    All metrics are computed on first access and cached via
    :func:`functools.cached_property`.  Call :meth:`invalidate` to
    clear all cached values (e.g. after replacing the underlying data).

    Parameters
    ----------
    returns : pd.Series
        Non-cumulative simple returns with a DatetimeIndex.
    factor_returns : pd.Series, optional
        Benchmark / factor returns aligned to the same dates.
    positions : pd.DataFrame, optional
        Daily net position values.
    transactions : pd.DataFrame, optional
        Executed trades.
    period : str, optional
        Data frequency.  Default ``DAILY``.

    """

    def __init__(
        self,
        returns: pd.Series,
        *,
        factor_returns: pd.Series | None = None,
        positions: pd.DataFrame | None = None,
        transactions: pd.DataFrame | None = None,
        period: str = DAILY,
    ) -> None:
        """Initialize the analysis context.

        Parameters
        ----------
        returns : pd.Series
            Portfolio returns.
        factor_returns : pd.Series, optional
            Benchmark or factor returns.
        positions : pd.DataFrame, optional
            Portfolio positions.
        transactions : pd.DataFrame, optional
            Executed trades.
        period : str, default DAILY
            Data frequency.
        """
        self._returns = returns
        self._factor_returns = factor_returns
        self._positions = positions
        self._transactions = transactions
        self._period = period

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @cached_property
    def _ann_factor(self) -> float:
        """Annualization factor for the configured period."""
        return _ann_factor(self._period, None)

    @cached_property
    def _sqrt_ann(self) -> float:
        """Square root of annualization factor."""
        return float(np.sqrt(self._ann_factor))

    @cached_property
    def _returns_array(self) -> np.ndarray:
        """Returns as numpy array."""
        return np.asanyarray(self._returns)

    @cached_property
    def _mean_return(self) -> float:
        """Mean of returns."""
        return float(nanmean(self._returns_array, axis=0))

    @cached_property
    def _std_return(self) -> float:
        """Standard deviation of returns."""
        return float(nanstd(self._returns_array, ddof=1, axis=0))

    # ------------------------------------------------------------------
    # Core metrics (cached_property)
    # ------------------------------------------------------------------

    @cached_property
    def annual_return(self) -> float:
        """Annualized return."""
        return float(_annual_return(self._returns, period=self._period))

    @cached_property
    def cumulative_returns(self) -> float:
        """Total cumulative return."""
        return float(cum_returns_final(self._returns, starting_value=0))

    @cached_property
    def annual_volatility(self) -> float:
        """Annualized volatility."""
        return float(self._std_return * self._sqrt_ann)

    @cached_property
    def sharpe_ratio(self) -> float:
        """Sharpe ratio (annualized)."""
        if len(self._returns) < 2:
            return np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            return float((self._mean_return / self._std_return) * self._sqrt_ann)

    @cached_property
    def calmar_ratio(self) -> float:
        """Calmar ratio (annual return / max drawdown)."""
        return float(_calmar_ratio(self._returns, period=self._period))

    @cached_property
    def stability(self) -> float:
        """R-squared of linear fit to cumulative returns."""
        return float(stability_of_timeseries(self._returns))

    @cached_property
    def max_drawdown(self) -> float:
        """Maximum drawdown."""
        return float(max_drawdown(self._returns))

    @cached_property
    def omega_ratio(self) -> float:
        """Omega ratio."""
        return float(_omega_ratio(self._returns))

    @cached_property
    def sortino_ratio(self) -> float:
        """Sortino ratio (annualized)."""
        return float(_sortino_ratio(self._returns, period=self._period))

    @cached_property
    def skew(self) -> float:
        """Return skewness."""
        return float(skewness(self._returns))

    @cached_property
    def kurtosis(self) -> float:
        """Return kurtosis."""
        return float(kurtosis(self._returns))

    @cached_property
    def tail_ratio(self) -> float:
        """Tail ratio (95th percentile / 5th percentile)."""
        return float(tail_ratio(self._returns))

    @cached_property
    def daily_value_at_risk(self) -> float:
        """Daily Value at Risk."""
        return float(value_at_risk(self._returns))

    # ------------------------------------------------------------------
    # Factor-dependent metrics
    # ------------------------------------------------------------------

    @cached_property
    def alpha(self) -> float:
        """Alpha (excess return over factor returns)."""
        if self._factor_returns is None:
            return np.nan
        from fincore.metrics.alpha_beta import alpha_beta

        return float(alpha_beta(self._returns, self._factor_returns)[0])

    @cached_property
    def beta(self) -> float:
        """Beta (sensitivity to factor returns)."""
        if self._factor_returns is None:
            return np.nan
        from fincore.metrics.alpha_beta import alpha_beta

        return float(alpha_beta(self._returns, self._factor_returns)[1])

    @cached_property
    def information_ratio(self) -> float:
        if self._factor_returns is None:
            return np.nan
        return float(_information_ratio(self._returns, self._factor_returns))

    # ------------------------------------------------------------------
    # Aggregate helpers
    # ------------------------------------------------------------------

    def perf_stats(self) -> pd.Series:
        """Return a :class:`pd.Series` of key performance metrics.

        This method assembles the cached sub-metrics so that repeated
        calls are essentially free after the first computation.
        """
        from collections import OrderedDict

        stats: dict[str, Any] = OrderedDict()
        stats["Annual return"] = self.annual_return
        stats["Cumulative returns"] = self.cumulative_returns
        stats["Annual volatility"] = self.annual_volatility
        stats["Sharpe ratio"] = self.sharpe_ratio
        stats["Calmar ratio"] = self.calmar_ratio
        stats["Stability"] = self.stability
        stats["Max drawdown"] = self.max_drawdown
        stats["Omega ratio"] = self.omega_ratio
        stats["Sortino ratio"] = self.sortino_ratio
        stats["Skew"] = self.skew
        stats["Kurtosis"] = self.kurtosis
        stats["Tail ratio"] = self.tail_ratio
        stats["Daily value at risk"] = self.daily_value_at_risk

        if self._factor_returns is not None:
            stats["Alpha"] = self.alpha
            stats["Beta"] = self.beta

        return pd.Series(stats)

    def to_dict(self) -> dict[str, Any]:
        """Return metrics as a plain dict (JSON-friendly values)."""
        s = self.perf_stats()
        return {k: (float(v) if np.isfinite(v) else None) for k, v in s.items()}

    def to_json(self, **kwargs: Any) -> str:
        """Serialize metrics to a JSON string."""
        return json.dumps(self.to_dict(), **kwargs)

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def plot(self, backend: str = "matplotlib", **kwargs: Any) -> Any:
        """Plot key performance charts using the specified backend.

        Parameters
        ----------
        backend : str
            Visualization backend name (``'matplotlib'`` or ``'html'``).

        Returns
        -------
        Depends on the backend (e.g. matplotlib Figure or HTML string).
        """
        from fincore.viz.base import get_backend

        viz = get_backend(backend)

        cum_ret = cum_returns(self._returns, starting_value=0)
        running_max = (1 + cum_ret).cummax()  # type: ignore[union-attr]
        drawdown = (1 + cum_ret) / running_max - 1

        viz.plot_returns(cum_ret, **kwargs)
        viz.plot_drawdown(drawdown, **kwargs)

        return viz

    def to_html(self, path: str | None = None) -> str:
        """Generate a self-contained HTML performance report.

        Parameters
        ----------
        path : str, optional
            If given, write the HTML to this file path.

        Returns
        -------
        str
            The HTML report as a string.
        """
        from fincore.viz.html_backend import HtmlReportBuilder

        builder = HtmlReportBuilder()
        builder.add_title("Performance Report")
        builder.add_metric_cards(
            self.perf_stats(),
            keys=["Annual return", "Sharpe ratio", "Max drawdown", "Annual volatility", "Calmar ratio"],
        )
        builder.add_heading("Performance Statistics")
        builder.add_stats_table(self.perf_stats())
        html = builder.build()
        if path is not None:
            Path(path).write_text(html, encoding="utf-8")
        return html

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        """Clear all cached metric values."""
        cls = type(self)
        for attr in list(self.__dict__):
            if (
                attr.startswith("_")
                and not attr.startswith("__")
                and attr in ("_returns", "_factor_returns", "_positions", "_transactions", "_period")
            ):
                continue
            if isinstance(getattr(cls, attr, None), cached_property):
                del self.__dict__[attr]

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        n = len(self._returns)
        start = self._returns.index[0].strftime("%Y-%m-%d") if n else "?"
        end = self._returns.index[-1].strftime("%Y-%m-%d") if n else "?"
        bm = "yes" if self._factor_returns is not None else "no"
        return f"AnalysisContext({start} → {end}, {n} obs, benchmark={bm})"


# ------------------------------------------------------------------
# Convenience constructor
# ------------------------------------------------------------------


def analyze(
    returns: pd.Series,
    *,
    factor_returns: pd.Series | None = None,
    positions: pd.DataFrame | None = None,
    transactions: pd.DataFrame | None = None,
    period: str = DAILY,
) -> AnalysisContext:
    """Create an :class:`AnalysisContext` — the recommended entry point.

    Example::

        import fincore
        ctx = fincore.analyze(returns, factor_returns=benchmark)
        print(ctx.sharpe_ratio)
        print(ctx.perf_stats())
    """
    return AnalysisContext(
        returns,
        factor_returns=factor_returns,
        positions=positions,
        transactions=transactions,
        period=period,
    )
