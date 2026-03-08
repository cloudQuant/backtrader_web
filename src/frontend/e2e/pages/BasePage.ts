import { Page, Locator, expect } from '@playwright/test';

/**
 * 基础页面类
 *
 * Page Object Model 模式
 * 封装常用页面操作和断言
 */
export abstract class BasePage {
  readonly page: Page;
  readonly baseURL: string;

  constructor(page: Page) {
    this.page = page;
    this.baseURL = process.env.BASE_URL || 'http://localhost:3000';
  }

  /**
   * 导航到页面
   */
  async navigate(path: string = '') {
    await this.page.goto(`${this.baseURL}${path}`);
  }

  /**
   * 刷新页面
   */
  async reload() {
    await this.page.reload();
  }

  /**
   * 等待元素可见（智能等待，替代 sleep）
   */
  async waitForVisible(selector: string, timeout: number = 5000) {
    await this.page.waitForSelector(selector, { state: 'visible', timeout });
  }

  /**
   * 等待元素隐藏
   */
  async waitForHidden(selector: string, timeout: number = 5000) {
    await this.page.waitForSelector(selector, { state: 'hidden', timeout });
  }

  /**
   * 点击元素
   */
  async click(selector: string, options?: { timeout?: number }) {
    await this.page.waitForSelector(selector, { state: 'visible' });
    await this.page.click(selector, options);
  }

  /**
   * 填写输入框
   */
  async fill(selector: string, value: string) {
    await this.page.waitForSelector(selector, { state: 'visible' });
    await this.page.fill(selector, value);
  }

  /**
   * 获取文本内容
   */
  async getText(selector: string): Promise<string> {
    await this.page.waitForSelector(selector, { state: 'visible' });
    return await this.page.textContent(selector) || '';
  }

  /**
   * 断言元素可见
   */
  async assertVisible(selector: string) {
    await expect(this.page.locator(selector)).toBeVisible();
  }

  /**
   * 断言元素包含文本
   */
  async assertTextContains(selector: string, text: string) {
    await expect(this.page.locator(selector)).toContainText(text);
  }

  /**
   * 断言 URL 包含路径
   */
  async assertURLContains(path: string) {
    await expect(this.page).toHaveURL(new RegExp(`${path}$`));
  }

  /**
   * 截图（用于调试）
   */
  async screenshot(name: string) {
    await this.page.screenshot({ path: `e2e-results/screenshots/${name}.png` });
  }

  /**
   * 等待 API 响应
   */
  async waitForAPIResponse(urlPattern: string | RegExp, timeout: number = 30000) {
    return await this.page.waitForResponse(
      (response) => response.url().match(urlPattern) !== null,
      { timeout }
    );
  }

  /**
   * 获取 Toast 消息
   */
  async getToastMessage(): Promise<string | null> {
    const toast = this.page.locator('.el-message__content, [role="alert"]');
    if (await toast.count() > 0) {
      return await toast.first().textContent();
    }
    return null;
  }

  /**
   * 等待 Toast 出现并消失
   */
  async waitForToast(message?: string) {
    const toast = this.page.locator('.el-message__content, [role="alert"]');
    if (message) {
      await expect(toast).toContainText(message);
    } else {
      await toast.waitFor({ state: 'visible' });
    }
    await toast.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
  }
}
