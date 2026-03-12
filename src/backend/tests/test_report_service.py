"""
Backtest Report Generation Service Tests.

Tests:
- HTML report generation
- PDF report generation
- Excel report generation
- Error handling when dependencies are missing
- Edge case handling
"""

from unittest.mock import patch

import pytest

from app.services.report_service import (
    JINJA2_AVAILABLE,
    OPENPYXL_AVAILABLE,
    PANDAS_AVAILABLE,
    WEASYPRINT_AVAILABLE,
    ReportService,
)


class TestReportServiceInitialization:
    """Test service initialization."""

    def test_initialization(self):
        """Test service initialization."""
        service = ReportService()
        assert service is not None


class TestGenerateHtmlReport:
    """Test HTML report generation."""

    @pytest.mark.asyncio
    async def test_generate_html_success(self):
        """Test successful HTML report generation."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_return": 15.5,
            "annual_return": 12.3,
            "sharpe_ratio": 1.5,
            "max_drawdown": -8.2,
            "win_rate": 60.0,
            "total_trades": 100,
            "profitable_trades": 60,
            "losing_trades": 40,
            "params": {"fast_period": 10, "slow_period": 20},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        strategy = {
            "name": "Dual Moving Average Strategy",
        }

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert "Dual Moving Average Strategy" in html
        assert "15.5" in html  # total_return
        assert "12.3" in html  # annual_return
        assert "1.5" in html  # sharpe_ratio
        assert "60.0" in html  # win_rate
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    @pytest.mark.asyncio
    async def test_generate_html_with_missing_values(self):
        """Test HTML generation with missing values."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {}  # Empty result
        strategy = {"name": "Test Strategy"}

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert "Test Strategy" in html
        # Should use default value 0
        assert "0" in html

    @pytest.mark.asyncio
    async def test_generate_html_without_jinja2(self):
        """Test error when jinja2 is not available."""
        if JINJA2_AVAILABLE:
            pytest.skip("jinja2 is available")

        service = ReportService()

        with pytest.raises(ImportError, match="jinja2"):
            await service.generate_html_report({}, {})

    @pytest.mark.asyncio
    async def test_generate_html_positive_returns(self):
        """Test positive returns display as green."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_return": 25.5,
            "annual_return": 20.0,
        }
        strategy = {"name": "Test"}

        html = await service.generate_html_report(result, strategy)

        assert "positive" in html

    @pytest.mark.asyncio
    async def test_generate_html_negative_returns(self):
        """Test negative returns display as red."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_return": -15.5,
            "annual_return": -10.0,
        }
        strategy = {"name": "Test"}

        html = await service.generate_html_report(result, strategy)

        assert "negative" in html

    @pytest.mark.asyncio
    async def test_generate_html_with_params(self):
        """Test HTML generation with strategy parameters."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "params": {
                "fast_period": 5,
                "slow_period": 20,
                "risk_ratio": 2.0,
            }
        }
        strategy = {"name": "Parameter Test"}

        html = await service.generate_html_report(result, strategy)

        assert "fast_period" in html
        assert "slow_period" in html
        assert "risk_ratio" in html

    @pytest.mark.asyncio
    async def test_generate_html_with_trades_summary(self):
        """Test HTML generation with trade statistics."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_trades": 150,
            "profitable_trades": 90,
            "losing_trades": 60,
            "win_rate": 60.0,
        }
        strategy = {"name": "Trade Test"}

        html = await service.generate_html_report(result, strategy)

        assert "150" in html
        assert "90" in html
        assert "60" in html


class TestGeneratePdfReport:
    """Test PDF report generation."""

    @pytest.mark.asyncio
    async def test_generate_pdf_success(self):
        """Test successful PDF report generation."""
        if not JINJA2_AVAILABLE or not WEASYPRINT_AVAILABLE:
            pytest.skip("jinja2 or weasyprint not available")

        service = ReportService()

        result = {
            "total_return": 15.5,
            "sharpe_ratio": 1.5,
            "max_drawdown": -8.2,
        }
        strategy = {"name": "PDF Test"}

        pdf_bytes = await service.generate_pdf_report(result, strategy)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # PDF should start with %PDF
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_generate_pdf_without_weasyprint(self):
        """Test error when weasyprint is not available."""
        if WEASYPRINT_AVAILABLE:
            pytest.skip("weasyprint is available")

        # Patch to simulate weasyprint not available
        service = ReportService()

        with patch("app.services.report_service.WEASYPRINT_AVAILABLE", False):
            with pytest.raises(ImportError, match="weasyprint"):
                await service.generate_pdf_report({}, {})

    @pytest.mark.asyncio
    async def test_generate_pdf_uses_html_generation(self):
        """Test PDF generation uses HTML generation."""
        if not JINJA2_AVAILABLE or not WEASYPRINT_AVAILABLE:
            pytest.skip("jinja2 or weasyprint not available")

        service = ReportService()

        result = {"total_return": 10.0}
        strategy = {"name": "Test"}

        # Generate HTML first and verify PDF uses it
        with patch.object(
            service, "generate_html_report", return_value="<html><body>Test HTML</body></html>"
        ) as mock_html:
            with patch("app.services.report_service.WeasyPrintHTML") as mock_weasy:
                mock_weasy.return_value.write_pdf.return_value = b"%PDF-test"

                await service.generate_pdf_report(result, strategy)

                # Should have called generate_html_report
                mock_html.assert_called_once_with(result, strategy)


class TestGenerateExcelReport:
    """Test Excel report generation."""

    @pytest.mark.asyncio
    async def test_generate_excel_success(self):
        """Test successful Excel report generation."""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            "total_return": 15.5,
            "annual_return": 12.3,
            "sharpe_ratio": 1.5,
            "max_drawdown": -8.2,
            "win_rate": 60.0,
            "total_trades": 100,
            "profitable_trades": 60,
            "losing_trades": 40,
            "params": {"period": 20},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "trades": [
                {"date": "2024-01-01", "symbol": "AAPL", "type": "buy", "price": 100, "size": 10},
                {"date": "2024-01-02", "symbol": "AAPL", "type": "sell", "price": 110, "size": 10},
            ],
            "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "equity_curve": [100000, 101000, 102000],
        }
        strategy = {"name": "Excel Test", "symbol": "AAPL"}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0
        # Excel files should start with PK (ZIP signature)
        assert excel_bytes.startswith(b"PK")

    @pytest.mark.asyncio
    async def test_generate_excel_without_dependencies(self):
        """Test error when dependencies are not available."""
        if PANDAS_AVAILABLE and OPENPYXL_AVAILABLE:
            pytest.skip("pandas and openpyxl are available")

        service = ReportService()

        with patch("app.services.report_service.PANDAS_AVAILABLE", False):
            with pytest.raises(ImportError, match="pandas.*openpyxl"):
                await service.generate_excel_report({}, {})

    @pytest.mark.asyncio
    async def test_generate_excel_minimal_data(self):
        """Test Excel generation with minimal data."""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {}  # Minimal data
        strategy = {"name": "Minimal Test"}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

    @pytest.mark.asyncio
    async def test_generate_excel_with_trades(self):
        """Test Excel generation with trade records."""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            "trades": [
                {"date": "2024-01-01", "symbol": "AAPL", "type": "buy", "price": 100, "pnl": 1000},
                {"date": "2024-01-02", "symbol": "MSFT", "type": "sell", "price": 200, "pnl": -500},
            ]
        }
        strategy = {"name": "Trade Test"}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

    @pytest.mark.asyncio
    async def test_generate_excel_with_equity_curve(self):
        """Test Excel generation with equity curve."""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "equity_curve": [100000, 101000, 100500, 102000, 103000],
        }
        strategy = {"name": "Equity Curve Test"}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_html_with_special_characters(self):
        """Test HTML generation with special characters."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {"total_return": 15.5, "params": {"param_<script>": "value_test"}}
        strategy = {"name": 'Strategy<>&"'}

        html = await service.generate_html_report(result, strategy)

        # Should generate valid HTML
        assert isinstance(html, str)
        assert len(html) > 0

    @pytest.mark.asyncio
    async def test_html_with_zero_values(self):
        """Test HTML generation with zero values."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_return": 0,
            "annual_return": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "win_rate": 0,
            "total_trades": 0,
            "profitable_trades": 0,
            "losing_trades": 0,
        }
        strategy = {"name": "Zero Value Test"}

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert "0" in html

    @pytest.mark.asyncio
    async def test_html_with_large_values(self):
        """Test HTML generation with large values."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_return": 999999.99,
            "total_trades": 1000000,
        }
        strategy = {"name": "Large Value Test"}

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert "999999" in html
        assert "1000000" in html

    @pytest.mark.asyncio
    async def test_excel_empty_trades_list(self):
        """Test Excel generation with empty trades list."""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            "trades": [],  # Empty list
            "equity_dates": [],  # Empty list
            "equity_curve": [],  # Empty list
        }
        strategy = {"name": "Empty Data Test"}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0


class TestTemplateRendering:
    """Test template rendering."""

    @pytest.mark.asyncio
    async def test_template_contains_all_sections(self):
        """Test HTML template contains all sections."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            "total_return": 10.0,
            "annual_return": 8.0,
            "sharpe_ratio": 1.2,
            "max_drawdown": -5.0,
            "win_rate": 55.0,
            "total_trades": 50,
            "profitable_trades": 28,
            "losing_trades": 22,
            "params": {"test": "value"},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        strategy = {"name": "Complete Test"}

        html = await service.generate_html_report(result, strategy)

        # Check HTML structure
        assert "<!DOCTYPE html>" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html
        assert "Backtest Overview" in html
        assert "Trade Statistics" in html
        assert "Strategy Parameters" in html
        assert "Risk Disclaimer" in html
        assert "Backtrader Web" in html

    @pytest.mark.asyncio
    async def test_template_styling(self):
        """Test template styling."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {"total_return": 10.0}
        strategy = {"name": "Style Test"}

        html = await service.generate_html_report(result, strategy)

        # Check CSS styles
        assert "<style>" in html
        assert "container" in html
        assert "metric-card" in html
        assert "table" in html
        assert "header" in html
        assert "footer" in html


class TestIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_full_report_generation_workflow(self):
        """Test complete report generation workflow."""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        # Complete backtest results
        result = {
            "symbol": "000001.SZ",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "total_return": 25.5,
            "annual_return": 22.0,
            "sharpe_ratio": 1.8,
            "max_drawdown": -10.5,
            "win_rate": 65.0,
            "total_trades": 200,
            "profitable_trades": 130,
            "losing_trades": 70,
            "params": {
                "fast_period": 5,
                "slow_period": 20,
                "risk_ratio": 2.0,
            },
            "trades": [
                {
                    "date": "2024-01-01",
                    "symbol": "000001.SZ",
                    "type": "buy",
                    "price": 10.0,
                    "size": 100,
                },
                {
                    "date": "2024-01-05",
                    "symbol": "000001.SZ",
                    "type": "sell",
                    "price": 12.0,
                    "size": 100,
                },
            ],
            "equity_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "equity_curve": [100000, 101000, 102000],
        }
        strategy = {
            "name": "Dual Moving Average Strategy",
            "description": "Trade based on fast/slow moving average crossover signals",
            "symbol": "000001.SZ",
        }

        # Generate HTML report
        html = await service.generate_html_report(result, strategy)
        assert "Dual Moving Average Strategy" in html
        assert "25.5" in html  # total_return

        # Generate Excel report (if dependencies available)
        if PANDAS_AVAILABLE and OPENPYXL_AVAILABLE:
            excel = await service.generate_excel_report(result, strategy)
            assert len(excel) > 0
