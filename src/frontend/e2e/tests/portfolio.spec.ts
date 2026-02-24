import { test, expect } from '@playwright/test';

/**
 * 投资组合功能 E2E 测试
 *
 * 简化版测试，专注于验证页面能正确加载和基本交互
 */
test.describe('投资组合', () => {

  test('投资组合页面加载', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    // 访问投资组合页面
    await page.goto('/portfolio');
    await page.waitForTimeout(1000);

    // 验证页面加载 - 检查是否有卡片
    const hasCard = await page.locator('.el-card').count() > 0;
    expect(hasCard).toBeTruthy();
  });

  test('验证概览卡片存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/portfolio');
    await page.waitForTimeout(2000);

    // 验证至少有一个概览指标（组合总资产或总盈亏等）
    const hasOverviewText = await page.getByText('组合总资产').count() > 0 ||
                            await page.getByText('总盈亏').count() > 0;
    expect(hasOverviewText).toBeTruthy();
  });

  test('验证标签页存在', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/portfolio');
    await page.waitForTimeout(2000);

    // 验证策略概览标签存在
    const hasStrategiesTab = await page.getByText('策略概览').count() > 0;
    expect(hasStrategiesTab).toBeTruthy();
  });

  test('验证其他标签页', async ({ page }) => {
    // 先登录
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin123');
    await page.click('button:has-text("登录")');
    await page.waitForTimeout(3000);

    await page.goto('/portfolio');
    await page.waitForTimeout(2000);

    // 验证至少有其他标签存在（当前持仓、交易记录、资金曲线、资产配置）
    const hasPositionsTab = await page.getByText('当前持仓').count() > 0;
    const hasTradesTab = await page.getByText('交易记录').count() > 0;
    const hasEquityTab = await page.getByText('资金曲线').count() > 0;
    const hasAllocationTab = await page.getByText('资产配置').count() > 0;

    expect(hasPositionsTab || hasTradesTab || hasEquityTab || hasAllocationTab).toBeTruthy();
  });
});
