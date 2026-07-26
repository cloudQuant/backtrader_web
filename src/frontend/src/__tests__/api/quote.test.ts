/**
 * Smoke tests for src/api/quote.ts (quote/market data client).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('quoteApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('listSources GETs /quote/sources', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.listSources()
    expect(get).toHaveBeenCalledWith('/quote/sources')
  })

  it('getSymbols GETs with source param', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.getSymbols('ctp')
    expect(get).toHaveBeenCalledWith('/quote/symbols', { params: { source: 'ctp' } })
  })

  it('addSymbols POSTs to /quote/symbols/add', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)
    await quoteApi.addSymbols('ctp', ['IF2510', 'IH2510'])
    expect(post).toHaveBeenCalledWith('/quote/symbols/add', { source: 'ctp', symbols: ['IF2510', 'IH2510'] })
  })

  it('removeSymbols POSTs to /quote/symbols/remove', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)
    await quoteApi.removeSymbols('ctp', ['IF2510'])
    expect(post).toHaveBeenCalledWith('/quote/symbols/remove', { source: 'ctp', symbols: ['IF2510'] })
  })

  it('removeSubscriptions POSTs to the dedicated subscription endpoint', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)

    await quoteApi.removeSubscriptions('ctp', ['IF2510'])

    expect(post).toHaveBeenCalledWith('/quote/subscriptions/remove', {
      source: 'ctp',
      symbols: ['IF2510'],
    })
  })

  it('searchSymbols GETs with source + keyword', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.searchSymbols('ctp', '螺纹')
    expect(get).toHaveBeenCalledWith('/quote/symbols/search', { params: { source: 'ctp', keyword: '螺纹' } })
  })

  it('getQuotes GETs without symbols param when none provided', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.getQuotes('ctp')
    expect(get).toHaveBeenCalledWith('/quote/ticks', { params: { source: 'ctp' } })
  })

  it('getQuotes GETs with comma-joined symbols when provided', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.getQuotes('ctp', ['IF2510', 'IH2510'])
    expect(get).toHaveBeenCalledWith('/quote/ticks', { params: { source: 'ctp', symbols: 'IF2510,IH2510' } })
  })

  it('getQuotes GETs without symbols param when array is empty', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.getQuotes('ctp', [])
    expect(get).toHaveBeenCalledWith('/quote/ticks', { params: { source: 'ctp' } })
  })

  it('getChartData GETs with default timeframe + count', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.getChartData('ctp', 'IF2510')
    expect(get).toHaveBeenCalledWith('/quote/chart', {
      params: { source: 'ctp', symbol: 'IF2510', timeframe: 'M1', count: 200 },
    })
  })

  it('getChartData GETs with custom timeframe + count', async () => {
    const { quoteApi } = await import('@/api/quote')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await quoteApi.getChartData('ctp', 'IF2510', 'D1', 500)
    expect(get).toHaveBeenCalledWith('/quote/chart', {
      params: { source: 'ctp', symbol: 'IF2510', timeframe: 'D1', count: 500 },
    })
  })
})
