"""
Backtest report generation service.

Supports exporting professional reports in HTML/PDF/Excel formats.
"""

import io
from datetime import datetime, timezone
from typing import Any

try:
    from jinja2 import Template

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

try:
    import pandas as pd
    from openpyxl import Workbook  # noqa: F401
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401

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

        # HTML template
        template_str = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{{ strategy.name }} - Backtest Report</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }

                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background: #f5f5f5;
                    padding: 20px;
                }

                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    overflow: hidden;
                }

                .header {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                }

                .header h1 {
                    margin: 0;
                    font-size: 28px;
                    font-weight: bold;
                }

                .header p {
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                }

                .content {
                    padding: 30px;
                }

                .section {
                    margin-bottom: 40px;
                }

                .section h2 {
                    color: #2c3e50;
                    border-bottom: 3px solid #667eea;
                    padding-bottom: 10px;
                    margin-bottom: 20px;
                }

                .metrics {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                }

                .metric-card {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }

                .metric-label {
                    color: #6c757d;
                    font-size: 14px;
                    margin-bottom: 10px;
                }

                .metric-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #2c3e50;
                }

                .metric-value.positive {
                    color: #28a745;
                }

                .metric-value.negative {
                    color: #dc3545;
                }

                .table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }

                .table th, .table td {
                    border: 1px solid #dee2e6;
                    padding: 12px;
                    text-align: left;
                }

                .table th {
                    background: #f8f9fa;
                    font-weight: bold;
                }

                .table tr:nth-child(even) {
                    background: #f8f9fa;
                }

                .table tr:hover {
                    background: #e9ecef;
                }

                .footer {
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }

                .chart-container {
                    height: 400px;
                    margin: 20px 0;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ strategy.name }} - Backtest Report</h1>
                    <p>Generated: {{ created_at }}</p>
                    <p>Backtest Period: {{ start_date }} to {{ end_date }}</p>
                </div>

                <div class="content">
                    <div class="section">
                        <h2>Backtest Overview</h2>
                        <div class="metrics">
                            <div class="metric-card">
                                <div class="metric-label">Total Return</div>
                                <div class="metric-value {{ 'positive' if total_return >= 0 else 'negative' }}">
                                    {{ total_return }}%
                                </div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">Annual Return</div>
                                <div class="metric-value {{ 'positive' if annual_return >= 0 else 'negative' }}">
                                    {{ annual_return }}%
                                </div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">Sharpe Ratio</div>
                                <div class="metric-value">{{ sharpe_ratio }}</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">Max Drawdown</div>
                                <div class="metric-value negative">{{ max_drawdown }}%</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">Win Rate</div>
                                <div class="metric-value">{{ win_rate }}%</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">Total Trades</div>
                                <div class="metric-value">{{ total_trades }}</div>
                            </div>
                            <div class="metric-card">
                                <div class="metric-label">Profitable Trades</div>
                                <div class="metric-value positive">{{ profitable_trades }}</div>
                            </div>
                        </div>
                    </div>

                    <div class="section">
                        <h2>Trade Statistics</h2>
                        <table class="table">
                            <tr>
                                <th>Metric</th>
                                <th>Value</th>
                            </tr>
                            <tr>
                                <td>Total Trades</td>
                                <td>{{ total_trades }}</td>
                            </tr>
                            <tr>
                                <td>Profitable Trades</td>
                                <td class="positive">{{ profitable_trades }}</td>
                            </tr>
                            <tr>
                                <td>Losing Trades</td>
                                <td class="negative">{{ losing_trades }}</td>
                            </tr>
                            <tr>
                                <td>Win Rate</td>
                                <td>{{ win_rate }}%</td>
                            </tr>
                        </table>
                    </div>

                    <div class="section">
                        <h2>Strategy Parameters</h2>
                        <table class="table">
                            <tr>
                                <th>Parameter</th>
                                <th>Value</th>
                            </tr>
                            {% for key, value in params.items() %}
                            <tr>
                                <td>{{ key }}</td>
                                <td>{{ value }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>

                    <div class="section">
                        <h2>Risk Disclaimer</h2>
                        <p style="color: #dc3545; background: #f8d7da; padding: 15px; border-radius: 4px;">
                            This report is based on historical backtesting data. Past performance does not guarantee future results.
                            Actual trading may differ from backtest results due to market volatility, commissions, slippage, and other factors.
                            Please invest cautiously and manage your risk appropriately.
                        </p>
                    </div>
                </div>

                <div class="footer">
                    <p>Generated by Backtrader Web</p>
                </div>
            </div>
        </body>
        </html>
        """

        template = Template(template_str)

        # Render template
        html_content = template.render(
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

        return html_content

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
