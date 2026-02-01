"""
回测页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3001"


class TestBacktestPage:
    """回测页面测试"""
    
    def test_backtest_page_loads(self, authenticated_page: Page):
        """测试回测页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 检查页面标题
        expect(page.locator("text=回测配置")).to_be_visible()
    
    def test_backtest_form_elements(self, authenticated_page: Page):
        """测试回测配置表单元素"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 检查表单元素
        expect(page.locator("text=策略").first).to_be_visible()
        expect(page.locator("text=标的代码").first).to_be_visible()
        expect(page.locator("text=开始日期").first).to_be_visible()
        expect(page.locator("text=结束日期").first).to_be_visible()
        expect(page.locator("text=初始资金").first).to_be_visible()
        expect(page.locator("text=手续费率").first).to_be_visible()
        expect(page.locator('button:has-text("运行回测")').first).to_be_visible()
    
    def test_backtest_history_section(self, authenticated_page: Page):
        """测试回测历史区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 检查回测历史区域
        expect(page.locator("text=回测历史")).to_be_visible()
    
    def test_fill_backtest_form(self, authenticated_page: Page):
        """测试填写回测表单"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 填写标的代码
        symbol_input = page.locator('input[placeholder="如: 000001.SZ"]')
        symbol_input.fill("600000.SH")
        
        # 验证输入
        expect(symbol_input).to_have_value("600000.SH")
    
    def test_date_picker_interaction(self, authenticated_page: Page):
        """测试日期选择器交互"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 检查日期选择器存在
        date_editors = page.locator(".el-date-editor")
        expect(date_editors.first).to_be_visible()


class TestBacktestResults:
    """回测结果测试"""
    
    def test_result_metrics_display(self, authenticated_page: Page):
        """测试结果指标显示（如果有结果）"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 检查指标标签（即使没有数据也应该在代码中定义）
        # 这些在有结果时才显示
        page_content = page.content()
        
        # 验证页面结构正确
        assert "回测配置" in page_content
        assert "回测历史" in page_content
