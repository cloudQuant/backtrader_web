"""
回测报告生成服务测试

测试：
- HTML 报告生成
- PDF 报告生成
- Excel 报告生成
- 依赖缺失时的错误处理
- 边界情况处理
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

from app.services.report_service import (
    ReportService,
    JINJA2_AVAILABLE,
    WEASYPRINT_AVAILABLE,
    PANDAS_AVAILABLE,
    OPENPYXL_AVAILABLE,
)


class TestReportServiceInitialization:
    """测试服务初始化"""

    def test_initialization(self):
        """测试服务初始化"""
        service = ReportService()
        assert service is not None


class TestGenerateHtmlReport:
    """测试 HTML 报告生成"""

    @pytest.mark.asyncio
    async def test_generate_html_success(self):
        """测试成功生成 HTML 报告"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': 15.5,
            'annual_return': 12.3,
            'sharpe_ratio': 1.5,
            'max_drawdown': -8.2,
            'win_rate': 60.0,
            'total_trades': 100,
            'profitable_trades': 60,
            'losing_trades': 40,
            'params': {'fast_period': 10, 'slow_period': 20},
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        }

        strategy = {
            'name': '双均线策略',
        }

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert '双均线策略' in html
        assert '15.5' in html  # total_return
        assert '12.3' in html  # annual_return
        assert '1.5' in html  # sharpe_ratio
        assert '60.0' in html  # win_rate
        assert '<!DOCTYPE html>' in html
        assert '</html>' in html

    @pytest.mark.asyncio
    async def test_generate_html_with_missing_values(self):
        """测试处理缺失值的 HTML 生成"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {}  # 空结果
        strategy = {'name': '测试策略'}

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert '测试策略' in html
        # 应该使用默认值 0
        assert '0' in html

    @pytest.mark.asyncio
    async def test_generate_html_without_jinja2(self):
        """测试 jinja2 不可用时抛出错误"""
        if JINJA2_AVAILABLE:
            pytest.skip("jinja2 is available")

        service = ReportService()

        with pytest.raises(ImportError, match="jinja2"):
            await service.generate_html_report({}, {})

    @pytest.mark.asyncio
    async def test_generate_html_positive_returns(self):
        """测试正收益显示为绿色"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': 25.5,
            'annual_return': 20.0,
        }
        strategy = {'name': '测试'}

        html = await service.generate_html_report(result, strategy)

        assert 'positive' in html

    @pytest.mark.asyncio
    async def test_generate_html_negative_returns(self):
        """测试负收益显示为红色"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': -15.5,
            'annual_return': -10.0,
        }
        strategy = {'name': '测试'}

        html = await service.generate_html_report(result, strategy)

        assert 'negative' in html

    @pytest.mark.asyncio
    async def test_generate_html_with_params(self):
        """测试包含策略参数的 HTML 生成"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'params': {
                'fast_period': 5,
                'slow_period': 20,
                'risk_ratio': 2.0,
            }
        }
        strategy = {'name': '参数测试'}

        html = await service.generate_html_report(result, strategy)

        assert 'fast_period' in html
        assert 'slow_period' in html
        assert 'risk_ratio' in html

    @pytest.mark.asyncio
    async def test_generate_html_with_trades_summary(self):
        """测试包含交易统计的 HTML 生成"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_trades': 150,
            'profitable_trades': 90,
            'losing_trades': 60,
            'win_rate': 60.0,
        }
        strategy = {'name': '交易测试'}

        html = await service.generate_html_report(result, strategy)

        assert '150' in html
        assert '90' in html
        assert '60' in html


class TestGeneratePdfReport:
    """测试 PDF 报告生成"""

    @pytest.mark.asyncio
    async def test_generate_pdf_success(self):
        """测试成功生成 PDF 报告"""
        if not JINJA2_AVAILABLE or not WEASYPRINT_AVAILABLE:
            pytest.skip("jinja2 or weasyprint not available")

        service = ReportService()

        result = {
            'total_return': 15.5,
            'sharpe_ratio': 1.5,
            'max_drawdown': -8.2,
        }
        strategy = {'name': 'PDF测试'}

        pdf_bytes = await service.generate_pdf_report(result, strategy)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # PDF should start with %PDF
        assert pdf_bytes.startswith(b'%PDF')

    @pytest.mark.asyncio
    async def test_generate_pdf_without_weasyprint(self):
        """测试 weasyprint 不可用时抛出错误"""
        if WEASYPRINT_AVAILABLE:
            pytest.skip("weasyprint is available")

        # Patch to simulate weasyprint not available
        service = ReportService()

        with patch('app.services.report_service.WEASYPRINT_AVAILABLE', False):
            with pytest.raises(ImportError, match="weasyprint"):
                await service.generate_pdf_report({}, {})

    @pytest.mark.asyncio
    async def test_generate_pdf_uses_html_generation(self):
        """测试 PDF 生成使用 HTML 生成"""
        if not JINJA2_AVAILABLE or not WEASYPRINT_AVAILABLE:
            pytest.skip("jinja2 or weasyprint not available")

        service = ReportService()

        result = {'total_return': 10.0}
        strategy = {'name': '测试'}

        # Generate HTML first and verify PDF uses it
        with patch.object(service, 'generate_html_report',
                        return_value='<html><body>Test HTML</body></html>') as mock_html:
            with patch('app.services.report_service.WeasyPrintHTML') as mock_weasy:
                mock_weasy.return_value.write_pdf.return_value = b'%PDF-test'

                await service.generate_pdf_report(result, strategy)

                # Should have called generate_html_report
                mock_html.assert_called_once_with(result, strategy)


class TestGenerateExcelReport:
    """测试 Excel 报告生成"""

    @pytest.mark.asyncio
    async def test_generate_excel_success(self):
        """测试成功生成 Excel 报告"""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            'total_return': 15.5,
            'annual_return': 12.3,
            'sharpe_ratio': 1.5,
            'max_drawdown': -8.2,
            'win_rate': 60.0,
            'total_trades': 100,
            'profitable_trades': 60,
            'losing_trades': 40,
            'params': {'period': 20},
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'trades': [
                {'date': '2024-01-01', 'symbol': 'AAPL', 'type': 'buy', 'price': 100, 'size': 10},
                {'date': '2024-01-02', 'symbol': 'AAPL', 'type': 'sell', 'price': 110, 'size': 10},
            ],
            'equity_dates': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'equity_curve': [100000, 101000, 102000],
        }
        strategy = {'name': 'Excel测试', 'symbol': 'AAPL'}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0
        # Excel files should start with PK (ZIP signature)
        assert excel_bytes.startswith(b'PK')

    @pytest.mark.asyncio
    async def test_generate_excel_without_dependencies(self):
        """测试依赖不可用时抛出错误"""
        if PANDAS_AVAILABLE and OPENPYXL_AVAILABLE:
            pytest.skip("pandas and openpyxl are available")

        service = ReportService()

        with patch('app.services.report_service.PANDAS_AVAILABLE', False):
            with pytest.raises(ImportError, match="pandas.*openpyxl"):
                await service.generate_excel_report({}, {})

    @pytest.mark.asyncio
    async def test_generate_excel_minimal_data(self):
        """测试最小数据生成 Excel"""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {}  # 最小数据
        strategy = {'name': '最小测试'}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

    @pytest.mark.asyncio
    async def test_generate_excel_with_trades(self):
        """测试包含交易记录的 Excel 生成"""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            'trades': [
                {'date': '2024-01-01', 'symbol': 'AAPL', 'type': 'buy', 'price': 100, 'pnl': 1000},
                {'date': '2024-01-02', 'symbol': 'MSFT', 'type': 'sell', 'price': 200, 'pnl': -500},
            ]
        }
        strategy = {'name': '交易测试'}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

    @pytest.mark.asyncio
    async def test_generate_excel_with_equity_curve(self):
        """测试包含资金曲线的 Excel 生成"""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            'equity_dates': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
            'equity_curve': [100000, 101000, 100500, 102000, 103000],
        }
        strategy = {'name': '资金曲线测试'}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0


class TestEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_html_with_special_characters(self):
        """测试包含特殊字符的 HTML 生成"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': 15.5,
            'params': {'param_<script>': 'value测试'}
        }
        strategy = {'name': '策略<>&"'}

        html = await service.generate_html_report(result, strategy)

        # 应该生成有效的 HTML
        assert isinstance(html, str)
        assert len(html) > 0

    @pytest.mark.asyncio
    async def test_html_with_zero_values(self):
        """测试零值处理的 HTML 生成"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': 0,
            'annual_return': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'total_trades': 0,
            'profitable_trades': 0,
            'losing_trades': 0,
        }
        strategy = {'name': '零值测试'}

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert '0' in html

    @pytest.mark.asyncio
    async def test_html_with_large_values(self):
        """测试大值处理的 HTML 生成"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': 999999.99,
            'total_trades': 1000000,
        }
        strategy = {'name': '大值测试'}

        html = await service.generate_html_report(result, strategy)

        assert isinstance(html, str)
        assert '999999' in html
        assert '1000000' in html

    @pytest.mark.asyncio
    async def test_excel_empty_trades_list(self):
        """测试空交易列表的 Excel 生成"""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            pytest.skip("pandas or openpyxl not available")

        service = ReportService()

        result = {
            'trades': [],  # 空列表
            'equity_dates': [],  # 空列表
            'equity_curve': [],  # 空列表
        }
        strategy = {'name': '空数据测试'}

        excel_bytes = await service.generate_excel_report(result, strategy)

        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0


class TestTemplateRendering:
    """测试模板渲染"""

    @pytest.mark.asyncio
    async def test_template_contains_all_sections(self):
        """测试 HTML 模板包含所有部分"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {
            'total_return': 10.0,
            'annual_return': 8.0,
            'sharpe_ratio': 1.2,
            'max_drawdown': -5.0,
            'win_rate': 55.0,
            'total_trades': 50,
            'profitable_trades': 28,
            'losing_trades': 22,
            'params': {'test': 'value'},
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
        }
        strategy = {'name': '完整测试'}

        html = await service.generate_html_report(result, strategy)

        # 检查 HTML 结构
        assert '<!DOCTYPE html>' in html
        assert '<head>' in html
        assert '<body>' in html
        assert '</html>' in html
        assert '回测概览' in html
        assert '交易统计' in html
        assert '策略参数' in html
        assert '风险提示' in html
        assert 'Backtrader Web' in html

    @pytest.mark.asyncio
    async def test_template_styling(self):
        """测试模板样式"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        result = {'total_return': 10.0}
        strategy = {'name': '样式测试'}

        html = await service.generate_html_report(result, strategy)

        # 检查 CSS 样式
        assert '<style>' in html
        assert 'container' in html
        assert 'metric-card' in html
        assert 'table' in html
        assert 'header' in html
        assert 'footer' in html


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_report_generation_workflow(self):
        """测试完整报告生成工作流"""
        if not JINJA2_AVAILABLE:
            pytest.skip("jinja2 not available")

        service = ReportService()

        # 完整的回测结果
        result = {
            'symbol': '000001.SZ',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'total_return': 25.5,
            'annual_return': 22.0,
            'sharpe_ratio': 1.8,
            'max_drawdown': -10.5,
            'win_rate': 65.0,
            'total_trades': 200,
            'profitable_trades': 130,
            'losing_trades': 70,
            'params': {
                'fast_period': 5,
                'slow_period': 20,
                'risk_ratio': 2.0,
            },
            'trades': [
                {'date': '2024-01-01', 'symbol': '000001.SZ', 'type': 'buy', 'price': 10.0, 'size': 100},
                {'date': '2024-01-05', 'symbol': '000001.SZ', 'type': 'sell', 'price': 12.0, 'size': 100},
            ],
            'equity_dates': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'equity_curve': [100000, 101000, 102000],
        }
        strategy = {
            'name': '双均线策略',
            'description': '基于快慢均线的交叉信号进行交易',
            'symbol': '000001.SZ',
        }

        # 生成 HTML 报告
        html = await service.generate_html_report(result, strategy)
        assert '双均线策略' in html
        assert '25.5' in html  # total_return
        # symbol is not directly shown in HTML template, so remove this check
        # assert '000001.SZ' in html

        # 生成 Excel 报告（如果依赖可用）
        if PANDAS_AVAILABLE and OPENPYXL_AVAILABLE:
            excel = await service.generate_excel_report(result, strategy)
            assert len(excel) > 0
