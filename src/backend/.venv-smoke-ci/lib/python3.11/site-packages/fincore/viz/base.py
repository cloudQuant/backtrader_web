"""Visualization backend protocol and registry.

Defines the :class:`VizBackend` protocol that all visualization backends
must satisfy, plus a helper :func:`get_backend` to resolve a backend by
name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["VizBackend", "get_backend"]


@runtime_checkable
class VizBackend(Protocol):
    """Protocol that every visualization backend must implement."""

    def plot_returns(self, cum_returns: pd.Series, **kwargs: Any) -> Any:
        """Plot cumulative returns."""
        ...  # pragma: no cover -- Protocol method

    def plot_drawdown(self, drawdown: pd.Series, **kwargs: Any) -> Any:
        """Plot drawdown underwater chart."""
        ...  # pragma: no cover -- Protocol method

    def plot_rolling_sharpe(
        self,
        sharpe: pd.Series,
        benchmark_sharpe: pd.Series | None = None,
        window: int = 252,
        **kwargs: Any,
    ) -> Any:
        """Plot rolling Sharpe ratio.

        Parameters
        ----------
        sharpe : pd.Series
            Rolling Sharpe ratio series.
        benchmark_sharpe : pd.Series, optional
            Optional benchmark rolling Sharpe series.
        window : int, default 252
            Window size (used for title/annotation).
        """
        ...  # pragma: no cover -- Protocol method

    def plot_monthly_heatmap(self, returns: pd.Series | pd.DataFrame, **kwargs: Any) -> Any:
        """Plot monthly returns heatmap.

        Parameters
        ----------
        returns : pd.Series or pd.DataFrame
            Either a daily returns series (will be aggregated internally) or a
            year x month table of monthly returns.
        """
        ...  # pragma: no cover -- Protocol method


def get_backend(name: str = "matplotlib") -> VizBackend:
    """Resolve a visualization backend by name.

    Parameters
    ----------
    name : str
        Backend identifier.  Supported backends:
        - ``'matplotlib'``: Static Matplotlib plots (requires matplotlib)
        - ``'html'``: Self-contained HTML reports
        - ``'plotly'``: Interactive Plotly plots (requires plotly)
        - ``'bokeh'``: Interactive Bokeh plots (requires bokeh)

    Returns
    -------
    VizBackend
        An instance satisfying the :class:`VizBackend` protocol.

    Raises
    ------
    ValueError
        If the requested backend is not recognized.
    ImportError
        If the backend's dependencies are not installed.
    """
    name = name.lower().strip()

    if name == "matplotlib":
        from fincore.viz.matplotlib_backend import MatplotlibBackend

        return MatplotlibBackend()

    if name == "html":
        from fincore.viz.html_backend import HtmlReportBuilder

        return HtmlReportBuilder()

    if name == "plotly":
        from fincore.viz.interactive.plotly_backend import PlotlyBackend

        return PlotlyBackend()

    if name == "bokeh":
        from fincore.viz.interactive.bokeh_backend import BokehBackend

        return BokehBackend()

    raise ValueError(f"Unknown viz backend {name!r}. Available: 'matplotlib', 'html', 'plotly', 'bokeh'")
