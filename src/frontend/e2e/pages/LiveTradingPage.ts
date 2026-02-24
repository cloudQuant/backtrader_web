import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 实盘交易管理 Page Object
 *
 * 封装实盘实例的创建、启动、停止、监控等操作
 */
export class LiveTradingPage extends BasePage {
  // 实例管理选择器
  readonly addInstanceButton = '[data-testid="add-instance"], button:has-text("添加实例")';

  // 实例表单
  readonly instanceNameInput = '[data-testid="instance-name"], input[name="name"]';
  readonly strategySelect = '[data-testid="strategy-select"], select[name="strategy_id"]';
  readonly symbolInput = '[data-testid="symbol-input"], input[name="symbol"]';
  readonly brokerSelect = '[data-testid="broker-select"], select[name="broker"]';
  readonly saveInstanceButton = '[data-testid="save-instance"], button:has-text("保存")';

  // 实例列表
  readonly instanceList = '[data-testid="instance-list"], .instance-list';
  readonly instanceCard = '[data-testid="instance-card"], .instance-card';

  // 实例状态
  readonly statusIndicator = '[data-testid="status"], .status';
  readonly startButton = '[data-testid="start-button"], button:has-text("启动")';
  readonly stopButton = '[data-testid="stop-button"], button:has-text("停止")';
  readonly restartButton = '[data-testid="restart-button"], button:has-text("重启")';

  // 实例详情
  readonly positionTab = '[data-testid="tab-positions"], tab:has-text("持仓")';
  readonly orderTab = '[data-testid="tab-orders"], tab:has-text("订单")';
  readonly tradeTab = '[data-testid="tab-trades"], tab:has-text("成交")';
  readonly logTab = '[data-testid="tab-logs"], tab:has-text("日志")';

  // 详情面板
  readonly instanceLog = '[data-testid="instance-log"], .instance-log';
  readonly metricsPanel = '[data-testid="metrics"], .metrics';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到实盘交易页面
   */
  async goto() {
    await this.navigate('/live-trading');
  }

  /**
   * 断言在实盘交易页面
   */
  async assertOnLiveTradingPage() {
    await expect(this.page.locator(this.addInstanceButton)).toBeVisible();
  }

  /**
   * 创建实盘实例
   */
  async createInstance(instance: {
    name: string;
    strategyId?: string;
    symbol: string;
    broker?: string;
  }) {
    await this.click(this.addInstanceButton);

    await this.fill(this.instanceNameInput, instance.name);

    if (instance.strategyId) {
      await this.page.selectOption(this.strategySelect, instance.strategyId);
    }

    await this.fill(this.symbolInput, instance.symbol);

    if (instance.broker) {
      await this.page.selectOption(this.brokerSelect, instance.broker);
    }

    await this.click(this.saveInstanceButton);
    await this.waitForToast();
  }

  /**
   * 获取实例数量
   */
  async getInstanceCount(): Promise<number> {
    await this.page.waitForSelector(this.instanceCard, { timeout: 5000 });
    return await this.page.locator(this.instanceCard).count();
  }

  /**
   * 启动实例
   */
  async startInstance(instanceName: string) {
    const card = this.page.locator(this.instanceCard).filter({ hasText: instanceName });
    await card.locator(this.startButton).click();
    await this.waitForToast();
  }

  /**
   * 停止实例
   */
  async stopInstance(instanceName: string) {
    const card = this.page.locator(this.instanceCard).filter({ hasText: instanceName });
    await card.locator(this.stopButton).click();
    await this.waitForToast();
  }

  /**
   * 获取实例状态
   */
  async getInstanceStatus(instanceName: string): Promise<string> {
    const card = this.page.locator(this.instanceCard).filter({ hasText: instanceName });
    const status = await card.locator(this.statusIndicator).textContent() || '';
    return status.trim();
  }

  /**
   * 断言实例正在运行
   */
  async assertInstanceRunning(instanceName: string) {
    const status = await this.getInstanceStatus(instanceName);
    expect(status.toLowerCase()).toMatch(/running|运行中/);
  }

  /**
   * 断言实例已停止
   */
  async assertInstanceStopped(instanceName: string) {
    const status = await this.getInstanceStatus(instanceName);
    expect(status.toLowerCase()).toMatch(/stopped|stopped|已停止/);
  }

  /**
   * 查看实例详情
   */
  async viewInstanceDetails(instanceName: string) {
    const card = this.page.locator(this.instanceCard).filter({ hasText: instanceName });
    await card.click();

    // 等待详情面板加载
    await expect(this.page.locator(this.positionTab)).toBeVisible();
  }

  /**
   * 切换到持仓选项卡
   */
  async showPositions() {
    await this.click(this.positionTab);
    await this.page.waitForTimeout(300);
  }

  /**
   * 切换到订单选项卡
   */
  async showOrders() {
    await this.click(this.orderTab);
    await this.page.waitForTimeout(300);
  }

  /**
   * 切换到成交选项卡
   */
  async showTrades() {
    await this.click(this.tradeTab);
    await this.page.waitForTimeout(300);
  }

  /**
   * 切换到日志选项卡
   */
  async showLogs() {
    await this.click(this.logTab);
    await this.page.waitForTimeout(300);
  }

  /**
   * 获取实例日志
   */
  async getInstanceLogs(): Promise<string[]> {
    const logs: string[] = [];
    const logLines = await this.page.locator(this.instanceLog).locator('.log-line, p, div').all();

    for (const line of logLines) {
      const text = await line.textContent();
      if (text) logs.push(text.trim());
    }

    return logs;
  }

  /**
   * 等待日志包含特定文本
   */
  async waitForLogText(text: string, timeout: number = 30000) {
    await this.page.waitForSelector(
      `${this.instanceLog}:has-text("${text}")`,
      { timeout }
    );
  }
}
