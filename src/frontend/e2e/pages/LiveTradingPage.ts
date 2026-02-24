import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 实盘交易管理 Page Object
 *
 * 适配实际前端 LiveTradingPage.vue
 */
export class LiveTradingPage extends BasePage {
  // 实例管理选择器 - 基于 LiveTradingPage.vue
  readonly pageTitle = 'h3:has-text("实盘交易")';
  readonly addInstanceButton = 'button:has-text("添加策略")';
  readonly startAllButton = 'button:has-text("一键启动")';
  readonly stopAllButton = 'button:has-text("一键停止")';

  // 实例表单
  readonly dialogTitle = '.el-dialog__title:has-text("添加实盘策略")';
  readonly strategySelect = '.el-select:has(.el-input__inner)';
  readonly saveInstanceButton = 'button.el-button--primary:has-text("添加")';
  readonly cancelButton = 'button:has-text("取消")';

  // 实例列表
  readonly instanceCard = '.el-card';

  // 实例状态标签
  readonly runningTag = '.el-tag--success';
  readonly stoppedTag = '.el-tag--info';
  readonly errorTag = '.el-tag--danger';

  // 实例操作按钮
  readonly startButton = 'button:has-text("启动")';
  readonly stopButton = 'button:has-text("停止")';
  readonly deleteButton = 'button:has-text("删除")';

  // 详情相关
  readonly analyzeButton = 'button:has-text("分析")';

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
    await expect(this.page.locator(this.pageTitle)).toBeVisible();
  }

  /**
   * 打开添加实例对话框
   */
  async openAddDialog() {
    await this.click(this.addInstanceButton);
    await this.page.waitForSelector(this.dialogTitle, { timeout: 5000 });
  }

  /**
   * 选择策略（在对话框中）
   */
  async selectStrategy(strategyId: string) {
    // 点击策略选择器
    await this.page.click('.el-select .el-input__inner');
    await this.page.waitForTimeout(500);
    // 选择策略
    await this.page.click(`.el-select-dropdown__item:has-text("${strategyId}")`);
  }

  /**
   * 点击添加按钮
   */
  async clickAdd() {
    await this.click(this.saveInstanceButton);
  }

  /**
   * 创建实盘实例（简化版）
   */
  async createInstance(strategyId: string) {
    await this.openAddDialog();
    await this.selectStrategy(strategyId);
    await this.clickAdd();
    await this.page.waitForTimeout(1000);
  }

  /**
   * 获取实例数量
   */
  async getInstanceCount(): Promise<number> {
    await this.page.waitForTimeout(500);
    return await this.page.locator(this.instanceCard).count();
  }

  /**
   * 获取指定实例的卡片
   */
  getInstanceCard(instanceId: string) {
    return this.page.locator(this.instanceCard).filter({ hasText: instanceId });
  }

  /**
   * 启动实例
   */
  async startInstance(instanceId: string) {
    const card = this.getInstanceCard(instanceId);
    await card.locator(this.startButton).click();
    await this.page.waitForTimeout(1000);
  }

  /**
   * 停止实例
   */
  async stopInstance(instanceId: string) {
    const card = this.getInstanceCard(instanceId);
    await card.locator(this.stopButton).click();
    await this.page.waitForTimeout(1000);
  }

  /**
   * 删除实例
   */
  async deleteInstance(instanceId: string) {
    const card = this.getInstanceCard(instanceId);
    await card.locator(this.deleteButton).click();
    await this.page.waitForTimeout(500);
  }

  /**
   * 获取实例状态
   */
  async getInstanceStatus(instanceId: string): Promise<string> {
    const card = this.getInstanceCard(instanceId);
    const status = await card.locator('.el-tag').first().textContent() || '';
    return status.trim();
  }
}
