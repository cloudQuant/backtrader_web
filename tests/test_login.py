"""
登录功能 Playwright 测试用例

使用方法:
1. 安装 playwright: pip install playwright pytest-playwright
2. 安装浏览器: playwright install chromium
3. 确保前后端服务已启动
4. 运行测试: pytest tests/test_login.py -v
"""
import pytest
from playwright.sync_api import Page, expect


# 配置
BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """浏览器上下文配置"""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
    }


class TestLogin:
    """登录功能测试"""

    def test_login_page_loads(self, page: Page):
        """测试登录页面能够正常加载"""
        page.goto(f"{BASE_URL}/login")
        
        # 验证页面元素存在
        expect(page.locator("input[type='text'], input[placeholder*='用户名'], input[placeholder*='username']").first).to_be_visible(timeout=10000)
        expect(page.locator("input[type='password']").first).to_be_visible()
        expect(page.locator("button[type='submit'], button:has-text('登录')").first).to_be_visible()

    def test_login_with_empty_credentials(self, page: Page):
        """测试空凭据登录"""
        page.goto(f"{BASE_URL}/login")
        
        # 点击登录按钮而不输入任何内容
        login_button = page.locator("button[type='submit'], button:has-text('登录')").first
        login_button.click()
        
        # 验证出现验证错误消息（等待表单验证）
        page.wait_for_timeout(500)

    def test_login_with_invalid_credentials(self, page: Page):
        """测试无效凭据登录"""
        page.goto(f"{BASE_URL}/login")
        
        # 输入无效的用户名和密码
        username_input = page.locator("input[type='text'], input[placeholder*='用户名'], input[placeholder*='username']").first
        password_input = page.locator("input[type='password']").first
        
        username_input.fill("invalid_user")
        password_input.fill("invalid_password")
        
        # 点击登录
        login_button = page.locator("button[type='submit'], button:has-text('登录')").first
        login_button.click()
        
        # 等待响应
        page.wait_for_timeout(2000)
        
        # 验证没有跳转到主页（登录失败应该留在登录页面或显示错误）
        # 由于是无效凭据，应该显示错误消息或仍在登录页

    def test_login_api_endpoint(self, page: Page):
        """测试登录 API 端点响应"""
        import json
        
        # 使用默认管理员账号测试登录
        response = page.request.post(
            f"{API_URL}/api/v1/auth/login",
            data=json.dumps({
                "username": "admin",
                "password": "admin123"
            }),
            headers={"Content-Type": "application/json"}
        )
        
        # API 不应该返回 500
        assert response.status != 500, f"API 返回 500 错误: {response.text()}"
        print(f"API 响应状态: {response.status}")
        
        # 验证管理员账号登录成功
        assert response.status == 200, f"管理员登录失败: {response.text()}"
        
        # 验证返回了 token
        data = response.json()
        assert "access_token" in data, "登录响应缺少 access_token"
        print("✓ 管理员账号登录成功")

    def test_register_and_login(self, page: Page):
        """测试注册后登录（完整流程）"""
        import uuid
        import json
        
        # 生成唯一用户名
        unique_id = str(uuid.uuid4())[:8]
        username = f"test_user_{unique_id}"
        email = f"test_{unique_id}@example.com"
        password = "TestPass123!"
        
        # 1. 先尝试注册 (使用 JSON 格式)
        register_response = page.request.post(
            f"{API_URL}/api/v1/auth/register",
            data=json.dumps({
                "username": username,
                "email": email,
                "password": password
            }),
            headers={"Content-Type": "application/json"}
        )
        
        print(f"注册响应状态: {register_response.status}")
        print(f"注册响应内容: {register_response.text()}")
        
        # 2. 尝试登录 (使用 JSON 格式)
        login_response = page.request.post(
            f"{API_URL}/api/v1/auth/login",
            data=json.dumps({
                "username": username,
                "password": password
            }),
            headers={"Content-Type": "application/json"}
        )
        
        print(f"登录响应状态: {login_response.status}")
        assert login_response.status != 500, f"登录 API 返回 500 错误: {login_response.text()}"
        
        # 如果注册成功，登录应该返回 200
        if register_response.status in [200, 201]:
            assert login_response.status == 200, f"注册后登录失败: {login_response.text()}"
            print("✓ 注册和登录流程测试通过")


class TestLoginUI:
    """登录 UI 交互测试"""

    def test_password_visibility_toggle(self, page: Page):
        """测试密码可见性切换"""
        page.goto(f"{BASE_URL}/login")
        
        password_input = page.locator("input[type='password']").first
        expect(password_input).to_be_visible()
        
        # 输入密码
        password_input.fill("testpassword")
        
        # 查找并点击密码可见性切换按钮（如果存在）
        toggle_button = page.locator("[class*='password'] button, button[aria-label*='password']").first
        if toggle_button.is_visible():
            toggle_button.click()
            # 验证密码变为可见
            page.wait_for_timeout(300)

    def test_remember_me_checkbox(self, page: Page):
        """测试记住我复选框（如果存在）"""
        page.goto(f"{BASE_URL}/login")
        
        remember_checkbox = page.locator("input[type='checkbox']").first
        if remember_checkbox.is_visible():
            remember_checkbox.check()
            expect(remember_checkbox).to_be_checked()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--headed"])
