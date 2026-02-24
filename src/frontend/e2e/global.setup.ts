import { FullConfig } from '@playwright/test';

/**
 * 全局测试设置
 *
 * 在所有测试运行前执行，用于设置全局测试环境
 */
async function globalSetup(config: FullConfig) {
  // 这里可以设置全局测试环境，比如创建测试数据等
  console.log('Global setup: E2E tests starting...');
}

export default globalSetup;
