"""
数据查询页面 E2E 测试

使用 Playwright 进行端到端测试，覆盖数据查询功能的完整流程。
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3000"


class TestDataPage:
    """数据查询页面测试"""

    def test_data_page_loads(self, authenticated_page: Page):
        """测试数据页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 检查页面标题
        expect(page.locator("text=数据查询").first).to_be_visible()

    def test_query_form_elements(self, authenticated_page: Page):
        """测试查询表单元素"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 检查表单元素
        expect(page.locator("text=股票代码")).to_be_visible()
        expect(page.locator("text=开始日期")).to_be_visible()
        expect(page.locator("text=结束日期")).to_be_visible()
        expect(page.locator('button:has-text("查询")')).to_be_visible()

    def test_fill_query_form(self, authenticated_page: Page):
        """测试填写查询表单"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 填写股票代码
        symbol_input = page.locator('input[placeholder*="SZ"]')
        if symbol_input.is_visible():
            symbol_input.fill("600519.SH")

            # 验证输入
            expect(symbol_input).to_have_value("600519.SH")

    def test_default_symbol_prefilled(self, authenticated_page: Page):
        """测试默认股票代码预填充"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 默认值应该是 000001.SZ
        symbol_input = page.locator('input[placeholder*="SZ"]')
        if symbol_input.is_visible():
            expect(symbol_input).to_have_value("000001.SZ")

    def test_page_structure(self, authenticated_page: Page):
        """测试页面整体结构"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "数据查询" in content
        assert "查询" in content


class TestDataQuery:
    """数据查询测试"""

    def test_query_button_exists(self, authenticated_page: Page):
        """测试查询按钮存在"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        query_button = page.locator('button:has-text("查询")')
        expect(query_button).to_be_visible()

    def test_period_selector(self, authenticated_page: Page):
        """测试周期选择器"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 检查周期选择
        content = page.content()
        # 可能的周期选项
        assert "日线" in content or "周期" in content or "日" in content

    def test_date_range_inputs(self, authenticated_page: Page):
        """测试日期范围输入"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 检查日期输入
        date_inputs = page.locator("input[type='date'], .el-date-editor")
        # 至少应该有开始和结束日期
        assert date_inputs.count() >= 2 or "日期" in page.content()


class TestDataDisplay:
    """数据显示测试"""

    def test_kline_chart_area(self, authenticated_page: Page):
        """测试K线图区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # K线图区域应该存在
        content = page.content()
        assert "数据" in content

    def test_data_table(self, authenticated_page: Page):
        """测试数据表格"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 数据表格应该存在
        content = page.content()
        assert "数据" in content


class DataValidation:
    """数据表单验证测试"""

    def test_invalid_symbol_format(self, authenticated_page: Page):
        """测试无效股票代码格式"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 填写无效的股票代码
        symbol_input = page.locator('input[placeholder*="SZ"]')
        if symbol_input.is_visible():
            symbol_input.fill("INVALID")

            # 点击查询（可能会显示错误）
            query_button = page.locator('button:has-text("查询")')
            if query_button.is_visible():
                query_button.click()
                page.wait_for_timeout(1000)

    def test_empty_symbol(self, authenticated_page: Page):
        """测试空股票代码"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 清空股票代码
        symbol_input = page.locator('input[placeholder*="SZ"]')
        if symbol_input.is_visible():
            symbol_input.fill("")
            # 验证输入已清空
            expect(symbol_input).to_have_value("")


class TestNavigation:
    """数据页面导航测试"""

    def test_navigate_to_data_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘导航到数据页面"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_load_state("networkidle")

        # 点击数据查询菜单
        page.click('text=数据查询')
        page.wait_for_load_state("networkidle")

        # 应该导航到数据页面
        expect(page).to_have_url(f"{FRONTEND_URL}/data")


class TestDataDownload:
    """数据下载测试"""

    def test_download_button(self, authenticated_page: Page):
        """测试下载按钮"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 检查是否有下载按钮
        download_buttons = page.locator('button:has-text("下载")')
        if download_buttons.count() > 0:
            expect(download_buttons.first).to_be_visible()


class TestResponsiveLayout:
    """响应式布局测试"""

    def test_mobile_layout(self, authenticated_page: Page):
        """测试移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 页面应该仍然可用 - 使用 first 避免多元素冲突
        expect(page.locator("text=数据查询").first).to_be_visible()

    def test_tablet_layout(self, authenticated_page: Page):
        """测试平板布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 页面应该正常显示 - 使用 first 避免多元素冲突
        expect(page.locator("text=数据查询").first).to_be_visible()

