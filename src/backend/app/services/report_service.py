"""
Backtest report generation service.

Supports exporting professional reports in HTML/PDF/Excel formats.
"""

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from jinja2 import Template

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

try:
    import pandas as pd
    from openpyxl import Workbook  # noqa: F401  # conditional import for optional feature
    from openpyxl.styles import (  # noqa: F401  # conditional import
        Alignment,
        Border,
        Font,
        PatternFill,
        Side,
    )

    PANDAS_AVAILABLE = True
    OPENPYXL_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    OPENPYXL_AVAILABLE = False

try:
    from weasyprint import HTML as WeasyPrintHTML

    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


class ReportService:
    """Service for generating backtest reports in multiple formats.

    Supported formats:
    1. HTML - Interactive web-based reports
    2. PDF - Professional PDF reports
    3. Excel - Editable Excel spreadsheets
    """

    # Path to the HTML report template (loaded once, cached as class attribute)
    _template_dir = Path(__file__).resolve().parent.parent / "templates"

    async def generate_html_report(
        self,
        result: dict[str, Any],
        strategy: dict[str, Any],
    ) -> str:
        """Generate an HTML report from backtest results.

        Args:
            result: Dictionary containing backtest results with metrics such as
                total_return, annual_return, sharpe_ratio, max_drawdown, etc.
            strategy: Dictionary containing strategy information including name,
                parameters, and configuration.

        Returns:
            String containing the complete HTML report.

        Raises:
            ImportError: If jinja2 is not installed.
        """
        if not JINJA2_AVAILABLE:
            raise ImportError("Please install jinja2: pip install jinja2")

        template_str = (self._template_dir / "backtest_report.html").read_text(encoding="utf-8")
        template = Template(template_str)

        return template.render(
            strategy=strategy,
            total_return=result.get("total_return", 0),
            annual_return=result.get("annual_return", 0),
            sharpe_ratio=result.get("sharpe_ratio", 0),
            max_drawdown=result.get("max_drawdown", 0),
            win_rate=result.get("win_rate", 0),
            total_trades=result.get("total_trades", 0),
            profitable_trades=result.get("profitable_trades", 0),
            losing_trades=result.get("losing_trades", 0),
            params=result.get("params", {}),
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            start_date=result.get("start_date", ""),
            end_date=result.get("end_date", ""),
        )

    async def generate_pdf_report(
        self,
        result: dict[str, Any],
        strategy: dict[str, Any],
    ) -> bytes:
        """Generate a PDF report from backtest results.

        Args:
            result: Dictionary containing backtest results with metrics.
            strategy: Dictionary containing strategy information.

        Returns:
            Bytes containing the PDF file content.

        Raises:
            ImportError: If weasyprint is not installed.
        """
        if not WEASYPRINT_AVAILABLE:
            raise ImportError("Please install weasyprint: pip install weasyprint")

        # First generate HTML
        html_content = await self.generate_html_report(result, strategy)

        # Convert to PDF
        pdf_bytes = WeasyPrintHTML(string=html_content).write_pdf()

        return pdf_bytes

    async def generate_excel_report(
        self,
        result: dict[str, Any],
        strategy: dict[str, Any],
    ) -> bytes:
        """Generate an Excel report from backtest results.

        Args:
            result: Dictionary containing backtest results with metrics,
                trades data, and equity curve information.
            strategy: Dictionary containing strategy information.

        Returns:
            Bytes containing the Excel file content.

        Raises:
            ImportError: If pandas or openpyxl is not installed.
        """
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            raise ImportError("Please install pandas and openpyxl: pip install pandas openpyxl")

        # Create Excel file
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Overview sheet
            overview_df = pd.DataFrame(
                {
                    "Metric": [
                        "Strategy Name",
                        "Symbol",
                        "Start Date",
                        "End Date",
                        "Total Return",
                        "Annual Return",
                        "Sharpe Ratio",
                        "Max Drawdown",
                        "Win Rate",
                        "Total Trades",
                        "Profitable Trades",
                        "Losing Trades",
                    ],
                    "Value": [
                        strategy.get("name", ""),
                        result.get("symbol", ""),
                        str(result.get("start_date", "")),
                        str(result.get("end_date", "")),
                        result.get("total_return", 0),
                        result.get("annual_return", 0),
                        result.get("sharpe_ratio", 0),
                        result.get("max_drawdown", 0),
                        result.get("win_rate", 0),
                        result.get("total_trades", 0),
                        result.get("profitable_trades", 0),
                        result.get("losing_trades", 0),
                    ],
                }
            )
            overview_df.to_excel(writer, sheet_name="Overview", index=False)

            # Trade records sheet
            trades_data = result.get("trades", [])
            if trades_data:
                trades_df = pd.DataFrame(trades_data)
                trades_df.to_excel(writer, sheet_name="Trades", index=False)

            # Equity curve sheet
            equity_dates = result.get("equity_dates", [])
            equity_curve = result.get("equity_curve", [])
            if equity_dates and equity_curve:
                equity_df = pd.DataFrame(
                    {
                        "Date": equity_dates,
                        "Equity": equity_curve,
                    }
                )
                equity_df.to_excel(writer, sheet_name="Equity Curve", index=False)

        output.seek(0)
        return output.getvalue()
