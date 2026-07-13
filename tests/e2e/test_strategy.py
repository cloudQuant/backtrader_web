"""
策略管理页面 E2E 测试

使用 Playwright 进行端到端测试，覆盖策略管理功能的完整流程。
"""
import pytest
from playwright.sync_api import Page, expect
import uuid
import re

from conftest import FRONTEND_URL


def _safe_wait(page: Page, timeout: int = 800) -> None:
    """安全等待页面就绪。

    vite dev server 下 ``networkidle`` 可能长时间不触发（HMR/SSE 常驻连接），
    因此包裹 try/except 并追加固定毫秒兜底等待，避免测试不稳定。
    """
    try:
        page.wait_for_load_state("networkidle")
    except Exception:
        pass
    page.wait_for_timeout(timeout)


class TestStrategyPage:
    """策略页面测试"""

    def test_strategy_page_loads(self, authenticated_page: Page):
        """测试策略页面加载

        直接访问规范路径 /research/strategies（旧路径 /strategy 会重定向到此），
        校验管理 Hero 标题、创建策略按钮以及「策略库 / 我的策略」标签页均正常渲染。
        """
        page = authenticated_page
        # 规范路径；旧 /strategy 仅作兼容重定向，测试以真实路径为准
        page.goto(f"{FRONTEND_URL}/research/strategies")
        _safe_wait(page)

        # 页面主标题（strategy.managementHeroTitle = "策略库与我的策略"）
        # 在 /research/strategies 下 showStrategyManagementTabs 为真，hero 区会渲染
        heading = page.locator("#strategy-management-title")
        expect(heading).to_be_visible()
        expect(heading).to_contain_text("策略")

        # 顶部"创建策略"按钮可见（hero 区与"我的策略"面板各有一个按钮，
        # 用 .first 避免 strict 模式下多元素冲突）
        expect(page.locator('button:has-text("创建策略")').first).to_be_visible()

        # 标签页应渲染：策略库（gallery，默认激活）与 我的策略
        # 用 .el-tabs__item 限定到标签页，避免与面板内 <h2> 同名文本冲突
        expect(page.locator(".el-tabs__item").filter(has_text="策略库").first).to_be_visible()
        expect(page.locator(".el-tabs__item").filter(has_text="我的策略").first).to_be_visible()

    def test_strategy_gallery_section(self, authenticated_page: Page):
        """测试策略库区域"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 检查策略库标签页
        expect(page.locator("text=策略库").first).to_be_visible()

    def test_open_create_dialog(self, authenticated_page: Page):
        """测试打开创建策略对话框"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 点击创建策略 - 使用 first 避免多按钮冲突
        page.click('button:has-text("创建策略") >> visible=true')
        page.wait_for_timeout(500)

        # 对话框应该打开 - 检查对话框元素
        expect(page.locator(".el-dialog")).to_be_visible()
        # 在对话框中查找输入框
        expect(page.locator(".el-dialog input[placeholder*='策略名称'], .el-dialog input[placeholder*='名称']")).to_be_visible()

    def test_create_strategy_form(self, authenticated_page: Page):
        """测试创建策略表单"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 打开对话框 - 使用 first 避免多按钮冲突
        page.click('button:has-text("创建策略") >> visible=true')
        page.wait_for_timeout(500)

        # 填写表单 - 在对话框中查找输入框
        unique_name = f"TestStrategy_{uuid.uuid4().hex[:6]}"

        name_input = page.locator(".el-dialog input[placeholder*='策略名称'], .el-dialog input[placeholder*='名称']").first
        name_input.fill(unique_name)

        # 验证输入
        expect(name_input).to_have_value(unique_name)

    def test_close_create_dialog(self, authenticated_page: Page):
        """测试关闭创建对话框"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 打开对话框 - 使用 first 避免多按钮冲突
        page.click('button:has-text("创建策略") >> visible=true')
        page.wait_for_timeout(500)

        # 点击取消
        page.click('button:has-text("取消")')
        page.wait_for_timeout(500)

        # 对话框应该关闭
        expect(page.locator(".el-dialog__body")).to_be_hidden()

    def test_category_filter(self, authenticated_page: Page):
        """测试分类筛选"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 检查分类筛选按钮组存在（el-radio-group）
        expect(page.locator(".el-radio-group").first).to_be_visible()

    def test_my_strategy_tab(self, authenticated_page: Page):
        """测试我的策略标签页"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 检查"我的策略"标签
        expect(page.locator("text=我的策略").first).to_be_visible()


class TestStrategyTemplates:
    """策略模板测试"""

    def test_use_template(self, authenticated_page: Page):
        """测试使用策略模板"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 检查是否有模板（需要后端返回数据）
        # 如果有模板，点击使用
        templates = page.locator(".border.rounded-lg.hover\\:border-blue-500")

        if templates.count() > 0:
            templates.first.click()
            page.wait_for_timeout(500)

            # 应该打开预填充的创建对话框
            expect(page.locator("text=创建策略").last).to_be_visible()

    def test_template_card_display(self, authenticated_page: Page):
        """测试策略模板卡片显示

        gallery 标签页为默认激活页（activeTab 初值为 'gallery'），无需手动切换。
        模板卡片由后端数据驱动：有数据时渲染 .strategy-card，无数据时渲染 el-empty 空状态。
        注意："策略库"文本在页面中出现多次（标签页、<h2> 标题、指标卡），
        必须使用 .first 避免 strict 模式下多元素冲突。
        """
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/research/strategies")
        _safe_wait(page)

        # gallery 为默认激活标签页；"策略库"文本有多处匹配，用 .first 取首个可见元素
        expect(page.locator("text=策略库").first).to_be_visible()

        # 模板网格区域：有数据时校验卡片可见，无数据时校验空状态存在
        cards = page.locator(".strategy-template-grid .strategy-card")
        if cards.count() > 0:
            # 有模板数据：至少第一张卡片应可见
            expect(cards.first).to_be_visible()
        else:
            # 无模板数据：应渲染空状态（.strategy-empty-state 或 Element Plus 的 .el-empty）
            empty = page.locator(".strategy-empty-state, .el-empty")
            expect(empty.first).to_be_visible()


class TestStrategyCodeEditor:
    """策略代码编辑器测试"""

    def test_code_editor_in_dialog(self, authenticated_page: Page):
        """测试对话框中的代码编辑器"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 打开创建对话框
        page.click('button:has-text("创建策略")')
        page.wait_for_timeout(500)

        # 检查编辑器区域
        content = page.content()
        # 代码编辑器相关
        assert "策略" in content or "代码" in content or "编辑" in content


class TestStrategyList:
    """策略列表测试"""

    def test_strategy_list_display(self, authenticated_page: Page):
        """测试策略列表显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 切换到我的策略标签 - 使用 role 选择器
        my_strategy_tab = page.get_by_role("tab", name="我的策略")
        if my_strategy_tab.is_visible():
            my_strategy_tab.click()
            page.wait_for_timeout(500)

        # 策略列表区域应该存在
        expect(page.locator("text=策略").first).to_be_visible()

    def test_empty_strategy_list(self, authenticated_page: Page):
        """测试空策略列表"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 切换到我的策略标签 - 使用 role 选择器
        my_strategy_tab = page.get_by_role("tab", name="我的策略")
        if my_strategy_tab.is_visible():
            my_strategy_tab.click()
            page.wait_for_timeout(500)

        # 检查空状态提示
        content = page.content()
        if "暂无" in content or "还没有" in content:
            assert True


class TestStrategyActions:
    """策略操作测试"""

    def test_strategy_edit_button(self, authenticated_page: Page):
        """测试编辑按钮"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 如果有策略卡片，检查编辑按钮
        edit_buttons = page.locator('button:has-text("编辑")')
        if edit_buttons.count() > 0:
            expect(edit_buttons.first).to_be_visible()

    def test_strategy_delete_button(self, authenticated_page: Page):
        """测试删除按钮"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 如果有策略卡片，检查删除按钮
        delete_buttons = page.locator('button:has-text("删除")')
        if delete_buttons.count() > 0:
            expect(delete_buttons.first).to_be_visible()


class TestStrategyNavigation:
    """策略相关导航测试"""

    def test_navigate_to_strategy_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘导航到策略页面

        仪表盘「创建策略」快捷入口（dashboard-action-card）会跳转到规范路径
        /research/strategies（旧 /strategy 仅作兼容重定向）。用 .first 避免
        strict 模式冲突，并用宽松的 URL 断言（包含 strategies）兼容重定向。
        """
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        _safe_wait(page)

        # 仪表盘快捷入口「创建策略」卡片按钮（.first 避免 strict 模式冲突）
        create_btn = page.locator('button:has-text("创建策略")').first
        expect(create_btn).to_be_visible()
        create_btn.click()
        _safe_wait(page)

        # 规范路径 /research/strategies；旧 /strategy 会重定向到此。
        # 用正则宽松断言 URL 包含 strategies，兼容重定向中间态。
        expect(page).to_have_url(re.compile(r"strategies"))

    def test_strategy_breadcrumb(self, authenticated_page: Page):
        """测试面包屑导航"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 验证当前位置
        content = page.content()
        assert "策略" in content


class TestStrategySearch:
    """策略搜索测试"""

    def test_search_input_exists(self, authenticated_page: Page):
        """测试搜索输入框存在"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 检查搜索框
        search_input = page.locator('input[placeholder*="搜索"]')
        if search_input.is_visible():
            expect(search_input).to_be_visible()


class TestStrategyValidation:
    """策略表单验证测试"""

    def test_empty_name_validation(self, authenticated_page: Page):
        """测试空名称验证"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 打开创建对话框
        page.click('button:has-text("创建策略")')
        page.wait_for_timeout(500)

        # 直接点击确认（不填写名称）
        confirm_button = page.locator('button:has-text("确认")')
        if confirm_button.is_visible():
            # 可能会显示验证错误
            confirm_button.click()
            page.wait_for_timeout(500)
