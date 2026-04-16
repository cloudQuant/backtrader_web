import { test, expect } from '@playwright/test';

/**
 * 实盘交易管理 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('实盘交易管理', () => {
  test.use({ storageState: 'e2e/fixtures/storage-state.json' });

  test('实盘交易页面加载', async ({ page }) => {
    // 访问实盘交易页面
    await page.goto('/live-trading');

    await expect(page).toHaveURL(/\/trading$/);
    await expect(page.locator('button:has-text("新建工作区")')).toBeVisible();
  });

  test('验证页面标题', async ({ page }) => {
    await page.goto('/live-trading');

    // 验证页面标题存在
    await expect(page.locator('header .text-lg.font-medium')).toHaveText('策略交易');
  });

  test('验证新建工作区按钮存在', async ({ page }) => {
    await page.goto('/live-trading');

    await expect(page.locator('button:has-text("新建工作区")')).toBeVisible();
  });

  test('验证批量操作按钮存在', async ({ page }) => {
    await page.goto('/live-trading');

    await expect(page.locator('button:has-text("删除工作区")')).toBeVisible();
  });
});
