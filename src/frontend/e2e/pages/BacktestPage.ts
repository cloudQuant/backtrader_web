import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { BacktestRequest } from '../fixtures/test-data.fixture';

/**
 * 回测页面 Page Object
 *
 * 封装回测配置、执行、结果查看等操作
 */
export class BacktestPage extends BasePage {
  // 回测配置选择器
  readonly strategySelect = '[data-testid="strategy-select"], select[name="strategy_id"]';
  readonly symbolInput = '[data-testid="symbol-input"], input[name="symbol"]';
  readonly startDateInput = '[data-testid="start-date"], input[name="start_date"]';
  readonly endDateInput = '[data-testid="end-date"], input[name="end_date"]';
  readonly initialCashInput = '[data-testid="initial-cash"], input[name="initial_cash"]';
  readonly commissionInput = '[data-testid="commission"], input[name="commission"]';
  readonly runButton = '[data-testid="run-backtest"], button:has-text("运行")';
  readonly stopButton = '[data-testid="stop-backtest"], button:has-text("停止")';

  // 回测状态
  readonly statusIndicator = '[data-testid="backtest-status"], .status';
  readonly progressBar = '[data-testid="progress-bar"], .el-progress';

  // 回测结果
  readonly resultsPanel = '[data-testid="backtest-results"], .results-panel';
  readonly sharpeRatio = '[data-testid="sharpe-ratio"], [data-sharpe]';
  readonly totalReturn = '[data-testid="total-return"], [data-return]';
  readonly maxDrawdown = '[data-testid="max-drawdown"], [data-drawdown]';
  readonly winRate = '[data-testid="win-rate"], [data-winrate]';
  readonly equityChart = '[data-testid="equity-chart"], canvas[data-chart*="equity"]';

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
    await expect(this.page.locator(this.runButton)).toBeVisible();
  }

  /**
   * 填写回测配置表单
   */
  async fillBacktestForm(request: BacktestRequest) {
    if (request.strategy_id) {
      await this.page.selectOption(this.strategySelect, request.strategy_id);
    }
    await this.fill(this.symbolInput, request.symbol);
    await this.fill(this.startDateInput, request.start_date);
    await this.fill(this.endDateInput, request.end_date);
    await this.fill(this.initialCashInput, request.initial_cash.toString());
    await this.fill(this.commissionInput, request.commission.toString());
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
    await this.fillBacktestForm(request);
    await this.clickRun();
  }

  /**
   * 等待回测完成
   *
   * 智能等待：等待 API 响应和状态更新
   */
  async waitForCompletion(timeout: number = 120000) {
    // 等待进度条消失或状态变为完成
    await Promise.race([
      this.page.waitForSelector(this.progressBar, { state: 'hidden', timeout }),
      this.page.waitForSelector(`${this.statusIndicator}:has-text("完成")`, { timeout }),
      this.page.waitForSelector(`${this.statusIndicator}:has-text("completed")`, { timeout }),
    ]);
  }

  /**
   * 等待回测结果显示
   */
  async waitForResults() {
    await this.page.waitForSelector(this.resultsPanel, { state: 'visible', timeout: 120000 });
  }

  /**
   * 断言回测结果可见
   */
  async assertResultsVisible() {
    await expect(this.page.locator(this.resultsPanel)).toBeVisible();
    await expect(this.page.locator(this.equityChart)).toBeVisible();
  }

  /**
   * 获取回测指标
   */
  async getMetrics(): Promise<{
    sharpeRatio: number;
    totalReturn: number;
    maxDrawdown: number;
    winRate: number;
  }> {
    return {
      sharpeRatio: await this.getMetricValue(this.sharpeRatio),
      totalReturn: await this.getMetricValue(this.totalReturn),
      maxDrawdown: await this.getMetricValue(this.maxDrawdown),
      winRate: await this.getMetricValue(this.winRate),
    };
  }

  /**
   * 获取单个指标值
   */
  private async getMetricValue(selector: string): Promise<number> {
    const text = await this.getText(selector);
    const match = text.match(/[-+]?\d*\.?\d+/);
    return match ? parseFloat(match[0]) : 0;
  }

  /**
   * 断言指标在合理范围内
   */
  async assertMetricsValid(metrics?: {
    sharpeRatio?: number;
    totalReturn?: number;
    maxDrawdown?: number;
    winRate?: number;
  }) {
    const actual = await this.getMetrics();

    if (metrics?.sharpeRatio !== undefined) {
      expect(actual.sharpeRatio).toBeCloseTo(metrics.sharpeRatio, 1);
    }
    if (metrics?.totalReturn !== undefined) {
      expect(actual.totalReturn).toBeCloseTo(metrics.totalReturn, 1);
    }
    // 最大回撤应该是负数
    expect(actual.maxDrawdown).toBeLessThan(0);
    // 胜率在 0-100 之间
    expect(actual.winRate).toBeGreaterThanOrEqual(0);
    expect(actual.winRate).toBeLessThanOrEqual(100);
  }
}
