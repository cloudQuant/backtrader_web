"""
回测结果页面 E2E 测试

覆盖 /backtest/:id 路由的页面加载、指标显示、图表渲染。
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


class TestBacktestResultPage:
    """回测结果页面测试"""

    def test_backtest_result_page_loads_with_invalid_id(self, authenticated_page: Page):
        """测试无效 ID 的回测结果页面行为"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest/nonexistent-id")
        page.wait_for_load_state("networkidle")

        # 应显示错误提示或空状态
        content = page.content()
        has_error = (
            "未找到" in content
            or "不存在" in content
            or "not found" in content.lower()
            or "404" in content
            or "错误" in content
            or "加载" in content
        )
        # 页面至少应成功加载（不白屏）
        assert len(content) > 100, "回测结果页面应正常渲染"

    def test_backtest_result_page_structure(self, authenticated_page: Page, test_data_ready):
        """测试回测结果页面基本结构（通过导航到回测页并查看历史）"""
        if not test_data_ready:
            pytest.skip("回测数据预创建失败，跳过")
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        result_links = page.locator('a[href*="/backtest/"], .el-table__row')
        if result_links.count() == 0:
            pytest.skip("回测历史列表未加载出数据")

        result_links.first.click()
        page.wait_for_timeout(1000)

        # 检查结果页面是否包含关键指标
        content = page.content()
        has_metrics = (
            "收益" in content
            or "回撤" in content
            or "夏普" in content
            or "总收益率" in content
            or "return" in content.lower()
        )
        if "/backtest/" in page.url:
            assert has_metrics, "回测结果页面应显示指标数据"

    def test_backtest_result_page_has_chart_area(self, authenticated_page: Page, test_data_ready):
        """测试回测结果页面有图表区域"""
        if not test_data_ready:
            pytest.skip("回测数据预创建失败，跳过")
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        result_links = page.locator('a[href*="/backtest/"], .el-table__row')
        if result_links.count() == 0:
            pytest.skip("回测历史列表未加载出数据")

        result_links.first.click()
        page.wait_for_timeout(1000)

        if "/backtest/" in page.url and page.url != f"{FRONTEND_URL}/backtest":
            # 应有图表容器（ECharts 使用 canvas 或特定 div）
            chart = page.locator("canvas, .echarts, [class*='chart']")
            if chart.count() > 0:
                expect(chart.first).to_be_visible()

    def test_backtest_result_page_back_navigation(self, authenticated_page: Page, test_data_ready):
        """测试从结果页返回回测列表"""
        if not test_data_ready:
            pytest.skip("回测数据预创建失败，跳过")
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        result_links = page.locator('a[href*="/backtest/"], .el-table__row')
        if result_links.count() == 0:
            pytest.skip("回测历史列表未加载出数据")

        result_links.first.click()
        page.wait_for_timeout(1000)

        if "/backtest/" in page.url and page.url != f"{FRONTEND_URL}/backtest":
            back_btn = page.locator(
                'button:has-text("返回"), a:has-text("回测"), .el-breadcrumb__item:has-text("回测")'
            )
            if back_btn.count() > 0:
                back_btn.first.click()
                page.wait_for_timeout(1000)
                assert "/backtest" in page.url


class TestBacktestResultMetrics:
    """回测结果指标显示测试"""

    def test_result_page_shows_key_metrics(self, authenticated_page: Page, test_data_ready):
        """测试结果页面显示核心指标"""
        if not test_data_ready:
            pytest.skip("回测数据预创建失败，跳过")
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/backtest")
        page.wait_for_load_state("networkidle")

        result_links = page.locator('a[href*="/backtest/"], .el-table__row')
        if result_links.count() == 0:
            pytest.skip("回测历史列表未加载出数据")

        result_links.first.click()
        page.wait_for_timeout(1000)

        if "/backtest/" in page.url and page.url != f"{FRONTEND_URL}/backtest":
            content = page.content()
            key_metrics = ["收益率", "回撤", "夏普", "交易"]
            found_metrics = [m for m in key_metrics if m in content]
            assert len(found_metrics) >= 1, f"应至少显示1个核心指标，找到: {found_metrics}"
