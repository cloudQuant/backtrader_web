import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { BacktestRequest } from '../fixtures/test-data.fixture';

/**
 * 回测页面 Page Object
 *
 * 适配实际前端 BacktestPage.vue
 */
export class BacktestPage extends BasePage {
  // 回测配置选择器 - 基于 BacktestPage.vue
  readonly cardTitle = '.el-card__header:has-text("回测配置")';
  readonly strategySelect = '.el-select:has(.el-input__inner)';
  readonly runButton = 'button.el-button--primary:has-text("运行回测")';
  readonly stopButton = 'button.el-button--danger:has-text("取消")';
  readonly viewButton = 'button:has-text("查看")';

  // 回测状态
  readonly progressBar = '.el-progress';
  readonly progressText = '.el-progress__text';

  // 回测结果卡片
  readonly resultsCard = '.el-card__header:has-text("回测结果")';
  readonly resultsTable = '.el-table';

  // 关键指标选择器
  readonly totalReturnMetric = '.el-card:has(.text-gray-500:has-text("总收益率"))';
  readonly sharpeRatioMetric = '.el-card:has(.text-gray-500:has-text("夏普比率"))';
  readonly maxDrawdownMetric = '.el-card:has(.text-gray-500:has-text("最大回撤"))';
  readonly winRateMetric = '.el-card:has(.text-gray-500:has-text("胜率"))';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到回测页面
   */
  async goto() {
    await this.navigate('/backtest');
  }

  /**
   * 断言在回测页面
   */
  async assertOnBacktestPage() {
    await expect(this.page.locator(this.cardTitle)).toBeVisible();
  }

  /**
   * 选择策略
   */
  async selectStrategy(strategyName: string) {
    // 点击策略选择器
    await this.page.click('.el-select:has(.el-input__inner)');
    // 等待下拉选项出现
    await this.page.waitForTimeout(500);
    // 选择对应的策略
    await this.page.click(`.el-select-dropdown__item:has-text("${strategyName}")`);
  }

  /**
   * 点击运行回测
   */
  async clickRun() {
    await this.click(this.runButton);
  }

  /**
   * 运行回测的完整流程
   */
  async runBacktest(request: BacktestRequest) {
    await this.goto();
    // 等待页面加载
    await this.page.waitForTimeout(1000);
    // 如果指定了策略，选择它
    if (request.strategy_id) {
      await this.selectStrategy(request.strategy_id);
    }
    await this.clickRun();
  }

  /**
   * 等待回测完成
   */
  async waitForCompletion(timeout: number = 60000) {
    // 等待进度条出现然后消失
    await this.page.waitForSelector(this.progressBar, { state: 'visible', timeout: 5000 }).catch(() => {});
    await this.page.waitForSelector(this.progressBar, { state: 'hidden', timeout }).catch(() => {});
    // 或者等待结果显示
    await this.page.waitForSelector(this.resultsCard, { state: 'visible', timeout: 10000 }).catch(() => {});
  }

  /**
   * 断言回测结果可见
   */
  async assertResultsVisible() {
    await expect(this.page.locator(this.resultsCard)).toBeVisible({ timeout: 10000 });
  }

  /**
   * 获取回测历史记录数
   */
  async getHistoryCount(): Promise<number> {
    await this.page.waitForTimeout(500);
    const rows = this.page.locator('.el-table__body-wrapper .el-table__row');
    return await rows.count();
  }
}
