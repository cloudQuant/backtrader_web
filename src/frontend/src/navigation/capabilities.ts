export type ProductDomainId =
  | 'home'
  | 'data'
  | 'research'
  | 'trading'
  | 'portfolio'
  | 'ai'
  | 'admin'

export type CapabilityStatus = 'stable' | 'beta' | 'admin' | 'legacy' | 'hidden'

export interface ProductDomain {
  id: ProductDomainId
  path: string
  labelKey: string
  icon: string
  requiresAdmin?: boolean
}

export interface Capability {
  id: string
  domainId: ProductDomainId
  path: string
  labelKey?: string
  label?: string
  icon: string
  legacyPaths?: string[]
  requiresAdmin?: boolean
  status?: CapabilityStatus
  visibleInSubnav?: boolean
}

export const productDomains: ProductDomain[] = [
  { id: 'home', path: '/', labelKey: 'nav.home', icon: 'HomeFilled' },
  { id: 'data', path: '/data', labelKey: 'nav.marketData', icon: 'Grid' },
  { id: 'research', path: '/research', labelKey: 'nav.strategyResearch', icon: 'Aim' },
  { id: 'trading', path: '/trading', labelKey: 'nav.tradingOperations', icon: 'TrendCharts' },
  { id: 'portfolio', path: '/portfolio', labelKey: 'nav.portfolioRisk', icon: 'TrendCharts' },
  { id: 'ai', path: '/ai', labelKey: 'nav.aiKnowledge', icon: 'ChatDotRound' },
  {
    id: 'admin',
    path: '/admin',
    labelKey: 'nav.platformAdmin',
    icon: 'Setting',
    requiresAdmin: true,
  },
]

export const capabilities: Capability[] = [
  {
    id: 'home.dashboard',
    domainId: 'home',
    path: '/',
    labelKey: 'nav.dashboard',
    icon: 'HomeFilled',
  },

  {
    id: 'data.quote',
    domainId: 'data',
    path: '/data/quote',
    labelKey: 'nav.quote',
    icon: 'Stopwatch',
    legacyPaths: ['/quote'],
  },
  {
    id: 'data.market',
    domainId: 'data',
    path: '/data/market',
    labelKey: 'nav.data',
    icon: 'Grid',
    legacyPaths: ['/data'],
  },
  {
    id: 'data.topics',
    domainId: 'data',
    path: '/data/topics',
    labelKey: 'dataPages.layoutTabTopics',
    icon: 'Collection',
  },
  {
    id: 'data.scripts',
    domainId: 'data',
    path: '/data/scripts',
    labelKey: 'dataPages.layoutTabScripts',
    icon: 'Document',
  },
  {
    id: 'data.tasks',
    domainId: 'data',
    path: '/data/tasks',
    labelKey: 'dataPages.layoutTabTasks',
    icon: 'Document',
  },
  {
    id: 'data.executions',
    domainId: 'data',
    path: '/data/executions',
    labelKey: 'dataPages.layoutTabExecutions',
    icon: 'Monitor',
  },
  {
    id: 'data.tables',
    domainId: 'data',
    path: '/data/tables',
    labelKey: 'dataPages.layoutTabTables',
    icon: 'Grid',
  },
  {
    id: 'data.sync',
    domainId: 'data',
    path: '/data/sync',
    labelKey: 'dataPages.layoutTabSync',
    icon: 'Monitor',
    requiresAdmin: true,
    status: 'admin',
  },
  {
    id: 'data.interfaces',
    domainId: 'data',
    path: '/data/interfaces',
    labelKey: 'dataPages.layoutTabInterfaces',
    icon: 'Document',
    requiresAdmin: true,
    status: 'admin',
  },
  {
    id: 'data.governance',
    domainId: 'data',
    path: '/data/governance',
    labelKey: 'dataPages.layoutTabGovernance',
    icon: 'Setting',
    requiresAdmin: true,
    status: 'admin',
  },
  {
    id: 'data.airflow',
    domainId: 'data',
    path: '/data/airflow',
    label: 'Airflow',
    icon: 'Monitor',
    requiresAdmin: true,
    status: 'admin',
  },
  {
    id: 'data.equityResearch',
    domainId: 'data',
    path: '/data/intelligence/equity',
    labelKey: 'nav.equityResearch',
    icon: 'Document',
    legacyPaths: ['/equity-research'],
  },
  {
    id: 'data.newsIntelligence',
    domainId: 'data',
    path: '/data/intelligence/news',
    labelKey: 'nav.newsIntelligence',
    icon: 'Document',
    legacyPaths: ['/news-intelligence'],
  },
  {
    id: 'data.optionsChain',
    domainId: 'data',
    path: '/data/intelligence/options',
    labelKey: 'nav.optionsChain',
    icon: 'Document',
    legacyPaths: ['/options-chain'],
  },
  {
    id: 'data.scanners',
    domainId: 'data',
    path: '/data/intelligence/scanners',
    labelKey: 'nav.scanners',
    icon: 'Aim',
    legacyPaths: ['/scanners'],
  },

  {
    id: 'research.strategies',
    domainId: 'research',
    path: '/research/strategies',
    labelKey: 'nav.strategy',
    icon: 'Document',
    legacyPaths: ['/strategy'],
  },
  {
    id: 'research.workspaces',
    domainId: 'research',
    path: '/research/workspaces',
    labelKey: 'nav.workspace',
    icon: 'Aim',
    legacyPaths: ['/workspace', '/backtest'],
  },
  {
    id: 'research.backtestResult',
    domainId: 'research',
    path: '/research/backtests/:id',
    labelKey: 'nav.backtest',
    icon: 'TrendCharts',
    legacyPaths: ['/backtest/result/:id', '/backtest/:id'],
    visibleInSubnav: false,
  },
  {
    id: 'research.legacyBacktest',
    domainId: 'research',
    path: '/research/backtests/legacy',
    labelKey: 'nav.backtest',
    icon: 'TrendCharts',
    legacyPaths: ['/backtest/legacy'],
    status: 'legacy',
    visibleInSubnav: false,
  },
  {
    id: 'research.quantTools',
    domainId: 'research',
    path: '/research/tools',
    labelKey: 'nav.quantTools',
    icon: 'ChatDotRound',
    legacyPaths: ['/quant-tools'],
  },

  {
    id: 'trading.workspaces',
    domainId: 'trading',
    path: '/trading/workspaces',
    labelKey: 'nav.trading',
    icon: 'TrendCharts',
    legacyPaths: ['/trading', '/simulate', '/live-trading'],
  },
  {
    id: 'trading.brokers',
    domainId: 'trading',
    path: '/trading/brokers',
    labelKey: 'nav.brokers',
    icon: 'Monitor',
    legacyPaths: ['/brokers'],
  },
  {
    id: 'trading.gateways',
    domainId: 'trading',
    path: '/trading/gateways',
    labelKey: 'nav.gateways',
    icon: 'Monitor',
    legacyPaths: ['/gateways'],
  },
  {
    id: 'trading.ai',
    domainId: 'trading',
    path: '/trading/ai',
    labelKey: 'nav.aiTrading',
    icon: 'ChatDotRound',
    legacyPaths: ['/ai-trading'],
  },

  {
    id: 'portfolio.overview',
    domainId: 'portfolio',
    path: '/portfolio/overview',
    labelKey: 'nav.portfolio',
    icon: 'TrendCharts',
    legacyPaths: ['/portfolio'],
  },
  {
    id: 'portfolio.ledger',
    domainId: 'portfolio',
    path: '/portfolio/ledger',
    labelKey: 'nav.portfolioLedger',
    icon: 'Document',
    legacyPaths: ['/portfolio-ledger'],
  },

  {
    id: 'ai.chat',
    domainId: 'ai',
    path: '/ai/chat',
    labelKey: 'nav.aiChat',
    icon: 'ChatDotRound',
    legacyPaths: ['/ai-chat'],
  },
  {
    id: 'ai.knowledgeBase',
    domainId: 'ai',
    path: '/ai/knowledge-base',
    labelKey: 'nav.knowledgeBase',
    icon: 'Collection',
    legacyPaths: ['/knowledge-base'],
  },
  {
    id: 'ai.promptGovernance',
    domainId: 'ai',
    path: '/ai/prompt-governance',
    labelKey: 'nav.promptGovernance',
    icon: 'Document',
    legacyPaths: ['/admin/prompt-templates'],
    requiresAdmin: true,
    status: 'admin',
  },
  {
    id: 'ai.observability',
    domainId: 'ai',
    path: '/ai/observability',
    labelKey: 'nav.aiCost',
    icon: 'Monitor',
    legacyPaths: ['/admin/ai-observability'],
    requiresAdmin: true,
    status: 'admin',
  },

  {
    id: 'admin.settings',
    domainId: 'admin',
    path: '/admin/settings',
    labelKey: 'nav.settings',
    icon: 'Setting',
    legacyPaths: ['/settings'],
    requiresAdmin: true,
    status: 'admin',
  },
]

export function normalizePath(path: string): string {
  if (path.length > 1 && path.endsWith('/')) {
    return path.slice(0, -1)
  }
  return path || '/'
}

function matchesPattern(pattern: string, rawPath: string): boolean {
  const path = normalizePath(rawPath).split('?')[0] ?? '/'
  const normalizedPattern = normalizePath(pattern)
  const patternParts = normalizedPattern.split('/').filter(Boolean)
  const pathParts = path.split('/').filter(Boolean)

  if (patternParts.length !== pathParts.length) {
    return false
  }

  return patternParts.every((part, index) => {
    return part.startsWith(':') || part === pathParts[index]
  })
}

function allCapabilityPatterns(capability: Capability): string[] {
  return [capability.path, ...(capability.legacyPaths ?? [])]
}

function specificityScore(pattern: string): number {
  return pattern
    .split('/')
    .filter(Boolean)
    .reduce((score, part) => score + (part.startsWith(':') ? 1 : 3), 0)
}

export function findCapabilityByPath(path: string): Capability | undefined {
  const candidates = capabilities
    .flatMap((capability) =>
      allCapabilityPatterns(capability).map((pattern) => ({ capability, pattern })),
    )
    .filter(({ pattern }) => matchesPattern(pattern, path))
    .sort((a, b) => specificityScore(b.pattern) - specificityScore(a.pattern))

  return candidates[0]?.capability
}

export function getDomainByPath(path: string): ProductDomain {
  const capability = findCapabilityByPath(path)
  if (capability) {
    return productDomains.find((domain) => domain.id === capability.domainId) ?? productDomains[0]
  }

  const normalizedPath = normalizePath(path)
  const matchedDomain = productDomains
    .filter((domain) => domain.path !== '/')
    .find((domain) => normalizedPath === domain.path || normalizedPath.startsWith(`${domain.path}/`))

  return matchedDomain ?? productDomains[0]
}

export function getCapabilitiesForDomain(
  domainId: ProductDomainId,
  isAdmin: boolean,
): Capability[] {
  return capabilities.filter((capability) => {
    if (capability.domainId !== domainId) return false
    if (capability.visibleInSubnav === false) return false
    if (capability.status === 'hidden') return false
    if (capability.requiresAdmin && !isAdmin) return false
    return true
  })
}

export function getVisibleDomains(isAdmin: boolean): ProductDomain[] {
  return productDomains.filter((domain) => !domain.requiresAdmin || isAdmin)
}

