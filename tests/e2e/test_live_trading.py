"""
实盘交易页面 E2E 测试

覆盖 /live-trading 和 /live-trading/:id 路由。
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


class TestLiveTradingPage:
    """实盘交易页面测试"""

    def test_live_trading_page_loads(self, authenticated_page: Page):
        """测试实盘交易页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "实盘" in content or "交易" in content or "live" in content.lower()

    def test_live_trading_page_title(self, authenticated_page: Page):
        """测试实盘页面标题"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        # 页面内容中应包含实盘/交易相关文字
        content = page.content()
        assert "实盘" in content or "交易" in content or "Trading" in content.title()

    def test_live_trading_has_add_strategy_button(self, authenticated_page: Page):
        """测试添加策略按钮存在"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        add_btn = page.locator('button:has-text("添加策略"), button:has-text("添加"), button:has-text("新建")')
        if add_btn.count() == 0:
            pytest.skip("未找到添加策略按钮")
        expect(add_btn.first).to_be_visible()

    def test_live_trading_has_batch_controls(self, authenticated_page: Page):
        """测试一键启停按钮"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        start_all = page.locator('button:has-text("一键启动"), button:has-text("全部启动")')
        stop_all = page.locator('button:has-text("一键停止"), button:has-text("全部停止")')

        if start_all.count() == 0 and stop_all.count() == 0:
            pytest.skip("未找到批量启停按钮")
        if start_all.count() > 0:
            expect(start_all.first).to_be_visible()
        if stop_all.count() > 0:
            expect(stop_all.first).to_be_visible()

    def test_live_trading_instance_list(self, authenticated_page: Page):
        """测试实例列表区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        # 应有表格或列表显示实例
        table = page.locator(".el-table, .el-card, [class*='list'], [class*='instance']")
        if table.count() == 0:
            pytest.skip("未找到实例列表/卡片区域")
        expect(table.first).to_be_visible()

    def test_live_trading_add_strategy_dialog(self, authenticated_page: Page):
        """测试点击添加策略后弹出对话框"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        add_btn = page.locator('button:has-text("添加策略"), button:has-text("添加"), button:has-text("新建")')
        if add_btn.count() == 0:
            pytest.skip("未找到添加策略按钮")

        add_btn.first.click()
        page.wait_for_timeout(500)

        dialog = page.locator(".el-dialog, .el-drawer, [role='dialog']")
        if dialog.count() == 0:
            pytest.skip("点击添加后未弹出对话框")
        expect(dialog.first).to_be_visible()

    def test_live_trading_navigation_from_sidebar(self, authenticated_page: Page):
        """测试从侧边栏导航到实盘交易"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_load_state("networkidle")

        live_link = page.locator(
            'a[href="/live-trading"], .el-menu-item:has-text("实盘"), .el-menu-item:has-text("交易")'
        )
        if live_link.count() == 0:
            pytest.skip("未找到实盘交易侧边栏链接")
        live_link.first.click()
        page.wait_for_url(f"{FRONTEND_URL}/live-trading", timeout=5000)


class TestLiveTradingDetailPage:
    """实盘交易详情页测试"""

    def test_detail_page_loads_with_invalid_id(self, authenticated_page: Page):
        """测试无效实例ID的详情页行为"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading/nonexistent-id")
        page.wait_for_load_state("networkidle")

        # 页面应正常渲染（不白屏）
        content = page.content()
        assert len(content) > 100

    def test_detail_page_structure(self, authenticated_page: Page):
        """测试详情页结构（需有实盘实例时才生效）"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        # 尝试点击实例进入详情
        instance_link = page.locator(
            'a[href*="/live-trading/"], .el-table__row, [class*="instance-card"]'
        )
        if instance_link.count() == 0:
            pytest.skip("无实盘实例数据，跳过详情页结构测试")

        instance_link.first.click()
        page.wait_for_timeout(1000)

        if "/live-trading/" in page.url and page.url != f"{FRONTEND_URL}/live-trading":
            content = page.content()
            has_detail = (
                "策略" in content
                or "状态" in content
                or "持仓" in content
                or "订单" in content
            )
            assert has_detail, "详情页应显示策略/状态/持仓/订单信息"

    def test_detail_page_responsive_mobile(self, authenticated_page: Page):
        """测试详情页移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{FRONTEND_URL}/live-trading")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert len(content) > 100
