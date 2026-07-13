"""
Playwright E2E 测试配置
"""
import pytest
import requests
from playwright.sync_api import Page, Browser, BrowserContext
from playwright.sync_api import sync_playwright

# 测试用户配置
TEST_USER = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "Test123456"
}

# 服务配置
FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8000"


def _ensure_test_user_exists(user: dict):
    """通过 API 确保测试用户已注册（比 UI 注册更快更可靠）

    先尝试登录：登录成功说明用户已存在，直接返回，避免反复调用 /auth/register
    触发 slowapi 注册限流（in-memory 计数器跨用例累积，200/hour 在全量 e2e 套件下会耗尽）。
    """
    try:
        login_resp = requests.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"username": user["username"], "password": user["password"]},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if login_resp.status_code == 200:
            return  # 用户已存在，无需注册
    except Exception:
        pass
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/auth/register",
            json={
                "username": user["username"],
                "email": user["email"],
                "password": user["password"],
            },
            timeout=10,
        )
        # 200/201 = 新注册成功, 400/409 = 用户已存在（都是 OK 的）
    except Exception:
        pass


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
    page.set_default_timeout(15000)
    yield page
    page.close()


@pytest.fixture(scope="session")
def test_user():
    """测试用户信息"""
    return TEST_USER


@pytest.fixture(scope="function")
def authenticated_page(context: BrowserContext, test_user: dict):
    """已登录的页面"""
    # 先通过 API 确保用户存在（跳过 UI 注册，速度快且可靠）
    _ensure_test_user_exists(test_user)

    page = context.new_page()
    page.set_default_timeout(15000)

    # 直接登录
    page.goto(f"{FRONTEND_URL}/login")
    page.wait_for_load_state("domcontentloaded")
    # 等待 Element Plus 输入框渲染
    page.wait_for_selector('input[placeholder="用户名"]', timeout=10000)

    page.fill('input[placeholder="用户名"]', test_user["username"])
    page.fill('input[placeholder="密码"]', test_user["password"])
    page.click('button:has-text("登录")')

    # 等待登录成功跳转：放宽为“离开登录页”即视为成功（最多等 30s）。
    # 既匹配跳转到根路径，也匹配带 redirect query 的中间态最终落地。
    login_ok = False
    deadline = 30
    for _ in range(deadline * 2):
        page.wait_for_timeout(500)
        current_url = page.url
        if "/login" not in current_url:
            login_ok = True
            break
    if not login_ok:
        raise RuntimeError(
            f"登录失败：仍在登录页 {page.url}。"
            f"请确认后端 ({BACKEND_URL}) 正在运行且响应正常。"
        )

    yield page
    page.close()


def _get_auth_token(user: dict) -> str | None:
    """通过 API 登录获取 JWT token（后端 /auth/login 接受 JSON 请求体）"""
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"username": user["username"], "password": user["password"]},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
    except Exception:
        pass
    return None


def _ensure_backtest_data(token: str) -> bool:
    """通过 API 确保至少有一条回测历史记录"""
    import time as _time
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/v1/backtest/",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])
            if len(items) > 0:
                return True

        # 没有记录，提交一个回测任务
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/backtest/run",
            headers=headers,
            json={
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00",
                "end_date": "2023-06-01T00:00:00",
                "initial_cash": 100000,
                "commission": 0.001,
                "params": {},
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            task_id = resp.json().get("task_id")
            for _ in range(30):
                _time.sleep(2)
                status_resp = requests.get(
                    f"{BACKEND_URL}/api/v1/backtest/{task_id}/status",
                    headers=headers,
                    timeout=10,
                )
                if status_resp.status_code == 200:
                    st = status_resp.json().get("status", "")
                    if st in ("completed", "failed", "cancelled"):
                        return st == "completed"
            return False
    except Exception:
        pass
    return False


@pytest.fixture(scope="session")
def test_data_ready(test_user):
    """确保测试数据就绪（至少有一条回测记录）

    Returns:
        bool: True 表示数据就绪，False 表示数据创建失败
    """
    _ensure_test_user_exists(test_user)
    token = _get_auth_token(test_user)
    if not token:
        return False
    return _ensure_backtest_data(token)
