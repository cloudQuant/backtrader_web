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

  it('covers the remaining akshare endpoint wrappers', async () => {
    vi.mocked(api.get).mockResolvedValue({})
    vi.mocked(api.post).mockResolvedValue({})
    vi.mocked(api.put).mockResolvedValue({})
    vi.mocked(api.patch).mockResolvedValue({})
    vi.mocked(api.delete).mockResolvedValue({})

    await akshareScriptsApi.getCategories()
    await akshareScriptsApi.getStats()
    await akshareScriptsApi.getDetail('script-1')
    await akshareScriptsApi.scan()
    await akshareScriptsApi.run('script-1', { parameters: { symbol: 'IF00' } })
    await akshareScriptsApi.toggle('script-1')
    await akshareScriptsApi.create({ script_id: 'script-1', script_name: '脚本', category: 'macro' })
    await akshareScriptsApi.update('script-1', { script_name: '已更新脚本' })
    await akshareScriptsApi.delete('script-1')

    await akshareTasksApi.getScheduleTemplates()
    await akshareTasksApi.list({ page: 1, is_active: true })
    await akshareTasksApi.getDetail(11)
    await akshareTasksApi.update(11, { name: 'task' })
    await akshareTasksApi.delete(11)
    await akshareTasksApi.toggle(11)
    await akshareTasksApi.run(11)
    await akshareTasksApi.getExecutions(11, { page: 2, page_size: 20 })

    await akshareExecutionsApi.list({ task_id: 11, script_id: 'script-1', status: 'running' })
    await akshareExecutionsApi.getStats()
    await akshareExecutionsApi.getRecent(5)
    await akshareExecutionsApi.getRunning()
    await akshareExecutionsApi.getDetail('exec-1')

    await akshareTablesApi.list({ search: 'macro', page: 1 })
    await akshareTablesApi.getDetail(3)
    await akshareTablesApi.getSchema(3)

    await akshareInterfacesApi.getCategories()
    await akshareInterfacesApi.list({ category_id: 2, search: 'stock', is_active: true })
    await akshareInterfacesApi.getDetail(9)
    await akshareInterfacesApi.create({
      name: 'stock_zh_a_hist',
      display_name: 'A股日线',
      category_id: 2,
      parameters: {},
      extra_config: {},
      return_type: 'DataFrame',
      is_active: true,
    })
    await akshareInterfacesApi.update(9, { display_name: '已更新接口' })
    await akshareInterfacesApi.delete(9)

    expect(api.get).toHaveBeenCalledWith('/data/scripts/categories')
    expect(api.get).toHaveBeenCalledWith('/data/scripts/stats')
    expect(api.get).toHaveBeenCalledWith('/data/scripts/script-1')
    expect(api.post).toHaveBeenCalledWith('/data/scripts/scan')
    expect(api.post).toHaveBeenCalledWith('/data/scripts/script-1/run', { parameters: { symbol: 'IF00' } })
    expect(api.put).toHaveBeenCalledWith('/data/scripts/script-1/toggle')
    expect(api.post).toHaveBeenCalledWith('/data/scripts/admin/scripts', {
      script_id: 'script-1',
      script_name: '脚本',
      category: 'macro',
    })
    expect(api.put).toHaveBeenCalledWith('/data/scripts/admin/scripts/script-1', { script_name: '已更新脚本' })
    expect(api.delete).toHaveBeenCalledWith('/data/scripts/admin/scripts/script-1')

    expect(api.get).toHaveBeenCalledWith('/data/tasks/schedule/templates')
    expect(api.get).toHaveBeenCalledWith('/data/tasks', { params: { page: 1, is_active: true } })
    expect(api.get).toHaveBeenCalledWith('/data/tasks/11')
    expect(api.put).toHaveBeenCalledWith('/data/tasks/11', { name: 'task' })
    expect(api.delete).toHaveBeenCalledWith('/data/tasks/11')
    expect(api.patch).toHaveBeenCalledWith('/data/tasks/11/toggle')
    expect(api.post).toHaveBeenCalledWith('/data/tasks/11/run')
    expect(api.get).toHaveBeenCalledWith('/data/tasks/11/executions', { params: { page: 2, page_size: 20 } })

    expect(api.get).toHaveBeenCalledWith('/data/executions', {
      params: { task_id: 11, script_id: 'script-1', status: 'running' },
    })
    expect(api.get).toHaveBeenCalledWith('/data/executions/stats')
    expect(api.get).toHaveBeenCalledWith('/data/executions/recent', { params: { limit: 5 } })
    expect(api.get).toHaveBeenCalledWith('/data/executions/running')
    expect(api.get).toHaveBeenCalledWith('/data/executions/exec-1')

    expect(api.get).toHaveBeenCalledWith('/data/tables', { params: { search: 'macro', page: 1 } })
    expect(api.get).toHaveBeenCalledWith('/data/tables/3')
    expect(api.get).toHaveBeenCalledWith('/data/tables/3/schema')

    expect(api.get).toHaveBeenCalledWith('/data/interfaces/categories')
    expect(api.get).toHaveBeenCalledWith('/data/interfaces', {
      params: { category_id: 2, search: 'stock', is_active: true },
    })
    expect(api.get).toHaveBeenCalledWith('/data/interfaces/9')
    expect(api.post).toHaveBeenCalledWith('/data/interfaces', {
      name: 'stock_zh_a_hist',
      display_name: 'A股日线',
      category_id: 2,
      parameters: {},
      extra_config: {},
      return_type: 'DataFrame',
      is_active: true,
    })
    expect(api.put).toHaveBeenCalledWith('/data/interfaces/9', { display_name: '已更新接口' })
    expect(api.delete).toHaveBeenCalledWith('/data/interfaces/9')
  })
})
