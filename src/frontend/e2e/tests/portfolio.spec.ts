import { test, expect } from '@playwright/test';
import { restorePersistedAuthSession } from '../support/auth';

/**
 * 投资组合功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('投资组合', () => {
  test.beforeEach(async ({ page }) => {
    await restorePersistedAuthSession(page);
  });

  test('投资组合页面加载', async ({ page }) => {
    // 访问投资组合页面
    await page.goto('/portfolio');

    // 验证页面加载 - 检查概览区块
    await expect(page.locator('[data-test="portfolio-hero"]')).toBeVisible();
  });

  test('验证概览卡片存在', async ({ page }) => {
    await page.goto('/portfolio');

    const overview = page.locator('[data-test="portfolio-overview"]');
    await expect(overview.getByText('组合总资产', { exact: true })).toBeVisible();
    await expect(overview.getByText('总盈亏', { exact: true })).toBeVisible();
  });

  test('验证标签页存在', async ({ page }) => {
    await page.goto('/portfolio');

    // 验证交易工作区标签存在
    await expect(
      page.locator('[data-test="portfolio-workbench"]').getByRole('tab', { name: '交易工作区' }),
    ).toBeVisible();
  });

  test('验证其他标签页', async ({ page }) => {
    await page.goto('/portfolio');

    const workbench = page.locator('[data-test="portfolio-workbench"]');
    await expect(workbench.getByRole('tab', { name: '当前持仓' })).toBeVisible();
    await expect(workbench.getByRole('tab', { name: '交易记录' })).toBeVisible();
    await expect(workbench.getByRole('tab', { name: '资金曲线' })).toBeVisible();
    await expect(workbench.getByRole('tab', { name: '资产配置' })).toBeVisible();
  });
});
