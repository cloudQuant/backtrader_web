import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/api/index'
import { marketDataApi } from '@/api/marketData'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('marketDataApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listInstrumentOptions calls the selectable instrument endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0 })

    await marketDataApi.listInstrumentOptions({
      asset_type: 'stock',
      search: '000',
      limit: 20,
    })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/options', {
      params: {
        asset_type: 'stock',
        search: '000',
        limit: 20,
      },
    })
  })

  it('lookupInstrument calls the aggregated market instrument endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ symbol: 'RB2510' })

    await marketDataApi.lookupInstrument({
      asset_type: 'futures',
      symbol: 'RB2510',
      start_date: '2026-06-01',
      end_date: '2026-06-19',
      period: 'daily',
      market: 'CF',
    })

    expect(api.get).toHaveBeenCalledWith('/data/market-instruments/lookup', {
      params: {
        asset_type: 'futures',
        symbol: 'RB2510',
        start_date: '2026-06-01',
        end_date: '2026-06-19',
        period: 'daily',
        market: 'CF',
      },
    })
  })

  it('listCoverage calls the data trust coverage endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0, refreshed: false })

    await marketDataApi.listCoverage({ asset_type: 'stock', timeframe: '1d', provider: 'local_csv' })

    expect(api.get).toHaveBeenCalledWith('/data/trust/coverage', {
      params: { asset_type: 'stock', timeframe: '1d', provider: 'local_csv' },
    })
  })

  it('refreshWarehouseCoverage posts to the warehouse coverage endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ items: [], total: 0, refreshed: true })

    await marketDataApi.refreshWarehouseCoverage({ asset_type: 'stock', timeframe: '1d' })

    expect(api.post).toHaveBeenCalledWith('/data/trust/coverage/refresh-warehouse', undefined, {
      params: { asset_type: 'stock', timeframe: '1d' },
    })
  })

  it('runPrecheck posts to the data trust precheck endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ passed: true })

    await marketDataApi.runPrecheck({ asset_type: 'stock', symbol: '000001', timeframe: '1d' })

    expect(api.post).toHaveBeenCalledWith('/data/trust/precheck', {
      asset_type: 'stock',
      symbol: '000001',
      timeframe: '1d',
    })
  })
})
