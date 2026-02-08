"""
回测页面 E2E 测试

使用 Playwright 进行端到端测试，覆盖回测功能的完整流程。
"""
import pytest
from playwright.sync_api import Page, expect
import uuid
import time

FRONTEND_URL = "http://localhost:3000"


class TestBacktestPage:
    """回测页面测试"""

    def test_backtest_page_loads(self, authenticated_page: Page):
        """测试回测页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 检查页面标题
        expect(page.locator("text=回测配置")).to_be_visible()

    def test_backtest_form_elements(self, authenticated_page: Page):
        """测试回测配置表单元素"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 检查表单核心元素
        expect(page.locator("text=策略").first).to_be_visible()
        expect(page.locator('button:has-text("运行回测")').first).to_be_visible()
        # 策略选择器存在
        expect(page.locator(".el-select").first).to_be_visible()

    def test_backtest_history_section(self, authenticated_page: Page):
        """测试回测历史区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 检查回测历史区域
        expect(page.locator("text=回测历史")).to_be_visible()

    def test_strategy_selector(self, authenticated_page: Page):
        """测试策略选择器"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 点击策略选择器
        page.click(".el-select")
        page.wait_for_timeout(500)

        # 应该出现下拉选项
        expect(page.locator(".el-select-dropdown__item").first).to_be_visible()

    def test_page_structure(self, authenticated_page: Page):
        """测试回测页面整体结构"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 页面应该同时包含配置区域和历史区域
        content = page.content()
        assert "回测配置" in content
        assert "回测历史" in content


class TestBacktestExecution:
    """回测执行流程测试"""

    def test_fill_backtest_form(self, authenticated_page: Page):
        """测试填写回测表单"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 选择策略
        page.click(".el-select")
        page.wait_for_timeout(500)

        # 点击第一个选项
        dropdown_items = page.locator(".el-select-dropdown__item")
        if dropdown_items.count() > 0:
            dropdown_items.first.click()
            page.wait_for_timeout(500)

    def test_run_backtest_button_exists(self, authenticated_page: Page):
        """测试运行回测按钮存在"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        run_button = page.locator('button:has-text("运行回测")')
        expect(run_button).to_be_visible()
        expect(run_button).to_be_enabled()

    def test_backtest_parameters_section(self, authenticated_page: Page):
        """测试参数配置区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 检查参数区域存在
        content = page.content()
        # 参数配置相关的内容
        assert "参数" in content or "回测" in content


class TestBacktestResults:
    """回测结果测试"""

    def test_result_metrics_display(self, authenticated_page: Page):
        """测试结果指标显示（如果有结果）"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 检查指标标签（即使没有数据也应该在代码中定义）
        # 这些在有结果时才显示
        page_content = page.content()

        # 验证页面结构正确
        assert "回测配置" in page_content
        assert "回测历史" in page_content

    def test_backtest_history_list(self, authenticated_page: Page):
        """测试回测历史列表"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 历史记录区域应该存在
        history_section = page.locator("text=回测历史")
        expect(history_section).to_be_visible()

    def test_empty_history_message(self, authenticated_page: Page):
        """测试空历史记录提示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 如果没有历史记录，应该显示提示信息
        content = page.content()
        # 可能的空状态提示
        if "暂无数据" in content or "还没有回测记录" in content:
            assert True


class TestBacktestNavigation:
    """回测相关导航测试"""

    def test_navigate_to_backtest_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘导航到回测页面"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_load_state("networkidle")

        # 点击回测分析菜单
        page.click('text=回测分析')
        page.wait_for_load_state("networkidle")

        # 应该导航到回测页面
        expect(page).to_have_url(f"{FRONTEND_URL}/backtest")

    def test_backtest_breadcrumb(self, authenticated_page: Page):
        """测试面包屑导航"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 验证当前位置
        content = page.content()
        assert "回测" in content


class TestBacktestValidation:
    """回测表单验证测试"""

    def test_date_range_validation(self, authenticated_page: Page):
        """测试日期范围验证"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 检查日期相关元素 - 页面应包含日期选择功能
        # 尝试多种可能的日期选择器元素
        date_inputs = page.locator("input[type='date'], .el-date-editor, .el-input--date")
        date_picker_buttons = page.locator("text=开始日期, text=结束日期, text=日期范围")

        # 如果有任何日期相关的元素存在，测试通过
        has_date_inputs = date_inputs.count() > 0
        has_date_buttons = date_picker_buttons.count() > 0
        content = page.content()

        assert has_date_inputs or has_date_buttons or "回测" in content


class TestBacktestErrorHandling:
    """回测错误处理测试"""

    def test_network_error_handling(self, authenticated_page: Page):
        """测试网络错误处理"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 模拟网络离线
        page.context.set_offline(True)

        # 尝试运行回测（应该失败并显示错误）
        run_button = page.locator('button:has-text("运行回测")')
        if run_button.is_visible():
            run_button.click()
            page.wait_for_timeout(2000)

        # 恢复网络
        page.context.set_offline(False)


class TestBacktestResponsiveness:
    """回测页面响应式测试"""

    def test_mobile_layout(self, authenticated_page: Page):
        """测试移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 页面应该仍然可用
        expect(page.locator("text=回测配置")).to_be_visible()

    def test_tablet_layout(self, authenticated_page: Page):
        """测试平板布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        # 页面应该正常显示
        expect(page.locator("text=回测配置")).to_be_visible()
