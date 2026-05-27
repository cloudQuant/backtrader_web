import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PortfolioLedgerPage from '@/views/PortfolioLedgerPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  create: vi.fn(),
  importTransactions: vi.fn(),
  getDetail: vi.fn(),
  getHoldings: vi.fn(),
  getTransactions: vi.fn(),
  backfillSnapshots: vi.fn(),
  getSnapshots: vi.fn(),
  exportPortfolio: vi.fn(),
  getVarCvar: vi.fn(),
  getPositionSizing: vi.fn(),
  getBenchmarkMetrics: vi.fn(),
}))

vi.mock('@/api/portfolioLedger', () => ({
  portfolioLedgerApi: apiMocks,
}))

describe('PortfolioLedgerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.create.mockResolvedValue({ id: 'ledger-1', name: 'demo', base_currency: 'CNY', source_type: 'manual' })
    apiMocks.importTransactions.mockResolvedValue({ duplicate: false, imported_count: 2 })
    apiMocks.getDetail.mockResolvedValue({ id: 'ledger-1', name: 'demo', base_currency: 'CNY', source_type: 'manual', transaction_count: 2 })
    apiMocks.getHoldings.mockResolvedValue({ items: [{ symbol: 'RB2510', quantity: 1, cost_basis: 3600 }], total: 1 })
    apiMocks.getTransactions.mockResolvedValue({
      items: [
        { symbol: 'RB2510', trade_type: 'buy', quantity: 2, price: 3500, trade_date: '2026-05-26' },
        { symbol: 'RB2510', trade_type: 'sell', quantity: 1, price: 3600, trade_date: '2026-05-27' },
      ],
      total: 2,
    })
    apiMocks.backfillSnapshots.mockResolvedValue({ items: [{ date: '2026-05-27', snapshot_index: 1, cash_flow: -7000, nav: 1003600 }], total: 1 })
    apiMocks.getSnapshots.mockResolvedValue({ items: [{ date: '2026-05-27', snapshot_index: 1, cash_flow: -7000, nav: 1003600 }], total: 1 })
    apiMocks.exportPortfolio.mockResolvedValue({ schema_version: 'portfolio-ledger.v1', portfolio: { id: 'ledger-1' }, transactions: [] })
    apiMocks.getVarCvar.mockResolvedValue({ portfolio_id: 'ledger-1', status: 'ok', method: 'historical', observation_count: 31, var_95: -0.0123, cvar_95: -0.021 })
    apiMocks.getPositionSizing.mockResolvedValue({ portfolio_id: 'ledger-1', status: 'ok', method: 'volatility_target', observation_count: 31, annualized_volatility: 0.11, target_volatility: 0.15, recommended_position: 0.8 })
    apiMocks.getBenchmarkMetrics.mockResolvedValue({ portfolio_id: 'ledger-1', status: 'ok', benchmark_id: 'hs300', observation_count: 31, alpha: 0.03, beta: 0.92, information_ratio: 0.55, risk_free_rate: 0 })
  })

  it('creates ledger and renders holdings', async () => {
    const wrapper = mountWithPlugins(PortfolioLedgerPage)
    expect(wrapper.text()).toContain('组合账本')

    await (wrapper.vm as any).createPortfolio()
    await flushPromises()

    expect(apiMocks.create).toHaveBeenCalled()
    expect(apiMocks.getDetail).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.getHoldings).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.getTransactions).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.getSnapshots).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.exportPortfolio).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.getVarCvar).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.getPositionSizing).toHaveBeenCalledWith('ledger-1')
    expect(apiMocks.getBenchmarkMetrics).toHaveBeenCalledWith('ledger-1')
    expect((wrapper.vm as any).holdings).toEqual([{ symbol: 'RB2510', quantity: 1, cost_basis: 3600 }])
    expect((wrapper.vm as any).transactions).toHaveLength(2)
    expect((wrapper.vm as any).portfolio?.transaction_count).toBe(2)
    expect(wrapper.text()).toContain('ledger-1')
    expect(wrapper.text()).toContain('portfolio-ledger.v1')
    expect(wrapper.text()).toContain('风险分析')
    expect(wrapper.text()).toContain('VaR / CVaR')
    expect(wrapper.text()).toContain('hs300')
  })
})
