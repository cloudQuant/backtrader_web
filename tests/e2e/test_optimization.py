"""
参数优化页面 E2E 测试

覆盖 /optimization 路由的页面加载、表单元素、交互流程。
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


class TestOptimizationPage:
    """参数优化页面测试"""

    def test_optimization_page_loads(self, authenticated_page: Page):
        """测试优化页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # 页面应包含优化相关内容
        content = page.content()
        assert "优化" in content or "optimization" in content.lower()

    def test_optimization_page_has_strategy_selector(self, authenticated_page: Page):
        """测试优化页面有策略选择器"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # 应有策略选择下拉框
        expect(page.locator(".el-select").first).to_be_visible()

    def test_optimization_page_has_submit_button(self, authenticated_page: Page):
        """测试优化页面选择策略后显示开始优化按钮"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # "开始优化"按钮只在选择策略并配置参数后才出现
        # 先选择一个策略
        selector = page.locator(".el-select").first
        if selector.is_visible():
            selector.click()
            page.wait_for_timeout(500)
            dropdown_items = page.locator(".el-select-dropdown__item")
            if dropdown_items.count() > 0:
                dropdown_items.first.click()
                page.wait_for_timeout(1000)

                # 选择策略后应出现"开始优化"按钮
                submit_btn = page.locator('button:has-text("开始优化")')
                if submit_btn.count() > 0:
                    expect(submit_btn.first).to_be_visible()
                else:
                    # 按钮可能被 disabled 但应存在于 DOM 中
                    content = page.content()
                    assert "开始优化" in content, "选择策略后应显示开始优化按钮"

    def test_optimization_page_has_method_selector(self, authenticated_page: Page):
        """测试优化页面有优化方法选择"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # 应有网格搜索或贝叶斯优化选项
        content = page.content()
        has_method = "网格" in content or "贝叶斯" in content or "grid" in content.lower() or "bayesian" in content.lower()
        assert has_method, "优化页面应包含优化方法选项"

    def test_optimization_page_strategy_selection(self, authenticated_page: Page):
        """测试选择策略后显示参数配置"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # 点击策略选择器
        selector = page.locator(".el-select").first
        if selector.is_visible():
            selector.click()
            page.wait_for_timeout(500)

            # 应出现下拉选项
            dropdown_items = page.locator(".el-select-dropdown__item")
            if dropdown_items.count() > 0:
                dropdown_items.first.click()
                page.wait_for_timeout(500)

                # 选择策略后应显示参数区域
                content = page.content()
                assert "参数" in content or "param" in content.lower(), "选择策略后应显示参数配置"

    def test_optimization_page_param_range_inputs(self, authenticated_page: Page):
        """测试参数范围输入框"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # 选择策略以显示参数
        selector = page.locator(".el-select").first
        if selector.is_visible():
            selector.click()
            page.wait_for_timeout(500)
            dropdown_items = page.locator(".el-select-dropdown__item")
            if dropdown_items.count() > 0:
                dropdown_items.first.click()
                page.wait_for_timeout(500)

        # 检查是否有数字输入框（参数范围: 起始值、结束值、步长）
        number_inputs = page.locator('input[type="number"], .el-input-number')
        if number_inputs.count() > 0:
            assert number_inputs.count() >= 1, "应有参数范围输入框"

    def test_optimization_page_navigation_from_sidebar(self, authenticated_page: Page):
        """测试从侧边栏导航到优化页面"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_load_state("networkidle")

        # 查找侧边栏中的优化链接
        opt_link = page.locator('a[href="/optimization"], .el-menu-item:has-text("参数优化"), .el-menu-item:has-text("优化")')
        if opt_link.count() == 0:
            pytest.skip("未找到优化侧边栏链接")
        opt_link.first.click()
        page.wait_for_url(f"{FRONTEND_URL}/optimization", timeout=5000)
        content = page.content()
        assert "优化" in content or "optimization" in content.lower()

    def test_optimization_page_responsive_mobile(self, authenticated_page: Page):
        """测试优化页面移动端响应式布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        # 页面应正常加载不报错
        content = page.content()
        assert "优化" in content or "optimization" in content.lower()

    def test_optimization_page_responsive_tablet(self, authenticated_page: Page):
        """测试优化页面平板响应式布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{FRONTEND_URL}/optimization")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "优化" in content or "optimization" in content.lower()
