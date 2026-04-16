import { test, expect } from '@playwright/test';

/**
 * 投资组合功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('投资组合', () => {
  test.use({ storageState: 'e2e/fixtures/storage-state.json' });

  test('投资组合页面加载', async ({ page }) => {
    // 访问投资组合页面
    await page.goto('/portfolio');

    // 验证页面加载 - 检查是否有卡片
    await expect(page.getByText('组合总资产')).toBeVisible();
  });

  test('验证概览卡片存在', async ({ page }) => {
    await page.goto('/portfolio');

    await expect(page.getByText('组合总资产')).toBeVisible();
    await expect(page.getByText('总盈亏')).toBeVisible();
  });

  test('验证标签页存在', async ({ page }) => {
    await page.goto('/portfolio');

    // 验证策略概览标签存在
    await expect(page.getByRole('tab', { name: '策略概览' })).toBeVisible();
  });

  test('验证其他标签页', async ({ page }) => {
    await page.goto('/portfolio');

    await expect(page.getByRole('tab', { name: '当前持仓' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '交易记录' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '资金曲线' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '资产配置' })).toBeVisible();
  });
});
