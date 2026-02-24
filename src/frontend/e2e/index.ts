/**
 * E2E 测试入口
 *
 * 导出所有 Page Objects 和 Fixtures 供测试使用
 */

// Page Objects
export { BasePage } from './pages/BasePage';
export { AuthPage } from './pages/AuthPage';
export { DashboardPage } from './pages/DashboardPage';
export { StrategyPage } from './pages/StrategyPage';
export { BacktestPage } from './pages/BacktestPage';

// Fixtures
export { test, authTest, expect } from './fixtures/test-data.fixture';
export {
  UserFactory,
  BacktestRequestFactory,
  StrategyFactory,
} from './fixtures/test-data.fixture';

// Types
export type { UserCredentials, BacktestRequest } from './fixtures/test-data.fixture';
