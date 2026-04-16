import { test, expect } from '@playwright/test';

/**
 * 回测功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 * 每个测试独立运行，不依赖共享的登录状态
 */
test.describe('回测功能', () => {
  test.use({ storageState: 'e2e/fixtures/storage-state.json' });

  test('回测页面加载', async ({ page }) => {
    // 访问回测页面
    await page.goto('/backtest');

    await expect(page).toHaveURL(/\/backtest$/);
    await expect(page.locator('button:has-text("新建工作区")')).toBeVisible();
  });

  test('研究工作区标题可见', async ({ page }) => {
    await page.goto('/backtest');

    await expect(page.locator('header .text-lg.font-medium')).toHaveText('策略研究');
  });

  test('研究工作区空状态或列表存在', async ({ page }) => {
    await page.goto('/backtest');

    await expect
      .poll(async () => {
        const hasEmpty = (await page.locator('.workspace-list-page .el-empty').count()) > 0;
        const hasTable = (await page.locator('.workspace-list-page .el-table').count()) > 0;
        const hasCards = (await page.locator('.workspace-list-page .workspace-card').count()) > 0;
        return hasEmpty || hasTable || hasCards;
      }, {
        timeout: 10000,
        message: 'workspace list should eventually render empty state, table, or cards',
      })
      .toBe(true);
  });

  test('新建工作区按钮存在', async ({ page }) => {
    await page.goto('/backtest');

    await expect(page.locator('button:has-text("新建工作区")')).toBeVisible();
  });

  test('删除工作区按钮存在', async ({ page }) => {
    await page.goto('/backtest');

    await expect(page.locator('button:has-text("删除工作区")')).toBeVisible();
  });
});
