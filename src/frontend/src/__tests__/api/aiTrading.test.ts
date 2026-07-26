import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
  },
}))

describe('aiTrading API', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('executeTrade POSTs with default dry_run=true and auto_confirm=false', async () => {
    const request = (await import('@/api/index')).default
    const post = vi.mocked(request.post).mockResolvedValue({ trade_id: 't-1' } as never)
    const { executeTrade } = await import('@/api/aiTrading')

    const result = await executeTrade({ message: 'buy 100 AAPL' })

    expect(post).toHaveBeenCalledWith('/ai-trading/execute', {
      message: 'buy 100 AAPL',
      gateway_id: null,
      account_id: null,
      dry_run: true,
      auto_confirm: false,
    })
    expect(result).toEqual({ trade_id: 't-1' })
  })

  it('executeTrade respects custom gateway/account/dry_run/auto_confirm', async () => {
    const request = (await import('@/api/index')).default
    const post = vi.mocked(request.post).mockResolvedValue({} as never)
    const { executeTrade } = await import('@/api/aiTrading')

    await executeTrade({
      message: 'sell',
      gateway_id: 'gw-1',
      account_id: 'acc-1',
      dry_run: false,
      auto_confirm: true,
    })

    expect(post).toHaveBeenCalledWith('/ai-trading/execute', {
      message: 'sell',
      gateway_id: 'gw-1',
      account_id: 'acc-1',
      dry_run: false,
      auto_confirm: true,
    })
  })

  it('confirmTrade POSTs the params verbatim', async () => {
    const request = (await import('@/api/index')).default
    const post = vi.mocked(request.post).mockResolvedValue({} as never)
    const { confirmTrade } = await import('@/api/aiTrading')

    await confirmTrade({ trade_id: 't-1', confirmed: true, user_note: 'looks ok' })
    expect(post).toHaveBeenCalledWith('/ai-trading/confirm', {
      trade_id: 't-1', confirmed: true, user_note: 'looks ok',
    })
  })

  it('getTradingConfig GETs /config', async () => {
    const request = (await import('@/api/index')).default
    const get = vi.mocked(request.get).mockResolvedValue({ enabled: true } as never)
    const { getTradingConfig } = await import('@/api/aiTrading')

    const result = await getTradingConfig()
    expect(get).toHaveBeenCalledWith('/ai-trading/config')
    expect(result).toEqual({ enabled: true })
  })

  it('getTradingHistory GETs /history with default limit', async () => {
    const request = (await import('@/api/index')).default
    const get = vi.mocked(request.get).mockResolvedValue({ total: 0, items: [] } as never)
    const { getTradingHistory } = await import('@/api/aiTrading')

    await getTradingHistory()
    expect(get).toHaveBeenCalledWith('/ai-trading/history', { params: { limit: 20 } })
  })

  it('getTradingHistory GETs with custom limit', async () => {
    const request = (await import('@/api/index')).default
    const get = vi.mocked(request.get).mockResolvedValue({} as never)
    const { getTradingHistory } = await import('@/api/aiTrading')

    await getTradingHistory(50)
    expect(get).toHaveBeenCalledWith('/ai-trading/history', { params: { limit: 50 } })
  })

  it('reflectOnTrade POSTs to the reflect endpoint with trade id in path', async () => {
    const request = (await import('@/api/index')).default
    const post = vi.mocked(request.post).mockResolvedValue({ success: true } as never)
    const { reflectOnTrade } = await import('@/api/aiTrading')

    await reflectOnTrade('t-1')
    expect(post).toHaveBeenCalledWith('/ai-trading/reflect/t-1')
  })
})
