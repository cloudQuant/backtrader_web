"""
报告生成服务测试

测试 HTML、PDF、Excel 报告生成功能
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
import io

from app.services.report_service import ReportService


@pytest.fixture
def report_service():
    """创建 ReportService 实例"""
    return ReportService()


class TestGenerateHTMLReport:
    """测试 HTML 报告生成"""

    @pytest.mark.asyncio
    async def test_generate_html_report_basic(self, report_service):
        """测试生成基本 HTML 报告"""
        # 模拟回测结果
        result = {
            "total_return": 15.5,
            "annual_return": 15.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": 12.5,
            "win_rate": 60.0,
            "total_trades": 20,
            "profitable_trades": 12,
            "losing_trades": 8,
            "params": {
                "fast_period": 5,
                "slow_period": 20,
            },
            "created_at": datetime.utcnow(),
        }

        strategy = {
            "name": "双均线策略",
            "description": "基于快慢均线交叉的趋势跟踪策略",
        }

        # 生成 HTML 报告
        html_content = await report_service.generate_html_report(result, strategy)

        # 验证 HTML 内容
        assert isinstance(html_content, str)
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "</html>" in html_content
        assert "双均线策略 - 回测报告" in html_content
        assert "15.5%" in html_content  # 总收益率
        assert "1.8" in html_content  # 夏普比率

    @pytest.mark.asyncio
    async def test_generate_html_report_positive_return(self, report_service):
        """测试正收益的 HTML 报告"""
        result = {
            "total_return": 25.5,
            "annual_return": 25.5,
            "sharpe_ratio": 2.5,
            "max_drawdown": 15.0,
            "win_rate": 70.0,
            "total_trades": 30,
            "profitable_trades": 21,
            "losing_trades": 9,
            "params": {},
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "测试策略"}

        html_content = await report_service.generate_html_report(result, strategy)

        # 正收益应该显示为绿色
        assert "positive" in html_content
        assert "25.5%" in html_content

    @pytest.mark.asyncio
    async def test_generate_html_report_negative_return(self, report_service):
        """测试负收益的 HTML 报告"""
        result = {
            "total_return": -10.5,
            "annual_return": -10.5,
            "sharpe_ratio": -0.8,
            "max_drawdown": 20.0,
            "win_rate": 40.0,
            "total_trades": 20,
            "profitable_trades": 8,
            "losing_trades": 12,
            "params": {},
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "亏损策略"}

        html_content = await report_service.generate_html_report(result, strategy)

        # 负收益应该显示为红色
        assert "negative" in html_content
        assert "-10.5%" in html_content

    @pytest.mark.asyncio
    async def test_generate_html_report_with_params(self, report_service):
        """测试包含参数的 HTML 报告"""
        result = {
            "total_return": 15.5,
            "annual_return": 15.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": 12.5,
            "win_rate": 60.0,
            "total_trades": 20,
            "profitable_trades": 12,
            "losing_trades": 8,
            "params": {
                "fast_period": 10,
                "slow_period": 30,
                "use_stop": True,
            },
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "参数化策略"}

        html_content = await report_service.generate_html_report(result, strategy)

        # 验证参数表格
        assert "fast_period" in html_content
        assert "slow_period" in html_content
        assert "use_stop" in html_content
        assert "10" in html_content
        assert "30" in html_content

    @pytest.mark.asyncio
    async def test_generate_html_report_without_jinja2(self, report_service):
        """测试 Jinja2 不可用时抛出错误"""
        with patch('app.services.report_service.JINJA2_AVAILABLE', False):
            with pytest.raises(ImportError, match="jinja2"):
                await report_service.generate_html_report({}, {})


class TestGeneratePDFReport:
    """测试 PDF 报告生成"""

    @pytest.mark.asyncio
    async def test_generate_pdf_report_basic(self, report_service):
        """测试生成基本 PDF 报告"""
        result = {
            "total_return": 15.5,
            "annual_return": 15.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": 12.5,
            "win_rate": 60.0,
            "total_trades": 20,
            "profitable_trades": 12,
            "losing_trades": 8,
            "params": {
                "fast_period": 5,
                "slow_period": 20,
            },
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "测试策略"}

        try:
            pdf_bytes = await report_service.generate_pdf_report(result, strategy)

            # 验证 PDF 字节
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 0
            # PDF 文件以 %PDF 开头
            assert pdf_bytes.startswith(b'%PDF')

        except ImportError as e:
            pytest.skip(f"WeasyPrint not available: {e}")

    @pytest.mark.asyncio
    async def test_generate_pdf_report_without_weasyprint(self, report_service):
        """测试 WeasyPrint 不可用时抛出错误"""
        with patch('app.services.report_service.WEASYPRINT_AVAILABLE', False):
            with pytest.raises(ImportError, match="weasyprint"):
                await report_service.generate_pdf_report({}, {})


class TestGenerateExcelReport:
    """测试 Excel 报告生成"""

    @pytest.mark.asyncio
    async def test_generate_excel_report_basic(self, report_service):
        """测试生成基本 Excel 报告"""
        result = {
            "total_return": 15.5,
            "annual_return": 15.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": 12.5,
            "win_rate": 60.0,
            "total_trades": 20,
            "profitable_trades": 12,
            "losing_trades": 8,
            "equity_curve": [100000, 101550, 103100, 104650],
            "equity_dates": ["2023-01-01", "2023-06-30", "2023-09-30", "2023-12-31"],
            "drawdown_curve": [0, -2.0, -5.0, -10.0],
            "trades": [],
            "params": {
                "fast_period": 5,
                "slow_period": 20,
            },
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "测试策略"}

        try:
            excel_bytes = await report_service.generate_excel_report(result, strategy)

            # 验证 Excel 字节
            assert isinstance(excel_bytes, bytes)
            assert len(excel_bytes) > 0
            # Excel 文件以 ZIP 魔法开头（.xlsx 格式）
            assert excel_bytes.startswith(b'PK\x03\x04') or excel_bytes.startswith(b'PK\x05\x06')

        except ImportError as e:
            pytest.skip(f"pandas/openpyxl not available: {e}")

    @pytest.mark.asyncio
    async def test_generate_excel_report_with_trades(self, report_service):
        """测试包含交易记录的 Excel 报告"""
        result = {
            "total_return": 15.5,
            "annual_return": 15.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": 12.5,
            "win_rate": 60.0,
            "total_trades": 2,
            "profitable_trades": 1,
            "losing_trades": 1,
            "equity_curve": [100000, 101550],
            "equity_dates": ["2023-01-01", "2023-12-31"],
            "drawdown_curve": [0, -10.0],
            "trades": [
                {
                    "date": datetime(2023, 1, 1),
                    "type": "buy",
                    "price": 100.0,
                    "size": 100,
                    "value": 10000,
                    "pnl": 1550,
                },
                {
                    "date": datetime(2023, 12, 31),
                    "type": "sell",
                    "price": 105.5,
                    "size": 100,
                    "value": 10550,
                    "pnl": 1550,
                },
            ],
            "params": {},
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "测试策略"}

        try:
            excel_bytes = await report_service.generate_excel_report(result, strategy)

            # 验证 Excel 字节
            assert isinstance(excel_bytes, bytes)
            assert len(excel_bytes) > 0

        except ImportError as e:
            pytest.skip(f"pandas/openpyxl not available: {e}")

    @pytest.mark.asyncio
    async def test_generate_excel_report_without_pandas(self, report_service):
        """测试 pandas 不可用时抛出错误"""
        with patch('app.services.report_service.PANDAS_AVAILABLE', False):
            with pytest.raises(ImportError, match="pandas"):
                await report_service.generate_excel_report({}, {})


class TestReportServiceIntegration:
    """测试报告生成服务的集成功能"""

    @pytest.mark.asyncio
    async def test_generate_all_report_formats(self, report_service):
        """测试生成所有报告格式"""
        result = {
            "total_return": 15.5,
            "annual_return": 15.5,
            "sharpe_ratio": 1.8,
            "max_drawdown": 12.5,
            "win_rate": 60.0,
            "total_trades": 20,
            "profitable_trades": 12,
            "losing_trades": 8,
            "equity_curve": [100000, 101550],
            "equity_dates": ["2023-01-01", "2023-12-31"],
            "drawdown_curve": [0, -10.0],
            "trades": [],
            "params": {
                "fast_period": 5,
                "slow_period": 20,
            },
            "created_at": datetime.utcnow(),
        }

        strategy = {"name": "测试策略"}

        # 生成 HTML 报告
        html_content = await report_service.generate_html_report(result, strategy)
        assert isinstance(html_content, str)
        assert "<!DOCTYPE html>" in html_content

        # 生成 PDF 报告（可能不可用）
        try:
            pdf_bytes = await report_service.generate_pdf_report(result, strategy)
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 0
        except ImportError:
            # PDF 功能不可用，跳过
            pass

        # 生成 Excel 报告（可能不可用）
        try:
            excel_bytes = await report_service.generate_excel_report(result, strategy)
            assert isinstance(excel_bytes, bytes)
            assert len(excel_bytes) > 0
        except ImportError:
            # Excel 功能不可用，跳过
            pass
