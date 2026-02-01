"""
数据查询页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3001"


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
    
    def test_query_data(self, authenticated_page: Page):
        """测试查询数据"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 填写表单
        page.fill('input[placeholder="如: 000001.SZ"]', "000001.SZ")
        
        # 点击查询
        page.click('button:has-text("查询")')
        
        # 等待数据加载
        page.wait_for_timeout(2000)
        
        # 应该显示K线图区域
        page_content = page.content()
        assert "K线图" in page_content or "历史数据" in page_content
    
    def test_kline_chart_display(self, authenticated_page: Page):
        """测试K线图显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 查询数据
        page.click('button:has-text("查询")')
        page.wait_for_timeout(2000)
        
        # K线图区域应该显示
        expect(page.locator("text=K线图")).to_be_visible()
    
    def test_data_table_display(self, authenticated_page: Page):
        """测试数据表格显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 查询数据
        page.click('button:has-text("查询")')
        page.wait_for_timeout(2000)
        
        # 表格区域应该显示
        expect(page.locator("text=历史数据")).to_be_visible()
    
    def test_export_csv(self, authenticated_page: Page):
        """测试导出CSV"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")
        
        # 查询数据
        page.click('button:has-text("查询")')
        page.wait_for_timeout(2000)
        
        # 导出按钮应该可见
        export_btn = page.locator('button:has-text("导出CSV")')
        expect(export_btn).to_be_visible()
