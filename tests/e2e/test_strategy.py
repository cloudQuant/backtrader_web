"""
策略管理页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect
import uuid

FRONTEND_URL = "http://localhost:3000"


class TestStrategyPage:
    """策略页面测试"""
    
    def test_strategy_page_loads(self, authenticated_page: Page):
        """测试策略页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 检查创建策略按钮
        expect(page.locator('button:has-text("创建策略")')).to_be_visible()
    
    def test_strategy_gallery_section(self, authenticated_page: Page):
        """测试策略库区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 检查策略库标签页
        expect(page.locator("text=策略库").first).to_be_visible()
    
    def test_open_create_dialog(self, authenticated_page: Page):
        """测试打开创建策略对话框"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 点击创建策略
        page.click('button:has-text("创建策略")')
        page.wait_for_timeout(500)
        
        # 对话框应该打开 - 检查对话框元素
        expect(page.locator(".el-dialog")).to_be_visible()
        expect(page.locator('input[placeholder="输入策略名称"]')).to_be_visible()
    
    def test_create_strategy_form(self, authenticated_page: Page):
        """测试创建策略表单"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 打开对话框
        page.click('button:has-text("创建策略")')
        page.wait_for_timeout(500)
        
        # 填写表单
        unique_name = f"TestStrategy_{uuid.uuid4().hex[:6]}"
        
        name_input = page.locator('input[placeholder="输入策略名称"]')
        name_input.fill(unique_name)
        
        # 验证输入
        expect(name_input).to_have_value(unique_name)
    
    def test_close_create_dialog(self, authenticated_page: Page):
        """测试关闭创建对话框"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 打开对话框
        page.click('button:has-text("创建策略")')
        page.wait_for_timeout(500)
        
        # 点击取消
        page.click('button:has-text("取消")')
        page.wait_for_timeout(500)
        
        # 对话框应该关闭
        expect(page.locator(".el-dialog__body")).to_be_hidden()
    
    def test_category_filter(self, authenticated_page: Page):
        """测试分类筛选"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 检查分类筛选按钮组存在（el-radio-group）
        expect(page.locator(".el-radio-group").first).to_be_visible()


class TestStrategyTemplates:
    """策略模板测试"""
    
    def test_use_template(self, authenticated_page: Page):
        """测试使用策略模板"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")
        
        # 检查是否有模板（需要后端返回数据）
        # 如果有模板，点击使用
        templates = page.locator(".border.rounded-lg.hover\\:border-blue-500")
        
        if templates.count() > 0:
            templates.first.click()
            page.wait_for_timeout(500)
            
            # 应该打开预填充的创建对话框
            expect(page.locator("text=创建策略").last).to_be_visible()
