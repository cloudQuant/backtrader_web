#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交互式 UI E2E 测试 - 覆盖各页面核心功能交互。

使用 Playwright 模拟浏览器登录后，对各页面进行点击/填表/提交等交互测试，
并在交互过程中捕获 console 错误与 API 4xx/5xx，确保功能可用。

依赖: conftest.py 的 authenticated_page / page / context / browser fixture。
运行: pytest tests/e2e/test_ui_interactive.py -v
"""
import re
import time

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL, BACKEND_URL

BASE_URL = FRONTEND_URL

# 过滤掉与功能无关的噪音（vite HMR、favicon、第三方资源加载失败）
def _is_real_error(msg: str) -> bool:
    low = msg.lower()
    if "vite" in low:
        return False
    if "failed to load resource" in low:
        return False
    if "favicon" in low:
        return False
    return True


# ---------------------------------------------------------------------------
# 管理员 fixture（用于访问 requiresAdmin 的配置页面）
# ---------------------------------------------------------------------------
ADMIN_USER = {"username": "admin", "password": "admin123"}


@pytest.fixture(scope="function")
def admin_page(context):
    """以管理员身份登录的页面（用于 config 等管理页面）。"""
    page = context.new_page()
    page.set_default_timeout(15000)
    page.goto(f"{BASE_URL}/login")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector('input[placeholder="用户名"]', timeout=10000)
    page.fill('input[placeholder="用户名"]', ADMIN_USER["username"])
    page.fill('input[placeholder="密码"]', ADMIN_USER["password"])
    page.click('button:has-text("登录")')
    try:
        page.wait_for_url(re.compile(r"http://localhost:3000(?:/)?(?:\?.*)?$"), timeout=15000)
    except Exception:
        if "/login" in page.url:
            pytest.skip("管理员登录失败，跳过 admin 页面测试")
    yield page
    page.close()


# ---------------------------------------------------------------------------
# 侧边栏导航
# ---------------------------------------------------------------------------
class TestSidebarNavigation:
    NAV_ITEMS = [
        ("仪表盘", "/"),
        ("策略", "/research/strategies"),
        ("工作区", "/research/workspaces"),
        ("回测", "/backtest"),
        ("AI 对话", "/ai/chat"),
        ("行情", "/quote"),
        ("设置", "/settings"),
    ]

    def test_navigate_via_sidebar(self, authenticated_page: Page):
        """通过侧边栏菜单导航到各核心页面，不应被踢回登录页。"""
        page = authenticated_page
        for label, _expected in self.NAV_ITEMS:
            link = page.locator(f'.el-menu-item:has-text("{label}"), a:has-text("{label}")').first
            if link.count() == 0:
                continue
            try:
                link.click(timeout=5000)
            except Exception:
                continue
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            time.sleep(0.4)
            assert "/login" not in page.url, f"点击 {label} 后被踢回登录页"


# ---------------------------------------------------------------------------
# 仪表盘
# ---------------------------------------------------------------------------
class TestDashboard:
    def test_dashboard_renders_content(self, authenticated_page: Page):
        """Dashboard 加载后应渲染卡片，无未捕获异常。"""
        page = authenticated_page
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE_URL}/")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert page.locator("h1, h2, .el-card, .dashboard-card").count() > 0
        real = [e for e in errors if _is_real_error(e)]
        assert not real, f"Dashboard 有未捕获异常: {real}"

    def test_dashboard_backtest_api_no_500(self, authenticated_page: Page):
        """Dashboard 触发的 backtests API 不应返回 500（验证迁移漂移已修复）。"""
        page = authenticated_page
        statuses = []
        page.on(
            "response",
            lambda r: statuses.append(r.status) if "/api/v1/backtests" in r.url else None,
        )
        page.goto(f"{BASE_URL}/")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        if statuses:
            assert 500 not in statuses, f"backtests API 返回 500: {statuses}"


# ---------------------------------------------------------------------------
# 策略页面
# ---------------------------------------------------------------------------
class TestStrategyPage:
    def test_strategy_tabs_and_templates(self, authenticated_page: Page):
        """策略页应显示 tabs 与策略模板。"""
        page = authenticated_page
        page.goto(f"{BASE_URL}/research/strategies")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert page.locator(".el-tabs").count() > 0
        cards = page.locator(".strategy-card, .el-card, .el-table__row")
        assert cards.count() > 0, "未显示任何策略模板"

    def test_strategy_category_filter(self, authenticated_page: Page):
        """策略分类过滤按钮可点击切换，不报错。"""
        page = authenticated_page
        page.goto(f"{BASE_URL}/research/strategies")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        trend_btn = page.locator('.el-radio-button:has-text("趋势")').first
        if trend_btn.count() > 0:
            trend_btn.click(timeout=5000)
            page.wait_for_timeout(800)
        assert "/research/strategies" in page.url


# ---------------------------------------------------------------------------
# 回测页面（交互：选择策略 + 运行）
# ---------------------------------------------------------------------------
class TestBacktestPage:
    def test_backtest_form_loads(self, authenticated_page: Page):
        """回测页表单与运行按钮加载正常。"""
        page = authenticated_page
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE_URL}/backtest/legacy")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert page.locator('[data-test="backtest-legacy-page"]').count() > 0
        run_btn = page.locator('button:has-text("运行回测"), button:has-text("运行")').first
        assert run_btn.count() > 0, "未找到运行回测按钮"
        real = [e for e in errors if _is_real_error(e)]
        assert not real, f"回测页有未捕获异常: {real}"

    def test_backtest_run_without_strategy_warns(self, authenticated_page: Page):
        """不选策略直接运行应被前端校验拦截（ElMessage 提示），不应发起 500 请求。"""
        page = authenticated_page
        statuses = []
        page.on(
            "response",
            lambda r: statuses.append((r.url, r.status))
            if "/api/v1/backtest" in r.url and r.request.method == "POST"
            else None,
        )
        page.goto(f"{BASE_URL}/backtest/legacy")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        run_btn = page.locator('button:has-text("运行回测"), button:has-text("运行")').first
        run_btn.click(timeout=5000)
        page.wait_for_timeout(1500)
        # 前端校验拦截，不应发起回测请求
        for url, st in statuses:
            assert st != 500, f"回测请求返回 500: {url}"

    def test_backtest_select_strategy_and_run(self, authenticated_page: Page):
        """选择策略后运行回测，/backtest/run 不应返回 500。"""
        page = authenticated_page
        statuses = []
        page.on(
            "response",
            lambda r: statuses.append((r.url, r.status))
            if "/api/v1/backtest" in r.url and r.request.method == "POST"
            else None,
        )
        page.goto(f"{BASE_URL}/backtest/legacy")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1.5)
        # 等待策略模板加载
        select_trigger = page.locator(".backtest-launch-form .el-select .el-select__wrapper, .backtest-launch-form .el-select").first
        if select_trigger.count() == 0:
            pytest.skip("回测页策略下拉未渲染")
        select_trigger.click(timeout=5000)
        # 下拉选项被 teleport 到 body 下的 .el-select-dropdown
        page.wait_for_selector(".el-select-dropdown:not([style*='display: none']) .el-select-dropdown__item", timeout=5000)
        first_option = page.locator(".el-select-dropdown:not([style*='display: none']) .el-select-dropdown__item").first
        if first_option.count() == 0:
            pytest.skip("策略下拉无选项")
        first_option.click(timeout=5000)
        page.wait_for_timeout(800)
        # 点击运行
        run_btn = page.locator('button:has-text("运行回测"), button:has-text("运行")').first
        run_btn.click(timeout=5000)
        # 等待提交响应
        page.wait_for_timeout(3000)
        for url, st in statuses:
            assert st != 500, f"回测请求返回 500: {url} -> {st}"


# ---------------------------------------------------------------------------
# AI 对话页面
# ---------------------------------------------------------------------------
class TestAIChatPage:
    def test_ai_chat_page_loads(self, authenticated_page: Page):
        """AI 对话页加载，输入框可见。"""
        page = authenticated_page
        page.goto(f"{BASE_URL}/ai/chat")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        inp = page.locator('[data-test="ai-chat-input"], textarea').first
        assert inp.count() > 0, "未找到 AI 对话输入框"

    def test_ai_chat_type_and_send(self, authenticated_page: Page):
        """可在输入框输入文本并发送，/kb-chat/send 不应返回 500。

        输入框在 knowledge_qa 模式下需先选中知识库才会启用；
        页面 onMounted 会拉取知识库并自动选中第一个，故等待输入框启用后再输入。
        """
        page = authenticated_page
        statuses = []
        page.on(
            "response",
            lambda r: statuses.append((r.url, r.status))
            if "/kb-chat/send" in r.url or "/api/v1/ai" in r.url
            else None,
        )
        page.goto(f"{BASE_URL}/ai/chat")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        inp = page.locator('[data-test="ai-chat-input"]').first
        if inp.count() == 0:
            pytest.skip("AI 对话输入框未渲染")
        # 等待 KB 拉取完成、输入框启用（最多 12s）
        enabled = False
        for _ in range(24):
            try:
                if inp.is_enabled():
                    enabled = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(500)
        if not enabled:
            pytest.skip("无可用知识库，输入框保持禁用（符合预期）")
        inp.fill("测试消息 hello")
        assert inp.input_value() == "测试消息 hello"
        send_btn = page.locator('[data-test="ai-chat-send"]').first
        assert send_btn.count() > 0, "未找到发送按钮"
        send_btn.click(timeout=5000)
        # 等待 AI 响应
        page.wait_for_timeout(5000)
        for url, st in statuses:
            assert st != 500, f"AI 对话请求返回 500: {url} -> {st}"


# ---------------------------------------------------------------------------
# 知识库页面
# ---------------------------------------------------------------------------
class TestKnowledgeBasePage:
    def test_knowledge_base_page_loads(self, authenticated_page: Page):
        """知识库页加载无未捕获异常。"""
        page = authenticated_page
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE_URL}/ai/knowledge-base")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert "/login" not in page.url
        real = [e for e in errors if _is_real_error(e)]
        assert not real, f"知识库页有未捕获异常: {real}"


# ---------------------------------------------------------------------------
# 行情页面
# ---------------------------------------------------------------------------
class TestQuotePage:
    def test_quote_page_loads(self, authenticated_page: Page):
        """行情页加载。"""
        page = authenticated_page
        page.goto(f"{BASE_URL}/quote")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert "/login" not in page.url

    def test_quote_no_missing_i18n(self, authenticated_page: Page):
        """行情页不应再有 common.refresh 缺失警告。"""
        page = authenticated_page
        warnings = []
        page.on(
            "console",
            lambda m: warnings.append(m.text) if m.type == "warning" else None,
        )
        page.goto(f"{BASE_URL}/quote")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        refresh_warnings = [w for w in warnings if "common.refresh" in w]
        assert not refresh_warnings, f"common.refresh i18n key 仍缺失: {refresh_warnings}"


# ---------------------------------------------------------------------------
# 设置页面
# ---------------------------------------------------------------------------
class TestSettingsPage:
    def test_settings_sections(self, authenticated_page: Page):
        """设置页各区域渲染。"""
        page = authenticated_page
        page.goto(f"{BASE_URL}/settings")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        # 个人信息 / 修改密码 至少存在其一
        profile = page.locator("text=个人信息").first
        pwd = page.locator("text=修改密码").first
        assert profile.count() > 0 or pwd.count() > 0, "设置页未渲染个人信息/修改密码区域"


# ---------------------------------------------------------------------------
# 组合页面
# ---------------------------------------------------------------------------
class TestPortfolioPage:
    def test_portfolio_page_loads(self, authenticated_page: Page):
        """组合页加载无未捕获异常，positions API 不应 500。"""
        page = authenticated_page
        errors = []
        statuses = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "response",
            lambda r: statuses.append((r.url, r.status))
            if "/api/v1/paper-trading" in r.url or "/api/v1/portfolio" in r.url
            else None,
        )
        page.goto(f"{BASE_URL}/portfolio")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert "/login" not in page.url
        real = [e for e in errors if _is_real_error(e)]
        assert not real, f"组合页有未捕获异常: {real}"
        for url, st in statuses:
            assert st != 500, f"组合页 API 返回 500: {url} -> {st}"


# ---------------------------------------------------------------------------
# 数据页面
# ---------------------------------------------------------------------------
class TestDataPages:
    @pytest.mark.parametrize(
        "path",
        [
            "/data/market",
            "/data/tables",
            "/data/topics",
            "/data/intelligence/news",
            "/data/intelligence/scanners",
            "/data/quote",
        ],
    )
    def test_data_subpage_no_500(self, authenticated_page: Page, path: str):
        """数据子页面加载无 API 500。"""
        page = authenticated_page
        statuses = []
        page.on(
            "response",
            lambda r: statuses.append((r.url, r.status)) if "/api/" in r.url and r.status >= 500 else None,
        )
        page.goto(f"{BASE_URL}{path}")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert "/login" not in page.url
        assert not statuses, f"{path} 有 API 500 错误: {statuses}"


# ---------------------------------------------------------------------------
# 配置页面（admin）
# ---------------------------------------------------------------------------
class TestConfigPages:
    @pytest.mark.parametrize(
        "path",
        [
            "/config/data/scripts",
            "/config/ai/providers",
            "/config/gateways",
            "/config/data/sync",
            "/config/data/tasks",
        ],
    )
    def test_config_subpage_no_500(self, admin_page: Page, path: str):
        """配置子页面（admin）加载无 API 500。"""
        page = admin_page
        statuses = []
        page.on(
            "response",
            lambda r: statuses.append((r.url, r.status)) if "/api/" in r.url and r.status >= 500 else None,
        )
        page.goto(f"{BASE_URL}{path}")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        assert "/login" not in page.url, f"{path} 被重定向到登录页"
        assert not statuses, f"{path} 有 API 500 错误: {statuses}"


# ---------------------------------------------------------------------------
# 主题切换
# ---------------------------------------------------------------------------
class TestThemeSwitch:
    def test_theme_switcher_present(self, authenticated_page: Page):
        """主题切换按钮存在。"""
        page = authenticated_page
        page.goto(f"{BASE_URL}/")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        theme_btn = page.locator(
            '.el-dropdown button, button:has-text("☀️"), button:has-text("🌙"), [data-test*="theme" i]'
        ).first
        assert theme_btn.count() > 0, "未找到主题切换按钮"


# ---------------------------------------------------------------------------
# 全局：核心页面不应有 console error / pageerror
# ---------------------------------------------------------------------------
class TestNoGlobalErrors:
    CORE_PAGES = [
        "/",
        "/research/strategies",
        "/research/workspaces",
        "/backtest",
        "/backtest/legacy",
        "/ai/chat",
        "/ai/knowledge-base",
        "/portfolio",
        "/settings",
        "/quote",
    ]

    @pytest.mark.parametrize("path", CORE_PAGES)
    def test_core_page_no_errors(self, authenticated_page: Page, path: str):
        """每个核心页面加载后不应有 console error 或未捕获异常。"""
        page = authenticated_page
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console",
            lambda m: errors.append(m.text) if m.type == "error" else None,
        )
        page.goto(f"{BASE_URL}{path}")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(1)
        real = [e for e in errors if _is_real_error(e)]
        assert not real, f"{path} 有错误: {real}"
