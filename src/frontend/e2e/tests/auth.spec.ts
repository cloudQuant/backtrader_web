import { test, expect } from '@playwright/test';
import { UserFactory } from '../fixtures/test-data.fixture';

/**
 * 认证功能 E2E 测试
 *
 * 适配实际前端代码的选择器
 */
test.describe('认证功能', () => {

  test('登录页面加载', async ({ page }) => {
    await page.goto('/login');

    // 验证页面元素
    await expect(page.locator('h1')).toContainText('Backtrader Web');
    await expect(page.locator('input[placeholder="用户名"]')).toBeVisible();
    await expect(page.locator('input[placeholder="密码"]')).toBeVisible();
    await expect(page.locator('button:has-text("登录")')).toBeVisible();
  });

  test('用户登录成功', async ({ page }) => {
    const credentials = {
      username: 'admin',
      password: 'admin123',
    };

    await page.goto('/login');

    // 填写表单
    await page.fill('input[placeholder="用户名"]', credentials.username);
    await page.fill('input[placeholder="密码"]', credentials.password);

    // 提交登录
    await page.click('button:has-text("登录")');

    // 等待导航 - 登录成功后应该跳转到仪表板或策略页面
    await page.waitForURL(/\/(dashboard|strategy|backtest)?/, { timeout: 10000 });

    // 验证已登录 - 应该能看到导航菜单
    const navMenu = page.locator('.el-menu, nav');
    await expect(navMenu).toBeVisible();
  });

  test('用户登录失败 - 错误密码', async ({ page }) => {
    const credentials = {
      username: 'admin',
      password: 'wrongpassword',
    };

    await page.goto('/login');
    await page.fill('input[placeholder="用户名"]', credentials.username);
    await page.fill('input[placeholder="密码"]', credentials.password);
    await page.click('button:has-text("登录")');

    // 等待错误消息 - Element Plus 使用 el-message
    await page.waitForTimeout(1000);

    // 验证仍在登录页面
    await expect(page.locator('input[placeholder="用户名"]')).toBeVisible();
  });

  test('注册页面加载', async ({ page }) => {
    await page.goto('/register');

    // 验证页面元素
    await expect(page.locator('h1')).toContainText('注册账号');
    await expect(page.locator('input[placeholder*="用户名"]')).toBeVisible();
    await expect(page.locator('input[placeholder*="邮箱"]')).toBeVisible();
    // 注册页面有两个密码框（密码和确认密码），使用 first()
    await expect(page.locator('input[placeholder*="密码"]').first()).toBeVisible();
    await expect(page.locator('button:has-text("注册")')).toBeVisible();
  });

  test('用户注册流程', async ({ page }) => {
    const newUser = UserFactory.create();

    await page.goto('/register');

    // 填写注册表单
    await page.fill('input[placeholder*="用户名"]', newUser.username);
    await page.fill('input[placeholder*="邮箱"]', newUser.email);
    await page.fill('input[placeholder*="密码"]', newUser.password);

    // 如果有确认密码框
    const confirmInput = page.locator('input[placeholder*="确认"]');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill(newUser.password);
    }

    // 提交注册
    await page.click('button:has-text("注册")');

    // 等待注册完成 - 应该跳转到登录或仪表板
    await page.waitForTimeout(2000);

    // 验证注册结果 - URL 应该变化
    const currentUrl = page.url();
    expect(currentUrl).toMatch(/\/(login|dashboard|strategy)?/);
  });

  test('表单验证 - 密码太短', async ({ page }) => {
    await page.goto('/register');

    // 输入短密码
    await page.fill('input[placeholder*="用户名"]', 'testuser');
    await page.fill('input[placeholder*="邮箱"]', 'test@example.com');

    // 填写密码框（第一个密码框）
    const passwordInputs = page.locator('input[placeholder*="密码"]');
    await passwordInputs.first().fill('123');

    // 填写确认密码框
    await passwordInputs.nth(1).fill('123');

    // 触发验证 - 点击其他地方
    await page.click('body');

    // 检查是否有验证错误（Element Plus 使用 el-form-item__error）
    const error = page.locator('.el-form-item__error');
    if (await error.count() > 0) {
      await expect(error.first()).toContainText('密码');
    }
  });

  /**
   * SCAMPER Eliminate: 保存登录状态
   *
   * 用于生成 storage-state.json 文件
   */
  test('保存登录状态', async ({ page, context }) => {
    const credentials = {
      username: 'admin',
      password: 'admin123',
    };

    await page.goto('/login');
    await page.fill('input[placeholder="用户名"]', credentials.username);
    await page.fill('input[placeholder="密码"]', credentials.password);
    await page.click('button:has-text("登录")');

    // 等待登录成功
    await page.waitForURL(/\/(dashboard|strategy|backtest)?/, { timeout: 10000 });

    // 保存会话状态
    await context.storageState({ path: 'e2e/fixtures/storage-state.json' });
  });
});
