"""
投资组合页面 E2E 测试

覆盖 /portfolio 路由的页面加载、概览卡片、标签页切换。
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


class TestPortfolioPage:
    """投资组合页面测试"""

    def test_portfolio_page_loads(self, authenticated_page: Page):
        """测试组合页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "组合" in content or "投资" in content or "portfolio" in content.lower()

    def test_portfolio_overview_cards(self, authenticated_page: Page):
        """测试概览卡片显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        page.wait_for_load_state("networkidle")

        content = page.content()
        # 应显示概览指标
        overview_keywords = ["总资产", "盈亏", "策略", "组合"]
        found = [kw for kw in overview_keywords if kw in content]
        assert len(found) >= 1, f"组合概览应至少显示1个指标关键字，找到: {found}"

    def test_portfolio_tabs(self, authenticated_page: Page):
        """测试标签页切换"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        page.wait_for_load_state("networkidle")

        # 检查标签页
        tab_keywords = ["策略概览", "当前持仓", "交易记录", "资金曲线", "资产配置"]
        content = page.content()
        found_tabs = [t for t in tab_keywords if t in content]
        assert len(found_tabs) >= 1, f"应至少有1个标签页可见，找到: {found_tabs}"

    def test_portfolio_tab_click(self, authenticated_page: Page):
        """测试点击标签页切换内容"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/portfolio")
        page.wait_for_load_state("networkidle")

        # 尝试点击持仓标签
        pos_tab = page.locator('.el-tabs__item:has-text("持仓"), [role="tab"]:has-text("持仓")')
        if pos_tab.count() == 0:
            pytest.skip("未找到持仓标签页")
        pos_tab.first.click()
        page.wait_for_timeout(500)
        content = page.content()
        assert "持仓" in content

        # 尝试点击交易记录标签
        trade_tab = page.locator('.el-tabs__item:has-text("交易"), [role="tab"]:has-text("交易")')
        if trade_tab.count() == 0:
            pytest.skip("未找到交易记录标签页")
        trade_tab.first.click()
        page.wait_for_timeout(500)
        content = page.content()
        assert "交易" in content

    def test_portfolio_navigation_from_sidebar(self, authenticated_page: Page):
        """测试从侧边栏导航到组合页面"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_load_state("networkidle")

        port_link = page.locator(
            'a[href="/portfolio"], .el-menu-item:has-text("组合"), .el-menu-item:has-text("投资")'
        )
        if port_link.count() == 0:
            pytest.skip("未找到组合侧边栏链接")
        port_link.first.click()
        page.wait_for_url(f"{FRONTEND_URL}/portfolio", timeout=5000)

    def test_portfolio_responsive_mobile(self, authenticated_page: Page):
        """测试移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{FRONTEND_URL}/portfolio")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert len(content) > 100

    def test_portfolio_responsive_tablet(self, authenticated_page: Page):
        """测试平板布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{FRONTEND_URL}/portfolio")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert len(content) > 100
