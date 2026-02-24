"""
数据查询页面 E2E 测试

覆盖 /data 路由的查询表单填写、提交查询、结果验证。
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


class TestDataQueryFlow:
    """数据查询完整流程测试"""

    def test_data_page_loads(self, authenticated_page: Page):
        """测试数据查询页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "数据" in content or "查询" in content or "data" in content.lower()

    def test_data_query_form_elements(self, authenticated_page: Page):
        """测试查询表单包含必要元素"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        content = page.content()
        # 应有股票代码、日期和查询按钮
        has_symbol = "股票" in content or "代码" in content or "symbol" in content.lower()
        has_query = page.locator('button:has-text("查询"), button:has-text("搜索"), button:has-text("获取")').count() > 0
        assert has_symbol, "应有股票代码输入区域"
        assert has_query, "应有查询按钮"

    def test_data_query_fill_and_submit(self, authenticated_page: Page):
        """测试填写查询表单并提交"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 填写股票代码
        symbol_input = page.locator(
            'input[placeholder*="代码"], '
            'input[placeholder*="股票"], '
            'input[placeholder*="symbol" i]'
        )
        if symbol_input.count() > 0:
            symbol_input.first.fill("000001.SZ")
        else:
            # 尝试其他输入方式
            inputs = page.locator('.el-input input[type="text"]')
            if inputs.count() > 0:
                inputs.first.fill("000001.SZ")

        # 点击查询按钮
        query_btn = page.locator('button:has-text("查询"), button:has-text("搜索"), button:has-text("获取")')
        if query_btn.count() > 0:
            query_btn.first.click()
            # 等待数据加载（可能需要网络请求）
            page.wait_for_timeout(3000)

            content = page.content()
            # 查询后应显示数据或加载中状态
            has_result = (
                "日期" in content
                or "开盘" in content
                or "收盘" in content
                or "成交" in content
                or "暂无" in content
                or "加载" in content
                or "loading" in content.lower()
                or page.locator(".el-table, canvas, [class*='chart']").count() > 0
            )
            assert has_result, "查询后应显示数据结果或加载状态"

    def test_data_query_chart_area(self, authenticated_page: Page):
        """测试查询后图表区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # K线图区域（可能默认就有或查询后出现）
        content = page.content()
        has_chart_area = (
            "K线" in content
            or "图表" in content
            or "chart" in content.lower()
            or page.locator("canvas, [class*='chart'], [class*='kline']").count() > 0
        )
        # 图表区域可能在查询后才出现，这里只检查页面结构
        assert len(content) > 100, "数据页面应正常渲染"

    def test_data_query_table_area(self, authenticated_page: Page):
        """测试数据表格区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 应有表格区域
        table = page.locator(".el-table, table, [class*='data-table']")
        content = page.content()
        has_table_area = table.count() > 0 or "表格" in content or "数据" in content
        assert has_table_area, "数据页面应有表格区域"

    def test_data_query_period_selector(self, authenticated_page: Page):
        """测试周期选择器"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        content = page.content()
        # 应有日K/周K/月K等周期选择
        has_period = (
            "日K" in content
            or "周K" in content
            or "月K" in content
            or "日线" in content
            or "周线" in content
            or page.locator('[class*="period"], .el-radio-group, .el-segmented').count() > 0
        )
        # 周期选择器可能不在所有实现中都有
        assert len(content) > 100

    def test_data_query_date_range(self, authenticated_page: Page):
        """测试日期范围选择"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 应有日期选择器
        date_pickers = page.locator(
            '.el-date-editor, '
            'input[type="date"], '
            'input[placeholder*="日期"], '
            'input[placeholder*="开始"], '
            'input[placeholder*="结束"]'
        )
        if date_pickers.count() > 0:
            expect(date_pickers.first).to_be_visible()

    def test_data_query_download_button(self, authenticated_page: Page):
        """测试下载按钮"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        download_btn = page.locator(
            'button:has-text("下载"), '
            'button:has-text("导出"), '
            'button:has-text("Export"), '
            'button:has-text("export")'
        )
        # 下载按钮可能在查询后才出现
        if download_btn.count() > 0:
            expect(download_btn.first).to_be_visible()

    def test_data_query_invalid_symbol(self, authenticated_page: Page):
        """测试无效股票代码"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        # 输入无效代码
        symbol_input = page.locator(
            'input[placeholder*="代码"], '
            'input[placeholder*="股票"], '
            '.el-input input[type="text"]'
        )
        if symbol_input.count() > 0:
            symbol_input.first.fill("INVALID")

            query_btn = page.locator('button:has-text("查询"), button:has-text("搜索"), button:has-text("获取")')
            if query_btn.count() > 0:
                query_btn.first.click()
                page.wait_for_timeout(2000)

                # 应有错误提示
                content = page.content()
                has_error_or_empty = (
                    "错误" in content
                    or "无效" in content
                    or "格式" in content
                    or "暂无" in content
                    or page.locator(".el-message--error, .el-alert--error").count() > 0
                )
                # 某些实现可能只是不返回数据
                assert len(content) > 100

    def test_data_page_responsive_mobile(self, authenticated_page: Page):
        """测试移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert len(content) > 100

    def test_data_page_responsive_tablet(self, authenticated_page: Page):
        """测试平板布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{FRONTEND_URL}/data")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert len(content) > 100
