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

vi.mock('@/api/akshare', () => ({
  akshareInterfacesApi: {
    getCategories: vi.fn().mockResolvedValue([
      { id: 1, name: 'stock', description: '股票' },
      { id: 2, name: 'future', description: '' },
    ]),
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    bootstrap: vi.fn().mockResolvedValue({ created: 2, updated: 1 }),
    getDetail: vi.fn().mockResolvedValue({ id: 1, name: 'stock_zh_a' }),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { is_admin: true } }),
}))

import DataInterfacesPage from '@/views/data/DataInterfacesPage.vue'
import { akshareInterfacesApi } from '@/api/akshare'
import { elStubs } from '@/test/stubs'

const api = akshareInterfacesApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function doMount() {
  return mount(DataInterfacesPage, { global: { stubs: elStubs } })
}

describe('DataInterfacesPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads categories and interfaces on mount', async () => {
    doMount()
    await new Promise(r => setTimeout(r, 0))
    expect(api.getCategories).toHaveBeenCalled()
    expect(api.list).toHaveBeenCalled()
  })

  it('isAdmin reflects the auth store', () => {
    expect((doMount().vm as any).isAdmin).toBe(true)
  })

  it('categoryNameMap maps id to description or name', async () => {
    const vm = doMount().vm as any
    await new Promise(r => setTimeout(r, 0))
    expect(vm.categoryNameMap[1]).toBe('股票')
    expect(vm.categoryNameMap[2]).toBe('future') // empty description falls back to name
  })

  it('resetForm restores defaults', () => {
    const vm = doMount().vm as any
    vm.form.name = 'dirty'
    vm.parametersText = '{"a":1}'
    vm.resetForm()
    expect(vm.form.name).toBe('')
    expect(vm.form.module_path).toBe('akshare')
    expect(vm.parametersText).toBe('{}')
  })

  it('openCreateDialog opens in create mode with a fresh form', () => {
    const vm = doMount().vm as any
    vm.openCreateDialog()
    expect(vm.dialogVisible).toBe(true)
    expect(vm.editingInterfaceId).toBeNull()
  })

  it('bootstrapInterfaces invokes the bootstrap API', async () => {
    const vm = doMount().vm as any
    await vm.bootstrapInterfaces()
    expect(api.bootstrap).toHaveBeenCalledWith(true)
  })

  it('openDetail fetches the interface detail', async () => {
    const vm = doMount().vm as any
    await vm.openDetail(1)
    expect(api.getDetail).toHaveBeenCalledWith(1)
    expect(vm.currentInterface?.id).toBe(1)
  })

  it('deleteInterface confirms and deletes', async () => {
    const vm = doMount().vm as any
    await vm.deleteInterface(7)
    expect(api.delete).toHaveBeenCalledWith(7)
  })
})
