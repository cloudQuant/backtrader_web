import { test, expect } from '@playwright/test';
import { PortfolioPage } from '../pages/PortfolioPage';
import { PaperTradingPage } from '../pages/PaperTradingPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 投资组合功能 E2E 测试
 *
 * SCAMPER 应用:
 * - Combine: 整合多个账户的投资组合
 * - Put to Other Uses: 导出报告用于分析
 * - Modify: 细化的指标验证
 */
test.describe('投资组合', () => {
  let portfolioPage: PortfolioPage;
  let paperTradingPage: PaperTradingPage;

  test.beforeEach(async ({ page }) => {
    // 登录
    const authPage = new AuthPage(page);
    await authPage.login(UserFactory.createAdmin());

    portfolioPage = new PortfolioPage(page);
    paperTradingPage = new PaperTradingPage(page);
  });

  test('查看投资组合概览', async ({ page }) => {
    await portfolioPage.goto();
    await portfolioPage.assertOnPortfolioPage();

    // 验证所有指标面板可见
    await expect(page.locator(portfolioPage.totalEquity)).toBeVisible();
    await expect(page.locator(portfolioPage.totalCash)).toBeVisible();
    await expect(page.locator(portfolioPage.totalPnL)).toBeVisible();
  });

  /**
   * SCAMPER Combine: 整合多账户的投资组合
   */
  test('多账户投资组合汇总', async ({ page }) => {
    // 创建两个模拟账户
    const accounts = [
      { name: `组合账户A_${Date.now()}`, initialCash: 100000 },
      { name: `组合账户B_${Date.now()}`, initialCash: 200000 },
    ];

    for (const account of accounts) {
      await paperTradingPage.goto();
      await paperTradingPage.createAccount(account);
    }

    // 查看投资组合
    await portfolioPage.goto();

    // 验证总权益是两个账户的汇总
    const summary = await portfolioPage.getPortfolioSummary();
    expect(summary.totalEquity).toBe(300000); // 100000 + 200000
  });

  test('查看汇总持仓', async ({ page }) => {
    // 先创建账户并进行交易
    const account = {
      name: `持仓账户_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    // 进行交易
    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'buy',
      size: 100,
    });

    await paperTradingPage.placeOrder({
      symbol: '600519.SH',
      side: 'buy',
      size: 10,
    });

    // 查看投资组合的持仓汇总
    await portfolioPage.goto();
    const positionCount = await portfolioPage.getAggregatedPositionCount();
    expect(positionCount).toBeGreaterThanOrEqual(2);
  });

  test('查看汇总交易记录', async ({ page }) => {
    const account = {
      name: `交易记录_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    // 进行交易
    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'buy',
      size: 100,
    });

    // 查看投资组合的交易记录
    await portfolioPage.goto();
    const tradeCount = await portfolioPage.getAggregatedTradeCount();
    expect(tradeCount).toBeGreaterThan(0);
  });

  /**
   * SCAMPER Modify: 日期范围过滤
   */
  test('按日期范围过滤投资组合', async ({ page }) => {
    await portfolioPage.goto();

    // 选择日期范围
    await portfolioPage.filterByDateRange('2024-01-01', '2024-12-31');

    // 验证数据更新
    await page.waitForTimeout(500);
    const summary = await portfolioPage.getPortfolioSummary();
    expect(summary.totalEquity).toBeGreaterThanOrEqual(0);
  });

  test('按账户过滤投资组合', async ({ page }) => {
    // 创建多个账户
    const accounts = [
      { name: `过滤测试A_${Date.now()}`, initialCash: 100000 },
      { name: `过滤测试B_${Date.now()}`, initialCash: 200000 },
    ];

    for (const account of accounts) {
      await paperTradingPage.goto();
      await paperTradingPage.createAccount(account);
    }

    // 按账户过滤
    await portfolioPage.goto();
    await portfolioPage.filterByAccount(accounts[0].name);

    // 验证只显示选中账户的数据
    const summary = await portfolioPage.getPortfolioSummary();
    expect(summary.totalEquity).toBe(100000);
  });

  /**
   * SCAMPER Put to Other Uses: 导出报告
   */
  test('导出投资组合报告 - CSV', async ({ page }) => {
    await portfolioPage.goto();

    // 导出 CSV 报告
    const download = await portfolioPage.exportReport('csv');

    // 验证下载
    expect(download).toBeDefined();
    expect(download.suggestedFilename()).toMatch(/\.csv$/);
  });

  test('导出投资组合报告 - Excel', async ({ page }) => {
    await portfolioPage.goto();

    // 导出 Excel 报告
    const download = await portfolioPage.exportReport('excel');

    // 验证下载
    expect(download).toBeDefined();
    expect(download.suggestedFilename()).toMatch(/\.xlsx?$/);
  });

  /**
   * SCAMPER Modify: 图表可视化验证
   */
  test('权益曲线图表显示', async ({ page }) => {
    // 先创建一些交易数据
    const account = {
      name: `图表测试_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);

    // 查看投资组合
    await portfolioPage.goto();

    // 验证权益图表可见
    await portfolioPage.assertEquityChartVisible();
  });

  test('资产配置图表显示', async ({ page }) => {
    // 创建账户并进行交易
    const account = {
      name: `资产配置_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'buy',
      size: 100,
    });

    // 查看投资组合
    await portfolioPage.goto();

    // 验证资产配置图表可见
    await portfolioPage.assertAllocationChartVisible();
  });

  /**
   * SCAMPER Reverse: 边界情况
   */
  test('空投资组合', async ({ page }) => {
    await portfolioPage.goto();

    // 没有账户时，应该显示空状态
    const summary = await portfolioPage.getPortfolioSummary();
    expect(summary.totalEquity).toBe(0);
    expect(summary.totalCash).toBe(0);
  });

  /**
   * SCAMPER Put to Other Uses: 性能基线
   */
  test('性能基线 - 投资组合计算时间', async ({ page }) => {
    // 创建多个账户以增加计算复杂度
    const accounts = [];
    for (let i = 0; i < 5; i++) {
      accounts.push({
        name: `性能测试${i}_${Date.now()}`,
        initialCash: 100000,
      });
    }

    for (const account of accounts) {
      await paperTradingPage.goto();
      await paperTradingPage.createAccount(account);
    }

    // 测量页面加载时间
    const startTime = Date.now();
    await portfolioPage.goto();
    await portfolioPage.assertOnPortfolioPage();
    const loadTime = Date.now() - startTime;

    console.log(`投资组合页面加载时间 (${accounts.length}个账户): ${loadTime}ms`);

    // 即使有多个账户，页面也应该在 3 秒内加载
    expect(loadTime).toBeLessThan(3000);
  });

  /**
   * SCAMPER Combine: 完整的用户流程
   */
  test('完整流程 - 创建账户、交易、查看投资组合、导出报告', async ({ page }) => {
    // 1. 创建账户
    const account = {
      name: `完整流程_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);

    // 2. 进行交易
    await paperTradingPage.clickAccountByName(account.name);

    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'buy',
      size: 200,
    });

    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'sell',
      size: 100,
    });

    // 3. 查看投资组合
    await portfolioPage.goto();
    const summary = await portfolioPage.getPortfolioSummary();
    expect(summary.totalEquity).toBeGreaterThan(0);

    // 4. 验证持仓
    const positions = await portfolioPage.getAggregatedPositions();
    const position = positions.find(p => p.symbol === '000001.SZ');
    expect(position).toBeDefined();
    expect(position?.totalSize).toBe(100); // 200 - 100

    // 5. 导出报告
    const download = await portfolioPage.exportReport('csv');
    expect(download).toBeDefined();
  });

  /**
   * SCAMPER Eliminate: 验证数据一致性
   */
  test('数据一致性 - 单个账户和投资组合汇总一致', async ({ page }) => {
    const account = {
      name: `一致性测试_${Date.now()}`,
      initialCash: 100000,
    };

    // 创建账户并交易
    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    const accountBalance = await paperTradingPage.getAccountBalance();
    const accountEquity = await paperTradingPage.getAccountEquity();

    // 在投资组合页面验证相同数据
    await portfolioPage.goto();
    await portfolioPage.filterByAccount(account.name);

    const summary = await portfolioPage.getPortfolioSummary();

    // 验证一致性
    expect(summary.totalCash).toBeCloseTo(accountBalance, 0.01);
    expect(summary.totalEquity).toBeCloseTo(accountEquity, 0.01);
  });
});
