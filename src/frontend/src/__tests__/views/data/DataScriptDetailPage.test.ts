import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { DataScript } from '@/types'
import { elStubs } from '@/test/stubs'

const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
}))

const scriptFixture: DataScript = {
  id: 1,
  script_id: 'stock_zh_a_hist',
  script_name: 'A-share daily bars',
  category: 'stock',
  sub_category: 'daily',
  frequency: 'daily',
  description: 'Collects daily A-share OHLCV data.',
  source: 'akshare',
  target_table: 'stock_zh_a_hist',
  module_path: 'collectors.stock',
  function_name: 'fetch_daily',
  dependencies: { symbol: { type: 'string', required: true } },
  estimated_duration: 45,
  timeout: 180,
  is_active: true,
  is_custom: false,
  created_by: null,
  updated_by: 'admin',
  created_at: '2026-06-30T10:00:00Z',
  updated_at: '2026-07-01T10:30:00Z',
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, params?: Record<string, unknown>) => (params?.id ? `${k}:${params.id}` : k) }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'stock_zh_a_hist' } }),
  useRouter: () => routerMock,
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/akshare', () => ({
  akshareScriptsApi: {
    getDetail: vi.fn(),
    run: vi.fn(),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { is_admin: true } }),
}))

import DataScriptDetailPage from '@/views/data/DataScriptDetailPage.vue'
import { akshareScriptsApi } from '@/api/akshare'

const api = akshareScriptsApi as unknown as Record<string, ReturnType<typeof vi.fn>>

async function flushAsync() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

function doMount() {
  return mount(DataScriptDetailPage, { global: { stubs: elStubs } })
}

describe('DataScriptDetailPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.getDetail.mockResolvedValue({ ...scriptFixture })
    api.run.mockResolvedValue({ execution_id: 'exec-1', status: 'queued' })
  })

  it('loads script detail and renders the redesigned workbench', async () => {
    const wrapper = doMount()
    await flushAsync()

    expect(api.getDetail).toHaveBeenCalledWith('stock_zh_a_hist')
    expect(wrapper.find('[data-test="script-detail-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="script-detail-metrics"]').findAll('.script-detail-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="script-detail-config-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="script-detail-run-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="script-detail-json-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('A-share daily bars')
    expect(wrapper.text()).toContain('scriptDetailConfigTitle')
    expect(wrapper.text()).toContain('scriptDetailManualRun')
    expect(wrapper.text()).toContain('scriptDetailDepsTitle')
  })

  it('runs the script and opens config execution history', async () => {
    const wrapper = doMount()
    await flushAsync()

    await (wrapper.vm as unknown as { runNow: () => Promise<void> }).runNow()

    expect(api.run).toHaveBeenCalledWith('stock_zh_a_hist', {
      parameters: { symbol: '000001' },
    })
    expect(routerMock.push).toHaveBeenCalledWith({
      name: 'ConfigDataExecutions',
      query: { script_id: 'stock_zh_a_hist' },
    })
  })

  it('opens scheduled task creation in config data center', async () => {
    const wrapper = doMount()
    await flushAsync()

    ;(wrapper.vm as unknown as { openTaskCreate: () => void }).openTaskCreate()

    expect(routerMock.push).toHaveBeenCalledWith({
      name: 'ConfigDataTasks',
      query: { script_id: 'stock_zh_a_hist' },
    })
  })
})
