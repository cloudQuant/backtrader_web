"""
设置页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3000"


class TestSettingsPage:
    """设置页面测试"""
    
    def test_settings_page_loads(self, authenticated_page: Page):
        """测试设置页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查页面区域
        expect(page.locator("text=个人信息")).to_be_visible()
    
    def test_user_info_section(self, authenticated_page: Page):
        """测试用户信息区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查用户信息字段
        expect(page.locator("text=用户名")).to_be_visible()
        expect(page.locator("text=邮箱")).to_be_visible()
        expect(page.locator("text=注册时间")).to_be_visible()
    
    def test_change_password_section(self, authenticated_page: Page):
        """测试修改密码区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查密码修改区域
        expect(page.locator("text=修改密码").first).to_be_visible()
        expect(page.locator("text=当前密码").first).to_be_visible()
    
    def test_about_section(self, authenticated_page: Page):
        """测试关于区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查关于区域
        expect(page.locator("text=关于").first).to_be_visible()
        expect(page.locator("text=Backtrader Web").first).to_be_visible()
    
    def test_change_password_button(self, authenticated_page: Page):
        """测试修改密码按钮存在"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        expect(page.locator('button:has-text("修改密码")')).to_be_visible()
