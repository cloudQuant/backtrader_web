import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import QuantToolsPage from '@/views/QuantToolsPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  listQuantTools: vi.fn(),
  callQuantTool: vi.fn(),
}))

vi.mock('@/api/marketIntel', () => ({
  marketIntelApi: apiMocks,
}))

describe('QuantToolsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listQuantTools.mockResolvedValue({
      tools: [
        {
          name: 'markets.get_quote',
          description: 'Get a latest market quote',
          auth_level: 'user',
          requires_confirmation: false,
          timeout_ms: 5000,
          rate_limit_per_user_per_min: 30,
        },
      ],
    })
    apiMocks.callQuantTool.mockResolvedValue({ status: 'ok', result: { symbol: 'RB2510', price: 100 } })
  })

  it('loads quant tool metadata and renders registry fields', async () => {
    const wrapper = mountWithPlugins(QuantToolsPage)
    expect(wrapper.text()).toContain('量化工具')

    await (wrapper.vm as any).load()
    await flushPromises()

    expect(apiMocks.listQuantTools).toHaveBeenCalled()
    expect((wrapper.vm as any).tools[0].auth_level).toBe('user')
    expect(wrapper.text()).toContain('markets.get_quote')
    expect(wrapper.text()).toContain('user')
    expect(wrapper.text()).toContain('5000')
    expect(wrapper.text()).toContain('30')

    await (wrapper.vm as any).callSelectedTool()
    await flushPromises()

    expect(apiMocks.callQuantTool).toHaveBeenCalledWith({ tool_name: 'markets.get_quote', input: { symbol: 'RB2510' } })
  })
})
