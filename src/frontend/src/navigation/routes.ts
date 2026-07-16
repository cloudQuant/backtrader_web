/**
 * Canonical paths for the primary research workflow.
 *
 * Keep user-facing navigation and browser tests on these paths. Compatibility
 * aliases live separately so legacy deep links cannot become the default UX.
 */
export const APP_PATHS = {
  dashboard: '/',
  research: {
    strategies: '/research/strategies',
    workspaces: '/research/workspaces',
    workspacePattern: '/research/workspaces/:id',
    workspace: (id: string | number): string =>
      `/research/workspaces/${encodeURIComponent(String(id))}`,
  },
  backtest: {
    list: '/backtest',
    resultPattern: '/backtest/result/:id',
    result: (id: string | number): string =>
      `/backtest/result/${encodeURIComponent(String(id))}`,
  },
  ai: {
    chat: '/ai/chat',
    knowledgeBase: '/ai/knowledge-base',
  },
  trading: {
    workspaces: '/trading/workspaces',
  },
  config: {
    gateways: '/config/gateways',
    dataScripts: '/config/data/scripts',
  },
} as const

/** Compatibility aliases. Do not use these for new navigation or tests. */
export const LEGACY_PATHS = {
  strategy: '/strategy',
  workspace: '/workspace',
  workspaceDetailPattern: '/workspace/:id',
  backtestResultPattern: '/backtest/:id',
  aiChat: '/ai-chat',
  knowledgeBase: '/knowledge-base',
} as const

/** Convert an absolute application path to a child path under the app shell. */
export function toAppChildPath(path: string): string {
  return path === '/' ? '' : path.replace(/^\//, '')
}
