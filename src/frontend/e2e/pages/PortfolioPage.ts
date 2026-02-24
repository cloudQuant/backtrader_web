import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 投资组合页面 Page Object
 *
 * 适配实际前端 PortfolioPage.vue
 */
export class PortfolioPage extends BasePage {
  // 概览卡片选择器 - 基于 PortfolioPage.vue
  readonly totalAssetsCard = '.el-card:has(.text-gray-500:has-text("组合总资产"))';
  readonly totalPnLCard = '.el-card:has(.text-gray-500:has-text("总盈亏"))';

  // 标签页
  readonly strategiesTab = 'button:has-text("策略概览")';
  readonly positionsTab = 'button:has-text("当前持仓")';
  readonly tradesTab = 'button:has-text("交易记录")';
  readonly equityTab = 'button:has-text("资金曲线")';
  readonly allocationTab = 'button:has-text("资产配置")';

  // 表格
  readonly strategiesTable = '.el-table';
  readonly tableRow = '.el-table__row';

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
    // 等待页面加载
    await this.page.waitForTimeout(1000);
    // 至少应该有一些卡片或内容
    const hasContent = await this.page.locator('.el-card').count() > 0;
    expect(hasContent).toBeTruthy();
  }

  /**
   * 切换到策略概览标签
   */
  async goToStrategiesTab() {
    await this.page.click(this.strategiesTab);
    await this.page.waitForTimeout(500);
  }

  /**
   * 切换到持仓标签
   */
  async goToPositionsTab() {
    await this.page.click(this.positionsTab);
    await this.page.waitForTimeout(500);
  }

  /**
   * 切换到交易记录标签
   */
  async goToTradesTab() {
    await this.page.click(this.tradesTab);
    await this.page.waitForTimeout(500);
  }

  /**
   * 切换到资金曲线标签
   */
  async goToEquityTab() {
    await this.page.click(this.equityTab);
    await this.page.waitForTimeout(500);
  }

  /**
   * 切换到资产配置标签
   */
  async goToAllocationTab() {
    await this.page.click(this.allocationTab);
    await this.page.waitForTimeout(500);
  }

  /**
   * 获取策略表格行数
   */
  async getStrategyCount(): Promise<number> {
    await this.page.waitForTimeout(500);
    const rows = this.page.locator(this.tableRow);
    return await rows.count();
  }

  /**
   * 等待数据加载
   */
  async waitForDataLoad() {
    await this.page.waitForSelector('.el-card', { state: 'visible', timeout: 10000 });
    await this.page.waitForTimeout(500);
  }
}
