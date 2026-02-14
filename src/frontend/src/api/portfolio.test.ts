import { describe, it, expect, vi, beforeEach } from 'vitest'
import { portfolioApi } from './portfolio'
import request from './index'

vi.mock('./index', () => ({
  default: { get: vi.fn() },
}))

describe('portfolioApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getOverview', async () => {
    vi.mocked(request.get).mockResolvedValue({ total_assets: 100000 })
    const r = await portfolioApi.getOverview()
    expect(request.get).toHaveBeenCalledWith('/portfolio/overview')
    expect(r).toEqual({ total_assets: 100000 })
  })

  it('getPositions', async () => {
    vi.mocked(request.get).mockResolvedValue({ total: 0, positions: [] })
    await portfolioApi.getPositions()
    expect(request.get).toHaveBeenCalledWith('/portfolio/positions')
  })

  it('getTrades with default limit', async () => {
    vi.mocked(request.get).mockResolvedValue({ total: 0, trades: [] })
    await portfolioApi.getTrades()
    expect(request.get).toHaveBeenCalledWith('/portfolio/trades', { params: { limit: 200 } })
  })

  it('getTrades with custom limit', async () => {
    vi.mocked(request.get).mockResolvedValue({ total: 0, trades: [] })
    await portfolioApi.getTrades(50)
    expect(request.get).toHaveBeenCalledWith('/portfolio/trades', { params: { limit: 50 } })
  })

  it('getEquity', async () => {
    vi.mocked(request.get).mockResolvedValue({ dates: [], total_equity: [] })
    await portfolioApi.getEquity()
    expect(request.get).toHaveBeenCalledWith('/portfolio/equity')
  })

  it('getAllocation', async () => {
    vi.mocked(request.get).mockResolvedValue({ total: 0, items: [] })
    await portfolioApi.getAllocation()
    expect(request.get).toHaveBeenCalledWith('/portfolio/allocation')
  })
})
