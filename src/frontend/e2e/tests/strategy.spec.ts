import { test, expect } from '@playwright/test';
import { APP_PATHS } from '../../src/navigation/routes';
import { restorePersistedAuthSession } from '../support/auth';

/**
 * 策略管理功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('策略管理', () => {
  test.beforeEach(async ({ page }) => {
    await restorePersistedAuthSession(page);
  });

  test('策略页面加载', async ({ page }) => {
    // 访问策略页面
    await page.goto(APP_PATHS.research.strategies);

    // 验证页面加载 - 检查管理区块
    await expect(page.locator('[data-test="strategy-management-hero"]')).toBeVisible();
  });

  test('验证页面标题', async ({ page }) => {
    await page.goto(APP_PATHS.research.strategies);

    // 验证策略管理标题存在
    await expect(
      page.locator('[data-test="strategy-management-hero"] h1'),
    ).toHaveText('策略库与我的策略');
  });

  test('验证创建策略按钮存在', async ({ page }) => {
    await page.goto(APP_PATHS.research.strategies);

    // 验证管理区中的创建策略按钮存在
    await expect(
      page
        .locator('[data-test="strategy-management-hero"]')
        .getByRole('button', { name: '创建策略' }),
    ).toBeVisible();
  });

  test('验证策略库标签存在', async ({ page }) => {
    await page.goto(APP_PATHS.research.strategies);

    // 验证策略库标签存在
    await expect(page.getByRole('tab', { name: '策略库' })).toBeVisible();
  });

  test('验证我的策略标签存在', async ({ page }) => {
    await page.goto(APP_PATHS.research.strategies);

    // 验证我的策略标签存在
    await expect(page.getByRole('tab', { name: '我的策略' })).toBeVisible();
  });

  test('验证搜索框存在', async ({ page }) => {
    await page.goto(APP_PATHS.research.strategies);

    // 验证搜索输入框存在
    await expect(page.locator('input[placeholder*="搜索"]')).toBeVisible();
  });
});
