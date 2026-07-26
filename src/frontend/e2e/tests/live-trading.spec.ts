import { test, expect } from '@playwright/test';
import { restorePersistedAuthSession } from '../support/auth';

/**
 * 实盘交易管理 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('实盘交易管理', () => {
  test.beforeEach(async ({ page }) => {
    await restorePersistedAuthSession(page);
  });

  test('实盘交易页面加载', async ({ page }) => {
    // 访问实盘交易页面
    await page.goto('/live-trading');

    await expect(page).toHaveURL(/\/trading$/);
    await expect(
      page.locator('[data-test="workspace-hero"]').getByRole('button', { name: '新建工作区' }),
    ).toBeVisible();
  });

  test('验证页面标题', async ({ page }) => {
    await page.goto('/live-trading');

    // 验证交易工作区标题存在
    await expect(page.locator('[data-test="workspace-hero"] h1')).toHaveText('交易工作区');
  });

  test('验证新建工作区按钮存在', async ({ page }) => {
    await page.goto('/live-trading');

    await expect(
      page.locator('[data-test="workspace-hero"]').getByRole('button', { name: '新建工作区' }),
    ).toBeVisible();
  });

  test('未选择工作区时删除操作处于禁用状态', async ({ page }) => {
    await page.goto('/live-trading');

    const deleteWorkspace = page.locator('button[aria-label="删除工作区"]');
    await expect(deleteWorkspace).toHaveCount(1);
    await expect(deleteWorkspace).toBeDisabled();
  });
});
