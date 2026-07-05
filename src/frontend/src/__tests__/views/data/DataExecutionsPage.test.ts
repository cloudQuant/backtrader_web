import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { ExecutionStatsResponse, TaskExecution } from '@/types'
import { elStubs } from '@/test/stubs'

const statsFixture: ExecutionStatsResponse = {
  total_count: 12,
  success_count: 8,
  failed_count: 3,
  running_count: 1,
  success_rate: 0.66,
  avg_duration: 12.5,
}

const executionFixture: TaskExecution = {
  id: 1,
  execution_id: 'exec-1',
  task_id: 11,
  script_id: 'stock_zh_a_hist',
  params: { symbol: '000001' },
  status: 'failed',
  start_time: '2026-07-01T08:00:00Z',
  end_time: '2026-07-01T08:00:10Z',
  duration: 10,
  result: { rows: 120 },
  error_message: 'network timeout',
  error_trace: 'Traceback...',
  rows_before: 100,
  rows_after: 120,
  retry_count: 1,
  triggered_by: 'scheduler',
  operator_id: 'admin',
  created_at: '2026-07-01T08:00:00Z',
  updated_at: '2026-07-01T08:00:10Z',
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, params?: Record<string, unknown>) => (params?.count !== undefined ? `${k}:${params.count}` : k) }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { task_id: '11', script_id: 'stock_zh_a_hist' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/akshare', () => ({
  akshareExecutionsApi: {
    list: vi.fn(),
    getStats: vi.fn(),
    getDetail: vi.fn(),
    retry: vi.fn(),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { is_admin: true } }),
}))

import DataExecutionsPage from '@/views/data/DataExecutionsPage.vue'
import { akshareExecutionsApi } from '@/api/akshare'

const api = akshareExecutionsApi as unknown as Record<string, ReturnType<typeof vi.fn>>

async function flushAsync() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

function doMount() {
  return mount(DataExecutionsPage, { global: { stubs: elStubs } })
}

describe('DataExecutionsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.getStats.mockResolvedValue({ ...statsFixture })
    api.list.mockResolvedValue({ items: [{ ...executionFixture }], total: 1 })
    api.getDetail.mockResolvedValue({ ...executionFixture })
    api.retry.mockResolvedValue({ execution_id: 'exec-retry-1', status: 'queued' })
  })

  it('loads stats and execution list with route filters', async () => {
    doMount()
    await flushAsync()

    expect(api.getStats).toHaveBeenCalled()
    expect(api.list).toHaveBeenCalledWith(expect.objectContaining({
      task_id: 11,
      script_id: 'stock_zh_a_hist',
    }))
  })

  it('renders the redesigned execution workbench', async () => {
    const wrapper = doMount()
    await flushAsync()

    expect(wrapper.find('[data-test="executions-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="executions-metrics"]').findAll('.executions-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="executions-workbench"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="executions-table"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('execWorkbenchTitle')
    expect(wrapper.text()).toContain('exec-1')
    expect(wrapper.text()).toContain('network timeout')
  })

  it('opens execution detail drawer', async () => {
    const wrapper = doMount()
    await flushAsync()

    await (wrapper.vm as unknown as { openDetail: (id: string) => Promise<void> }).openDetail('exec-1')

    expect(api.getDetail).toHaveBeenCalledWith('exec-1')
    expect((wrapper.vm as unknown as { detailVisible: boolean }).detailVisible).toBe(true)
    expect(wrapper.text()).toContain('Traceback')
  })

  it('retries failed execution and reloads data', async () => {
    const wrapper = doMount()
    await flushAsync()

    await (wrapper.vm as unknown as { retryExecution: (id: string) => Promise<void> }).retryExecution('exec-1')

    expect(api.retry).toHaveBeenCalledWith('exec-1')
    expect(api.getStats).toHaveBeenCalledTimes(2)
    expect(api.list).toHaveBeenCalledTimes(2)
  })
})
