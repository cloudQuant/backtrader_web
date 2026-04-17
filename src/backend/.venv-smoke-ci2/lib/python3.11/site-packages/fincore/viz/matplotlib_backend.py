"""Matplotlib visualization backend.

Provides a concrete :class:`MatplotlibBackend` implementing the
:class:`~fincore.viz.base.VizBackend` protocol using matplotlib.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

__all__ = ["MatplotlibBackend"]


class MatplotlibBackend:
    """Visualization backend powered by matplotlib.

    All methods return the ``matplotlib.axes.Axes`` object so callers
    can further customise the plot.
    """

    def _import_plt(self):
        import matplotlib.pyplot as plt

        return plt

    def plot_returns(
        self,
        cum_returns: pd.Series,
        *,
        title: str = "Cumulative Returns",
        ax: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Plot cumulative returns as a line chart."""
        plt = self._import_plt()
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 4))
        ax.plot(cum_returns.index, cum_returns.values, **kwargs)
        ax.set_title(title)
        ax.set_ylabel("Cumulative Return")
        ax.axhline(0, color="black", linewidth=0.5, linestyle="--")
        ax.grid(True, alpha=0.3)
        return ax

    def plot_drawdown(
        self,
        drawdown: pd.Series,
        *,
        title: str = "Drawdown",
        ax: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Plot drawdown as a filled area chart."""
        plt = self._import_plt()
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 3))
        ax.fill_between(drawdown.index, drawdown.values, 0, color="red", alpha=0.3, **kwargs)
        ax.plot(drawdown.index, drawdown.values, color="red", linewidth=0.8)
        ax.set_title(title)
        ax.set_ylabel("Drawdown")
        ax.grid(True, alpha=0.3)
        return ax

    def plot_rolling_sharpe(
        self,
        sharpe: pd.Series,
        benchmark_sharpe: pd.Series | None = None,
        window: int = 252,
        *,
        title: str | None = None,
        ax: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Plot rolling Sharpe ratio with optional benchmark overlay."""
        plt = self._import_plt()
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 3))
        ax.plot(sharpe.index, sharpe.values, label="Portfolio Sharpe", **kwargs)
        if benchmark_sharpe is not None:
            ax.plot(
                benchmark_sharpe.index,
                benchmark_sharpe.values,
                label="Benchmark Sharpe",
                color="gray",
                linestyle="--",
                linewidth=1.2,
            )
            ax.legend(loc="best")
        if title is None:
            title = f"Rolling Sharpe Ratio ({window}-day window)"
        ax.set_title(title)
        ax.set_ylabel("Sharpe Ratio")
        ax.axhline(0, color="black", linewidth=0.5, linestyle="--")
        ax.grid(True, alpha=0.3)
        return ax

    def plot_monthly_heatmap(
        self,
        returns: pd.Series | pd.DataFrame,
        *,
        title: str = "Monthly Returns (%)",
        ax: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Plot a year × month heatmap of returns using ``imshow``."""
        plt = self._import_plt()
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 5))
        import matplotlib.colors as mcolors

        monthly_returns: pd.DataFrame
        if isinstance(returns, pd.Series):
            monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
            monthly_df = pd.DataFrame(
                {
                    "year": monthly.index.year,
                    "month": monthly.index.month,
                    "return": monthly.values,
                }
            )
            pivot = monthly_df.pivot(index="year", columns="month", values="return")
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            pivot = pivot.reindex(columns=list(range(1, 13)))
            pivot.columns = month_names
            monthly_returns = pivot
        else:
            monthly_returns = returns

        vmin = float(monthly_returns.min().min())
        vmax = float(monthly_returns.max().max())
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            vmin, vmax = -10.0, 10.0
        elif abs(vmax - vmin) < 1e-12:
            vmin, vmax = vmin - 1.0, vmax + 1.0

        # TwoSlopeNorm requires vmin < vcenter < vmax; fall back to a linear
        # normalization when the data does not cross zero.
        norm: mcolors.Normalize | mcolors.TwoSlopeNorm
        if vmin < 0 < vmax:
            norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)
        else:
            norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        im = ax.imshow(monthly_returns.values, cmap="RdYlGn", norm=norm, aspect="auto", **kwargs)
        ax.set_xticks(range(monthly_returns.shape[1]))
        ax.set_xticklabels([str(c) for c in monthly_returns.columns], fontsize=8)
        ax.set_yticks(range(monthly_returns.shape[0]))
        ax.set_yticklabels([str(i) for i in monthly_returns.index], fontsize=8)
        ax.set_title(title)
        plt.colorbar(im, ax=ax, shrink=0.8)
        return ax
