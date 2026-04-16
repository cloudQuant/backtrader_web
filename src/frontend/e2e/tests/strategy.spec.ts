import { test, expect } from '@playwright/test';

/**
 * 策略管理功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('策略管理', () => {
  test.use({ storageState: 'e2e/fixtures/storage-state.json' });

  test('策略页面加载', async ({ page }) => {
    // 访问策略页面
    await page.goto('/strategy');

    // 验证页面加载 - 检查是否有标题或卡片
    await expect(page.getByText('策略中心')).toBeVisible();
  });

  test('验证页面标题', async ({ page }) => {
    await page.goto('/strategy');

    // 验证策略中心标题存在
    await expect(page.getByText('策略中心')).toBeVisible();
  });

  test('验证创建策略按钮存在', async ({ page }) => {
    await page.goto('/strategy');

    // 验证创建策略按钮存在
    await expect(page.locator('button:has-text("创建策略")')).toBeVisible();
  });

  test('验证策略库标签存在', async ({ page }) => {
    await page.goto('/strategy');

    // 验证策略库标签存在
    await expect(page.getByRole('tab', { name: '策略库' })).toBeVisible();
  });

  test('验证我的策略标签存在', async ({ page }) => {
    await page.goto('/strategy');

    // 验证我的策略标签存在
    await expect(page.getByRole('tab', { name: '我的策略' })).toBeVisible();
  });

  test('验证搜索框存在', async ({ page }) => {
    await page.goto('/strategy');

    // 验证搜索输入框存在
    await expect(page.locator('input[placeholder*="搜索"]')).toBeVisible();
  });
});
