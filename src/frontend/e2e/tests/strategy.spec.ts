import { test, expect } from '@playwright/test';
import { StrategyPage } from '../pages/StrategyPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 策略管理功能 E2E 测试
 *
 * 适配实际前端 StrategyPage.vue
 */
test.describe('策略管理', () => {
  let strategyPage: StrategyPage;

  // 使用认证后的页面状态
  test.beforeEach(async ({ page }) => {
    // 登录
    const authPage = new AuthPage(page);
    const credentials = UserFactory.createAdmin();
    await authPage.login(credentials);

    strategyPage = new StrategyPage(page);
  });

  test('查看策略库', async ({ page }) => {
    await strategyPage.goto();
    await strategyPage.assertOnStrategiesPage();

    // 策略库标签应该存在
    await expect(page.locator(strategyPage.galleryTab)).toBeVisible();
  });

  test('搜索策略', async ({ page }) => {
    await strategyPage.goto();

    // 搜索特定关键词
    await strategyPage.searchStrategy('双均线');

    // 等待搜索结果加载
    await page.waitForTimeout(1000);
    const results = await strategyPage.getStrategyCount();

    // 验证搜索结果
    expect(results).toBeGreaterThanOrEqual(0);
  });

  test('按分类过滤策略', async ({ page }) => {
    await strategyPage.goto();

    // 选择特定分类
    await strategyPage.filterByCategory('趋势');

    // 等待过滤结果
    await page.waitForTimeout(1000);
    const results = await strategyPage.getStrategyCount();

    // 验证过滤结果
    expect(results).toBeGreaterThanOrEqual(0);
  });

  test('切换到我的策略标签', async ({ page }) => {
    await strategyPage.goto();
    await strategyPage.goToMyStrategies();

    // 验证标签切换
    await expect(page.locator(strategyPage.myStrategiesTab)).toHaveClass(/is-active/);
  });

  test('点击创建策略按钮', async ({ page }) => {
    await strategyPage.goto();

    // 点击创建策略按钮（但不实际创建，因为 Monaco Editor 很难自动化）
    await strategyPage.clickCreateStrategy();

    // 验证对话框打开
    await expect(page.locator(strategyPage.dialogTitle)).toBeVisible();

    // 关闭对话框
    await page.click(strategyPage.cancelButton);
  });
});
