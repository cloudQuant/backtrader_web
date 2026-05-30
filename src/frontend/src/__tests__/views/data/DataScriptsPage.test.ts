import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/akshare', () => ({
  akshareScriptsApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getCategories: vi.fn().mockResolvedValue(['stock', 'future']),
    getStats: vi.fn().mockResolvedValue({
      total_scripts: 3,
      active_scripts: 2,
      custom_scripts: 1,
      categories: [],
    }),
    create: vi.fn().mockResolvedValue({ script_id: 's-1' }),
    update: vi.fn().mockResolvedValue({ script_id: 's-1' }),
    delete: vi.fn().mockResolvedValue(undefined),
    run: vi.fn().mockResolvedValue({ execution_id: 'e-1' }),
    scan: vi.fn().mockResolvedValue({ created: 1, updated: 0 }),
    toggle: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { is_admin: true } }),
}))

import DataScriptsPage from '@/views/data/DataScriptsPage.vue'
import { akshareScriptsApi } from '@/api/akshare'
import { elStubs } from '@/test/stubs'

const api = akshareScriptsApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function doMount() {
  return mount(DataScriptsPage, { global: { stubs: elStubs } })
}

describe('DataScriptsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads categories, stats and scripts on mount', async () => {
    doMount()
    await new Promise(r => setTimeout(r, 0))
    expect(api.getCategories).toHaveBeenCalled()
    expect(api.getStats).toHaveBeenCalled()
    expect(api.list).toHaveBeenCalled()
  })

  it('isAdmin reflects the auth store', () => {
    const vm = doMount().vm as any
    expect(vm.isAdmin).toBe(true)
  })

  it('resetForm clears the form back to defaults', () => {
    const vm = doMount().vm as any
    vm.form.script_id = 'dirty'
    vm.form.function_name = 'changed'
    vm.dependenciesText = '{"a":1}'
    vm.resetForm()
    expect(vm.form.script_id).toBe('')
    expect(vm.form.function_name).toBe('main')
    expect(vm.dependenciesText).toBe('{}')
  })

  it('openCreateDialog resets form and opens dialog in create mode', () => {
    const vm = doMount().vm as any
    vm.openCreateDialog()
    expect(vm.dialogVisible).toBe(true)
    expect(vm.dialogMode).toBe('create')
    expect(vm.form.script_id).toBe('')
  })

  it('openEditDialog loads the script into the form in edit mode', () => {
    const vm = doMount().vm as any
    vm.openEditDialog({
      script_id: 's-9',
      script_name: 'Nine',
      category: 'stock',
      frequency: 'daily',
      function_name: 'run',
      dependencies: {},
    })
    expect(vm.dialogVisible).toBe(true)
    expect(vm.dialogMode).toBe('edit')
    expect(vm.form.script_id).toBe('s-9')
  })

  it('handleScan invokes the scan API', async () => {
    const vm = doMount().vm as any
    await vm.handleScan()
    expect(api.scan).toHaveBeenCalled()
  })

  it('runScript invokes the run API', async () => {
    const vm = doMount().vm as any
    await vm.runScript('s-1')
    expect(api.run).toHaveBeenCalledWith('s-1', { parameters: {} })
  })

  it('toggleScript invokes the toggle API', async () => {
    const vm = doMount().vm as any
    await vm.toggleScript('s-1')
    expect(api.toggle).toHaveBeenCalledWith('s-1')
  })
})
