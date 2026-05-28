import { registerA11yPageSpec } from './_template.spec'

// Iteration 175 §3.1 — Critical_Page_Set authenticated pages (6 of 7).
// Login page is in login.spec.ts and runs with empty storageState.
// Authenticated pages reuse the project's default storageState (configured in
// playwright.config.ts via globalSetup).

registerA11yPageSpec('dashboard (#2)', { url: '/dashboard' })
registerA11yPageSpec('ai-chat (#3)', { url: '/ai-chat' })
registerA11yPageSpec('backtests list (#4)', { url: '/backtests' })
// Backtest detail uses :id placeholder; smoke seed creates id=1 (or first
// available). Test will skip gracefully if the route fails to render.
registerA11yPageSpec('backtest detail (#5)', {
  url: '/backtests/1',
  readySelector: 'main, [data-test=backtest-detail], body',
})
registerA11yPageSpec('knowledge-base (#6)', { url: '/knowledge-base' })
registerA11yPageSpec('strategies (#7)', { url: '/strategies' })
