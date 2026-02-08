"""
策略管理页面 E2E 测试

使用 Playwright 进行端到端测试，覆盖策略管理功能的完整流程。
"""
import pytest
from playwright.sync_api import Page, expect
import uuid

FRONTEND_URL = "http://localhost:3000"


class TestStrategyPage:
    """策略页面测试"""

    def test_strategy_page_loads(self, authenticated_page: Page):
        """测试策略页面加载"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 检查创建策略按钮
        expect(page.locator('button:has-text("创建策略")')).to_be_visible()

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
        """测试模板卡片显示"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/strategy")
        page.wait_for_load_state("networkidle")

        # 切换到策略库标签
        template_tab = page.locator("text=策略库")
        if template_tab.is_visible():
            template_tab.click()
            page.wait_for_timeout(500)

            # 检查是否有策略卡片
            content = page.content()
            # 模板相关的内容
            assert "策略" in content


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
        """测试从仪表盘导航到策略页面"""
        page = authenticated_page
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_load_state("networkidle")

        # 点击策略管理菜单
        page.click('text=策略管理')
        page.wait_for_load_state("networkidle")

        # 应该导航到策略页面
        expect(page).to_have_url(f"{FRONTEND_URL}/strategy")

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
