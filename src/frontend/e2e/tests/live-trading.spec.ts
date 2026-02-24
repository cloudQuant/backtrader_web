import { test, expect } from '@playwright/test';

/**
 * 实盘交易管理 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('实盘交易管理', () => {

  test('实盘交易页面加载', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    // 访问实盘交易页面
    await page.goto('/live-trading');
    await page.waitForTimeout(1000);

    // 验证页面加载 - 检查是否有卡片或空状态
    const hasContent = await page.locator('.el-card, .el-empty').count() > 0;
    expect(hasContent).toBeTruthy();
  });

  test('验证页面标题', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/live-trading');
    await page.waitForTimeout(2000);

    // 验证页面标题存在
    const hasTitle = await page.getByText('实盘交易').count() > 0;
    expect(hasTitle).toBeTruthy();
  });

  test('验证添加策略按钮存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/live-trading');
    await page.waitForTimeout(2000);

    // 验证添加策略按钮存在
    const hasAddButton = await page.locator('button:has-text("添加策略")').count() > 0;
    expect(hasAddButton).toBeTruthy();
  });

  test('验证批量操作按钮存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/live-trading');
    await page.waitForTimeout(2000);

    // 验证一键启动和一键停止按钮存在
    const hasStartAll = await page.locator('button:has-text("一键启动")').count() > 0;
    const hasStopAll = await page.locator('button:has-text("一键停止")').count() > 0;
    expect(hasStartAll || hasStopAll).toBeTruthy();
  });
});
