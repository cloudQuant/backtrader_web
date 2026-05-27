import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/api/index'
import { brokerProfilesApi } from '@/api/brokerProfiles'
import { dataGovernanceApi } from '@/api/dataGovernance'
import { dataTopicsApi } from '@/api/dataTopics'
import { portfolioLedgerApi } from '@/api/portfolioLedger'
import { marketIntelApi } from '@/api/marketIntel'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

describe('iteration170 api wrappers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls data governance bootstrap and listing endpoints', async () => {
    vi.mocked(request.post).mockResolvedValue({ providers: 6 })
    vi.mocked(request.get).mockResolvedValue({ items: [], total: 0 })

    await dataGovernanceApi.bootstrap()
    await dataGovernanceApi.listProviders()
    await dataGovernanceApi.listEndpoints('akshare')

    expect(request.post).toHaveBeenCalledWith('/data-governance/bootstrap')
    expect(request.get).toHaveBeenNthCalledWith(1, '/data-governance/providers')
    expect(request.get).toHaveBeenNthCalledWith(2, '/data-governance/endpoints', { params: { provider_id: 'akshare' } })
  })

  it('calls portfolio ledger endpoints', async () => {
    vi.mocked(request.post).mockResolvedValue({ id: 'ledger-1' })
    vi.mocked(request.get).mockResolvedValue({ items: [], total: 0 })

    await portfolioLedgerApi.create({ name: 'ledger' })
    await portfolioLedgerApi.importTransactions('ledger-1', { format: 'json', idempotency_key: 'abc', transactions: [] })
    await portfolioLedgerApi.getDetail('ledger-1')
    await portfolioLedgerApi.getHoldings('ledger-1')
    await portfolioLedgerApi.getTransactions('ledger-1')
    await portfolioLedgerApi.backfillSnapshots('ledger-1')
    await portfolioLedgerApi.getSnapshots('ledger-1')
    await portfolioLedgerApi.exportPortfolio('ledger-1')
    await portfolioLedgerApi.getVarCvar('ledger-1', 'parametric')
    await portfolioLedgerApi.getPositionSizing('ledger-1', 0.2, 1.5)
    await portfolioLedgerApi.getBenchmarkMetrics('ledger-1', 'hs300', 0.02)
    await portfolioLedgerApi.calculateBrinson('ledger-1', {
      benchmark_weights: { AAA: 0.6 },
      benchmark_returns: { AAA: 0.05 },
    })
    await portfolioLedgerApi.calculateFamaFrench('ledger-1', {
      smb_returns: [0.001],
      hml_returns: [0.002],
      benchmark_id: 'hs300',
    })

    expect(request.post).toHaveBeenNthCalledWith(1, '/portfolio-ledger', { name: 'ledger' })
    expect(request.post).toHaveBeenNthCalledWith(2, '/portfolio-ledger/ledger-1/import', { format: 'json', idempotency_key: 'abc', transactions: [] })
    expect(request.get).toHaveBeenNthCalledWith(1, '/portfolio-ledger/ledger-1')
    expect(request.get).toHaveBeenNthCalledWith(2, '/portfolio-ledger/ledger-1/holdings')
    expect(request.get).toHaveBeenNthCalledWith(3, '/portfolio-ledger/ledger-1/transactions')
    expect(request.post).toHaveBeenNthCalledWith(3, '/portfolio-ledger/ledger-1/snapshots/backfill')
    expect(request.get).toHaveBeenNthCalledWith(4, '/portfolio-ledger/ledger-1/snapshots')
    expect(request.get).toHaveBeenNthCalledWith(5, '/portfolio-ledger/ledger-1/export', { params: { format: 'json' } })
    expect(request.get).toHaveBeenNthCalledWith(6, '/portfolio-ledger/ledger-1/analytics/var-cvar', { params: { method: 'parametric' } })
    expect(request.get).toHaveBeenNthCalledWith(7, '/portfolio-ledger/ledger-1/analytics/position-sizing', {
      params: { target_volatility: 0.2, max_position: 1.5 },
    })
    expect(request.get).toHaveBeenNthCalledWith(8, '/portfolio-ledger/ledger-1/analytics/benchmark-metrics', {
      params: { benchmark_id: 'hs300', risk_free_rate: 0.02 },
    })
    expect(request.post).toHaveBeenNthCalledWith(4, '/portfolio-ledger/ledger-1/analytics/brinson', {
      benchmark_weights: { AAA: 0.6 },
      benchmark_returns: { AAA: 0.05 },
    })
    expect(request.post).toHaveBeenNthCalledWith(5, '/portfolio-ledger/ledger-1/analytics/fama-french', {
      smb_returns: [0.001],
      hml_returns: [0.002],
      benchmark_id: 'hs300',
    })
  })

  it('calls market intelligence endpoints', async () => {
    vi.mocked(request.get).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(request.post).mockResolvedValue({ status: 'ok' })

    await marketIntelApi.searchEquities('RB')
    await marketIntelApi.getEquityInfo('RB2510')
    await marketIntelApi.getEquityFinancials('RB2510')
    await marketIntelApi.getEquityPeers('RB2510')
    await marketIntelApi.createNewsSource({ name: 'terminal-rss', url: 'https://example.com/rss' })
    await marketIntelApi.pullNewsSource('terminal-rss', 10)
    await marketIntelApi.listArticles({ sentiment: 'BULLISH', ticker: 'RB2510' })
    await marketIntelApi.getOptionsChain('RB2510', '2026-12-31')
    await marketIntelApi.runScanner({ universe: ['RB2510'], condition: 'price > 100' })
    await marketIntelApi.getScannerTask('task-1')
    await marketIntelApi.listQuantTools()
    await marketIntelApi.callQuantTool({ tool_name: 'markets.get_quote', input: { symbol: 'RB2510' } })

    expect(request.get).toHaveBeenNthCalledWith(1, '/equity-research/search', { params: { q: 'RB' } })
    expect(request.get).toHaveBeenNthCalledWith(2, '/equity-research/info/RB2510')
    expect(request.get).toHaveBeenNthCalledWith(3, '/equity-research/financials/RB2510')
    expect(request.get).toHaveBeenNthCalledWith(4, '/equity-research/peers/RB2510')
    expect(request.post).toHaveBeenNthCalledWith(1, '/news-intelligence/sources', { name: 'terminal-rss', url: 'https://example.com/rss' })
    expect(request.post).toHaveBeenNthCalledWith(2, '/news-intelligence/sources/terminal-rss/pull', undefined, { params: { limit: 10 } })
    expect(request.get).toHaveBeenNthCalledWith(5, '/news-intelligence/articles', { params: { sentiment: 'BULLISH', ticker: 'RB2510' } })
    expect(request.get).toHaveBeenNthCalledWith(6, '/options-chain/RB2510', { params: { expiry: '2026-12-31', provider: 'auto' } })
    expect(request.post).toHaveBeenNthCalledWith(3, '/scanners/run', { universe: ['RB2510'], condition: 'price > 100' })
    expect(request.get).toHaveBeenNthCalledWith(7, '/scanners/tasks/task-1')
    expect(request.get).toHaveBeenNthCalledWith(8, '/quant-tools')
    expect(request.post).toHaveBeenNthCalledWith(4, '/quant-tools/call', { tool_name: 'markets.get_quote', input: { symbol: 'RB2510' } })
  })

  it('calls data topics endpoints', async () => {
    vi.mocked(request.get).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(request.post).mockResolvedValue({ topic: 'market:quote:RB2510', value: { price: 100 } })

    await dataTopicsApi.listTopics()
    await dataTopicsApi.peekTopic('market:quote:RB2510')
    await dataTopicsApi.refreshTopic('market:quote:RB2510')
    await dataTopicsApi.getStats()

    expect(request.get).toHaveBeenNthCalledWith(1, '/data-topics')
    expect(request.get).toHaveBeenNthCalledWith(2, '/data-topics/market:quote:RB2510/peek')
    expect(request.post).toHaveBeenCalledWith('/data-topics/market:quote:RB2510/refresh')
    expect(request.get).toHaveBeenNthCalledWith(3, '/data-topics/stats')
  })

  it('calls broker profiles endpoints', async () => {
    vi.mocked(request.get).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(request.post).mockResolvedValue({ id: 'profile-1', is_destructive_enabled: false })

    await brokerProfilesApi.listProfiles()
    await brokerProfilesApi.createProfile({
      broker_id: 'gateway_bridge',
      account_alias: 'sim-account',
      capabilities: ['health', 'accounts'],
      credentials_ref: { api_key_env: 'BT_BROKER_SIM_KEY' },
      credentials_rotated_at: '2026-05-26T00:00:00+00:00',
      runtime_gateway_key: 'manual:IB_WEB:DU123456',
      runtime_account_id: 'DU123456',
    })
    await brokerProfilesApi.getHealth('profile-1')
    await brokerProfilesApi.getAccounts('profile-1')
    await brokerProfilesApi.getPositions('profile-1')
    await brokerProfilesApi.getOrders('profile-1')
    await brokerProfilesApi.getQuote('profile-1', 'RB2510')
    await brokerProfilesApi.enableWrite('profile-1', {
      confirmation_text: 'ENABLE sim-account',
      idempotency_key: 'req-1',
    })

    expect(request.get).toHaveBeenNthCalledWith(1, '/brokers/profiles')
    expect(request.post).toHaveBeenNthCalledWith(1, '/brokers/profiles', {
      broker_id: 'gateway_bridge',
      account_alias: 'sim-account',
      capabilities: ['health', 'accounts'],
      credentials_ref: { api_key_env: 'BT_BROKER_SIM_KEY' },
      credentials_rotated_at: '2026-05-26T00:00:00+00:00',
      runtime_gateway_key: 'manual:IB_WEB:DU123456',
      runtime_account_id: 'DU123456',
    })
    expect(request.get).toHaveBeenNthCalledWith(2, '/brokers/profiles/profile-1/health')
    expect(request.get).toHaveBeenNthCalledWith(3, '/brokers/profiles/profile-1/accounts')
    expect(request.get).toHaveBeenNthCalledWith(4, '/brokers/profiles/profile-1/positions')
    expect(request.get).toHaveBeenNthCalledWith(5, '/brokers/profiles/profile-1/orders')
    expect(request.get).toHaveBeenNthCalledWith(6, '/brokers/profiles/profile-1/quotes', { params: { symbol: 'RB2510' } })
    expect(request.post).toHaveBeenNthCalledWith(2, '/brokers/profiles/profile-1/enable-write', {
      confirmation_text: 'ENABLE sim-account',
      idempotency_key: 'req-1',
    })
  })
})
