import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../support/auth';

/**
 * 基本 E2E 测试 - 验证关键页面加载
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('基本页面测试', () => {

  test('登录页面加载', async ({ page }) => {
    await page.goto('/login');

    // 验证登录表单存在
    await expect(page.getByTestId('login-username')).toBeVisible();
    await expect(page.getByTestId('login-password')).toBeVisible();
    await expect(page.getByTestId('login-submit')).toBeVisible();
  });

  test('登录成功并跳转', async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page).not.toHaveURL(/\/login(?:\?.*)?$/);
    await expect(page.locator('.el-menu')).toBeVisible();
  });
});

test.describe('基本页面测试 - 已登录路由', () => {
  test.use({ storageState: 'e2e/fixtures/storage-state.json' });

  test('访问策略页面', async ({ page }) => {
    // 访问策略页面
    await page.goto('/strategy');

    await expect(page.getByText('策略中心')).toBeVisible();
    await expect(page.locator('button:has-text("创建策略")')).toBeVisible();
  });

  test('访问回测页面', async ({ page }) => {
    // 访问回测页面
    await page.goto('/backtest');

    await expect(page).toHaveURL(/\/backtest$/);
    await expect(page.locator('button:has-text("新建工作区")')).toBeVisible();
  });

  test('访问投资组合页面', async ({ page }) => {
    // 访问投资组合页面
    await page.goto('/portfolio');

    // 验证页面加载
    await expect(page.getByText('组合总资产')).toBeVisible();
  });

  test('访问实盘交易页面', async ({ page }) => {
    // 访问实盘交易页面
    await page.goto('/live-trading');

    await expect(page).toHaveURL(/\/trading$/);
    await expect(page.locator('button:has-text("新建工作区")')).toBeVisible();
  });

  test('访问数据页面', async ({ page }) => {
    // 访问数据页面
    await page.goto('/data');

    // 验证页面加载
    await expect(page.getByText('数据治理中心')).toBeVisible();
  });
});
