"""
仪表盘页面 E2E 测试
"""
import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://localhost:3001"


class TestDashboard:
    """仪表盘测试"""
    
    def test_dashboard_loads(self, authenticated_page: Page):
        """测试仪表盘页面加载"""
        page = authenticated_page
        
        # 确认在首页
        expect(page).to_have_url(f"{FRONTEND_URL}/")
        
        # 检查页面标题
        expect(page.locator("text=仪表盘")).to_be_visible()
    
    def test_dashboard_stats_cards(self, authenticated_page: Page):
        """测试统计卡片显示"""
        page = authenticated_page
        
        # 检查统计卡片
        expect(page.locator("text=回测次数")).to_be_visible()
        expect(page.locator("text=策略数量")).to_be_visible()
        expect(page.locator("text=平均收益率")).to_be_visible()
        expect(page.locator("text=最佳夏普比率")).to_be_visible()
    
    def test_dashboard_quick_actions(self, authenticated_page: Page):
        """测试快速操作区域"""
        page = authenticated_page
        
        # 检查快速开始区域
        expect(page.locator("text=快速开始").first).to_be_visible()
        expect(page.locator("text=运行回测").first).to_be_visible()
        expect(page.locator("text=创建策略").first).to_be_visible()
        expect(page.locator("text=查询数据").first).to_be_visible()
    
    def test_navigate_to_backtest_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘导航到回测页面"""
        page = authenticated_page
        
        # 点击运行回测
        page.click("text=运行回测")
        page.wait_for_timeout(500)
        
        # 验证跳转到回测页面
        expect(page).to_have_url(f"{FRONTEND_URL}/backtest")
    
    def test_navigate_to_strategy_from_dashboard(self, authenticated_page: Page):
        """测试从仪表盘导航到策略页面"""
        page = authenticated_page
        
        # 点击创建策略
        page.click("text=创建策略")
        page.wait_for_timeout(500)
        
        # 验证跳转到策略页面
        expect(page).to_have_url(f"{FRONTEND_URL}/strategy")
    
    def test_recent_backtests_section(self, authenticated_page: Page):
        """测试最近回测区域"""
        page = authenticated_page
        
        # 检查最近回测区域
        expect(page.locator("text=最近回测")).to_be_visible()
        expect(page.locator("text=查看全部")).to_be_visible()
    
    def test_sidebar_navigation(self, authenticated_page: Page):
        """测试侧边栏导航"""
        page = authenticated_page
        
        # 检查侧边栏菜单
        expect(page.locator("text=首页").first).to_be_visible()
        expect(page.locator("text=回测分析").first).to_be_visible()
        expect(page.locator("text=策略管理").first).to_be_visible()
        expect(page.locator("text=数据查询").first).to_be_visible()
        expect(page.locator("text=系统设置").first).to_be_visible()
    
    def test_sidebar_navigate_to_backtest(self, authenticated_page: Page):
        """测试侧边栏导航到回测"""
        page = authenticated_page
        
        page.click("text=回测分析")
        page.wait_for_timeout(500)
        
        expect(page).to_have_url(f"{FRONTEND_URL}/backtest")
    
    def test_sidebar_navigate_to_strategy(self, authenticated_page: Page):
        """测试侧边栏导航到策略"""
        page = authenticated_page
        
        page.click("text=策略管理")
        page.wait_for_timeout(500)
        
        expect(page).to_have_url(f"{FRONTEND_URL}/strategy")
    
    def test_sidebar_navigate_to_data(self, authenticated_page: Page):
        """测试侧边栏导航到数据"""
        page = authenticated_page
        
        page.click("text=数据查询")
        page.wait_for_timeout(500)
        
        expect(page).to_have_url(f"{FRONTEND_URL}/data")
    
    def test_sidebar_navigate_to_settings(self, authenticated_page: Page):
        """测试侧边栏导航到设置"""
        page = authenticated_page
        
        page.click("text=系统设置")
        page.wait_for_timeout(500)
        
        expect(page).to_have_url(f"{FRONTEND_URL}/settings")
    
    def test_user_dropdown(self, authenticated_page: Page):
        """测试用户下拉菜单"""
        page = authenticated_page
        
        # 点击用户头像区域打开下拉
        page.click(".el-dropdown")
        page.wait_for_timeout(300)
        
        # 检查下拉菜单项
        expect(page.locator("text=个人设置")).to_be_visible()
        expect(page.locator("text=退出登录")).to_be_visible()
    
    def test_logout(self, authenticated_page: Page):
        """测试退出登录"""
        page = authenticated_page
        
        # 点击用户头像区域打开下拉
        page.click(".el-dropdown")
        page.wait_for_timeout(300)
        
        # 点击退出登录
        page.click("text=退出登录")
        page.wait_for_timeout(1000)
        
        # 应该跳转到登录页
        expect(page).to_have_url(f"{FRONTEND_URL}/login")
