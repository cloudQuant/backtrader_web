"""
认证模块 E2E 测试
使用 Playwright 模拟浏览器测试登录、注册功能
"""
import pytest
from playwright.sync_api import Page, expect
import uuid

FRONTEND_URL = "http://localhost:3000"


class TestAuthPages:
    """认证页面测试"""
    
    def test_login_page_loads(self, page: Page):
        """测试登录页面加载"""
        page.goto(f"{FRONTEND_URL}/login")
        page.wait_for_load_state("networkidle")
        
        # 检查页面标题
        expect(page.locator("h1")).to_contain_text("Backtrader Web")
        
        # 检查表单元素
        expect(page.locator('input[placeholder="用户名"]')).to_be_visible()
        expect(page.locator('input[placeholder="密码"]')).to_be_visible()
        expect(page.locator('button:has-text("登录")')).to_be_visible()
        
        # 检查注册链接
        expect(page.locator('a:has-text("立即注册")')).to_be_visible()
    
    def test_register_page_loads(self, page: Page):
        """测试注册页面加载"""
        page.goto(f"{FRONTEND_URL}/register")
        page.wait_for_load_state("networkidle")
        
        # 检查页面标题
        expect(page.locator("h1")).to_contain_text("注册账号")
        
        # 检查表单元素
        expect(page.locator('input[placeholder="用户名"]')).to_be_visible()
        expect(page.locator('input[placeholder="邮箱"]')).to_be_visible()
        expect(page.locator('input[placeholder="密码"]')).to_be_visible()
        expect(page.locator('input[placeholder="确认密码"]')).to_be_visible()
        expect(page.locator('button:has-text("注册")')).to_be_visible()
    
    def test_register_new_user(self, page: Page):
        """测试新用户注册"""
        unique_id = str(uuid.uuid4())[:8]
        username = f"user_{unique_id}"
        email = f"user_{unique_id}@test.com"
        password = "TestPassword123"
        
        page.goto(f"{FRONTEND_URL}/register")
        page.wait_for_load_state("networkidle")
        
        # 填写注册表单
        page.fill('input[placeholder="用户名"]', username)
        page.fill('input[placeholder="邮箱"]', email)
        page.fill('input[placeholder="密码"]', password)
        page.fill('input[placeholder="确认密码"]', password)
        
        # 点击注册按钮
        page.click('button:has-text("注册")')
        
        # 等待跳转到登录页
        page.wait_for_url(f"{FRONTEND_URL}/login", timeout=10000)
        
        # 验证成功提示
        expect(page).to_have_url(f"{FRONTEND_URL}/login")
    
    def test_login_with_registered_user(self, page: Page):
        """测试已注册用户登录"""
        # 先注册一个用户
        unique_id = str(uuid.uuid4())[:8]
        username = f"login_test_{unique_id}"
        email = f"login_{unique_id}@test.com"
        password = "TestPassword123"
        
        # 注册
        page.goto(f"{FRONTEND_URL}/register")
        page.wait_for_load_state("networkidle")
        page.fill('input[placeholder="用户名"]', username)
        page.fill('input[placeholder="邮箱"]', email)
        page.fill('input[placeholder="密码"]', password)
        page.fill('input[placeholder="确认密码"]', password)
        page.click('button:has-text("注册")')
        page.wait_for_url(f"{FRONTEND_URL}/login", timeout=10000)
        
        # 登录
        page.fill('input[placeholder="用户名"]', username)
        page.fill('input[placeholder="密码"]', password)
        page.click('button:has-text("登录")')
        
        # 等待跳转到首页
        page.wait_for_url(f"{FRONTEND_URL}/", timeout=10000)
        
        # 验证登录成功 - 应该显示用户名
        expect(page.locator("text=仪表盘")).to_be_visible()
    
    def test_login_with_wrong_password(self, page: Page):
        """测试错误密码登录"""
        page.goto(f"{FRONTEND_URL}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[placeholder="用户名"]', "nonexistent_user")
        page.fill('input[placeholder="密码"]', "wrong_password")
        page.click('button:has-text("登录")')
        
        # 等待错误提示
        page.wait_for_timeout(2000)
        
        # 应该还在登录页
        expect(page).to_have_url(f"{FRONTEND_URL}/login")
    
    def test_navigate_between_login_and_register(self, page: Page):
        """测试登录和注册页面导航"""
        # 从登录页到注册页
        page.goto(f"{FRONTEND_URL}/login")
        page.wait_for_load_state("networkidle")
        page.click('a:has-text("立即注册")')
        expect(page).to_have_url(f"{FRONTEND_URL}/register")
        
        # 从注册页到登录页
        page.click('a:has-text("立即登录")')
        expect(page).to_have_url(f"{FRONTEND_URL}/login")
    
    def test_form_validation(self, page: Page):
        """测试表单验证"""
        page.goto(f"{FRONTEND_URL}/register")
        page.wait_for_load_state("networkidle")
        
        # 直接点击注册，不填写任何内容
        page.click('button:has-text("注册")')
        
        # 等待验证错误
        page.wait_for_timeout(500)
        
        # 应该还在注册页，不会提交
        expect(page).to_have_url(f"{FRONTEND_URL}/register")
    
    def test_password_mismatch(self, page: Page):
        """测试密码不匹配验证"""
        page.goto(f"{FRONTEND_URL}/register")
        page.wait_for_load_state("networkidle")
        
        page.fill('input[placeholder="用户名"]', "testuser")
        page.fill('input[placeholder="邮箱"]', "test@test.com")
        page.fill('input[placeholder="密码"]', "password123")
        page.fill('input[placeholder="确认密码"]', "different123")
        
        # 点击注册
        page.click('button:has-text("注册")')
        
        # 等待验证
        page.wait_for_timeout(500)
        
        # 应该还在注册页
        expect(page).to_have_url(f"{FRONTEND_URL}/register")


class TestAuthenticatedRedirect:
    """认证重定向测试"""
    
    def test_unauthenticated_redirect_to_login(self, page: Page):
        """测试未登录访问受保护页面重定向到登录"""
        import re
        # 尝试直接访问仪表盘
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_timeout(1000)
        
        # 应该被重定向到登录页（可能带redirect参数）
        expect(page).to_have_url(re.compile(r".*/login.*"))
    
    def test_unauthenticated_redirect_backtest(self, page: Page):
        """测试未登录访问回测页面重定向"""
        import re
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_timeout(1000)
        
        # 应该被重定向到登录页（可能带redirect参数）
        expect(page).to_have_url(re.compile(r".*/login.*"))
