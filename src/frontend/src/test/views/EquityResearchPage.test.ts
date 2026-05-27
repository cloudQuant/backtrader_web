import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EquityResearchPage from '@/views/EquityResearchPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  searchEquities: vi.fn(),
  getEquityQuote: vi.fn(),
  getEquityInfo: vi.fn(),
  getEquityHistory: vi.fn(),
  getEquityFinancials: vi.fn(),
  getTechnicals: vi.fn(),
  getEquityPeers: vi.fn(),
}))

vi.mock('@/api/marketIntel', () => ({
  marketIntelApi: apiMocks,
}))

describe('EquityResearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.searchEquities.mockResolvedValue({
      items: [{ symbol: 'RB2510', name: '螺纹钢主力', asset_type: 'futures', exchange: 'SHFE' }],
      total: 1,
    })
    apiMocks.getEquityQuote.mockResolvedValue({ symbol: 'RB2510', price: 3524, previous_close: 3474, change_pct: 0.0144, currency: 'CNY', provider: 'data_governance' })
    apiMocks.getEquityInfo.mockResolvedValue({ symbol: 'RB2510', name: '螺纹钢主力', exchange: 'SHFE', industry: 'Metals & Futures', sector: 'Industrials', country: 'CN', description: '统一合约画像' })
    apiMocks.getEquityHistory.mockResolvedValue({ symbol: 'RB2510', rows: [{ date: '2026-05-10', close: 3524, volume: 1000 }] })
    apiMocks.getEquityFinancials.mockResolvedValue({ symbol: 'RB2510', annual: [{ period: '2025', revenue: 82000, net_income: 10660, eps: 1.26, roe: 11.3 }] })
    apiMocks.getTechnicals.mockResolvedValue({ symbol: 'RB2510', factors: { momentum_5: [null, 0.1], volatility_5: [null, 0.02] } })
    apiMocks.getEquityPeers.mockResolvedValue({ symbol: 'RB2510', total: 1, items: [{ symbol: 'HC2510', name: '热卷主力', reason: '黑色系产业链联动' }] })
  })

  it('loads search results and symbol detail panels', async () => {
    const wrapper = mountWithPlugins(EquityResearchPage)
    expect(wrapper.text()).toContain('权益研究')

    await flushPromises()

    expect(apiMocks.searchEquities).toHaveBeenCalledWith('RB')
    expect(apiMocks.getEquityQuote).toHaveBeenCalledWith('RB2510')
    expect(apiMocks.getEquityInfo).toHaveBeenCalledWith('RB2510')
    expect(apiMocks.getEquityFinancials).toHaveBeenCalledWith('RB2510')
    expect(apiMocks.getEquityPeers).toHaveBeenCalledWith('RB2510')
    expect((wrapper.vm as any).selectedSymbol).toBe('RB2510')
    expect((wrapper.vm as any).quote?.provider).toBe('data_governance')
    expect((wrapper.vm as any).annualRows).toHaveLength(1)
    expect(wrapper.text()).toContain('RB2510')
  })
})
