"""
Strategy report generator: build an HTML or PDF strategy report from the data you provide.

The more inputs you pass, the more sections the report will include:

- **returns** (required): core performance metrics + return charts
- **+ benchmark_rets**: alpha/beta, information ratio, tracking error, rolling beta
- **+ positions**: holdings analysis, long/short exposure, leverage, concentration
- **+ transactions**: turnover, volume analysis, trading time distribution
- **+ trades**: trade statistics (win rate, payoff ratio, long/short breakdown, holding time distribution)

Usage::

    from fincore.report import create_strategy_report

    # Minimal: returns only
    create_strategy_report(returns, output="report.html")

    # Full: pass everything you have
    create_strategy_report(
        returns,
        benchmark_rets=benchmark,
        positions=positions,
        transactions=transactions,
        trades=closed_trades_df,
        title="My Strategy",
        output="report.pdf",
    )

Modular structure
-----------------
- ``compute``     – statistics computation engine
- ``format``      – CSS styles and HTML formatting helpers
- ``render_html`` – HTML body assembly + ECharts JavaScript
- ``render_pdf``  – PDF rendering via Playwright + PyPDF2 bookmarks
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import pandas as pd


def create_strategy_report(
    returns: pd.Series,
    *,
    benchmark_rets: pd.Series | None = None,
    positions: pd.DataFrame | None = None,
    transactions: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
    title: str = "Strategy Report",
    output: str = "report.html",
    rolling_window: int = 63,
) -> str:
    """Generate a strategy report (HTML or PDF) based on the inputs you provide.

    Parameters
    ----------
    returns : pd.Series
        Daily return series (required). Must be indexed by a DatetimeIndex.
    benchmark_rets : pd.Series, optional
        Benchmark return series. Enables alpha/beta, tracking error, rolling beta, etc.
    positions : pd.DataFrame, optional
        Daily positions DataFrame (columns = asset symbols plus a ``cash`` column). Enables positions analysis.
    transactions : pd.DataFrame, optional
        Transactions DataFrame (must include ``amount``, ``price``, ``symbol``). Enables transaction analysis.
    trades : pd.DataFrame, optional
        Closed trades DataFrame (must include ``pnlcomm``; optional ``long``, ``barlen``, ``commission``).
        Enables trade statistics (win rate, payoff ratio, etc.).
    title : str
        Report title.
    output : str
        Output path. Use ``.html`` for HTML and ``.pdf`` for PDF.
    rolling_window : int
        Rolling window size (trading days). Default is 63 (about 3 months).

    Returns
    -------
    str
        The path to the generated report.
    """
    if output.lower().endswith(".pdf"):
        from fincore.report.render_pdf import generate_pdf

        return cast(
            "str",
            generate_pdf(
                returns,
                benchmark_rets=benchmark_rets,
                positions=positions,
                transactions=transactions,
                trades=trades,
                title=title,
                output=output,
                rolling_window=rolling_window,
            ),
        )
    from fincore.report.render_html import generate_html

    return cast(
        "str",
        generate_html(
            returns,
            benchmark_rets=benchmark_rets,
            positions=positions,
            transactions=transactions,
            trades=trades,
            title=title,
            output=output,
            rolling_window=rolling_window,
        ),
    )


__all__ = ["create_strategy_report"]
