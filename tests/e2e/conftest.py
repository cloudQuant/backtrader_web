"""
Playwright E2E 测试配置
"""
import pytest
from playwright.sync_api import Page, Browser, BrowserContext
from playwright.sync_api import sync_playwright
import time
import subprocess
import os
import signal

# 测试用户配置
TEST_USER = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "Test123456"
}

# 服务配置
FRONTEND_URL = "http://localhost:3001"
BACKEND_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def browser():
    """启动浏览器"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def context(browser: Browser):
    """创建浏览器上下文"""
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context: BrowserContext):
    """创建页面"""
    page = context.new_page()
    page.set_default_timeout(10000)
    yield page
    page.close()


@pytest.fixture(scope="session")
def test_user():
    """测试用户信息"""
    return TEST_USER


@pytest.fixture(scope="function")
def authenticated_page(context: BrowserContext, test_user: dict):
    """已登录的页面"""
    page = context.new_page()
    page.set_default_timeout(10000)
    
    # 先尝试注册（如果用户不存在）
    page.goto(f"{FRONTEND_URL}/register")
    page.wait_for_load_state("networkidle")
    
    # 填写注册表单
    page.fill('input[placeholder="用户名"]', test_user["username"])
    page.fill('input[placeholder="邮箱"]', test_user["email"])
    page.fill('input[placeholder="密码"]', test_user["password"])
    page.fill('input[placeholder="确认密码"]', test_user["password"])
    page.click('button:has-text("注册")')
    
    # 等待跳转或错误
    page.wait_for_timeout(1000)
    
    # 登录
    page.goto(f"{FRONTEND_URL}/login")
    page.wait_for_load_state("networkidle")
    
    page.fill('input[placeholder="用户名"]', test_user["username"])
    page.fill('input[placeholder="密码"]', test_user["password"])
    page.click('button:has-text("登录")')
    
    # 等待登录成功跳转到首页
    page.wait_for_url(f"{FRONTEND_URL}/", timeout=5000)
    
    yield page
    page.close()
