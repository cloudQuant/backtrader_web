import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '@/api/index'
import { akshareExecutionsApi, akshareInterfacesApi, akshareScriptsApi, akshareTablesApi, akshareTasksApi } from '@/api/akshare'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('akshare api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('scripts list calls GET /data/scripts', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    await akshareScriptsApi.list({ page: 1, keyword: 'hist' })
    expect(api.get).toHaveBeenCalledWith('/data/scripts', {
      params: { page: 1, keyword: 'hist' },
    })
  })

  it('tasks create calls POST /data/tasks', async () => {
    vi.mocked(api.post).mockResolvedValue({ id: 1 })
    await akshareTasksApi.create({
      name: 'job',
      script_id: 'stock_zh_a_hist',
      schedule_type: 'cron',
      schedule_expression: '0 8 * * *',
    })
    expect(api.post).toHaveBeenCalledWith('/data/tasks', {
      name: 'job',
      script_id: 'stock_zh_a_hist',
      schedule_type: 'cron',
      schedule_expression: '0 8 * * *',
    })
  })

  it('executions retry calls POST /data/executions/:id/retry', async () => {
    vi.mocked(api.post).mockResolvedValue({ execution_id: 'ak_exec_1' })
    await akshareExecutionsApi.retry('ak_exec_1')
    expect(api.post).toHaveBeenCalledWith('/data/executions/ak_exec_1/retry')
  })

  it('tables rows calls GET /data/tables/:id/data', async () => {
    vi.mocked(api.get).mockResolvedValue({ columns: [], rows: [], total: 0, page: 1, page_size: 50 })
    await akshareTablesApi.getRows(3, { page: 2, page_size: 50 })
    expect(api.get).toHaveBeenCalledWith('/data/tables/3/data', {
      params: { page: 2, page_size: 50 },
    })
  })

  it('interfaces bootstrap passes refresh param', async () => {
    vi.mocked(api.post).mockResolvedValue({ created: 1, updated: 0 })
    await akshareInterfacesApi.bootstrap(true)
    expect(api.post).toHaveBeenCalledWith('/data/interfaces/bootstrap', undefined, {
      params: { refresh: true },
    })
  })
})
