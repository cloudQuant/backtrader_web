"""
数据查询页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3000"


class TestDataPage:
    """数据查询页面测试"""
    
    def test_data_page_loads(self, authenticated_page: Page):
        """测试数据页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 检查页面标题
        expect(page.locator("text=数据查询").first).to_be_visible()
    
    def test_query_form_elements(self, authenticated_page: Page):
        """测试查询表单元素"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 检查表单元素
        expect(page.locator("text=股票代码")).to_be_visible()
        expect(page.locator("text=开始日期")).to_be_visible()
        expect(page.locator("text=结束日期")).to_be_visible()
        expect(page.locator('button:has-text("查询")')).to_be_visible()
    
    def test_fill_query_form(self, authenticated_page: Page):
        """测试填写查询表单"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 填写股票代码
        symbol_input = page.locator('input[placeholder="如: 000001.SZ"]')
        symbol_input.fill("600519.SH")
        
        # 验证输入
        expect(symbol_input).to_have_value("600519.SH")
    
    def test_default_symbol_prefilled(self, authenticated_page: Page):
        """测试默认股票代码预填充"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 默认值应该是 000001.SZ
        symbol_input = page.locator('input[placeholder="如: 000001.SZ"]')
        expect(symbol_input).to_have_value("000001.SZ")
    
    def test_page_structure(self, authenticated_page: Page):
        """测试页面整体结构"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        content = page.content()
        assert "数据查询" in content
        assert "查询" in content
