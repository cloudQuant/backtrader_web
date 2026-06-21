import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/api/index'
import { marketDataApi } from '@/api/marketData'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
  },
}))

describe('marketDataApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
})
