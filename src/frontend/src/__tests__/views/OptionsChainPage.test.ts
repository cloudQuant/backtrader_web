import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OptionsChainPage from '@/views/OptionsChainPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  getOptionsChain: vi.fn(),
}))

vi.mock('@/api/marketIntel', () => ({
  marketIntelApi: apiMocks,
}))

describe('OptionsChainPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getOptionsChain.mockResolvedValue({
      underlying: 'RB2510',
      source: 'data_governance',
      pcr: 0.8,
      max_pain: 3550,
      atm_strike: 3550,
      atm_iv: 0.22,
      spot: 3524,
      strike_count: 9,
      strike_step: 50,
      timestamp: '2026-05-26T00:00:00+00:00',
      rows: [
        {
          strike: 3550,
          call: { oi: 100, volume: 20, iv: 0.22, greeks: { delta: 0.5 } },
          put: { oi: 80, volume: 18, iv: 0.22, greeks: { delta: -0.5 } },
        },
      ],
    })
  })

  it('loads option chain summary and renders richer fields', async () => {
    const wrapper = mountWithPlugins(OptionsChainPage)
    expect(wrapper.text()).toContain('期权链')

    await (wrapper.vm as any).load()
    await flushPromises()

    expect(apiMocks.getOptionsChain).toHaveBeenCalledWith('RB2510', '2026-12-31', 'data_governance')
    expect((wrapper.vm as any).summary?.underlying).toBe('RB2510')
    expect((wrapper.vm as any).summary?.atm_iv).toBe(0.22)
    expect((wrapper.vm as any).summary?.strike_count).toBe(9)
    expect((wrapper.vm as any).rows[0].call.volume).toBe(20)
    expect(wrapper.text()).toContain('RB2510')
    expect(wrapper.text()).toContain('data_governance')
    expect(wrapper.find('.options-workbench').exists()).toBe(true)
    expect(wrapper.find('.options-query-bar').exists()).toBe(true)
    expect(wrapper.find('.options-metric-grid').exists()).toBe(true)
    expect(wrapper.find('.options-table-panel').exists()).toBe(true)
    expect(wrapper.text()).toContain('核心指标')
    expect(wrapper.text()).toContain('链表明细')
    expect(wrapper.text()).toContain('Put / Call Ratio')
    expect(wrapper.text()).toContain('22.00%')
  })
})
