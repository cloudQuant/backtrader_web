import { test, expect } from '@playwright/test';
import { AuthPage } from '../pages/AuthPage';
import { DashboardPage } from '../pages/DashboardPage';
import { UserFactory } from '../fixtures/test-data.fixture';

/**
 * 认证功能 E2E 测试
 *
 * 测试用户登录、注册、登出等核心认证流程
 *
 * SCAMPER 应用:
 * - Substitute: 用智能等待替代 sleep
 * - Combine: 在一个测试中覆盖登录和跳转验证
 * - Eliminate: 每个测试独立，无依赖
 */
test.describe('认证功能', () => {
  let authPage: AuthPage;
  let dashboardPage: DashboardPage;

  test.beforeEach(async ({ page }) => {
    authPage = new AuthPage(page);
    dashboardPage = new DashboardPage(page);
  });

  test('用户登录成功', async ({ page }) => {
    // 准备测试数据
    const credentials = UserFactory.createAdmin();

    // 执行登录
    await authPage.gotoLogin();
    await authPage.fillLogin(credentials);
    await authPage.clickLogin();

    // 验证登录成功 - 跳转到仪表板
    await authPage.assertLoginSuccess();
    await dashboardPage.assertOnDashboard();
  });

  test('用户登录失败 - 错误密码', async ({ page }) => {
    const credentials = {
      username: 'admin',
      password: 'WrongPassword123',
    };

    await authPage.gotoLogin();
    await authPage.fillLogin(credentials);
    await authPage.clickLogin();

    // 验证显示错误消息
    await authPage.assertError('用户名或密码错误');
    await authPage.assertOnLoginPage();
  });

  test('用户登录失败 - 不存在的用户', async ({ page }) => {
    const credentials = {
      username: `nonexistent_${Date.now()}`,
      password: 'Test12345678',
    };

    await authPage.gotoLogin();
    await authPage.fillLogin(credentials);
    await authPage.clickLogin();

    // 验证显示错误消息
    await authPage.assertError('用户不存在');
  });

  test('用户注册成功', async ({ page }) => {
    // 生成唯一测试用户
    const newUser = UserFactory.create();

    await authPage.gotoRegister();
    await authPage.fillRegister(newUser);
    await authPage.clickRegister();

    // 验证注册成功
    await authPage.waitForToast('注册成功');
    await authPage.assertLoginSuccess();
  });

  test('用户注册失败 - 用户名重复', async ({ page }) => {
    const existingUser = UserFactory.createAdmin();
    const newUser = UserFactory.create({
      username: existingUser.username,
      email: `different_${Date.now()}@test.com`,
    });

    await authPage.gotoRegister();
    await authPage.fillRegister(newUser);
    await authPage.clickRegister();

    // 验证显示错误消息
    await authPage.assertError('用户名已存在');
  });

  test('用户注册失败 - 邮箱格式错误', async ({ page }) => {
    const invalidUser = UserFactory.create({
      email: 'not-an-email',
    });

    await authPage.gotoRegister();
    await authPage.fillRegister(invalidUser);
    await authPage.clickRegister();

    // 验证显示格式验证错误
    await expect(page.locator('.el-form-item__error')).toContainText('邮箱格式');
  });

  test('表单验证 - 密码太短', async ({ page }) => {
    const shortPasswordUser = UserFactory.create({
      password: '123',
    });

    await authPage.gotoRegister();
    await authPage.fillRegister(shortPasswordUser);

    // 密码输入框应该显示验证错误
    const passwordInput = page.locator(authPage.passwordInput);
    await passwordInput.blur();
    await expect(page.locator('.el-form-item__error')).toContainText('密码');
  });

  /**
   * SCAMPER Eliminate: 保存登录状态以消除其他测试的重复登录
   *
   * 此测试用于生成 storage-state.json 文件
   * 在 CI/CD 中可以作为 setup 脚本运行
   */
  test('保存登录状态', async ({ page }) => {
    const credentials = UserFactory.createAdmin();

    await authPage.login(credentials);

    // 保存会话状态
    await authPage.saveAuthState('e2e/fixtures/storage-state.json');

    // 验证保存成功
    expect(page.context().storageState()).toBeDefined();
  });
});

/**
 * SCAMPER Combine: 合并多个流程的完整用户旅程测试
 */
test.describe('用户旅程 - 从注册到查看仪表板', () => {
  test('新用户首次使用流程', async ({ page }) => {
    const authPage = new AuthPage(page);
    const dashboardPage = new DashboardPage(page);

    // 1. 注册
    const newUser = UserFactory.create();
    await authPage.register(newUser);
    await authPage.waitForToast('注册成功');

    // 2. 自动登录到仪表板
    await dashboardPage.assertOnDashboard();

    // 3. 验证欢迎消息显示用户名
    await expect(page.locator('h1, .welcome')).toContainText(newUser.username);
  });
});
