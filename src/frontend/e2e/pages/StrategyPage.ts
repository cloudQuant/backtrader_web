import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 策略管理页面 Page Object
 *
 * 封装策略创建、编辑、删除等操作
 */
export class StrategyPage extends BasePage {
  // 策略列表选择器
  readonly strategyList = '[data-testid="strategy-list"], .strategy-list';
  readonly strategyCard = '[data-testid="strategy-card"], .strategy-card';
  readonly createButton = '[data-testid="create-strategy-button"], button:has-text("创建策略")';

  // 策略表单选择器
  readonly strategyNameInput = '[data-testid="strategy-name"], input[name="name"]';
  readonly strategyDescInput = '[data-testid="strategy-description"], textarea[name="description"]';
  readonly strategyCodeInput = '[data-testid="strategy-code"], textarea[name="code"], .monaco-editor';
  readonly saveButton = '[data-testid="save-strategy"], button:has-text("保存")';
  readonly cancelButton = '[data-testid="cancel-strategy"], button:has-text("取消")';

  // 搜索和过滤
  readonly searchInput = '[data-testid="search-input"], input[placeholder*="搜索"]';
  readonly categoryFilter = '[data-testid="category-filter"], select[name="category"]';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到策略页面
   */
  async goto() {
    await this.navigate('/strategies');
  }

  /**
   * 断言在策略页面
   */
  async assertOnStrategiesPage() {
    await expect(this.page.locator(this.strategyList)).toBeVisible();
  }

  /**
   * 点击创建策略按钮
   */
  async clickCreateStrategy() {
    await this.click(this.createButton);
  }

  /**
   * 填写策略表单
   */
  async fillStrategyForm(data: {
    name: string;
    description?: string;
    code?: string;
  }) {
    await this.fill(this.strategyNameInput, data.name);
    if (data.description) {
      await this.fill(this.strategyDescInput, data.description);
    }
    if (data.code) {
      // 对于 Monaco Editor，可能需要特殊处理
      await this.page.evaluate(
        ([selector, code]) => {
          const editor = document.querySelector(selector) as any;
          if (editor && editor.editor) {
            editor.editor.setValue(code);
          } else {
            const textarea = document.querySelector('textarea[name="code"]');
            if (textarea) textarea.value = code;
          }
        },
        [this.strategyCodeInput, data.code]
      );
    }
  }

  /**
   * 点击保存策略
   */
  async clickSaveStrategy() {
    await this.click(this.saveButton);
  }

  /**
   * 创建策略的完整流程
   */
  async createStrategy(data: {
    name: string;
    description?: string;
    code?: string;
  }) {
    await this.goto();
    await this.clickCreateStrategy();
    await this.fillStrategyForm(data);
    await this.clickSaveStrategy();
    await this.waitForToast();
  }

  /**
   * 搜索策略
   */
  async searchStrategy(keyword: string) {
    await this.fill(this.searchInput, keyword);
  }

  /**
   * 按分类过滤
   */
  async filterByCategory(category: string) {
    await this.page.selectOption(this.categoryFilter, category);
  }

  /**
   * 获取策略列表数量
   */
  async getStrategyCount(): Promise<number> {
    await this.page.waitForSelector(this.strategyCard, { timeout: 5000 });
    return await this.page.locator(this.strategyCard).count();
  }

  /**
   * 点击策略卡片（通过名称）
   */
  async clickStrategyByName(name: string) {
    const card = this.page.locator(this.strategyCard).filter({ hasText: name });
    await card.click();
  }

  /**
   * 断言策略存在
   */
  async assertStrategyExists(name: string) {
    const card = this.page.locator(this.strategyCard).filter({ hasText: name });
    await expect(card).toBeVisible();
  }
}
