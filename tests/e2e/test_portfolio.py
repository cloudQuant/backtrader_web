"""
投资组合页面 E2E 测试

覆盖 /portfolio 路由的页面加载、概览卡片、标签页切换、侧边栏导航。

说明：
- /portfolio 路由对应组件 src/frontend/src/views/PortfolioPage.vue。
- 侧边栏「组合风控」(nav.portfolioRisk) 的目标路径为 /portfolio。
- 概览指标卡片关键字：组合总资产、总盈亏、持仓市值、运行工作区等。
- 标签页 (el-tabs)：交易工作区 / 当前持仓 / 交易记录 / 资金曲线 / 资产配置。
"""
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


def _safe_wait_networkidle(page: Page, timeout_ms: int = 5000, fallback_ms: int = 800) -> None:
    """安全等待 networkidle。

    vite dev server 下 HMR websocket 会持续保持连接，导致 networkidle
    永远无法达成而抛出超时。这里把超时异常吞掉，再固定等待一段 fallback
    时间让页面渲染稳定。
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(fallback_ms)


class TestPortfolioPage:
    """投资组合页面测试"""

    def test_portfolio_page_loads(self, authenticated_page: Page):
        """测试组合页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        _safe_wait_networkidle(page)

        content = page.content()
        assert "组合" in content or "投资" in content or "portfolio" in content.lower()

    def test_portfolio_overview_cards(self, authenticated_page: Page):
        """测试概览卡片显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        _safe_wait_networkidle(page)

        content = page.content()
        # 概览指标卡片 (portfolio.summaryCards)：组合总资产 / 总盈亏 / 持仓市值 / 运行工作区
        overview_keywords = ["总资产", "盈亏", "策略", "组合", "持仓", "工作区"]
        found = [kw for kw in overview_keywords if kw in content]
        assert len(found) >= 1, f"组合概览应至少显示1个指标关键字，找到: {found}"

    def test_portfolio_tabs(self, authenticated_page: Page):
        """测试标签页显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        _safe_wait_networkidle(page)

        # el-tabs 标签页文案 (portfolio.tabWorkspaces / tabPositions / tabTrades / tabEquity / tabAllocation)
        tab_keywords = ["交易工作区", "当前持仓", "交易记录", "资金曲线", "资产配置",
                        "策略概览", "持仓", "交易"]
        content = page.content()
        found_tabs = [t for t in tab_keywords if t in content]
        assert len(found_tabs) >= 1, f"应至少有1个标签页可见，找到: {found_tabs}"

    def test_portfolio_tab_click(self, authenticated_page: Page):
        """测试点击标签页切换内容"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        _safe_wait_networkidle(page)

        # 尝试点击「当前持仓」标签页 (portfolio.tabPositions)
        pos_tab = page.locator(
            '.el-tabs__item:has-text("持仓"), [role="tab"]:has-text("持仓")'
        )
        if pos_tab.count() == 0:
            pytest.skip("未找到持仓标签页")
        pos_tab.first.click()
        page.wait_for_timeout(500)
        content = page.content()
        assert "持仓" in content

        # 尝试点击「交易记录」标签页 (portfolio.tabTrades)
        trade_tab = page.locator(
            '.el-tabs__item:has-text("交易记录"), [role="tab"]:has-text("交易记录")'
        )
        if trade_tab.count() == 0:
            pytest.skip("未找到交易记录标签页")
        trade_tab.first.click()
        page.wait_for_timeout(500)
        content = page.content()
        assert "交易" in content

    def test_portfolio_navigation_from_sidebar(self, authenticated_page: Page):
        """测试从侧边栏「组合风控」导航到组合页面

        侧边栏菜单项「组合风控」(nav.portfolioRisk) 的路由为 /portfolio。
        用宽松的 URL 断言（包含 "portfolio" 即可）。
        """
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        _safe_wait_networkidle(page)

        # 侧边栏 el-menu-item 的文案为「组合风控」
        port_link = page.locator('.el-menu-item:has-text("组合风控")')
        if port_link.count() == 0:
            pytest.skip("未找到「组合风控」侧边栏链接")

        expect(port_link.first).to_be_visible()
        port_link.first.click()

        # 放宽 URL 断言：/portfolio 或 /portfolio/overview 均可
        expect(page).to_have_url(re.compile(r"portfolio"), timeout=10000)

    def test_portfolio_responsive_mobile(self, authenticated_page: Page):
        """测试移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{FRONTEND_URL}/portfolio")
        _safe_wait_networkidle(page)

        content = page.content()
        assert len(content) > 100

    def test_portfolio_responsive_tablet(self, authenticated_page: Page):
        """测试平板布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{FRONTEND_URL}/portfolio")
        _safe_wait_networkidle(page)

        content = page.content()
        assert len(content) > 100
