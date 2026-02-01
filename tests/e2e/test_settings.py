"""
设置页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3001"


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
    
    def test_system_settings_section(self, authenticated_page: Page):
        """测试系统设置区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查系统设置
        expect(page.locator("text=系统设置").first).to_be_visible()
        expect(page.locator("text=主题").first).to_be_visible()
    
    def test_about_section(self, authenticated_page: Page):
        """测试关于区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查关于区域
        expect(page.locator("text=关于").first).to_be_visible()
    
    def test_theme_selection(self, authenticated_page: Page):
        """测试主题选择"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 检查主题选项
        expect(page.locator("text=浅色")).to_be_visible()
        expect(page.locator("text=深色")).to_be_visible()
    
    def test_language_selection(self, authenticated_page: Page):
        """测试语言选择"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/settings")
        page.wait_for_load_state("networkidle")
        
        # 点击语言选择器
        page.click('.el-select >> text=中文')
        page.wait_for_timeout(300)
        
        # 下拉选项应该出现
        expect(page.locator("text=English")).to_be_visible()
