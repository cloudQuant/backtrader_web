import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DataPage from './DataPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn().mockResolvedValue({ kline: null, records: [], count: 0 }) },
}))

vi.mock('@/components/charts/KlineChart.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('dayjs', () => {
  const fn: any = (_v?: any) => ({
    subtract: () => fn(),
    format: () => '2024-01-01',
    toDate: () => new Date('2024-01-01'),
  })
  fn.default = fn
  return { default: fn }
})

describe('DataPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(DataPage, { global: { stubs: { ...elStubs, KlineChart: true } } })

  it('renders query form', () => {
    const wrapper = doMount()
    expect(wrapper.exists()).toBe(true)
  })

  it('has default query form values', () => {
    const vm = doMount().vm as any
    expect(vm.queryForm.symbol).toBe('000001.SZ')
    expect(vm.loading).toBe(false)
  })

  it('exportData does nothing when no data', () => {
    const vm = doMount().vm as any
    vm.exportData()
  })

  it('exportData creates CSV download', async () => {
    const vm = doMount().vm as any
    vm.tableData = [{ date: '2024-01-01', open: 10, high: 11, low: 9, close: 10.5, volume: 1000, change: 1.5 }]

    const mockLink = { href: '', download: '', click: vi.fn() }
    vi.spyOn(document, 'createElement').mockReturnValue(mockLink as any)
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:url')
    globalThis.URL.revokeObjectURL = vi.fn()

    vm.exportData()

    const { ElMessage } = await import('element-plus')
    expect(ElMessage.success).toHaveBeenCalledWith('导出成功')
    expect(mockLink.click).toHaveBeenCalled()
  })
})
