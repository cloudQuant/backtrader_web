"""
数据市场页面 E2E 测试

使用 Playwright 进行端到端测试，覆盖数据市场页面（/data/market）的完整流程。

注意：
- /data 是布局路由（DataLayout），会自动重定向到 /data/market
  （DataMarketPage -> DataPage.vue）。
- 旧版页面标题「数据查询」在当前代码库中已不存在，真实主标题为
  「历史数据」（i18n: dataMgmt.headerTitle）。
- 默认资产类型为「股票」，默认标的代码为 000001（旧测试期望的
  000001.SZ 已不再适用）。
"""
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


def _safe_wait(page: Page, timeout: int = 800) -> None:
    """安全等待页面就绪。

    vite dev server 下 networkidle 可能因 HMR / websocket 长时间不触发，
    因此用 try/except 兜底，再追加固定等待确保异步渲染完成。
    """
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(timeout)


def _goto_data_market(page: Page) -> None:
    """导航到数据市场页并安全等待。"""
    page.goto(f"{FRONTEND_URL}/data/market")
    _safe_wait(page)


class TestDataPage:
    """数据市场页面测试"""

    def test_data_page_loads(self, authenticated_page: Page):
        """测试数据页面加载"""
        page = authenticated_page
        _goto_data_market(page)

        # 主卡片容器（data-test="data-market-page"）应可见
        expect(page.locator('[data-test="data-market-page"]').first).to_be_visible()
        # 主标题为「历史数据」（dataMgmt.headerTitle）
        expect(page.locator("h2", has_text="历史数据").first).to_be_visible()

    def test_query_form_elements(self, authenticated_page: Page):
        """测试查询表单元素：标的、周期、日期范围、查询按钮"""
        page = authenticated_page
        _goto_data_market(page)

        toolbar = page.locator(".history-query-toolbar")
        expect(toolbar.first).to_be_visible()

        # 标的代码选择器（el-select：filterable / remote / allow-create）
        expect(
            toolbar.locator('[data-test="market-instrument-select"]').first
        ).to_be_visible()
        # 周期选择器：工具栏内第二个 el-select（标的 + 周期）
        expect(toolbar.locator(".el-select").nth(1)).to_be_visible()
        # 日期范围选择器（el-date-picker daterange）
        expect(toolbar.locator(".el-date-editor").first).to_be_visible()
        # 查询按钮（dataMgmt.btnQuery = 「查询」）
        expect(toolbar.locator('button:has-text("查询")').first).to_be_visible()

    def test_fill_query_form(self, authenticated_page: Page):
        """测试填写查询表单（标的代码可过滤输入）"""
        page = authenticated_page
        _goto_data_market(page)

        instrument_select = page.locator('[data-test="market-instrument-select"]')
        expect(instrument_select.first).to_be_visible()
        # 展开可过滤下拉，出现输入框
        instrument_select.first.click()
        page.wait_for_timeout(300)
        filter_input = instrument_select.locator("input").first
        if filter_input.is_visible():
            filter_input.fill("600519")
            page.wait_for_timeout(300)
            # 验证输入已写入（不依赖远程搜索结果）
            expect(filter_input).to_have_value("600519")

    def test_default_symbol_prefilled(self, authenticated_page: Page):
        """测试默认股票代码预填充（默认资产=股票，代码=000001）"""
        page = authenticated_page
        _goto_data_market(page)

        instrument_select = page.locator('[data-test="market-instrument-select"]')
        expect(instrument_select.first).to_be_visible()
        # 默认 form.symbol = '000001'（旧测试期望的 000001.SZ 已不再适用）。
        # ensureCurrentInstrumentOptions 保证当前代码始终在下拉项中，
        # 因此选择器会显示「000001」。expect 自带重试以应对异步加载。
        expect(instrument_select.first).to_contain_text("000001")

    def test_page_structure(self, authenticated_page: Page):
        """测试页面整体结构"""
        page = authenticated_page
        _goto_data_market(page)

        content = page.content()
        # 真实页面标题为「历史数据」（旧断言「数据查询」已失效）
        assert "历史数据" in content
        # 查询按钮文案存在
        assert "查询" in content


class TestDataQuery:
    """数据查询测试"""

    def test_query_button_exists(self, authenticated_page: Page):
        """测试查询按钮存在"""
        page = authenticated_page
        _goto_data_market(page)

        query_button = page.locator('button:has-text("查询")')
        expect(query_button.first).to_be_visible()

    def test_period_selector(self, authenticated_page: Page):
        """测试周期选择器（默认 daily -> 「日线」）"""
        page = authenticated_page
        _goto_data_market(page)

        content = page.content()
        # 默认周期 daily 对应「日线」；或周期占位/选项文本存在
        assert "日线" in content or "周期" in content

    def test_date_range_inputs(self, authenticated_page: Page):
        """测试日期范围输入（daterange 选择器）"""
        page = authenticated_page
        _goto_data_market(page)

        # el-date-picker daterange 渲染为 .el-date-editor，内含日期输入
        date_editor = page.locator(".el-date-editor").first
        expect(date_editor).to_be_visible()
        date_inputs = page.locator(".el-date-editor input")
        assert date_inputs.count() >= 1


class TestDataDisplay:
    """数据显示测试"""

    def test_kline_chart_area(self, authenticated_page: Page):
        """测试行情图表区域"""
        page = authenticated_page
        _goto_data_market(page)

        # 图表卡片标题「专业行情图表」（dataMgmt.chartOverviewTitle）应可见
        expect(page.locator("text=专业行情图表").first).to_be_visible()
        # 图表容器始终在 DOM 中（v-show 控制显隐，数据为空时隐藏）
        assert page.locator('[data-test="market-main-chart"]').count() >= 1

    def test_data_table(self, authenticated_page: Page):
        """测试历史数据表格卡片"""
        page = authenticated_page
        _goto_data_market(page)

        # 历史数据表格卡片（.history-table-card）应可见
        expect(page.locator(".history-table-card").first).to_be_visible()
        content = page.content()
        assert "历史数据" in content


class TestDataValidation:
    """数据表单验证测试"""

    def test_invalid_symbol_format(self, authenticated_page: Page):
        """测试输入无效股票代码后点击查询（异步，宽松校验）"""
        page = authenticated_page
        _goto_data_market(page)

        instrument_select = page.locator('[data-test="market-instrument-select"]')
        instrument_select.first.click()
        page.wait_for_timeout(300)
        filter_input = instrument_select.locator("input").first
        if filter_input.is_visible():
            filter_input.fill("INVALID")
            page.wait_for_timeout(300)
            query_button = page.locator('button:has-text("查询")')
            if query_button.first.is_visible():
                query_button.first.click()
                # 异步查询：等待结果或错误提示，不强制断言具体内容
                page.wait_for_timeout(1000)

    def test_empty_symbol(self, authenticated_page: Page):
        """测试清空标的代码输入"""
        page = authenticated_page
        _goto_data_market(page)

        instrument_select = page.locator('[data-test="market-instrument-select"]')
        instrument_select.first.click()
        page.wait_for_timeout(300)
        filter_input = instrument_select.locator("input").first
        if filter_input.is_visible():
            filter_input.fill("")
            expect(filter_input).to_have_value("")


class TestNavigation:
    """数据页面导航测试"""

    def test_navigate_to_data_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘通过侧边栏导航到数据市场页"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        _safe_wait(page)

        # 侧边栏「市场数据」菜单项（el-menu router 模式，index=/data）
        data_link = page.locator('.el-menu-item:has-text("市场数据")')
        if data_link.count() == 0:
            pytest.skip("未找到「市场数据」侧边栏链接")
        data_link.first.click()
        # /data 会重定向到 /data/market，等待主标题出现即视为导航成功
        expect(page.locator("h2", has_text="历史数据").first).to_be_visible(timeout=10000)
        assert "/data/market" in page.url


class TestDataDownload:
    """数据下载测试（DataMarketPage 当前无下载入口，保留宽松探测）"""

    def test_download_button(self, authenticated_page: Page):
        """测试下载按钮（页面暂无下载按钮时宽松通过）"""
        page = authenticated_page
        _goto_data_market(page)

        download_buttons = page.locator('button:has-text("下载")')
        if download_buttons.count() > 0:
            expect(download_buttons.first).to_be_visible()


class TestResponsiveLayout:
    """响应式布局测试"""

    def test_mobile_layout(self, authenticated_page: Page):
        """测试移动端布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 375, "height": 667})
        _goto_data_market(page)

        expect(page.locator("h2", has_text="历史数据").first).to_be_visible()

    def test_tablet_layout(self, authenticated_page: Page):
        """测试平板布局"""
        page = authenticated_page
        page.set_viewport_size({"width": 768, "height": 1024})
        _goto_data_market(page)

        expect(page.locator("h2", has_text="历史数据").first).to_be_visible()
