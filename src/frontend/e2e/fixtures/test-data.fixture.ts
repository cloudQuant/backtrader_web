import { test as base } from '@playwright/test';

/**
 * E2E 测试数据工厂
 *
 * 适应后端 tests/factories.py 模式到前端测试
 * 提供一致的测试数据生成，避免硬编码
 */

export interface UserCredentials {
  username: string;
  email: string;
  password: string;
}

export interface BacktestRequest {
  strategy_id?: string;
  symbol: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  commission: number;
}

/**
 * 用户数据工厂
 */
export class UserFactory {
  /**
   * 生成唯一的测试用户数据
   */
  static create(overrides: Partial<UserCredentials> = {}): UserCredentials {
    const timestamp = Date.now();
    const random = Math.random().toString(36).substring(7);
    const username = `testuser_${timestamp}_${random}`;

    return {
      username: overrides.username || username,
      email: overrides.email || `${username}@test.example.com`,
      password: overrides.password || 'Test12345678',
    };
  }

  /**
   * 生成管理员用户
   */
  static createAdmin(): UserCredentials {
    return {
      username: 'admin',
      email: 'admin@test.example.com',
      password: 'Admin12345678',
    };
  }
}

/**
 * 回测请求数据工厂
 */
export class BacktestRequestFactory {
  static create(overrides: Partial<BacktestRequest> = {}): BacktestRequest {
    return {
      symbol: '000001.SZ',
      start_date: '2024-01-01',
      end_date: '2024-06-30',
      initial_cash: 100000,
      commission: 0.001,
      ...overrides,
    };
  }

  static createWithCustomStrategy(
    strategyId: string,
    overrides: Partial<BacktestRequest> = {}
  ): BacktestRequest {
    return this.create({
      strategy_id: strategyId,
      ...overrides,
    });
  }
}

/**
 * 策略数据工厂
 */
export class StrategyFactory {
  static create(overrides: Record<string, any> = {}) {
    return {
      name: `测试策略_${Date.now()}`,
      description: '自动化测试生成的策略',
      code: 'class TestStrategy(bt.Strategy):\n    pass',
      params: {},
      category: 'custom',
      ...overrides,
    };
  }
}

/**
 * 扩展的 test fixture，包含工厂方法
 */
export const test = base.extend<{
  userFactory: typeof UserFactory;
  backtestFactory: typeof BacktestRequestFactory;
  strategyFactory: typeof StrategyFactory;
}>({
  userFactory: async ({}, use) => {
    await use(UserFactory);
  },
  backtestFactory: async ({}, use) => {
    await use(BacktestRequestFactory);
  },
  strategyFactory: async ({}, use) => {
    await use(StrategyFactory);
  },
});

/**
 * 认证 fixture - 保存和加载会话状态
 *
 * 基于 SCAMPER Eliminate: 使用 storageState 消除重复登录
 */
export const authTest = base.extend<{
  authenticatedPage: Page;
}>({
  authenticatedPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: 'e2e/fixtures/storage-state.json',
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { expect } from '@playwright/test';
