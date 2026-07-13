"""
仪表盘页面 E2E 测试

针对重构后的 Vue3 前端仪表盘重写：
- 侧边栏由 capabilities.ts 数据驱动，顶级菜单为 首页/市场数据/投资研究/策略研究/交易运营/组合风控/知识库
- 仪表盘统计卡片标签不变（回测次数/策略数量/平均收益率/最佳夏普比率）
- 快捷操作按钮：运行回测 -> /research/workspaces，创建策略 -> /research/strategies，查询数据 -> /data/market
- 最近回测面板标题为"最近回测"，内容可能为表格或空状态
- 用户下拉菜单项：个人设置 / 退出登录
- /research 重定向到 /research/workspaces，/data 重定向到 /data/market
"""
import re
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def safe_wait(page: Page, timeout: int = 800) -> None:
    """安全等待：先尝试 networkidle（vite dev 可能超时），失败后固定等待。

    vite 开发服务器长连接会导致 networkidle 永不触发，
    因此用 try/except 包裹，再补一个固定等待确保渲染完成。
    """
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(timeout)


def wait_dashboard_ready(page: Page) -> None:
    """等待仪表盘核心元素渲染完成。"""
    try:
        page.wait_for_selector("#dashboard-overview-title", timeout=10000)
    except Exception:
        pass
    safe_wait(page)


def click_sidebar_item(page: Page, label: str) -> None:
    """点击桌面侧边栏中包含指定文案的菜单项。

    侧边栏菜单项由 capabilities.ts 的 visibleDomains 驱动，
    每一项渲染为 .sidebar-menu-item，内含 .sidebar-menu-label 文案。
    通过 has_text 过滤定位到目标菜单项。
    """
    locator = (
        page.locator(".app-sidebar-desktop .sidebar-menu-item")
        .filter(has_text=label)
    )
    expect(locator).to_be_visible(timeout=10000)
    locator.click()


class TestDashboard:
    """仪表盘测试"""

    # ──────────────────────────────────────────────────────────────────────
    # 1. 仪表盘加载
    # ──────────────────────────────────────────────────────────────────────

    def test_dashboard_loads(self, authenticated_page: Page):
        """测试仪表盘页面加载：URL 在根路径，工作台标题可见。"""
        page = authenticated_page
        wait_dashboard_ready(page)

        # 确认 URL 在前端根路径（宽松匹配，允许带不带末尾斜杠）
        expect(page).to_have_url(re.compile(r"localhost:3000"))

        # 仪表盘标题 h2#dashboard-overview-title 文案为"工作台"
        expect(page.locator("#dashboard-overview-title")).to_be_visible()

    # ──────────────────────────────────────────────────────────────────────
    # 2. 统计卡片
    # ──────────────────────────────────────────────────────────────────────

    def test_dashboard_stats_cards(self, authenticated_page: Page):
        """测试统计卡片显示：4 张卡片，标签为 回测次数/策略数量/平均收益率/最佳夏普比率。"""
        page = authenticated_page
        wait_dashboard_ready(page)

        # 等待 4 张统计卡片渲染（卡片始终渲染，数值异步加载）
        expect(page.locator(".dashboard-stat-card")).to_have_count(4, timeout=10000)

        # 逐个断言卡片标签可见（标签来自 i18n，静态渲染）
        for label in ("回测次数", "策略数量", "平均收益率", "最佳夏普比率"):
            expect(
                page.locator(".dashboard-stat-label").filter(has_text=label)
            ).to_be_visible()

    # ──────────────────────────────────────────────────────────────────────
    # 3. 快捷操作
    # ──────────────────────────────────────────────────────────────────────

    def test_dashboard_quick_actions(self, authenticated_page: Page):
        """测试快捷操作区域：快速开始标题 + 3 个操作卡片。"""
        page = authenticated_page
        wait_dashboard_ready(page)

        # "快速开始"面板标题
        expect(page.locator("text=快速开始").first).to_be_visible()

        # 3 个快捷操作卡片
        expect(page.locator(".dashboard-action-card")).to_have_count(3, timeout=10000)

        # 逐个断言操作按钮文案可见
        for label in ("运行回测", "创建策略", "查询数据"):
            expect(
                page.locator(".dashboard-action-card").filter(has_text=label)
            ).to_be_visible()

    # ──────────────────────────────────────────────────────────────────────
    # 4. 从仪表盘导航到回测
    # ──────────────────────────────────────────────────────────────────────

    def test_navigate_to_backtest_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘快捷操作跳转到回测工作区。

        "运行回测"按钮跳转到 /research/workspaces（回测工作区列表页），
        宽松断言 URL 包含 research。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        # 点击"运行回测"快捷操作卡片
        page.locator(".dashboard-action-card").filter(has_text="运行回测").click()
        safe_wait(page)

        # 验证跳转到回测工作区（/research/workspaces，宽松匹配 research）
        expect(page).to_have_url(re.compile(r"research"), timeout=10000)

    # ──────────────────────────────────────────────────────────────────────
    # 5. 从仪表盘导航到策略
    # ──────────────────────────────────────────────────────────────────────

    def test_navigate_to_strategy_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘快捷操作跳转到策略管理。

        "创建策略"按钮跳转到 /research/strategies，
        宽松断言 URL 包含 strategies。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        # 点击"创建策略"快捷操作卡片
        page.locator(".dashboard-action-card").filter(has_text="创建策略").click()
        safe_wait(page)

        # 验证跳转到策略管理页（/research/strategies）
        expect(page).to_have_url(re.compile(r"strategies"), timeout=10000)

    # ──────────────────────────────────────────────────────────────────────
    # 6. 最近回测区域
    # ──────────────────────────────────────────────────────────────────────

    def test_recent_backtests_section(self, authenticated_page: Page):
        """测试最近回测区域：标题"最近回测"和"查看全部"按钮可见。

        面板标题始终渲染，内容区域根据是否有回测数据显示表格或空状态。
        此处只断言标题和"查看全部"按钮，不依赖回测数据是否存在。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        # "最近回测"面板标题（可能匹配多个元素，用 .first）
        expect(page.locator("text=最近回测").first).to_be_visible()

        # "查看全部"链接按钮
        expect(page.locator("text=查看全部").first).to_be_visible()

    # ──────────────────────────────────────────────────────────────────────
    # 7. 侧边栏导航菜单可见性
    # ──────────────────────────────────────────────────────────────────────

    def test_sidebar_navigation(self, authenticated_page: Page):
        """测试侧边栏导航菜单标签可见。

        侧边栏由 capabilities.ts 的 productDomains 驱动，
        顶级菜单（非管理员）：首页/市场数据/投资研究/策略研究/交易运营/组合风控/知识库。
        仅断言确认存在的标签，每个用 .first 避免 strict mode 冲突。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        # 确认侧边栏菜单容器存在
        expect(page.locator(".app-sidebar-desktop .sidebar-menu")).to_be_visible()

        # 断言关键菜单项可见
        for label in ("首页", "市场数据", "投资研究", "策略研究", "交易运营", "组合风控", "知识库"):
            expect(page.locator("text=" + label).first).to_be_visible()

    # ──────────────────────────────────────────────────────────────────────
    # 8. 侧边栏导航：回测工作区
    # ──────────────────────────────────────────────────────────────────────

    def test_sidebar_navigate_to_backtest(self, authenticated_page: Page):
        """测试侧边栏导航到回测工作区。

        回测功能已并入"策略研究"域，点击"策略研究"侧边栏菜单
        会重定向到 /research/workspaces（回测工作区列表页）。
        宽松断言 URL 包含 research。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        click_sidebar_item(page, "策略研究")
        safe_wait(page)

        # /research 重定向到 /research/workspaces
        expect(page).to_have_url(re.compile(r"research"), timeout=10000)

    # ──────────────────────────────────────────────────────────────────────
    # 9. 侧边栏导航：策略管理
    # ──────────────────────────────────────────────────────────────────────

    def test_sidebar_navigate_to_strategy(self, authenticated_page: Page):
        """测试侧边栏导航到策略管理页。

        "策略管理"现在是"策略研究"域下的子导航项（/research/strategies），
        不再是顶级侧边栏菜单。因此先点击侧边栏"策略研究"进入研究域，
        再点击页头子导航"策略管理"跳转到 /research/strategies。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        # 第一步：点击侧边栏"策略研究"，进入研究域（重定向到 /research/workspaces）
        click_sidebar_item(page, "策略研究")
        safe_wait(page)

        # 第二步：等待页头子导航"策略管理"出现并点击
        subnav = page.locator(".domain-subnav-item").filter(has_text="策略管理")
        expect(subnav).to_be_visible(timeout=10000)
        subnav.click()
        safe_wait(page)

        # 验证跳转到策略管理页（/research/strategies）
        expect(page).to_have_url(re.compile(r"strategies"), timeout=10000)

    # ──────────────────────────────────────────────────────────────────────
    # 10. 侧边栏导航：市场数据
    # ──────────────────────────────────────────────────────────────────────

    def test_sidebar_navigate_to_data(self, authenticated_page: Page):
        """测试侧边栏导航到市场数据页。

        点击"市场数据"侧边栏菜单，/data 重定向到 /data/market。
        宽松断言 URL 包含 data。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        click_sidebar_item(page, "市场数据")
        safe_wait(page)

        # /data 重定向到 /data/market
        expect(page).to_have_url(re.compile(r"data"), timeout=10000)

    # ──────────────────────────────────────────────────────────────────────
    # 11. 导航到设置页
    # ──────────────────────────────────────────────────────────────────────

    def test_sidebar_navigate_to_settings(self, authenticated_page: Page):
        """测试导航到设置页。

        重构后"系统设置"不再是侧边栏顶级菜单（侧边栏的"配置中心"仅管理员可见）。
        设置页入口移至用户下拉菜单的"个人设置"项，点击后跳转到 /settings。
        """
        page = authenticated_page
        wait_dashboard_ready(page)

        # 打开用户下拉菜单
        page.locator(".user-dropdown-trigger").click()

        # 等待"个人设置"菜单项出现并点击
        profile_item = page.locator(".el-dropdown-menu__item").filter(has_text="个人设置")
        expect(profile_item).to_be_visible(timeout=5000)
        profile_item.click()
        safe_wait(page)

        # 验证跳转到设置页（/settings）
        expect(page).to_have_url(re.compile(r"settings"), timeout=10000)

    # ──────────────────────────────────────────────────────────────────────
    # 12. 用户下拉菜单
    # ──────────────────────────────────────────────────────────────────────

    def test_user_dropdown(self, authenticated_page: Page):
        """测试用户下拉菜单：打开后包含"个人设置"和"退出登录"。"""
        page = authenticated_page
        wait_dashboard_ready(page)

        # 点击用户下拉触发器打开菜单
        page.locator(".user-dropdown-trigger").click()

        # 断言下拉菜单项可见
        expect(
            page.locator(".el-dropdown-menu__item").filter(has_text="个人设置")
        ).to_be_visible(timeout=5000)
        expect(
            page.locator(".el-dropdown-menu__item").filter(has_text="退出登录")
        ).to_be_visible(timeout=5000)

    # ──────────────────────────────────────────────────────────────────────
    # 13. 退出登录
    # ──────────────────────────────────────────────────────────────────────

    def test_logout(self, authenticated_page: Page):
        """测试退出登录：打开下拉 -> 点击退出登录 -> 跳转到 /login。"""
        page = authenticated_page
        wait_dashboard_ready(page)

        # 打开用户下拉菜单
        page.locator(".user-dropdown-trigger").click()

        # 等待"退出登录"菜单项出现并点击
        logout_item = page.locator(".el-dropdown-menu__item").filter(has_text="退出登录")
        expect(logout_item).to_be_visible(timeout=5000)
        logout_item.click()

        # 验证跳转到登录页（宽松匹配 /login，给予充足超时）
        expect(page).to_have_url(re.compile(r"/login"), timeout=10000)
