import { test, expect } from '@playwright/test';
import { LiveTradingPage } from '../pages/LiveTradingPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 实盘交易管理 E2E 测试
 *
 * 适配实际前端 LiveTradingPage.vue
 */
test.describe('实盘交易管理', () => {
  let liveTradingPage: LiveTradingPage;

  test.beforeEach(async ({ page }) => {
    const authPage = new AuthPage(page);
    await authPage.login(UserFactory.createAdmin());

    liveTradingPage = new LiveTradingPage(page);
  });

  test('查看实盘交易页面', async ({ page }) => {
    await liveTradingPage.goto();
    await liveTradingPage.assertOnLiveTradingPage();
  });

  test('打开添加策略对话框', async ({ page }) => {
    await liveTradingPage.goto();

    await liveTradingPage.openAddDialog();

    // 验证对话框打开
    await expect(page.locator(liveTradingPage.dialogTitle)).toBeVisible();

    // 关闭对话框
    await page.click(liveTradingPage.cancelButton);
  });

  test('查看实例列表', async ({ page }) => {
    await liveTradingPage.goto();

    const count = await liveTradingPage.getInstanceCount();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('查看操作按钮', async ({ page }) => {
    await liveTradingPage.goto();

    // 验证批量操作按钮存在
    await expect(page.locator(liveTradingPage.startAllButton)).toBeVisible();
    await expect(page.locator(liveTradingPage.stopAllButton)).toBeVisible();
  });
});
