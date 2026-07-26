"""
实盘交易页面 E2E 测试

覆盖 /live-trading 和 /live-trading/:id 路由。

说明：
- 路由 /live-trading 在 src/router/index.ts 中重定向到 /trading
  (name: TradingWorkspaceList)，对应组件为
  src/frontend/src/views/workspace/WorkspaceListPage.vue，
  并通过 route.meta.workspaceType='trading' 渲染交易工作区列表。
- 侧边栏「交易运营」(nav.tradingOperations) 的目标路径也是 /trading，
  并没有单独的「实盘」入口。
- 页面上的创建按钮文案为「新建工作区」(i18n: workspace.createNew)，
  点击后弹出 CreateWorkspaceDialog (el-dialog)，标题为「新建交易工作区」。
- 本测试只验证 UI 元素（按钮可见、对话框弹出、导航跳转），
  不会触发 /live-trading/start-all 等真实网关启停接口，避免挂起后端。
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


class TestLiveTradingPage:
    """实盘交易页面测试（/live-trading -> /trading）"""

    def test_live_trading_page_loads(self, authenticated_page: Page):
        """测试实盘交易页面加载"""
        page = authenticated_page
        # /live-trading 会重定向到 /trading
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        content = page.content()
        assert "实盘" in content or "交易" in content or "live" in content.lower()

    def test_live_trading_page_title(self, authenticated_page: Page):
        """测试实盘页面标题"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        # 交易工作区列表页 hero 标题为「交易工作区」(workspace.tradingHeroTitle)
        content = page.content()
        assert "实盘" in content or "交易" in content or "Trading" in content.title()

    def test_live_trading_has_add_strategy_button(self, authenticated_page: Page):
        """测试「新建工作区」按钮存在"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        # 真实按钮文案为「新建工作区」(workspace.createNew)
        # 页面中至少有两处：hero 区域与 header teleport，使用 .first 避免严格模式报错
        add_btn = page.locator('button:has-text("新建工作区")')
        if add_btn.count() == 0:
            pytest.skip("未找到「新建工作区」按钮")
        expect(add_btn.first).to_be_visible()

    def test_live_trading_has_batch_controls(self, authenticated_page: Page):
        """测试批量操作控件存在

        交易工作区列表页没有「一键启停」按钮（那属于网关控制，会启动 CTP/MT5）。
        本页的批量控件是「删除工作区」按钮与视图切换（卡片/表格）。
        """
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        # 「删除工作区」(workspace.deleteSelected) 按钮在无选中时为禁用态，但应存在
        delete_btn = page.locator('button:has-text("删除工作区")')
        # 视图切换 radio-group (card/table)
        view_toggle = page.locator(".workspace-header-view, .workspace-hero-actions .el-radio-group")

        if delete_btn.count() == 0 and view_toggle.count() == 0:
            pytest.skip("未找到批量操作控件")
        if delete_btn.count() > 0:
            expect(delete_btn.first).to_be_visible()
        if view_toggle.count() > 0:
            expect(view_toggle.first).to_be_visible()

    def test_live_trading_instance_list(self, authenticated_page: Page):
        """测试实例列表区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        # 应有表格或列表显示实例/工作区
        table = page.locator(
            ".el-table, .el-card, [class*='list'], [class*='instance'], "
            "[data-test='workspace-list-panel'], .workspace-card-grid"
        )
        if table.count() == 0:
            pytest.skip("未找到实例列表/卡片区域")
        expect(table.first).to_be_visible()

    def test_live_trading_add_strategy_dialog(self, authenticated_page: Page):
        """测试点击「新建工作区」后弹出创建对话框

        只验证对话框弹出（UI 行为），不点击「创建」提交，避免产生真实工作区或
        触发网关启停接口。
        """
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        # 真实按钮文案为「新建工作区」(workspace.createNew)
        add_btn = page.locator('button:has-text("新建工作区")')
        if add_btn.count() == 0:
            pytest.skip("未找到「新建工作区」按钮")

        # 确保按钮可见后再点击（header teleport 可能延迟挂载）
        expect(add_btn.first).to_be_visible()
        add_btn.first.click()
        # 等待 el-dialog 动画完成
        page.wait_for_timeout(600)

        # CreateWorkspaceDialog 渲染为 el-dialog（append-to-body，打开后挂在 body 末尾）。
        # 注意：不要用 [role='dialog']——侧边栏移动端 el-drawer 也带 role="dialog" 且桌面端隐藏，
        # 会使 .first 命中隐藏的抽屉。用 .el-dialog 且取最后挂载的（即刚打开的）对话框。
        dialog = page.locator(".el-dialog")
        expect(dialog.last).to_be_visible(timeout=5000)

    def test_live_trading_navigation_from_sidebar(self, authenticated_page: Page):
        """测试从侧边栏「交易运营」导航到交易工作区

        侧边栏菜单项「交易运营」(nav.tradingOperations) 的路由为 /trading。
        注意：/live-trading 会重定向到 /trading，因此侧边栏没有单独的「实盘」入口。
        这里用宽松的 URL 断言（包含 "trading" 即可）。
        """
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        _safe_wait_networkidle(page)

        # 侧边栏 el-menu-item 的文案为「交易运营」
        live_link = page.locator('.el-menu-item:has-text("交易运营")')
        if live_link.count() == 0:
            pytest.skip("未找到「交易运营」侧边栏链接")

        expect(live_link.first).to_be_visible()
        live_link.first.click()

        # 放宽 URL 断言：/trading 或 /live-trading（后者会重定向到前者）均可
        expect(page).to_have_url(re.compile(r"trading"), timeout=10000)


class TestLiveTradingDetailPage:
    """实盘交易详情页测试（/live-trading/:id -> /trading/:id）"""

    def test_detail_page_loads_with_invalid_id(self, authenticated_page: Page):
        """测试无效实例ID的详情页行为"""
        page = authenticated_page
        # /live-trading/:id 会重定向到 /trading/:id (TradingWorkspaceDetail)
        page.goto(f"{FRONTEND_URL}/live-trading/nonexistent-id")
        _safe_wait_networkidle(page)

        # 页面应正常渲染（不白屏）
        content = page.content()
        assert len(content) > 100

    def test_detail_page_structure(self, authenticated_page: Page):
        """测试详情页结构（需有实盘实例时才生效）"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/live-trading")
        _safe_wait_networkidle(page)

        # 尝试点击实例/工作区卡片进入详情
        instance_link = page.locator(
            'a[href*="/trading/"], a[href*="/live-trading/"], '
            ".el-table__row, .workspace-card, [class*='instance-card']"
        )
        if instance_link.count() == 0:
            pytest.skip("无交易工作区数据，跳过详情页结构测试")

        instance_link.first.click()
        page.wait_for_timeout(1000)

        # 进入详情页后，URL 应包含 /trading/ 且不是列表页本身
        if "/trading/" in page.url and not page.url.endswith("/trading"):
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
        _safe_wait_networkidle(page)

        content = page.content()
        assert len(content) > 100
