import { registerA11yPageSpec } from './_template.spec'

// Iteration 175 §3.1 — Critical_Page_Set authenticated pages (6 of 7).
// Login page is in login.spec.ts and runs with empty storageState.
// Authenticated pages reuse the project's default storageState (configured in
// playwright.config.ts via globalSetup).
//
// URLs updated to match actual router (src/frontend/src/router/index.ts):
//   - dashboard:     '/'              (route path: '', child of '/')
//   - ai-chat:       '/ai-chat'
//   - backtests:     '/backtest'      (workspace list — not '/backtests')
//   - backtest detail '/backtest/result/1' (not '/backtests/:id')
//   - knowledge-base:'/knowledge-base'
//   - strategies:    '/strategy'      (singular — not '/strategies')

registerA11yPageSpec('dashboard (#2)', { url: '/' })
registerA11yPageSpec('ai-chat (#3)', { url: '/ai-chat' })
registerA11yPageSpec('backtests list (#4)', { url: '/backtest' })
// Backtest detail uses :id placeholder; smoke seed creates id=1 (or first
// available). Test will skip gracefully if the route fails to render.
registerA11yPageSpec('backtest detail (#5)', {
  url: '/backtest/result/1',
  readySelector: 'main, [data-test=backtest-detail], body',
})
registerA11yPageSpec('knowledge-base (#6)', { url: '/knowledge-base' })
registerA11yPageSpec('strategies (#7)', { url: '/strategy' })
