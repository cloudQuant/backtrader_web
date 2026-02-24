import { test, expect } from '@playwright/test';
import { LiveTradingPage } from '../pages/LiveTradingPage';
import { UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 实盘交易管理 E2E 测试
 *
 * SCAMPER 应用:
 * - Modify: 细化的状态检查
 * - Reverse: 测试异常状态转换
 * - Eliminate: 独立的测试实例
 */
test.describe('实盘交易管理', () => {
  let liveTradingPage: LiveTradingPage;

  test.beforeEach(async ({ page }) => {
    // 登录
    const authPage = new AuthPage(page);
    await authPage.login(UserFactory.createAdmin());

    liveTradingPage = new LiveTradingPage(page);
  });

  test('查看实盘交易页面', async ({ page }) => {
    await liveTradingPage.goto();
    await liveTradingPage.assertOnLiveTradingPage();

    // 验证添加实例按钮可见
    await expect(page.locator(liveTradingPage.addInstanceButton)).toBeVisible();
  });

  test('创建实盘实例', async ({ page }) => {
    const instance = {
      name: `测试实例_${Date.now()}`,
      symbol: '000001.SZ',
      broker: 'simulator',  // 使用模拟经纪人进行测试
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);

    // 验证创建成功
    await liveTradingPage.waitForToast('创建成功');
    const count = await liveTradingPage.getInstanceCount();
    expect(count).toBeGreaterThan(0);
  });

  /**
   * SCAMPER Combine: 完整的实例生命周期
   */
  test('实例完整生命周期 - 创建、启动、停止、删除', async ({ page }) => {
    const instance = {
      name: `生命周期测试_${Date.now()}`,
      symbol: '000001.SZ',
    };

    // 1. 创建实例
    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);
    await liveTradingPage.waitForToast('创建成功');

    // 2. 启动实例
    await liveTradingPage.startInstance(instance.name);

    // 3. 验证实例状态
    await liveTradingPage.assertInstanceRunning(instance.name);

    // 4. 停止实例
    await liveTradingPage.stopInstance(instance.name);
    await liveTradingPage.waitForToast('停止成功');

    // 5. 验证停止状态
    await liveTradingPage.assertInstanceStopped(instance.name);

    // 6. 删除实例
    const card = page.locator(liveTradingPage.instanceCard).filter({ hasText: instance.name });
    await card.locator('[data-testid="delete-instance"], button:has-text("删除"]').click();
    await page.click('.el-button--primary:has-text("确定")');
    await liveTradingPage.waitForToast('删除成功');
  });

  test('查看实例详情 - 持仓', async ({ page }) => {
    const instance = {
      name: `详情查看_${Date.now()}`,
      symbol: '000001.SZ',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);
    await liveTradingPage.viewInstanceDetails(instance.name);

    // 切换到持仓选项卡
    await liveTradingPage.showPositions();

    // 验证持仓面板可见
    await expect(page.locator(liveTradingPage.positionTab)).toHaveClass(/active/);
  });

  test('查看实例详情 - 订单', async ({ page }) => {
    const instance = {
      name: `订单查看_${Date.now()}`,
      symbol: '600519.SH',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);
    await liveTradingPage.viewInstanceDetails(instance.name);

    // 切换到订单选项卡
    await liveTradingPage.showOrders();

    // 验证订单面板可见
    await expect(page.locator(liveTradingPage.orderTab)).toHaveClass(/active/);
  });

  test('查看实例详情 - 日志', async ({ page }) => {
    const instance = {
      name: `日志查看_${Date.now()}`,
      symbol: '000001.SZ',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);

    // 启动实例以生成日志
    await liveTradingPage.startInstance(instance.name);
    await liveTradingPage.viewInstanceDetails(instance.name);

    // 切换到日志选项卡
    await liveTradingPage.showLogs();

    // 验证日志可见
    await expect(page.locator(liveTradingPage.instanceLog)).toBeVisible();

    // 停止实例
    await liveTradingPage.stopInstance(instance.name);
  });

  /**
   * SCAMPER Reverse: 异常状态转换
   */
  test('状态转换异常 - 启动已运行的实例', async ({ page }) => {
    const instance = {
      name: `重复启动_${Date.now()}`,
      symbol: '000001.SZ',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);
    await liveTradingPage.startInstance(instance.name);

    // 尝试再次启动
    await liveTradingPage.startInstance(instance.name);

    // 验证显示警告
    await expect(page.locator('.el-message--warning')).toBeVisible();

    // 清理
    await liveTradingPage.stopInstance(instance.name);
  });

  test('状态转换异常 - 停止未运行的实例', async ({ page }) => {
    const instance = {
      name: `未运行停止_${Date.now()}`,
      symbol: '000001.SZ',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);

    // 实例未运行时尝试停止
    const card = page.locator(liveTradingPage.instanceCard).filter({ hasText: instance.name });
    await card.locator(liveTradingPage.stopButton).click();

    // 验证显示错误提示
    await expect(page.locator('.el-message--error')).toBeVisible();
  });

  /**
   * SCAMPER Modify: 细化实例状态监控
   */
  test('实时状态监控', async ({ page }) => {
    const instance = {
      name: `状态监控_${Date.now()}`,
      symbol: '000001.SZ',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);

    // 获取初始状态
    const initialStatus = await liveTradingPage.getInstanceStatus(instance.name);

    // 启动实例
    await liveTradingPage.startInstance(instance.name);

    // 验证状态变化
    const runningStatus = await liveTradingPage.getInstanceStatus(instance.name);
    expect(runningStatus).not.toBe(initialStatus);

    // 停止实例
    await liveTradingPage.stopInstance(instance.name);

    // 验证状态回到停止
    const stoppedStatus = await liveTradingPage.getInstanceStatus(instance.name);
    expect(stoppedStatus).toMatch(/stopped|已停止/);
  });

  /**
   * SCAMPER Put to Other Uses: 日志验证
   *
   * 验证实例日志记录关键操作
   */
  test('日志验证 - 记录关键操作', async ({ page }) => {
    const instance = {
      name: `日志验证_${Date.now()}`,
      symbol: '000001.SZ',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);
    await liveTradingPage.viewInstanceDetails(instance.name);
    await liveTradingPage.showLogs();

    // 启动实例
    await liveTradingPage.startInstance(instance.name);

    // 等待日志出现启动信息
    await liveTradingPage.waitForLogText('启动', 10000);
    await liveTradingPage.waitForLogText('running|运行中', 10000);

    // 验证日志包含实例名称
    const logs = await liveTradingPage.getInstanceLogs();
    const logText = logs.join(' ');
    expect(logText).toContain(instance.name);

    // 清理
    await liveTradingPage.stopInstance(instance.name);
  });

  test('多个实例管理', async ({ page }) => {
    const instances = [
      { name: `实例1_${Date.now()}`, symbol: '000001.SZ' },
      { name: `实例2_${Date.now()}`, symbol: '600519.SH' },
    ];

    // 创建多个实例
    for (const instance of instances) {
      await liveTradingPage.goto();
      await liveTradingPage.createInstance(instance);
    }

    // 验证所有实例都存在
    await liveTradingPage.goto();
    const count = await liveTradingPage.getInstanceCount();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  /**
   * SCAMPER Eliminate: 使用 API 准备策略
   */
  test('使用现有策略创建实例', async ({ page, request }) => {
    // 通过 API 创建策略
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

    const strategyResponse = await apiContext.post('/api/v1/strategy/', {
      headers: { Authorization: `Bearer ${access_token}` },
      json: {
        name: `实盘策略_${Date.now()}`,
        description: '用于实盘测试',
        code: 'class LiveStrategy(bt.Strategy):\n    pass',
        params: {},
        category: 'trend',
      },
    });

    const { id: strategyId } = await strategyResponse.json();
    await apiContext.dispose();

    // 使用该策略创建实盘实例
    const instance = {
      name: `策略实例_${Date.now()}`,
      symbol: '000001.SZ',
      strategyId: strategyId.toString(),
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(instance);

    // 验证实例创建成功
    await liveTradingPage.waitForToast('创建成功');

    // 验证策略名称显示
    const card = page.locator(liveTradingPage.instanceCard).filter({ hasText: instance.name });
    await expect(card).toBeVisible();
  });

  /**
   * SCAMPER Reverse: 边界情况 - 无效参数
   */
  test('创建实例失败 - 无效股票代码', async ({ page }) => {
    const invalidInstance = {
      name: `无效代码_${Date.now()}`,
      symbol: 'INVALID_SYMBOL',
    };

    await liveTradingPage.goto();
    await liveTradingPage.createInstance(invalidInstance);

    // 验证显示错误
    await expect(page.locator('.el-message--error')).toBeVisible();
  });
});
