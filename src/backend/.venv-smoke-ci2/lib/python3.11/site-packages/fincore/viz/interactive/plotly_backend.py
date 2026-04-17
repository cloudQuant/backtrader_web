"""Plotly-based interactive visualization backend.

Provides rich interactive visualizations with zoom, pan, hover,
and export capabilities using Plotly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    import plotly.graph_objects as go

from fincore.viz.base import VizBackend

__all__ = ["PlotlyBackend"]


class PlotlyBackend(VizBackend):
    """Interactive visualization backend using Plotly.

    Features:
    - Interactive zoom, pan, hover tooltips
    - Export to PNG, SVG, PDF
    - Responsive design
    - Theme support (light, dark)
    - Multiple plot types: line, area, heatmap, 3D surface

    Parameters
    ----------
    theme : str, default "light"
        Color theme. Options: 'light', 'dark', 'plotly', 'plotly_white',
        'plotly_dark', 'ggplot2', 'seaborn', 'simple_white'

    height : int, default 500
        Default figure height in pixels.

    width : int or None, default None
        Default figure width in pixels. None for responsive.

    template : str or None, default None
        Custom Plotly template name. Overrides theme if provided.

    show_legend : bool, default True
        Whether to show legend by default.

    Examples
    --------
    >>> backend = PlotlyBackend(theme="dark")
    >>> fig = backend.plot_returns(returns)
    >>> fig.show()

    >>> # Export to HTML
    >>> fig.write_html("returns.html")

    >>> # Export to PNG
    >>> fig.write_image("returns.png")
    """

    # Color themes for different financial visualizations
    COLORS = {
        "positive": "#00C853",  # Green for gains
        "negative": "#D50000",  # Red for losses
        "neutral": "#212121",  # Dark gray
        "highlight": "#2962FF",  # Blue for highlights
        "warning": "#FF6D00",  # Orange for warnings
        "background_light": "#FFFFFF",
        "background_dark": "#1E1E1E",
        "grid_light": "#E0E0E0",
        "grid_dark": "#424242",
        "text_light": "#424242",
        "text_dark": "#E0E0E0",
    }

    def __init__(
        self,
        theme: str = "light",
        height: int = 500,
        width: int | None = None,
        template: str | None = None,
        show_legend: bool = True,
    ):
        self.theme = theme
        self.height = height
        self.width = width
        self.template = template
        self.show_legend = show_legend
        self._fig: go.Figure | None = None

        # Set up theme-specific colors
        self._setup_theme()

    def _setup_theme(self) -> None:
        """Configure theme-specific colors and templates."""
        if self.theme in ("dark", "plotly_dark"):
            self.colors = {
                "background": self.COLORS["background_dark"],
                "grid": self.COLORS["grid_dark"],
                "text": self.COLORS["text_dark"],
                "positive": self.COLORS["positive"],
                "negative": self.COLORS["negative"],
                "neutral": self.COLORS["neutral"],
                "highlight": self.COLORS["highlight"],
                "warning": self.COLORS["warning"],
            }
            self.default_template = "plotly_dark"
        else:
            self.colors = {
                "background": self.COLORS["background_light"],
                "grid": self.COLORS["grid_light"],
                "text": self.COLORS["text_light"],
                "positive": self.COLORS["positive"],
                "negative": self.COLORS["negative"],
                "neutral": self.COLORS["neutral"],
                "highlight": self.COLORS["highlight"],
                "warning": self.COLORS["warning"],
            }
            self.default_template = "plotly_white"

    def _get_template(self) -> str:
        """Get the Plotly template to use."""
        if self.template:
            return self.template
        return self.default_template

    def _create_figure(self) -> go.Figure:
        """Create a new figure with configured template."""
        try:
            import plotly.graph_objects as go
        except ImportError as e:
            raise ImportError("Plotly is required for PlotlyBackend. Install with: pip install plotly") from e

        fig = go.Figure(
            layout=dict(
                template=self._get_template(),
                height=self.height,
                width=self.width,
                showlegend=self.show_legend,
                font=dict(color=self.colors["text"]),
                plot_bgcolor=self.colors["background"],
                paper_bgcolor=self.colors["background"],
            )
        )

        # Update grid colors
        fig.update_xaxes(gridcolor=self.colors["grid"], zerolinecolor=self.colors["grid"])
        fig.update_yaxes(gridcolor=self.colors["grid"], zerolinecolor=self.colors["grid"])

        return fig

    def plot_returns(
        self,
        cum_returns: pd.Series,
        benchmark: pd.Series | None = None,
        **kwargs,
    ) -> go.Figure:
        """Plot cumulative returns with optional benchmark.

        Parameters
        ----------
        cum_returns : pd.Series
            Cumulative returns series.
        benchmark : pd.Series, optional
            Benchmark cumulative returns for comparison.
        **kwargs
            Additional arguments for plotly.graph_objects.Figure

        Returns
        -------
        go.Figure
            Interactive Plotly figure.
        """
        fig = self._create_figure()

        # Add cumulative returns line
        fig.add_scatter(
            x=cum_returns.index,
            y=cum_returns.values,
            mode="lines",
            name="Portfolio",
            line=dict(color=self.colors["highlight"], width=2),
            hovertemplate="%{x}<br>Return: %{y:.2%}<extra></extra>",
        )

        # Add benchmark if provided
        if benchmark is not None:
            fig.add_scatter(
                x=benchmark.index,
                y=benchmark.values,
                mode="lines",
                name="Benchmark",
                line=dict(color=self.colors["neutral"], width=2, dash="dash"),
                hovertemplate="%{x}<br>Return: %{y:.2%}<extra></extra>",
            )

        # Add zero line
        fig.add_hline(
            y=0,
            line=dict(color=self.colors["grid"], width=1, dash="dot"),
        )

        fig.update_layout(
            title="Cumulative Returns",
            xaxis_title="Date",
            yaxis_title="Cumulative Return",
            hovermode="x unified",
            **kwargs,
        )

        self._fig = fig
        return fig

    def plot_drawdown(
        self,
        drawdown: pd.Series,
        **kwargs,
    ) -> go.Figure:
        """Plot underwater drawdown chart.

        Parameters
        ----------
        drawdown : pd.Series
            Drawdown series (negative values).
        **kwargs
            Additional arguments for plotly.graph_objects.Figure

        Returns
        -------
        go.Figure
            Interactive Plotly figure.
        """
        fig = self._create_figure()

        fig.add_scatter(
            x=drawdown.index,
            y=drawdown.values,
            mode="lines",
            name="Drawdown",
            line=dict(color=self.colors["negative"], width=1.5),
            fill="tozeroy",
            fillcolor="rgba(213, 0, 0, 0.3)",
            hovertemplate="%{x}<br>Drawdown: %{y:.2%}<extra></extra>",
        )

        fig.update_layout(
            title="Drawdown (Underwater Chart)",
            xaxis_title="Date",
            yaxis_title="Drawdown",
            hovermode="x unified",
            **kwargs,
        )

        self._fig = fig
        return fig

    def plot_rolling_sharpe(
        self,
        sharpe: pd.Series,
        benchmark_sharpe: pd.Series | None = None,
        window: int = 252,
        **kwargs,
    ) -> go.Figure:
        """Plot rolling Sharpe ratio.

        Parameters
        ----------
        sharpe : pd.Series
            Rolling Sharpe ratio series.
        benchmark_sharpe : pd.Series, optional
            Benchmark rolling Sharpe ratio.
        window : int, default 252
            Rolling window size (for title).
        **kwargs
            Additional arguments for plotly.graph_objects.Figure

        Returns
        -------
        go.Figure
            Interactive Plotly figure.
        """
        fig = self._create_figure()

        fig.add_scatter(
            x=sharpe.index,
            y=sharpe.values,
            mode="lines",
            name="Portfolio Sharpe",
            line=dict(color=self.colors["highlight"], width=2),
            hovertemplate="%{x}<br>Sharpe: %{y:.2f}<extra></extra>",
        )

        if benchmark_sharpe is not None:
            fig.add_scatter(
                x=benchmark_sharpe.index,
                y=benchmark_sharpe.values,
                mode="lines",
                name="Benchmark Sharpe",
                line=dict(color=self.colors["neutral"], width=2, dash="dash"),
                hovertemplate="%{x}<br>Sharpe: %{y:.2f}<extra></extra>",
            )

        # Add zero line
        fig.add_hline(
            y=0,
            line=dict(color=self.colors["grid"], width=1),
        )

        fig.update_layout(
            title=f"Rolling Sharpe Ratio ({window}-day window)",
            xaxis_title="Date",
            yaxis_title="Sharpe Ratio",
            hovermode="x unified",
            **kwargs,
        )

        self._fig = fig
        return fig

    def plot_monthly_heatmap(
        self,
        returns: pd.Series | pd.DataFrame,
        **kwargs,
    ) -> go.Figure:
        """Plot monthly returns heatmap.

        Parameters
        ----------
        returns : pd.Series
            Daily returns series.
        **kwargs
            Additional arguments for plotly.graph_objects.Figure

        Returns
        -------
        go.Figure
            Interactive Plotly figure.
        """
        pivot: pd.DataFrame
        if isinstance(returns, pd.Series):
            # Calculate monthly returns
            monthly_returns = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100

            # Create pivot table (year x month)
            monthly_returns_df = pd.DataFrame(
                {
                    "year": monthly_returns.index.year,
                    "month": monthly_returns.index.month,
                    "return": monthly_returns.values,
                }
            )
            pivot = monthly_returns_df.pivot(index="year", columns="month", values="return")
        else:
            pivot = returns.copy()

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        fig = self._create_figure()

        # Color scale from red (negative) to green (positive)
        colorscale = [
            [0.0, "#D32F2F"],  # Dark red (worst)
            [0.5, "#FFFFFF"],  # White (break-even)
            [1.0, "#388E3C"],  # Dark green (best)
        ]

        fig.add_heatmap(
            z=pivot.values,
            x=list(range(1, 13)) if list(pivot.columns) == list(range(1, 13)) else list(pivot.columns),
            y=pivot.index,
            colorscale=colorscale,
            colorbar=dict(
                title="Return (%)",
                tickformat=".1f",
            ),
            hovertemplate=("<b>%{y}</b><br>Month: %{x}<br>Return: %{z:.2f}%<extra></extra>"),
            **kwargs,
        )

        fig.update_layout(
            title="Monthly Returns Heatmap",
            xaxis=dict(
                tickmode="array",
                tickvals=list(range(1, 13)),
                ticktext=month_names,
                title="Month",
            ),
            yaxis=dict(title="Year", autorange="reversed"),
        )

        self._fig = fig
        return fig

    def plot_efficient_frontier(
        self,
        returns: pd.DataFrame,
        n_points: int = 50,
        **kwargs,
    ) -> go.Figure:
        """Plot efficient frontier with random portfolios.

        Parameters
        ----------
        returns : pd.DataFrame
            Asset returns (T x N).
        n_points : int, default 50
            Number of points on the efficient frontier.
        **kwargs
            Additional arguments for plotly.graph_objects.Figure

        Returns
        -------
        go.Figure
            Interactive Plotly figure.
        """
        from fincore.optimization import efficient_frontier

        frontier = efficient_frontier(returns, n_points=n_points)

        fig = self._create_figure()

        # Plot efficient frontier
        fig.add_scatter(
            x=frontier["frontier_volatilities"],
            y=frontier["frontier_returns"],
            mode="lines+markers",
            name="Efficient Frontier",
            line=dict(color=self.colors["highlight"], width=3),
            marker=dict(size=6),
            hovertemplate=("Vol: %{x:.2%}<br>Return: %{y:.2%}<br>Sharpe: %{customdata[0]:.2f}<extra></extra>"),
            customdata=np.stack(
                [
                    frontier["frontier_sharpe"],
                ],
                axis=-1,
            ),
        )

        # Highlight max Sharpe portfolio
        if "max_sharpe" in frontier:
            max_sharpe = frontier["max_sharpe"]
            fig.add_scatter(
                x=[max_sharpe["volatility"]],
                y=[max_sharpe["return"]],
                mode="markers",
                name="Max Sharpe",
                marker=dict(
                    size=15,
                    color=self.colors["positive"],
                    symbol="star",
                ),
                hovertemplate=("Max Sharpe<br>Vol: %{x:.2%}<br>Return: %{y:.2%}<extra></extra>"),
            )

        # Highlight minimum-variance portfolio
        if "min_variance" in frontier:
            min_vol = frontier["min_variance"]
            fig.add_scatter(
                x=[min_vol["volatility"]],
                y=[min_vol["return"]],
                mode="markers",
                name="Min Variance",
                marker=dict(
                    size=15,
                    color=self.colors["warning"],
                    symbol="diamond",
                ),
                hovertemplate=("Min Variance<br>Vol: %{x:.2%}<br>Return: %{y:.2%}<extra></extra>"),
            )

        fig.update_layout(
            title="Efficient Frontier",
            xaxis_title="Volatility (Annualized)",
            yaxis_title="Expected Return (Annualized)",
            hovermode="closest",
            **kwargs,
        )

        self._fig = fig
        return fig

    def plot_correlation_matrix(
        self,
        returns: pd.DataFrame,
        **kwargs,
    ) -> go.Figure:
        """Plot correlation matrix heatmap.

        Parameters
        ----------
        returns : pd.DataFrame
            Asset returns (T x N).
        **kwargs
            Additional arguments for plotly.graph_objects.Figure

        Returns
        -------
        go.Figure
            Interactive Plotly figure.
        """
        corr = returns.corr()

        fig = self._create_figure()

        fig.add_heatmap(
            z=corr.values,
            x=corr.columns,
            y=corr.index,
            colorscale="RdBu",
            zmid=0,
            colorbar=dict(title="Correlation"),
            hovertemplate=("Asset 1: %{y}<br>Asset 2: %{x}<br>Correlation: %{z:.2f}<extra></extra>"),
            **kwargs,
        )

        fig.update_layout(
            title="Asset Correlation Matrix",
            xaxis_side="bottom",
        )

        self._fig = fig
        return fig

    def show(self) -> None:
        """Display the current figure."""
        if self._fig is None:
            raise ValueError("No figure to display. Call a plot method first.")
        self._fig.show()

    def save_html(self, filename: str) -> None:
        """Save the current figure as HTML.

        Parameters
        ----------
        filename : str
            Output HTML filename.
        """
        if self._fig is None:
            raise ValueError("No figure to save. Call a plot method first.")
        self._fig.write_html(filename)

    def save_image(self, filename: str, **kwargs) -> None:
        """Save the current figure as an image.

        Requires kaleido: pip install kaleido

        Parameters
        ----------
        filename : str
            Output image filename (.png, .jpg, .svg, .pdf).
        **kwargs
            Additional arguments for write_image().
        """
        if self._fig is None:
            raise ValueError("No figure to save. Call a plot method first.")
        self._fig.write_image(filename, **kwargs)
