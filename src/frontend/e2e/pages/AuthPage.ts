import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { UserCredentials } from '../fixtures/test-data.fixture';

/**
 * 认证页面 Page Object
 *
 * 封装登录、注册、密码管理等功能
 */
export class AuthPage extends BasePage {
  // 登录页面选择器
  readonly usernameInput = '[data-testid="username-input"], input[name="username"], input[placeholder*="用户名"]';
  readonly passwordInput = '[data-testid="password-input"], input[name="password"], input[placeholder*="密码"], input[type="password"]';
  readonly emailInput = '[data-testid="email-input"], input[name="email"], input[placeholder*="邮箱"]';
  readonly loginButton = '[data-testid="login-button"], button:has-text("登录")';
  readonly registerButton = '[data-testid="register-button"], button:has-text("注册")';
  readonly errorMessage = '.el-message--error, [role="alert"]';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到登录页面
   */
  async gotoLogin() {
    await this.navigate('/login');
  }

  /**
   * 导航到注册页面
   */
  async gotoRegister() {
    await this.navigate('/register');
  }

  /**
   * 填写登录表单
   */
  async fillLogin(credentials: Pick<UserCredentials, 'username' | 'password'>) {
    await this.fill(this.usernameInput, credentials.username);
    await this.fill(this.passwordInput, credentials.password);
  }

  /**
   * 填写注册表单
   */
  async fillRegister(credentials: UserCredentials) {
    await this.fill(this.usernameInput, credentials.username);
    await this.fill(this.emailInput, credentials.email);
    await this.fill(this.passwordInput, credentials.password);
  }

  /**
   * 点击登录按钮
   */
  async clickLogin() {
    await this.click(this.loginButton);
  }

  /**
   * 点击注册按钮
   */
  async clickRegister() {
    await this.click(this.registerButton);
  }

  /**
   * 执行登录操作
   */
  async login(credentials: Pick<UserCredentials, 'username' | 'password'>) {
    await this.gotoLogin();
    await this.fillLogin(credentials);
    await this.clickLogin();

    // 等待登录完成 - 检查 URL 变化或成功提示
    // 登录成功后会跳转到 / (Dashboard)
    await this.page.waitForURL(/\//, { timeout: 10000 });
    // 等待页面加载
    await this.page.waitForTimeout(1000);
  }

  /**
   * 执行注册操作
   */
  async register(credentials: UserCredentials) {
    await this.gotoRegister();
    await this.fillRegister(credentials);
    await this.clickRegister();

    // 等待注册完成
    await this.waitForToast();
  }

  /**
   * 断言登录成功
   */
  async assertLoginSuccess() {
    // 检查是否跳转到仪表板或策略页面
    await expect(this.page.url()).toMatch(/\/(dashboard|strategies)?/);
  }

  /**
   * 断言显示错误消息
   */
  async assertError(message: string) {
    await expect(this.page.locator(this.errorMessage)).toContainText(message);
  }

  /**
   * 断言在登录页面
   */
  async assertOnLoginPage() {
    await expect(this.page.locator(this.loginButton)).toBeVisible();
  }

  /**
   * 保存登录状态（用于消除重复登录）
   *
   * SCAMPER Eliminate: 使用 storageState 保存会话
   */
  async saveAuthState(filePath: string = 'e2e/fixtures/storage-state.json') {
    await this.page.context().storageState({ path: filePath });
  }
}
