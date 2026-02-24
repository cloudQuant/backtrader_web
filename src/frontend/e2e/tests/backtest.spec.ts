import { test, expect } from '@playwright/test';

/**
 * 回测功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 * 每个测试独立运行，不依赖共享的登录状态
 */
test.describe('回测功能', () => {

  test('回测页面加载', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    // 访问回测页面
    await page.goto('/backtest');
    await page.waitForTimeout(1000);

    // 验证页面加载 - 检查是否有回测配置卡片
    const hasCard = await page.locator('.el-card').count() > 0;
    expect(hasCard).toBeTruthy();
  });

  test('查看回测配置表单', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/backtest');
    await page.waitForTimeout(2000);

    // 验证回测配置卡片标题存在
    const hasConfigText = await page.getByText('回测配置').count() > 0;
    expect(hasConfigText).toBeTruthy();
  });

  test('验证策略选择器存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/backtest');
    await page.waitForTimeout(2000);

    // 验证策略选择器存在
    const hasSelect = await page.locator('.el-select').count() > 0;
    expect(hasSelect).toBeTruthy();
  });

  test('验证运行回测按钮存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/backtest');
    await page.waitForTimeout(2000);

    // 验证运行按钮存在
    const hasRunButton = await page.locator('button:has-text("运行回测")').count() > 0;
    expect(hasRunButton).toBeTruthy();
  });

  test('查看回测历史表格', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/backtest');
    await page.waitForTimeout(2000);

    // 验证回测历史卡片标题存在
    const hasHistoryText = await page.getByText('回测历史').count() > 0;
    expect(hasHistoryText).toBeTruthy();
  });
});
