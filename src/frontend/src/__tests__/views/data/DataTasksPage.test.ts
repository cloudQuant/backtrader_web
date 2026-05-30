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
  useRoute: () => ({ query: {}, params: {}, path: '/data/tasks' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('@/api/akshare', () => ({
  akshareScriptsApi: {
    list: vi.fn().mockResolvedValue({
      items: [{ script_id: 's-1', script_name: 'Alpha' }],
      total: 1,
    }),
  },
  akshareTasksApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getScheduleTemplates: vi.fn().mockResolvedValue({
      templates: [{ value: 'every_day', label: 'Daily', cron_expression: '0 8 * * *' }],
    }),
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    run: vi.fn().mockResolvedValue({ execution_id: 'e-1' }),
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

import DataTasksPage from '@/views/data/DataTasksPage.vue'
import { akshareTasksApi } from '@/api/akshare'
import { elStubs } from '@/test/stubs'

const tasksApi = akshareTasksApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function doMount() {
  return mount(DataTasksPage, { global: { stubs: elStubs } })
}

describe('DataTasksPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads scripts, templates and tasks on mount', async () => {
    doMount()
    await new Promise(r => setTimeout(r, 0))
    expect(tasksApi.list).toHaveBeenCalled()
    expect(tasksApi.getScheduleTemplates).toHaveBeenCalled()
  })

  it('isAdmin reflects the auth store', () => {
    expect((doMount().vm as any).isAdmin).toBe(true)
  })

  it('scriptNameMap maps script_id to script_name', async () => {
    const vm = doMount().vm as any
    await new Promise(r => setTimeout(r, 0))
    expect(vm.scriptNameMap['s-1']).toBe('Alpha')
  })

  it('resetForm restores defaults', () => {
    const vm = doMount().vm as any
    vm.form.name = 'dirty'
    vm.paramsText = '{"a":1}'
    vm.resetForm()
    expect(vm.form.name).toBe('')
    expect(vm.form.schedule_type).toBe('cron')
    expect(vm.paramsText).toBe('{}')
  })

  it('handleTemplateChange applies the chosen template schedule', async () => {
    const vm = doMount().vm as any
    await new Promise(r => setTimeout(r, 0))
    vm.handleTemplateChange('every_day')
    expect(vm.form.schedule_type).toBe('cron')
    expect(vm.form.schedule_expression).toBe('0 8 * * *')
  })

  it('openCreateDialog opens in create mode', () => {
    const vm = doMount().vm as any
    vm.openCreateDialog()
    expect(vm.dialogVisible).toBe(true)
    expect(vm.editingTaskId).toBeNull()
  })

  it('runTask invokes the run API', async () => {
    const vm = doMount().vm as any
    await vm.runTask(3)
    expect(tasksApi.run).toHaveBeenCalledWith(3)
  })

  it('toggleTask invokes the toggle API', async () => {
    const vm = doMount().vm as any
    await vm.toggleTask(3)
    expect(tasksApi.toggle).toHaveBeenCalledWith(3)
  })

  it('deleteTask confirms and deletes', async () => {
    const vm = doMount().vm as any
    await vm.deleteTask(9)
    expect(tasksApi.delete).toHaveBeenCalledWith(9)
  })
})
