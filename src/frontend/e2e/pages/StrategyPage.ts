import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * 策略管理页面 Page Object
 *
 * 适配实际前端 Element Plus 组件
 */
export class StrategyPage extends BasePage {
  // 策略列表选择器 - 基于实际 StrategyPage.vue
  readonly pageTitle = 'h1:has-text("策略中心")';
  readonly createButton = 'button:has-text("创建策略")';
  readonly galleryTab = 'button:has-text("策略库")';
  readonly myStrategiesTab = 'button:has-text("我的策略")';

  // 策略卡片选择器
  readonly strategyCard = '.el-card:has(.strategy-card)';

  // 策略表单选择器 - 基于实际 Dialog
  readonly dialogTitle = '.el-dialog__title:has-text("创建策略"), .el-dialog__title:has-text("编辑策略")';
  readonly strategyNameInput = 'input[placeholder="输入策略名称"]';
  readonly strategyDescInput = 'textarea[placeholder="策略描述"]';
  readonly categorySelect = '.el-select:has(.el-input__inner)';
  readonly saveButton = 'button.el-button--primary:has-text("创建"), button.el-button--primary:has-text("保存")';
  readonly cancelButton = 'button:has-text("取消")';

  // 搜索和过滤 - 基于实际组件
  readonly searchInput = 'input[placeholder*="搜索"]';
  readonly categoryFilter = '.el-radio-group';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到策略页面
   */
  async goto() {
    await this.navigate('/strategy');
  }

  /**
   * 断言在策略页面
   */
  async assertOnStrategiesPage() {
    await expect(this.page.locator(this.pageTitle)).toBeVisible();
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
    category?: string;
  }) {
    await this.fill(this.strategyNameInput, data.name);
    if (data.description) {
      await this.fill(this.strategyDescInput, data.description);
    }
    // 代码字段是 Monaco Editor，需要特殊处理
    // 在测试中通常跳过或使用 API 预设数据
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
    await this.waitForTimeout(1000);
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
  async filterByCategory(categoryLabel: string) {
    // 点击对应的分类单选按钮
    await this.page.click(`.el-radio-button:has-text("${categoryLabel}")`);
  }

  /**
   * 获取策略列表数量
   */
  async getStrategyCount(): Promise<number> {
    // 等待策略卡片加载
    await this.page.waitForTimeout(500);
    // 策略卡片在 el-card 内部
    const cards = this.page.locator('.el-card').filter({ hasText: /./ });
    return await cards.count();
  }

  /**
   * 点击策略卡片（通过名称）
   */
  async clickStrategyByName(name: string) {
    const card = this.page.locator('.el-card').filter({ hasText: name });
    await card.click();
  }

  /**
   * 断言策略存在
   */
  async assertStrategyExists(name: string) {
    const card = this.page.locator('.el-card').filter({ hasText: name });
    await expect(card.first()).toBeVisible();
  }

  /**
   * 切换到"我的策略"标签
   */
  async goToMyStrategies() {
    await this.page.click(this.myStrategiesTab);
    await this.page.waitForTimeout(500);
  }
}
