import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 投资组合页面 Page Object
 *
 * 封装投资组合概览、持仓汇总、交易记录等功能
 */
export class PortfolioPage extends BasePage {
  // 概览面板
  readonly totalEquity = '[data-testid="total-equity"], [data-metric="total-equity"]';
  readonly totalCash = '[data-testid="total-cash"], [data-metric="total-cash"]';
  readonly totalPnL = '[data-testid="total-pnl"], [data-metric="total-pnl"]';
  readonly todayPnL = '[data-testid="today-pnl"], [data-metric="today-pnl"]';

  // 权益曲线图表
  readonly equityChart = '[data-testid="equity-chart"], canvas[data-chart*="equity"]';
  readonly dateRangeSelector = '[data-testid="date-range"], .date-range-selector';

  // 资产配置
  readonly allocationChart = '[data-testid="allocation-chart"], canvas[data-chart*="allocation"]';
  readonly allocationLegend = '[data-testid="allocation-legend"], .legend';

  // 汇总持仓
  readonly aggregatedPositions = '[data-testid="aggregated-positions"], .position-list';
  readonly positionRow = '[data-testid="position-row"], .position-row';

  // 汇总交易
  readonly aggregatedTrades = '[data-testid="aggregated-trades"], .trade-list';
  readonly tradeRow = '[data-testid="trade-row"], .trade-row';

  // 过滤器
  readonly accountFilter = '[data-testid="account-filter"], select[name="account"]';
  readonly dateFromInput = '[data-testid="date-from"], input[name="date_from"]';
  readonly dateToInput = '[data-testid="date-to"], input[name="date_to"]';
  readonly applyFilterButton = '[data-testid="apply-filter"], button:has-text("应用")';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到投资组合页面
   */
  async goto() {
    await this.navigate('/portfolio');
  }

  /**
   * 断言在投资组合页面
   */
  async assertOnPortfolioPage() {
    await expect(this.page.locator(this.totalEquity)).toBeVisible();
  }

  /**
   * 获取总权益
   */
  async getTotalEquity(): Promise<number> {
    const text = await this.getText(this.totalEquity);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 获取总现金
   */
  async getTotalCash(): Promise<number> {
    const text = await this.getText(this.totalCash);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 获取总盈亏
   */
  async getTotalPnL(): Promise<number> {
    const text = await this.getText(this.totalPnL);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 获取今日盈亏
   */
  async getTodayPnL(): Promise<number> {
    const text = await this.getText(this.todayPnL);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 获取投资组合摘要
   */
  async getPortfolioSummary(): Promise<{
    totalEquity: number;
    totalCash: number;
    totalPnL: number;
    todayPnL: number;
  }> {
    return {
      totalEquity: await this.getTotalEquity(),
      totalCash: await this.getTotalCash(),
      totalPnL: await this.getTotalPnL(),
      todayPnL: await this.getTodayPnL(),
    };
  }

  /**
   * 按日期范围过滤
   */
  async filterByDateRange(fromDate: string, toDate: string) {
    await this.fill(this.dateFromInput, fromDate);
    await this.fill(this.dateToInput, toDate);
    await this.click(this.applyFilterButton);
    await this.page.waitForTimeout(500);
  }

  /**
   * 按账户过滤
   */
  async filterByAccount(accountName: string) {
    await this.page.selectOption(this.accountFilter, accountName);
    await this.page.waitForTimeout(500);
  }

  /**
   * 获取汇总持仓数量
   */
  async getAggregatedPositionCount(): Promise<number> {
    await this.page.waitForSelector(this.positionRow, { timeout: 5000 });
    return await this.page.locator(this.positionRow).count();
  }

  /**
   * 获取所有汇总持仓
   */
  async getAggregatedPositions(): Promise<Array<{
    symbol: string;
    totalSize: number;
    avgPrice: number;
    marketValue: number;
    pnl: number;
  }>> {
    const positions: Array<{
      symbol: string;
      totalSize: number;
      avgPrice: number;
      marketValue: number;
      pnl: number;
    }> = [];

    const count = await this.getAggregatedPositionCount();
    for (let i = 0; i < count; i++) {
      const row = this.page.locator(this.positionRow).nth(i);
      const symbol = await row.locator('[data-symbol], .symbol').textContent() || '';
      const sizeText = await row.locator('[data-size], .size').textContent() || '0';
      const priceText = await row.locator('[data-price], .price').textContent() || '0';
      const valueText = await row.locator('[data-value], .value').textContent() || '0';
      const pnlText = await row.locator('[data-pnl], .pnl').textContent() || '0';

      positions.push({
        symbol: symbol.trim(),
        totalSize: parseFloat(sizeText.replace(/[^0-9.-]/g, '')),
        avgPrice: parseFloat(priceText.replace(/[^0-9.-]/g, '')),
        marketValue: parseFloat(valueText.replace(/[^0-9.-]/g, '')),
        pnl: parseFloat(pnlText.replace(/[^0-9.-]/g, '')),
      });
    }

    return positions;
  }

  /**
   * 获取汇总交易记录数量
   */
  async getAggregatedTradeCount(): Promise<number> {
    await this.page.waitForSelector(this.tradeRow, { timeout: 5000 });
    return await this.page.locator(this.tradeRow).count();
  }

  /**
   * 断言权益图表可见
   */
  async assertEquityChartVisible() {
    await expect(this.page.locator(this.equityChart)).toBeVisible();
  }

  /**
   * 断言资产配置图表可见
   */
  async assertAllocationChartVisible() {
    await expect(this.page.locator(this.allocationChart)).toBeVisible();
  }

  /**
   * 导出投资组合报告
   */
  async exportReport(format: 'csv' | 'excel' = 'csv') {
    const exportButton = `[data-testid="export-${format}"], button:has-text("导出${format === 'csv' ? 'CSV' : 'Excel'}")`;
    await this.click(exportButton);

    // 等待下载开始
    const [download] = await Promise.all([
      this.page.waitForEvent('download'),
      this.click(exportButton)
    ]);

    return download;
  }
}
