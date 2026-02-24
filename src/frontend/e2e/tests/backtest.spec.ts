import { test, expect } from '@playwright/test';
import { BacktestPage } from '../pages/BacktestPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 回测功能 E2E 测试
 *
 * 适配实际前端 BacktestPage.vue
 */
test.describe('回测功能', () => {
  let backtestPage: BacktestPage;

  test.beforeEach(async ({ page }) => {
    const authPage = new AuthPage(page);
    const credentials = UserFactory.createAdmin();
    await authPage.login(credentials);

    backtestPage = new BacktestPage(page);
  });

  test('回测页面加载', async () => {
    await backtestPage.goto();
    await backtestPage.assertOnBacktestPage();
  });

  test('查看回测历史', async ({ page }) => {
    await backtestPage.goto();
    await page.waitForTimeout(1000);

    const count = await backtestPage.getHistoryCount();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('点击运行回测按钮（不实际运行）', async ({ page }) => {
    await backtestPage.goto();
    await page.waitForTimeout(1000);

    // 验证运行按钮存在
    await expect(page.locator(backtestPage.runButton)).toBeVisible();
  });

  test('选择策略', async ({ page }) => {
    await backtestPage.goto();
    await page.waitForTimeout(1000);

    // 点击策略选择器
    await page.click('.el-select');
    await page.waitForTimeout(500);

    // 验证下拉选项出现
    await expect(page.locator('.el-select-dropdown')).toBeVisible();
  });
});
