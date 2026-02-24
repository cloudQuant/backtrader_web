import { test, expect } from '@playwright/test';
import { PaperTradingPage } from '../pages/PaperTradingPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 模拟交易功能 E2E 测试
 *
 * SCAMPER 应用:
 * - Combine: 创建账户、下单、查看持仓的完整流程
 * - Eliminate: 独立的测试数据
 * - Reverse: 测试边界条件（资金不足、无效订单等）
 */
test.describe('模拟交易', () => {
  let paperTradingPage: PaperTradingPage;

  test.beforeEach(async ({ page }) => {
    // 登录
    const authPage = new AuthPage(page);
    await authPage.login(UserFactory.createAdmin());

    paperTradingPage = new PaperTradingPage(page);
  });

  test('查看模拟交易页面', async ({ page }) => {
    await paperTradingPage.goto();
    await paperTradingPage.assertOnPaperTradingPage();

    // 验证创建账户按钮可见
    await expect(page.locator(paperTradingPage.createAccountButton)).toBeVisible();
  });

  test('创建新的模拟账户', async ({ page }) => {
    const account = {
      name: `测试账户_${Date.now()}`,
      initialCash: 100000,
      commission: 0.001,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);

    // 验证创建成功
    await paperTradingPage.waitForToast('创建成功');
    const count = await paperTradingPage.getAccountCount();
    expect(count).toBeGreaterThan(0);
  });

  /**
   * SCAMPER Reverse: 测试边界条件
   */
  test('创建账户失败 - 资金为负数', async ({ page }) => {
    const invalidAccount = {
      name: `无效账户_${Date.now()}`,
      initialCash: -1000,
      commission: 0.001,
    };

    await paperTradingPage.goto();
    await paperTradingPage.click(paperTradingPage.createAccountButton);
    await paperTradingPage.fill(paperTradingPage.accountNameInput, invalidAccount.name);
    await paperTradingPage.fill(paperTradingPage.initialCashInput, invalidAccount.initialCash.toString());
    await paperTradingPage.click(paperTradingPage.saveAccountButton);

    // 验证显示验证错误
    await expect(page.locator('.el-form-item__error')).toContainText('资金');
  });

  test('创建账户失败 - 名称重复', async ({ page }) => {
    const account = {
      name: `重复账户_${Date.now()}`,
      initialCash: 50000,
    };

    // 创建第一个账户
    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);

    // 尝试创建同名账户
    await paperTradingPage.createAccount(account);

    // 验证显示错误
    await expect(page.locator('.el-message--error')).toBeVisible();
  });

  /**
   * SCAMPER Combine: 完整的账户使用流程
   */
  test('完整账户流程 - 创建、查看余额、下单、查看持仓', async ({ page }) => {
    // 1. 创建账户
    const account = {
      name: `完整测试账户_${Date.now()}`,
      initialCash: 100000,
      commission: 0.001,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);

    // 2. 点击账户查看详情
    await paperTradingPage.clickAccountByName(account.name);

    // 3. 验证余额显示正确
    const balance = await paperTradingPage.getAccountBalance();
    expect(balance).toBe(account.initialCash);

    // 4. 下市价买入单
    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      orderType: 'market',
      side: 'buy',
      size: 100,
    });

    // 5. 验证订单成功
    await paperTradingPage.waitForToast('下单成功');

    // 6. 查看持仓
    const positionCount = await paperTradingPage.getPositionCount();
    expect(positionCount).toBeGreaterThan(0);

    // 7. 验证持仓数据
    const positions = await paperTradingPage.getPositions();
    expect(positions[0].symbol).toBe('000001.SZ');
    expect(positions[0].size).toBe(100);
  });

  test('卖出持仓', async ({ page }) => {
    const account = {
      name: `卖出测试_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    // 先买入
    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'buy',
      size: 100,
    });

    // 再卖出
    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'sell',
      size: 50,
    });

    await paperTradingPage.waitForToast('下单成功');

    // 验证持仓减少
    const positions = await paperTradingPage.getPositions();
    expect(positions[0].size).toBe(50);
  });

  /**
   * SCAMPER Reverse: 边界情况 - 资金不足
   */
  test('下单失败 - 资金不足', async ({ page }) => {
    const account = {
      name: `资金不足_${Date.now()}`,
      initialCash: 1000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    // 尝试买入超出资金的股票
    await paperTradingPage.placeOrder({
      symbol: '600519.SH',  // 贵州茅台，价格较高
      side: 'buy',
      size: 100,
    });

    // 验证显示资金不足错误
    const toast = await paperTradingPage.getToastMessage();
    expect(toast).toMatch(/资金|余额/);
  });

  test('下单失败 - 卖空（无持仓）', async ({ page }) => {
    const account = {
      name: `无持仓账户_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    // 尝试卖出没有持仓的股票
    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'sell',
      size: 100,
    });

    // 验证显示持仓不足错误
    const toast = await paperTradingPage.getToastMessage();
    expect(toast).toMatch(/持仓|不足/);
  });

  test('查看多个账户的总览', async ({ page }) => {
    // 创建多个账户
    const accounts = [
      { name: `账户A_${Date.now()}`, initialCash: 100000 },
      { name: `账户B_${Date.now()}`, initialCash: 200000 },
    ];

    for (const account of accounts) {
      await paperTradingPage.goto();
      await paperTradingPage.createAccount(account);
    }

    // 验证账户列表
    await paperTradingPage.goto();
    const count = await paperTradingPage.getAccountCount();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  /**
   * SCAMPER Put to Other Uses: 性能监控
   *
   * 记录页面加载时间作为性能基线
   */
  test('性能基线 - 页面加载时间', async ({ page }) => {
    const startTime = Date.now();

    await paperTradingPage.goto();
    await paperTradingPage.assertOnPaperTradingPage();

    const loadTime = Date.now() - startTime;
    console.log(`模拟交易页面加载时间: ${loadTime}ms`);

    // 页面应该在 2 秒内加载完成
    expect(loadTime).toBeLessThan(2000);
  });

  test('实时数据更新', async ({ page }) => {
    const account = {
      name: `实时更新_${Date.now()}`,
      initialCash: 100000,
    };

    await paperTradingPage.goto();
    await paperTradingPage.createAccount(account);
    await paperTradingPage.clickAccountByName(account.name);

    // 下单后，验证余额和权益更新
    const balanceBefore = await paperTradingPage.getAccountBalance();

    await paperTradingPage.placeOrder({
      symbol: '000001.SZ',
      side: 'buy',
      size: 100,
    });

    // 等待数据刷新
    await page.waitForTimeout(500);

    const balanceAfter = await paperTradingPage.getAccountBalance();
    // 余额应该减少（扣除保证金）
    expect(balanceAfter).toBeLessThan(balanceBefore);

    // 权益应该更新
    const equity = await paperTradingPage.getAccountEquity();
    expect(equity).toBeGreaterThan(0);
  });
});
