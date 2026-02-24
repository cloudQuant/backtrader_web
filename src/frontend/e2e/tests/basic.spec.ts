import { test, expect } from '@playwright/test';

/**
 * 基本 E2E 测试 - 验证关键页面加载
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('基本页面测试', () => {

  test('登录页面加载', async ({ page }) => {
    await page.goto('/login');

    // 验证登录表单存在
    await expect(page.locator('input[placeholder*="用户名"]')).toBeVisible();
    await expect(page.locator('input[placeholder*="密码"]')).toBeVisible();
    await expect(page.locator('button:has-text("登录")')).toBeVisible();
  });

  test('登录成功并跳转', async ({ page }) => {
    await page.goto('/login');

    // 填写登录表单
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');

    // 等待登录完成 - 检查 URL 变化
    await page.waitForTimeout(3000);

    // 验证当前 URL - 可能是首页或仍然在登录页（如果登录失败）
    const url = page.url();
    // 登录成功应该不在 /login 页面
    // 登录失败仍然在 /login 页面
    const loginSuccess = !url.includes('/login');
    expect(loginSuccess).toBeTruthy();
  });

  test('访问策略页面', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(2000);

    // 访问策略页面
    await page.goto('/strategy');
    await page.waitForTimeout(2000);

    // 验证页面加载 - 检查是否有基本内容
    const hasContent = await page.locator('h1, .el-card, .el-empty').count() > 0;
    expect(hasContent).toBeTruthy();
  });

  test('访问回测页面', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForURL(/\//, { timeout: 10000 });

    // 访问回测页面
    await page.goto('/backtest');
    await page.waitForTimeout(1000);

    // 验证页面加载 - 检查是否有回测配置卡片
    const hasCard = await page.locator('.el-card').count() > 0;
    expect(hasCard).toBeTruthy();
  });

  test('访问投资组合页面', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForURL(/\//, { timeout: 10000 });

    // 访问投资组合页面
    await page.goto('/portfolio');
    await page.waitForTimeout(1000);

    // 验证页面加载
    const hasCard = await page.locator('.el-card').count() > 0;
    expect(hasCard).toBeTruthy();
  });

  test('访问实盘交易页面', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForURL(/\//, { timeout: 10000 });

    // 访问实盘交易页面
    await page.goto('/live-trading');
    await page.waitForTimeout(1000);

    // 验证页面加载
    const hasContent = await page.locator('.el-card').count() > 0 ||
                        await page.locator('.el-empty').count() > 0;
    expect(hasContent).toBeTruthy();
  });

  test('访问数据页面', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForURL(/\//, { timeout: 10000 });

    // 访问数据页面
    await page.goto('/data');
    await page.waitForTimeout(1000);

    // 验证页面加载
    const hasContent = await page.locator('.el-card, .el-empty').count() > 0;
    expect(hasContent).toBeTruthy();
  });
});
