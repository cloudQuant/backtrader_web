import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import DataScriptsPage from '@/views/data/DataScriptsPage.vue'
import { mountWithPlugins } from '@/test/mountWithPlugins'

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
}))

const apiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getCategories: vi.fn(),
  getStats: vi.fn(),
  scan: vi.fn(),
  run: vi.fn(),
  toggle: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
}))

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}))

const confirmMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ push: routerMocks.push }),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: messageMocks,
  ElMessageBox: {
    confirm: confirmMock,
  },
}))

vi.mock('@/api/akshare', () => ({
  akshareScriptsApi: apiMocks,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: {
      is_admin: true,
    },
  }),
}))

describe('DataScriptsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getCategories.mockResolvedValue(['macro', 'futures'])
    apiMocks.getStats.mockResolvedValue({
      total_scripts: 3,
      active_scripts: 2,
      custom_scripts: 1,
      categories: ['macro', 'futures'],
    })
    apiMocks.list.mockResolvedValue({
      items: [
        {
          script_id: 'script-1',
          script_name: '主力脚本',
          category: 'macro',
          sub_category: null,
          frequency: 'daily',
          description: '测试脚本',
          source: 'akshare',
          target_table: 'market_macro',
          module_path: 'app.scripts.market_macro',
          function_name: 'main',
          dependencies: { limit: 10 },
          estimated_duration: 60,
          timeout: 300,
          is_active: true,
          is_custom: true,
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      total: 1,
    })
    apiMocks.scan.mockResolvedValue({ registered: 1, updated: 2, errors: [] })
    apiMocks.run.mockResolvedValue({ execution_id: 'exec-1' })
    apiMocks.toggle.mockResolvedValue(undefined)
    apiMocks.create.mockResolvedValue(undefined)
    apiMocks.update.mockResolvedValue(undefined)
    apiMocks.delete.mockResolvedValue(undefined)
    confirmMock.mockResolvedValue(undefined)
  })

  it('loads scripts and executes create/edit/run/toggle/delete flows', async () => {
    const wrapper = mountWithPlugins(DataScriptsPage)
    await flushPromises()

    expect(apiMocks.getCategories).toHaveBeenCalledTimes(1)
    expect(apiMocks.getStats).toHaveBeenCalledTimes(1)
    expect(apiMocks.list).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('数据脚本')

    const vm = wrapper.vm as any

    vm.openCreateDialog()
    vm.form.script_id = 'custom.script'
    vm.form.script_name = '自定义脚本'
    vm.form.category = 'macro'
    vm.dependenciesText = '{"limit": 5}'
    await vm.submitForm()
    await flushPromises()

    expect(apiMocks.create).toHaveBeenCalledWith(expect.objectContaining({
      script_id: 'custom.script',
      script_name: '自定义脚本',
      category: 'macro',
      dependencies: { limit: 5 },
    }))
    expect(messageMocks.success).toHaveBeenCalledWith('脚本已创建')

    const currentScript = apiMocks.list.mock.results[0]?.value ? undefined : undefined
    const row = {
      script_id: 'script-1',
      script_name: '主力脚本',
      category: 'macro',
      sub_category: null,
      frequency: 'daily',
      description: '测试脚本',
      source: 'akshare',
      target_table: 'market_macro',
      module_path: 'app.scripts.market_macro',
      function_name: 'main',
      dependencies: { limit: 10 },
      estimated_duration: 60,
      timeout: 300,
      is_active: true,
      is_custom: true,
    }
    void currentScript

    vm.openEditDialog(row)
    await vm.submitForm()
    await flushPromises()

    expect(apiMocks.update).toHaveBeenCalledWith('script-1', expect.objectContaining({
      script_name: '主力脚本',
      category: 'macro',
      dependencies: { limit: 10 },
    }))

    await vm.handleScan()
    await vm.runScript('script-1')
    await vm.toggleScript('script-1')
    await vm.deleteScript(row)
    await flushPromises()

    expect(apiMocks.scan).toHaveBeenCalledTimes(1)
    expect(apiMocks.run).toHaveBeenCalledWith('script-1', { parameters: {} })
    expect(routerMocks.push).toHaveBeenCalledWith({ name: 'DataExecutions', query: { script_id: 'script-1' } })
    expect(apiMocks.toggle).toHaveBeenCalledWith('script-1')
    expect(apiMocks.delete).toHaveBeenCalledWith('script-1')
  })
})
