import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 仪表板页面 Page Object
 *
 * 封装仪表板相关操作
 */
export class DashboardPage extends BasePage {
  // 仪表板选择器
  readonly welcomeMessage = '[data-testid="welcome-message"], h1';
  readonly quickActions = '[data-testid="quick-actions"]';
  readonly statsCards = '.stat-card, [data-testid*="stat"]';

  // 导航菜单
  readonly strategiesMenu = '[data-testid="menu-strategies"], a:has-text("策略")';
  readonly backtestMenu = '[data-testid="menu-backtest"], a:has-text("回测")';
  readonly tradingMenu = '[data-testid="menu-trading"], a:has-text("交易")';
  readonly portfolioMenu = '[data-testid="menu-portfolio"], a:has-text("组合")';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到仪表板
   */
  async goto() {
    await this.navigate('/dashboard');
  }

  /**
   * 断言在仪表板页面
   */
  async assertOnDashboard() {
    await expect(this.page.locator(this.welcomeMessage)).toBeVisible();
  }

  /**
   * 导航到策略管理
   */
  async gotoStrategies() {
    await this.click(this.strategiesMenu);
  }

  /**
   * 导航到回测
   */
  async gotoBacktest() {
    await this.click(this.backtestMenu);
  }

  /**
   * 导航到交易
   */
  async gotoTrading() {
    await this.click(this.tradingMenu);
  }

  /**
   * 导航到投资组合
   */
  async gotoPortfolio() {
    await this.click(this.portfolioMenu);
  }

  /**
   * 获取统计卡片数据
   */
  async getStatValue(statName: string): Promise<number> {
    const selector = `[data-testid="stat-${statName}"], .stat-card:has-text("${statName}")`;
    const text = await this.getText(selector);
    const match = text.match(/[\d,]+\.?\d*/);
    return match ? parseFloat(match[0].replace(/,/g, '')) : 0;
  }
}
