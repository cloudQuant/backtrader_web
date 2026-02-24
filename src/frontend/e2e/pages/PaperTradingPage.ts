import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { UserFactory } from '../fixtures/test-data.fixture';

/**
 * 模拟交易账户 Page Object
 *
 * 封装模拟交易账户的创建、管理、下单等操作
 */
export class PaperTradingPage extends BasePage {
  // 账户管理选择器
  readonly createAccountButton = '[data-testid="create-account-button"], button:has-text("创建账户")';
  readonly accountNameInput = '[data-testid="account-name"], input[name="name"]';
  readonly initialCashInput = '[data-testid="initial-cash"], input[name="initial_cash"]';
  readonly commissionInput = '[data-testid="commission"], input[name="commission_rate"]';
  readonly saveAccountButton = '[data-testid="save-account"], button:has-text("保存")';

  // 账户列表
  readonly accountList = '[data-testid="account-list"], .account-list';
  readonly accountCard = '[data-testid="account-card"], .account-card';

  // 账户详情
  readonly accountBalance = '[data-testid="account-balance"], [data-balance]';
  readonly accountEquity = '[data-testid="account-equity"], [data-equity]';
  readonly accountPnL = '[data-testid="account-pnl"], [data-pnl]';

  // 订单管理
  readonly placeOrderButton = '[data-testid="place-order"], button:has-text("下单")';
  readonly symbolInput = '[data-testid="order-symbol"], input[name="symbol"]';
  readonly orderTypeSelect = '[data-testid="order-type"], select[name="order_type"]';
  readonly sideSelect = '[data-testid="order-side"], select[name="side"]';
  readonly sizeInput = '[data-testid="order-size"], input[name="size"]';
  readonly priceInput = '[data-testid="order-price"], input[name="price"]';
  readonly submitOrderButton = '[data-testid="submit-order"], button:has-text("提交")';
  readonly orderList = '[data-testid="order-list"], .order-list';

  // 持仓
  readonly positionList = '[data-testid="position-list"], .position-list';
  readonly positionCard = '[data-testid="position-card"], .position-card';

  // 交易记录
  readonly tradeList = '[data-testid="trade-list"], .trade-list';

  constructor(page: Page) {
    super(page);
  }

  /**
   * 导航到模拟交易页面
   */
  async goto() {
    await this.navigate('/paper-trading');
  }

  /**
   * 断言在模拟交易页面
   */
  async assertOnPaperTradingPage() {
    await expect(this.page.locator(this.createAccountButton)).toBeVisible();
  }

  /**
   * 创建新账户
   */
  async createAccount(account: {
    name: string;
    initialCash?: number;
    commission?: number;
  }) {
    await this.click(this.createAccountButton);
    await this.fill(this.accountNameInput, account.name);

    if (account.initialCash !== undefined) {
      await this.fill(this.initialCashInput, account.initialCash.toString());
    }
    if (account.commission !== undefined) {
      await this.fill(this.commissionInput, account.commission.toString());
    }

    await this.click(this.saveAccountButton);
    await this.waitForToast();
  }

  /**
   * 获取账户数量
   */
  async getAccountCount(): Promise<number> {
    await this.page.waitForSelector(this.accountCard, { timeout: 5000 });
    return await this.page.locator(this.accountCard).count();
  }

  /**
   * 点击账户卡片（通过名称）
   */
  async clickAccountByName(name: string) {
    const card = this.page.locator(this.accountCard).filter({ hasText: name });
    await card.click();
  }

  /**
   * 获取账户余额
   */
  async getAccountBalance(): Promise<number> {
    const text = await this.getText(this.accountBalance);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 获取账户权益
   */
  async getAccountEquity(): Promise<number> {
    const text = await this.getText(this.accountEquity);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 获取盈亏
   */
  async getPnL(): Promise<number> {
    const text = await this.getText(this.accountPnL);
    return parseFloat(text.replace(/[^0-9.-]/g, ''));
  }

  /**
   * 下单
   */
  async placeOrder(order: {
    symbol: string;
    orderType?: 'market' | 'limit';
    side: 'buy' | 'sell';
    size: number;
    price?: number;
  }) {
    await this.click(this.placeOrderButton);

    await this.fill(this.symbolInput, order.symbol);

    if (order.orderType) {
      await this.page.selectOption(this.orderTypeSelect, order.orderType);
    }
    await this.page.selectOption(this.sideSelect, order.side);
    await this.fill(this.sizeInput, order.size.toString());

    if (order.price) {
      await this.fill(this.priceInput, order.price.toString());
    }

    await this.click(this.submitOrderButton);
    await this.waitForToast();
  }

  /**
   * 获取持仓数量
   */
  async getPositionCount(): Promise<number> {
    const positions = this.page.locator(this.positionCard);
    return await positions.count();
  }

  /**
   * 获取所有持仓
   */
  async getPositions(): Promise<Array<{
    symbol: string;
    size: number;
    price: number;
    pnl: number;
  }>> {
    const positions: Array<{
      symbol: string;
      size: number;
      price: number;
      pnl: number;
    }> = [];

    const count = await this.getPositionCount();
    for (let i = 0; i < count; i++) {
      const card = this.page.locator(this.positionCard).nth(i);
      const symbol = await card.locator('[data-symbol], .symbol').textContent() || '';
      const sizeText = await card.locator('[data-size], .size').textContent() || '0';
      const priceText = await card.locator('[data-price], .price').textContent() || '0';
      const pnlText = await card.locator('[data-pnl], .pnl').textContent() || '0';

      positions.push({
        symbol: symbol.trim(),
        size: parseFloat(sizeText.replace(/[^0-9.-]/g, '')),
        price: parseFloat(priceText.replace(/[^0-9.-]/g, '')),
        pnl: parseFloat(pnlText.replace(/[^0-9.-]/g, '')),
      });
    }

    return positions;
  }
}
