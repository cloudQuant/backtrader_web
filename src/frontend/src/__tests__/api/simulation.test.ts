import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/api/index'
import { simulationApi } from '@/api/simulation'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('simulationApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('covers simulation instance and config endpoints', async () => {
    vi.mocked(request.get).mockResolvedValue({})
    vi.mocked(request.post).mockResolvedValue({})
    vi.mocked(request.put).mockResolvedValue({})
    vi.mocked(request.delete).mockResolvedValue({})

    await simulationApi.list()
    await simulationApi.add('strategy-1', { fast: 10 })
    await simulationApi.remove('sim-1')
    await simulationApi.get('sim-1')
    await simulationApi.start('sim-1')
    await simulationApi.stop('sim-1')
    await simulationApi.startAll()
    await simulationApi.stopAll()
    await simulationApi.getTemplateConfig('template-1')
    await simulationApi.listLogs('sim-1')
    await simulationApi.getLog('sim-1', 'run.log', 100)
    await simulationApi.getConfig('sim-1')
    await simulationApi.updateConfig('sim-1', { raw: '{}' })
    await simulationApi.clearLog('sim-1', 'run.log')
    await simulationApi.clearAllLogs('sim-1')

    expect(request.get).toHaveBeenCalledWith('/simulation/')
    expect(request.post).toHaveBeenCalledWith('/simulation/', { strategy_id: 'strategy-1', params: { fast: 10 } })
    expect(request.delete).toHaveBeenCalledWith('/simulation/sim-1')
    expect(request.get).toHaveBeenCalledWith('/simulation/sim-1/logs/run.log', {
      params: { tail: 100 },
      responseType: 'text',
    })
    expect(request.put).toHaveBeenCalledWith('/simulation/sim-1/config', { raw: '{}' })
    expect(request.delete).toHaveBeenCalledWith('/simulation/sim-1/logs/run.log')
    expect(request.delete).toHaveBeenCalledWith('/simulation/sim-1/logs')
  })

  it('downloads simulation logs', async () => {
    const blob = new Blob(['log'])
    vi.mocked(request.get).mockResolvedValue(blob)
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:log')
    globalThis.URL.revokeObjectURL = vi.fn()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await simulationApi.downloadLog('sim-1', 'run.log')

    expect(request.get).toHaveBeenCalledWith('/simulation/sim-1/logs/run.log/download', {
      responseType: 'blob',
    })
    expect(globalThis.URL.createObjectURL).toHaveBeenCalled()
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:log')
    clickSpy.mockRestore()
  })
})
