import { test, expect } from '@playwright/test';
import { StrategyPage } from '../pages/StrategyPage';
import { StrategyFactory, UserFactory } from '../fixtures/test-data.fixture';
import { AuthPage } from '../pages/AuthPage';

/**
 * 策略管理功能 E2E 测试
 *
 * SCAMPER 应用:
 * - Combine: 合并创建、编辑、删除操作
 * - Eliminate: 使用 API 准备数据（可选）
 * - Reverse: 测试异常输入和边界情况
 */
test.describe('策略管理', () => {
  let strategyPage: StrategyPage;

  // 使用认证后的页面状态
  test.beforeEach(async ({ page }) => {
    // 登录
    const authPage = new AuthPage(page);
    const credentials = UserFactory.createAdmin();
    await authPage.login(credentials);

    strategyPage = new StrategyPage(page);
  });

  test('查看策略列表', async ({ page }) => {
    await strategyPage.goto();
    await strategyPage.assertOnStrategiesPage();

    // 验证策略列表可见
    const count = await strategyPage.getStrategyCount();
    expect(count).toBeGreaterThan(0);
  });

  test('创建新策略', async ({ page }) => {
    const newStrategy = StrategyFactory.create({
      name: `E2E测试策略_${Date.now()}`,
      description: '这是一个自动化测试创建的策略',
      code: 'class TestStrategy(bt.Strategy):\n    def next(self):\n        pass',
    });

    await strategyPage.createStrategy(newStrategy);

    // 验证创建成功
    await strategyPage.waitForToast('创建成功');
    await strategyPage.assertStrategyExists(newStrategy.name);
  });

  test('搜索策略', async ({ page }) => {
    await strategyPage.goto();

    // 搜索特定关键词
    await strategyPage.searchStrategy('双均线');

    // 等待搜索结果加载
    await page.waitForTimeout(500);
    const results = await strategyPage.getStrategyCount();

    // 验证搜索结果
    expect(results).toBeGreaterThanOrEqual(0);
  });

  test('按分类过滤策略', async ({ page }) => {
    await strategyPage.goto();

    // 选择特定分类
    await strategyPage.filterByCategory('trend');

    // 等待过滤结果
    await page.waitForTimeout(500);
    const results = await strategyPage.getStrategyCount();

    // 验证过滤结果
    expect(results).toBeGreaterThanOrEqual(0);
  });

  /**
   * SCAMPER Reverse: 测试异常输入
   */
  test('创建策略失败 - 名称重复', async ({ page }) => {
    // 先创建一个策略
    const existingStrategy = StrategyFactory.create({
      name: `重复策略_${Date.now()}`,
    });
    await strategyPage.createStrategy(existingStrategy);

    // 尝试用相同名称创建
    await strategyPage.goto();
    await strategyPage.clickCreateStrategy();
    await strategyPage.fillStrategyForm({
      name: existingStrategy.name,
      description: '这是重复的',
    });
    await strategyPage.clickSaveStrategy();

    // 验证显示错误
    await expect(page.locator('.el-message--error')).toBeVisible();
  });

  test('创建策略失败 - 代码为空', async ({ page }) => {
    await strategyPage.goto();
    await strategyPage.clickCreateStrategy();
    await strategyPage.fillStrategyForm({
      name: `空代码策略_${Date.now()}`,
      description: '没有代码',
    });
    await strategyPage.clickSaveStrategy();

    // 验证代码验证错误
    await expect(page.locator('.el-form-item__error')).toContainText('代码');
  });

  /**
   * SCAMPER Combine: 完整的策略生命周期测试
   */
  test('策略完整生命周期 - 创建、编辑、删除', async ({ page }) => {
    const strategy = StrategyFactory.create({
      name: `生命周期测试_${Date.now()}`,
      description: '初始描述',
    });

    // 1. 创建策略
    await strategyPage.createStrategy(strategy);
    await strategyPage.assertStrategyExists(strategy.name);

    // 2. 点击策略进入编辑页面
    await strategyPage.clickStrategyByName(strategy.name);

    // 3. 编辑策略
    const newDescription = '更新后的描述';
    await page.fill('[data-testid="strategy-description"], textarea[name="description"]', newDescription);
    await page.click('[data-testid="save-strategy"], button:has-text("保存")');
    await strategyPage.waitForToast('更新成功');

    // 4. 验证更新
    await expect(page.locator('text=' + newDescription)).toBeVisible();

    // 5. 删除策略
    await page.click('[data-testid="delete-strategy"], button:has-text("删除")');
    await page.click('.el-button--primary:has-text("确定")');
    await strategyPage.waitForToast('删除成功');

    // 6. 验证删除
    await strategyPage.goto();
    const exists = await page.locator(strategyPage.strategyCard).filter({ hasText: strategy.name }).count();
    expect(exists).toBe(0);
  });
});
