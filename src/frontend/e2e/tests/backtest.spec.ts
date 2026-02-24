import { test, expect } from '@playwright/test';
import { BacktestPage } from '../pages/BacktestPage';
import { StrategyPage } from '../pages/StrategyPage';
import { BacktestRequestFactory, UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 回测功能 E2E 测试
 *
 * SCAMPER 应用:
 * - Combine: 合并配置、运行、结果验证
 * - Put to Other Uses: 记录性能基线
 * - Modify: 细化断言粒度
 */
test.describe('回测功能', () => {
  let backtestPage: BacktestPage;

  test.beforeEach(async ({ page }) => {
    // 登录
    const authPage = new AuthPage(page);
    const credentials = UserFactory.createAdmin();
    await authPage.login(credentials);

    backtestPage = new BacktestPage(page);
  });

  test('回测页面加载', async ({ page }) => {
    await backtestPage.goto();
    await backtestPage.assertOnBacktestPage();

    // 验证所有配置选项可见
    await expect(page.locator(backtestPage.strategySelect)).toBeVisible();
    await expect(page.locator(backtestPage.symbolInput)).toBeVisible();
    await expect(page.locator(backtestPage.startDateInput)).toBeVisible();
    await expect(page.locator(backtestPage.endDateInput)).toBeVisible();
    await expect(page.locator(backtestPage.runButton)).toBeVisible();
  });

  /**
   * SCAMPER Combine: 完整的回测流程测试
   *
   * 从配置到查看结果的端到端测试
   */
  test('完整回测流程 - 配置、运行、查看结果', async ({ page }) => {
    // 准备回测请求
    const request = BacktestRequestFactory.create({
      symbol: '000001.SZ',
      start_date: '2024-01-01',
      end_date: '2024-06-30',
    });

    // 运行回测
    await backtestPage.runBacktest(request);

    // 等待回测完成
    // 注意：实际回测可能需要较长时间，这里设置较长超时
    await backtestPage.waitForCompletion();

    // 验证结果显示
    await backtestPage.assertResultsVisible();

    // 获取并验证指标
    const metrics = await backtestPage.getMetrics();
    expect(metrics.totalReturn).toBeDefined();
    expect(metrics.maxDrawdown).toBeLessThan(0);
    expect(metrics.winRate).toBeGreaterThanOrEqual(0);
    expect(metrics.winRate).toBeLessThanOrEqual(100);
  });

  test('回测表单验证', async ({ page }) => {
    await backtestPage.goto();

    // 尝试不填写任何字段直接运行
    await backtestPage.clickRun();

    // 验证表单验证错误
    const errors = page.locator('.el-form-item__error');
    await expect(errors.first()).toBeVisible();
  });

  test('回测表单验证 - 日期范围错误', async ({ page }) => {
    await backtestPage.goto();

    // 填写无效日期范围
    await backtestPage.fillBacktestForm({
      symbol: '000001.SZ',
      start_date: '2024-06-30',  // 结束日期晚于开始日期
      end_date: '2024-01-01',
      initial_cash: 100000,
      commission: 0.001,
    });

    await backtestPage.clickRun();

    // 验证日期验证错误
    await expect(page.locator('.el-message--error')).toContainText('日期');
  });

  /**
   * SCAMPER Put to Other Uses: 性能基线测试
   *
   * 记录回测执行时间作为性能基线
   */
  test('性能基线 - 回测执行时间', async ({ page }) => {
    const request = BacktestRequestFactory.create();

    await backtestPage.goto();
    await backtestPage.fillBacktestForm(request);

    // 记录开始时间
    const startTime = Date.now();

    await backtestPage.clickRun();
    await backtestPage.waitForCompletion();

    const executionTime = Date.now() - startTime;

    // 记录性能基线
    console.log(`回测执行时间: ${executionTime}ms`);

    // 断言性能在合理范围内（例如 2 分钟内）
    expect(executionTime).toBeLessThan(120000);

    // 可选：保存到文件用于趋势分析
    // fs.appendFileSync('e2e-results/performance-baseline.json', JSON.stringify({
    //   date: new Date().toISOString(),
    //   executionTime
    // }));
  });

  /**
   * SCAMPER Reverse: 测试边界情况
   */
  test('边界情况 - 极短日期范围', async ({ page }) => {
    const request = BacktestRequestFactory.create({
      start_date: '2024-01-01',
      end_date: '2024-01-05',  // 只有 4 天
    });

    await backtestPage.runBacktest(request);
    await backtestPage.waitForCompletion();

    // 应该仍然能够完成，但可能结果有限
    await backtestPage.assertResultsVisible();
  });

  test('边界情况 - 极小初始资金', async ({ page }) => {
    const request = BacktestRequestFactory.create({
      initial_cash: 1000,  // 非常小的资金
    });

    await backtestPage.runBacktest(request);
    await backtestPage.waitForCompletion();

    // 应该显示资金不足的警告或错误
    const toast = await backtestPage.getToastMessage();
    expect(toast).toBeTruthy();
  });

  /**
   * SCAMPER Modify: 并发测试控制
   *
   * 验证只能有一个回测同时运行
   */
  test('并发控制 - 同时运行多个回测', async ({ page }) => {
    const request = BacktestRequestFactory.create();

    // 启动第一个回测
    await backtestPage.goto();
    await backtestPage.fillBacktestForm(request);
    await backtestPage.clickRun();

    // 等待状态变为运行中
    await page.waitForSelector(backtestPage.progressBar);

    // 尝试启动第二个回测
    await backtestPage.clickRun();

    // 验证显示警告（已有回测正在运行）
    await expect(page.locator('.el-message--warning')).toBeVisible();
  });

  /**
   * SCAMPER Eliminate: 使用 API 准备数据
   *
   * 通过 API 直接创建策略，跳过 UI 操作
   */
  test('使用 API 准备数据的快速回测', async ({ page, request }) => {
    // 通过 API 创建测试策略
    const apiContext = await request.newContext({
      baseURL: process.env.API_BASE_URL || 'http://localhost:8000',
    });

    const loginResponse = await apiContext.post('/api/v1/auth/login', {
      json: {
        username: 'admin',
        password: 'Admin12345678',
      },
    });
    const { access_token } = await loginResponse.json();

    // 创建策略
    await apiContext.post('/api/v1/strategy/', {
      headers: { Authorization: `Bearer ${access_token}` },
      json: {
        name: `API测试策略_${Date.now()}`,
        description: '通过API创建',
        code: 'class APIStrategy(bt.Strategy):\n    pass',
        params: {},
        category: 'custom',
      },
    });

    await apiContext.dispose();

    // 现在在 UI 中运行回测
    await backtestPage.goto();
    await backtestPage.runBacktest(
      BacktestRequestFactory.create()
    );

    await backtestPage.waitForCompletion();
    await backtestPage.assertResultsVisible();
  });
});

/**
 * SCAMPER Combine: 策略到回测的完整流程
 */
test.describe('完整用户流程 - 创建策略并回测', () => {
  test('从策略创建到回测结果', async ({ page }) => {
    // 1. 登录
    const authPage = new AuthPage(page);
    await authPage.login(UserFactory.createAdmin());

    // 2. 创建策略
    const strategyPage = new StrategyPage(page);
    const strategy = {
      name: `双均线测试_${Date.now()}`,
      description: '用于回测的测试策略',
      code: 'class DualMA(bt.Strategy):\n    pass',
    };
    await strategyPage.createStrategy(strategy);

    // 3. 跳转到回测页面
    const backtestPage = new BacktestPage(page);
    await backtestPage.goto();

    // 4. 配置并运行回测
    await backtestPage.runBacktest(
      BacktestRequestFactory.create()
    );

    // 5. 等待结果
    await backtestPage.waitForCompletion();
    await backtestPage.assertResultsVisible();

    // 6. 验证策略名称显示
    await expect(page.locator(`text=${strategy.name}`)).toBeVisible();
  });
});
