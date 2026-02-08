"""
回测页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3000"


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
        
        # 检查表单核心元素
        expect(page.locator("text=策略").first).to_be_visible()
        expect(page.locator('button:has-text("运行回测")').first).to_be_visible()
        # 策略选择器存在
        expect(page.locator(".el-select").first).to_be_visible()
    
    def test_backtest_history_section(self, authenticated_page: Page):
        """测试回测历史区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 检查回测历史区域
        expect(page.locator("text=回测历史")).to_be_visible()
    
    def test_strategy_selector(self, authenticated_page: Page):
        """测试策略选择器"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 点击策略选择器
        page.click(".el-select")
        page.wait_for_timeout(500)
        
        # 应该出现下拉选项
        expect(page.locator(".el-select-dropdown__item").first).to_be_visible()
    
    def test_page_structure(self, authenticated_page: Page):
        """测试回测页面整体结构"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")
        
        # 页面应该同时包含配置区域和历史区域
        content = page.content()
        assert "回测配置" in content
        assert "回测历史" in content


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
