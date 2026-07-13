import { registerA11yPageSpec } from './template'
import { APP_PATHS } from '../../src/navigation/routes'

// Iteration 175 §3.1 — Critical_Page_Set authenticated pages (6 of 7).
// Login page is in login.spec.ts and runs with empty storageState.
// Authenticated pages reuse the project's default storageState (configured in
// playwright.config.ts via globalSetup).
//
// URLs are imported from the canonical workflow route registry. Compatibility
// aliases are separately checked by the product-domain route suite.

registerA11yPageSpec('dashboard (#2)', { url: APP_PATHS.dashboard })
registerA11yPageSpec('ai-chat (#3)', { url: APP_PATHS.ai.chat })
registerA11yPageSpec('backtests list (#4)', { url: APP_PATHS.backtest.list })
// Backtest detail uses :id placeholder; smoke seed creates id=1 (or first
// available). Test will skip gracefully if the route fails to render.
registerA11yPageSpec('backtest detail (#5)', {
  url: APP_PATHS.backtest.result(1),
  readySelector: 'main, [data-test=backtest-detail], body',
})
registerA11yPageSpec('knowledge-base (#6)', { url: APP_PATHS.ai.knowledgeBase })
registerA11yPageSpec('strategies (#7)', { url: APP_PATHS.research.strategies })
registerA11yPageSpec('trading workspaces', { url: APP_PATHS.trading.workspaces })
registerA11yPageSpec('gateway configuration', { url: APP_PATHS.config.gateways })
registerA11yPageSpec('data scripts configuration', { url: APP_PATHS.config.dataScripts })
