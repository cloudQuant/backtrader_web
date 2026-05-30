/**
 * Smoke tests for small API client modules (audit, autoTrading, sync) which
 * had 0% coverage. Each module is a thin wrapper around the shared `api`
 * axios instance; we mock the instance and verify each export delegates to
 * the right HTTP verb and path.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

// audit.ts imports from '@/api' (re-export). Ensure the same default is used.
vi.mock('@/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('api/sync', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.clearAllMocks() })

  it('exposes 8 verbs that delegate to api.{get,post,put}', async () => {
    const { syncApi } = await import('@/api/sync')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)
    const put = vi.mocked(apiModule.put).mockResolvedValue({} as never)

    await syncApi.getConfig()
    expect(get).toHaveBeenCalledWith('/data/sync/config')

    await syncApi.saveConfig({} as any)
    expect(put).toHaveBeenCalledWith('/data/sync/config', expect.any(Object))

    await syncApi.testConnection({} as any)
    expect(post).toHaveBeenCalledWith('/data/sync/test-connection', expect.any(Object))

    await syncApi.getDatabases()
    expect(get).toHaveBeenCalledWith('/data/sync/databases')

    await syncApi.upload({ database: 'd', table: 't' } as any)
    expect(post).toHaveBeenCalledWith('/data/sync/upload', expect.any(Object))

    await syncApi.download({ database: 'd', table: 't' } as any)
    expect(post).toHaveBeenCalledWith('/data/sync/download', expect.any(Object))

    await syncApi.getStatus('task-1')
    expect(get).toHaveBeenCalledWith('/data/sync/status/task-1')

    await syncApi.getHistory(20)
    expect(get).toHaveBeenCalledWith('/data/sync/history', { params: { limit: 20 } })

    await syncApi.getHistory()
    expect(get).toHaveBeenCalledWith('/data/sync/history', { params: { limit: 50 } })
  })
})

describe('api/audit', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('postAuditEvents POSTs to /audit/events with the events payload', async () => {
    const { postAuditEvents } = await import('@/api/audit')
    const apiModule = (await import('@/api')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({ persisted: 3, total: 3 } as never)

    const events = [
      { event_type: 'click', page_path: '/', client_timestamp: '2026-05-29T00:00:00Z' },
    ]
    const result = await postAuditEvents(events as any)

    expect(post).toHaveBeenCalledWith('/audit/events', { events })
    expect(result).toEqual({ persisted: 3, total: 3 })
  })

  it('getAuditRecords GETs /audit/records with params', async () => {
    const { getAuditRecords } = await import('@/api/audit')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({
      items: [], total_count: 0, current_page: 1, total_pages: 0,
    } as never)

    await getAuditRecords({ user_id: 'u-1', page: 1, page_size: 10 })
    expect(get).toHaveBeenCalledWith('/audit/records', {
      params: { user_id: 'u-1', page: 1, page_size: 10 },
    })
  })
})

describe('api/autoTrading', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getConfig GETs /auto-trading/config', async () => {
    const { autoTradingApi } = await import('@/api/autoTrading')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({ enabled: false } as never)

    await autoTradingApi.getConfig()
    expect(get).toHaveBeenCalledWith('/auto-trading/config')
  })

  it('updateConfig PUTs /auto-trading/config with the payload', async () => {
    const { autoTradingApi } = await import('@/api/autoTrading')
    const apiModule = (await import('@/api/index')).default
    const put = vi.mocked(apiModule.put).mockResolvedValue({ enabled: true } as never)

    await autoTradingApi.updateConfig({ enabled: true })
    expect(put).toHaveBeenCalledWith('/auto-trading/config', { enabled: true })
  })

  it('getSchedule GETs /auto-trading/schedule', async () => {
    const { autoTradingApi } = await import('@/api/autoTrading')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({ schedule: [], config: {} } as never)

    await autoTradingApi.getSchedule()
    expect(get).toHaveBeenCalledWith('/auto-trading/schedule')
  })
})
