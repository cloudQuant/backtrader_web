"""Bokeh-based interactive visualization backend.

Provides server-compatible interactive visualizations using Bokeh.
"""

from __future__ import annotations

import importlib
from typing import Any, cast

import numpy as np
import pandas as pd

from fincore.viz.base import VizBackend

__all__ = ["BokehBackend", "PrintfTickFormatter"]


class BokehBackend(VizBackend):
    """Interactive visualization backend using Bokeh.

    Features:
    - Server-compatible plots
    - Streaming data support
    - Interactive widgets
    - Theme support (light, dark)
    - Export to PNG

    Parameters
    ----------
    theme : str, default "light"
        Color theme. Options: 'light', 'dark', 'caliber'.

    height : int, default 500
        Default figure height in pixels.

    width : int, default 800
        Default figure width in pixels.

    sizing_mode : str, default "fixed"
        Sizing mode for responsive layouts.
        Options: 'fixed', 'stretch_width', 'stretch_height',
        'stretch_both', 'scale_width', 'scale_height',
        'scale_both'.

    Examples
    --------
    >>> backend = BokehBackend(theme="dark")
    >>> p = backend.plot_returns(returns)
    >>>
    >>> # Show in notebook
    >>> from bokeh.io import show, output_notebook
    >>> output_notebook()
    >>> show(p)
    >>>
    >>> # Or save to HTML
    >>> from bokeh.io import save
    >>> save(p, "returns.html")
    """

    # Color palettes
    COLORS = {
        "positive": "#00C853",
        "negative": "#D50000",
        "neutral": "#212121",
        "highlight": "#2962FF",
        "warning": "#FF6D00",
    }

    def __init__(
        self,
        theme: str = "light",
        height: int = 500,
        width: int = 800,
        sizing_mode: str = "fixed",
    ):
        self.theme = theme
        self.height = height
        self.width = width
        self.sizing_mode = sizing_mode
        self._setup_theme()

    def _setup_theme(self) -> None:
        """Configure theme-specific settings."""
        if self.theme == "dark":
            self.bg_color = "#1E1E1E"
            self.grid_color = "#424242"
            self.text_color = "#E0E0E0"
        else:
            self.bg_color = "#FFFFFF"
            self.grid_color = "#E0E0E0"
            self.text_color = "#424242"

    def _create_figure(self, **kwargs) -> Any:
        """Create a new Bokeh figure."""
        try:
            from bokeh.plotting import figure
        except ImportError as e:
            raise ImportError("Bokeh is required for BokehBackend. Install with: pip install bokeh") from e

        fig = figure(
            height=self.height,
            width=self.width,
            sizing_mode=cast("Any", self.sizing_mode),
            background_fill_color=self.bg_color,
            border_fill_color=self.bg_color,
            **kwargs,
        )

        # Style grid
        fig.xgrid.grid_line_color = self.grid_color
        fig.ygrid.grid_line_color = self.grid_color
        fig.axis.major_label_text_color = self.text_color
        fig.axis.major_tick_line_color = self.grid_color
        fig.axis.axis_line_color = self.grid_color

        return fig

    def plot_returns(
        self,
        cum_returns: pd.Series,
        benchmark: pd.Series | None = None,
        **kwargs,
    ) -> Any:
        """Plot cumulative returns with optional benchmark.

        Parameters
        ----------
        cum_returns : pd.Series
            Cumulative returns series.
        benchmark : pd.Series, optional
            Benchmark cumulative returns for comparison.
        **kwargs
            Additional arguments for figure.

        Returns
        -------
        LayoutDOM
            Bokeh figure object.
        """
        from bokeh.models import ColumnDataSource, HoverTool

        p = self._create_figure(
            x_axis_type="datetime",
            title="Cumulative Returns",
            x_axis_label="Date",
            y_axis_label="Cumulative Return",
            **kwargs,
        )

        # Create data source
        source = ColumnDataSource(
            data={
                "date": cum_returns.index,
                "returns": cum_returns.values,
            }
        )

        # Add portfolio line
        p.line(
            "date",
            "returns",
            source=source,
            line_width=2,
            color=self.COLORS["highlight"],
            legend_label="Portfolio",
        )

        # Add benchmark if provided
        if benchmark is not None:
            bench_source = ColumnDataSource(
                data={
                    "date": benchmark.index,
                    "returns": benchmark.values,
                }
            )
            p.line(
                "date",
                "returns",
                source=bench_source,
                line_width=2,
                color=self.COLORS["neutral"],
                line_dash="dashed",
                legend_label="Benchmark",
            )

        # Add hover tool
        hover = HoverTool(
            tooltips=[
                ("Date", "@date{%F}"),
                ("Return", "@returns{0.00%}"),
            ],
            formatters={"@date": "datetime"},
            mode="vline",
        )
        p.add_tools(hover)

        p.legend.location = "top_left"
        p.legend.click_policy = "hide"

        return p

    def plot_drawdown(
        self,
        drawdown: pd.Series,
        **kwargs,
    ) -> Any:
        """Plot underwater drawdown chart.

        Parameters
        ----------
        drawdown : pd.Series
            Drawdown series (negative values).
        **kwargs
            Additional arguments for figure.

        Returns
        -------
        LayoutDOM
            Bokeh figure object.
        """
        from bokeh.models import ColumnDataSource, HoverTool

        p = self._create_figure(
            x_axis_type="datetime",
            title="Drawdown (Underwater Chart)",
            x_axis_label="Date",
            y_axis_label="Drawdown",
            **kwargs,
        )

        source = ColumnDataSource(
            data={
                "date": drawdown.index,
                "drawdown": drawdown.values,
            }
        )

        # Create area patch for drawdown
        p.varea(
            x="date",
            y1=0,
            y2="drawdown",
            source=source,
            fill_color=self.COLORS["negative"],
            fill_alpha=0.3,
        )

        # Add line on top
        p.line(
            "date",
            "drawdown",
            source=source,
            line_width=1.5,
            color=self.COLORS["negative"],
        )

        hover = HoverTool(
            tooltips=[
                ("Date", "@date{%F}"),
                ("Drawdown", "@drawdown{0.00%}"),
            ],
            formatters={"@date": "datetime"},
        )
        p.add_tools(hover)

        return p

    def plot_rolling_sharpe(
        self,
        sharpe: pd.Series,
        benchmark_sharpe: pd.Series | None = None,
        window: int = 252,
        **kwargs,
    ) -> Any:
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
            Additional arguments for figure.

        Returns
        -------
        LayoutDOM
            Bokeh figure object.
        """
        from bokeh.models import ColumnDataSource, HoverTool

        p = self._create_figure(
            x_axis_type="datetime",
            title=f"Rolling Sharpe Ratio ({window}-day window)",
            x_axis_label="Date",
            y_axis_label="Sharpe Ratio",
            **kwargs,
        )

        source = ColumnDataSource(
            data={
                "date": sharpe.index,
                "sharpe": sharpe.values,
            }
        )

        p.line(
            "date",
            "sharpe",
            source=source,
            line_width=2,
            color=self.COLORS["highlight"],
            legend_label="Portfolio Sharpe",
        )

        if benchmark_sharpe is not None:
            bench_source = ColumnDataSource(
                data={
                    "date": benchmark_sharpe.index,
                    "sharpe": benchmark_sharpe.values,
                }
            )
            p.line(
                "date",
                "sharpe",
                source=bench_source,
                line_width=2,
                color=self.COLORS["neutral"],
                line_dash="dashed",
                legend_label="Benchmark Sharpe",
            )

        # Add zero line (Span may be absent in some bokeh stubs/versions).
        models = importlib.import_module("bokeh.models")
        Span = getattr(models, "Span", None)
        if Span is not None:
            zero_line = Span(location=0, dimension="width", line_color=self.grid_color, line_alpha=0.5)
            p.add_layout(zero_line)
        else:
            HSpan = getattr(models, "HSpan", None)
            if HSpan is not None:
                p.add_layout(HSpan(location=0, line_color=self.grid_color, line_alpha=0.5))

        hover = HoverTool(
            tooltips=[
                ("Date", "@date{%F}"),
                ("Sharpe", "@sharpe{0.00}"),
            ],
            formatters={"@date": "datetime"},
        )
        p.add_tools(hover)

        p.legend.location = "top_left"
        p.legend.click_policy = "hide"

        return p

    def plot_monthly_heatmap(
        self,
        returns: pd.Series | pd.DataFrame,
        **kwargs,
    ) -> Any:
        """Plot monthly returns heatmap.

        Parameters
        ----------
        returns : pd.Series
            Daily returns series.
        **kwargs
            Additional arguments for figure.

        Returns
        -------
        LayoutDOM
            Bokeh figure object.
        """
        from bokeh.models import BasicTicker, ColumnDataSource, FactorRange, HoverTool, LinearColorMapper
        from bokeh.plotting import figure

        pivot: pd.DataFrame
        if isinstance(returns, pd.Series):
            monthly_returns = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
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

        years = pivot.index.tolist()
        months = list(range(1, 13))

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # Prepare data for Bokeh (flatten to dict format)
        data: dict[str, list[object]] = {
            "year": [],
            "month": [],
            "value": [],
        }
        for y in years:
            for m in months:
                val = pivot.loc[y, m] if m in pivot.columns else np.nan
                data["year"].append(str(y))
                data["month"].append(month_names[m - 1])
                data["value"].append(float(val) if not np.isnan(val) else np.nan)

        source = ColumnDataSource(data)

        # Create color mapper
        values: list[float] = [float(v) for v in data["value"] if isinstance(v, (int, float)) and np.isfinite(float(v))]
        if not values:
            min_val, max_val = -10.0, 10.0  # Default range
        else:
            min_val = float(min(values))
            max_val = float(max(values))

        mapper = LinearColorMapper(
            palette="RdYlGn11",
            low=min_val,
            high=max_val,
        )

        p = figure(  # type: ignore[call-arg]
            title="Monthly Returns Heatmap",
            x_range=FactorRange(factors=month_names),
            y_range=FactorRange(factors=[str(y) for y in reversed(years)]),
            width=self.width,
            height=self.height,
            x_axis_location="above",
            tools="hover",
            toolbar_location=None,
        )

        p.rect(
            x="month",
            y="year",
            width=1,
            height=1,
            source=source,
            fill_color={"field": "value", "transform": mapper},
            line_color=None,
        )

        p.grid.grid_line_color = None
        p.axis.axis_line_color = None
        p.axis.major_tick_line_color = None

        p.axis.major_label_text_font_size = "10px"
        p.axis.major_label_standoff = 2

        hover = HoverTool(
            tooltips=[
                ("Year", "@year"),
                ("Month", "@month"),
                ("Return", "@value{0.0}%"),
            ]
        )
        p.add_tools(hover)

        models = importlib.import_module("bokeh.models")
        ColorBar = getattr(models, "ColorBar", None)
        if ColorBar is not None:
            color_bar = ColorBar(
                color_mapper=mapper,
                major_label_text_font_size="10px",
                ticker=BasicTicker(desired_num_ticks=10),
                label_standoff=12,
                border_line_color=None,
                location=(0, 0),
            )
            p.add_layout(color_bar, "right")

        return p

    def show(self, fig: Any) -> None:
        """Display the figure in a browser or notebook."""
        from bokeh.io import show as bokeh_show

        bokeh_show(fig)

    def save_html(self, fig: Any, filename: str) -> None:
        """Save the figure as HTML.

        Parameters
        ----------
        fig : Any
            Bokeh figure to save.
        filename : str
            Output HTML filename.
        """
        from bokeh.io import save as bokeh_save

        bokeh_save(fig, filename)


class PrintfTickFormatter:
    """Simple tick formatter for percentage display."""

    def __init__(self, format: str = "%.1f"):
        self.format = format

    def __call__(self, x):
        return self.format % x
