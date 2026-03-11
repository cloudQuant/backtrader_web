import { describe, it, expect, vi, beforeEach } from 'vitest'
import { liveTradingApi } from '@/api/liveTrading'
import request from '@/api/index'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

describe('liveTradingApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('list', async () => {
    vi.mocked(request.get).mockResolvedValue({ total: 0, instances: [] })
    await liveTradingApi.list()
    expect(request.get).toHaveBeenCalledWith('/live-trading/')
  })

  it('listPresets', async () => {
    vi.mocked(request.get).mockResolvedValue({ total: 2, presets: [] })
    await liveTradingApi.listPresets()
    expect(request.get).toHaveBeenCalledWith('/live-trading/presets')
  })

  it('listPresets returns preset metadata', async () => {
    const mockPreset = {
      id: 'ib_web_stock_gateway',
      name: 'IB Web Stock Gateway',
      description: 'IB Web preset for US stock trading.',
      editable_fields: [
        { key: 'account_id', label: '账户', input_type: 'string', placeholder: '如 DU123456' },
        { key: 'verify_ssl', label: 'SSL校验', input_type: 'boolean', placeholder: null },
      ],
      params: { gateway: { provider: 'gateway' } },
    }
    vi.mocked(request.get).mockResolvedValue({ total: 1, presets: [mockPreset] })
    const result = await liveTradingApi.listPresets()
    expect(result.presets[0].description).toBe('IB Web preset for US stock trading.')
    expect(result.presets[0].editable_fields).toHaveLength(2)
    expect(result.presets[0].editable_fields[0].key).toBe('account_id')
    expect(result.presets[0].editable_fields[1].input_type).toBe('boolean')
  })

  it('add', async () => {
    vi.mocked(request.post).mockResolvedValue({ id: 'i1' })
    await liveTradingApi.add('s1', { period: 20 })
    expect(request.post).toHaveBeenCalledWith('/live-trading/', { strategy_id: 's1', params: { period: 20 } })
  })

  it('add without params', async () => {
    vi.mocked(request.post).mockResolvedValue({ id: 'i1' })
    await liveTradingApi.add('s1')
    expect(request.post).toHaveBeenCalledWith('/live-trading/', { strategy_id: 's1', params: undefined })
  })

  it('remove', async () => {
    vi.mocked(request.delete).mockResolvedValue({ message: 'ok' })
    await liveTradingApi.remove('i1')
    expect(request.delete).toHaveBeenCalledWith('/live-trading/i1')
  })

  it('get', async () => {
    vi.mocked(request.get).mockResolvedValue({ id: 'i1' })
    await liveTradingApi.get('i1')
    expect(request.get).toHaveBeenCalledWith('/live-trading/i1')
  })

  it('start', async () => {
    vi.mocked(request.post).mockResolvedValue({ id: 'i1', status: 'running' })
    await liveTradingApi.start('i1')
    expect(request.post).toHaveBeenCalledWith('/live-trading/i1/start')
  })

  it('stop', async () => {
    vi.mocked(request.post).mockResolvedValue({ id: 'i1', status: 'stopped' })
    await liveTradingApi.stop('i1')
    expect(request.post).toHaveBeenCalledWith('/live-trading/i1/stop')
  })

  it('startAll', async () => {
    vi.mocked(request.post).mockResolvedValue({ success: 2, failed: 0, details: [] })
    await liveTradingApi.startAll()
    expect(request.post).toHaveBeenCalledWith('/live-trading/start-all')
  })

  it('stopAll', async () => {
    vi.mocked(request.post).mockResolvedValue({ success: 2, failed: 0, details: [] })
    await liveTradingApi.stopAll()
    expect(request.post).toHaveBeenCalledWith('/live-trading/stop-all')
  })
})
