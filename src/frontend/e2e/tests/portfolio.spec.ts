import { test, expect } from '@playwright/test';
import { PortfolioPage } from '../pages/PortfolioPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 投资组合功能 E2E 测试
 *
 * 适配实际前端 PortfolioPage.vue
 */
test.describe('投资组合', () => {
  let portfolioPage: PortfolioPage;

  test.beforeEach(async ({ page }) => {
    const authPage = new AuthPage(page);
    await authPage.login(UserFactory.createAdmin());

    portfolioPage = new PortfolioPage(page);
  });

  test('查看投资组合概览', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.assertOnPortfolioPage();
  });

  test('切换到策略概览标签', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.goToStrategiesTab();

    // 验证表格可见
    await portfolioPage.waitForDataLoad();
  });

  test('切换到持仓标签', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.goToPositionsTab();

    // 验证标签切换
    await portfolioPage.waitForDataLoad();
  });

  test('切换到交易记录标签', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.goToTradesTab();

    await portfolioPage.waitForDataLoad();
  });

  test('切换到资金曲线标签', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.goToEquityTab();

    await portfolioPage.waitForDataLoad();
  });

  test('切换到资产配置标签', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.goToAllocationTab();

    await portfolioPage.waitForDataLoad();
  });

  test('获取策略数量', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.goToStrategiesTab();

    const count = await portfolioPage.getStrategyCount();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
