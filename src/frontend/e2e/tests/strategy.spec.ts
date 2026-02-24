import { test, expect } from '@playwright/test';

/**
 * 策略管理功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('策略管理', () => {

  test('策略页面加载', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    // 访问策略页面
    await page.goto('/strategy');
    await page.waitForTimeout(1000);

    // 验证页面加载 - 检查是否有标题或卡片
    const hasTitle = await page.getByText('策略中心').count() > 0;
    const hasCard = await page.locator('.el-card').count() > 0;
    expect(hasTitle || hasCard).toBeTruthy();
  });

  test('验证页面标题', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/strategy');
    await page.waitForTimeout(2000);

    // 验证策略中心标题存在
    const hasTitle = await page.getByText('策略中心').count() > 0;
    expect(hasTitle).toBeTruthy();
  });

  test('验证创建策略按钮存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/strategy');
    await page.waitForTimeout(2000);

    // 验证创建策略按钮存在
    const hasCreateButton = await page.locator('button:has-text("创建策略")').count() > 0;
    expect(hasCreateButton).toBeTruthy();
  });

  test('验证策略库标签存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/strategy');
    await page.waitForTimeout(2000);

    // 验证策略库标签存在
    const hasGalleryTab = await page.getByText('策略库').count() > 0;
    expect(hasGalleryTab).toBeTruthy();
  });

  test('验证我的策略标签存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/strategy');
    await page.waitForTimeout(2000);

    // 验证我的策略标签存在
    const hasMyStrategiesTab = await page.getByText('我的策略').count() > 0;
    expect(hasMyStrategiesTab).toBeTruthy();
  });

  test('验证搜索框存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/strategy');
    await page.waitForTimeout(2000);

    // 验证搜索输入框存在
    const hasSearchInput = await page.locator('input[placeholder*="搜索"]').count() > 0;
    expect(hasSearchInput).toBeTruthy();
  });
});
