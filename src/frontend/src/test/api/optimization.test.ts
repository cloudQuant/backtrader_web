import { describe, it, expect, vi, beforeEach } from 'vitest'
import { optimizationApi } from '@/api/optimization'
import request from '@/api/index'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

describe('optimizationApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getStrategyParams', async () => {
    vi.mocked(request.get).mockResolvedValue({ strategy_id: 's1', params: [] })
    await optimizationApi.getStrategyParams('s1')
    expect(request.get).toHaveBeenCalledWith('/optimization/strategy-params/s1')
  })

  it('submit', async () => {
    vi.mocked(request.post).mockResolvedValue({ task_id: 't1', total_combinations: 10 })
    const data = { strategy_id: 's1', param_ranges: {}, n_workers: 4 }
    await optimizationApi.submit(data)
    expect(request.post).toHaveBeenCalledWith('/optimization/submit', data)
  })

  it('getProgress', async () => {
    vi.mocked(request.get).mockResolvedValue({ task_id: 't1', progress: 50 })
    await optimizationApi.getProgress('t1')
    expect(request.get).toHaveBeenCalledWith('/optimization/progress/t1')
  })

  it('getResults', async () => {
    vi.mocked(request.get).mockResolvedValue({ task_id: 't1', rows: [] })
    await optimizationApi.getResults('t1')
    expect(request.get).toHaveBeenCalledWith('/optimization/results/t1')
  })

  it('cancel', async () => {
    vi.mocked(request.post).mockResolvedValue({ message: 'ok', task_id: 't1' })
    await optimizationApi.cancel('t1')
    expect(request.post).toHaveBeenCalledWith('/optimization/cancel/t1')
  })
})
