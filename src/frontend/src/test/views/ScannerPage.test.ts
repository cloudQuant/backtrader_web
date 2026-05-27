import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ScannerPage from '@/views/ScannerPage.vue'
import { mountWithPlugins } from '../mountWithPlugins'

const apiMocks = vi.hoisted(() => ({
  runScanner: vi.fn(),
  getScannerTask: vi.fn(),
}))

vi.mock('@/api/marketIntel', () => ({
  marketIntelApi: apiMocks,
}))

describe('ScannerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.runScanner.mockResolvedValue({
      task_id: 'task-1',
      status: 'completed',
      lookback_days: 20,
      timeframe: '1d',
      matches: [{ symbol: 'RB2510', price: 3524, volume: 4200, indicator: 0.77, factor: 0.71, news_sentiment: 0.65, portfolio_exposure: 0.18 }],
    })
    apiMocks.getScannerTask.mockResolvedValue({
      task_id: 'task-1',
      status: 'completed',
      lookback_days: 20,
      timeframe: '1d',
      matches: [{ symbol: 'RB2510', price: 3524, volume: 4200, indicator: 0.77, factor: 0.71, news_sentiment: 0.65, portfolio_exposure: 0.18 }],
    })
  })

  it('runs scanner and loads task status result', async () => {
    const wrapper = mountWithPlugins(ScannerPage)
    expect(wrapper.text()).toContain('条件扫描')

    await (wrapper.vm as any).run()
    await flushPromises()

    expect(apiMocks.runScanner).toHaveBeenCalledWith({
      universe: ['RB2510', 'IF2510'],
      condition: 'indicator > 0.6 and news_sentiment > 0.5',
      lookback_days: 20,
      timeframe: '1d',
    })
    expect(apiMocks.getScannerTask).toHaveBeenCalledWith('task-1')
    expect((wrapper.vm as any).taskId).toBe('task-1')
    expect((wrapper.vm as any).taskStatus).toBe('completed')
    expect((wrapper.vm as any).matches[0].indicator).toBe(0.77)
    expect(wrapper.text()).toContain('task-1')
    expect(wrapper.text()).toContain('completed')
  })
})
