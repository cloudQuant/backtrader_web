import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DataPage from '@/views/DataPage.vue'
import { elStubs } from '@/test/stubs'
import type { KlineRecord } from '@/types'

type DataPageVm = {
  queryForm: { symbol: string; start_date: string; end_date: string }
  tableData: KlineRecord[]
  loading: boolean
  exportData: () => void
}

type MockDayjsInstance = {
  subtract: () => MockDayjsInstance
  format: () => string
  toDate: () => Date
}

type MockDayjsFactory = {
  (_value?: unknown): MockDayjsInstance
  default?: MockDayjsFactory
}

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn().mockResolvedValue({ kline: null, records: [], count: 0 }) },
}))

vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    listConnectedGateways: vi.fn().mockResolvedValue({ gateways: [] }),
    queryGatewayAccount: vi.fn().mockResolvedValue({}),
    queryGatewayPositions: vi.fn().mockResolvedValue({ positions: [] }),
  },
}))

vi.mock('@/components/charts/KlineChart.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('dayjs', () => {
  const fn: MockDayjsFactory = (_v?: unknown) => ({
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
    const vm = doMount().vm as unknown as DataPageVm
    expect(vm.queryForm.symbol).toBe('000001.SZ')
    expect(vm.loading).toBe(false)
  })

  it('exportData does nothing when no data', () => {
    const vm = doMount().vm as unknown as DataPageVm
    vm.exportData()
  })

  it('exportData creates CSV download', async () => {
    const vm = doMount().vm as unknown as DataPageVm
    vm.tableData = [{ date: '2024-01-01', open: 10, high: 11, low: 9, close: 10.5, volume: 1000, change: 1.5 }]

    // Mock URL methods using globalThis
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:url')
    globalThis.URL.revokeObjectURL = vi.fn()

    // Track the click event without interfering with DOM creation
    let clickedHref = ''
    let clickedDownload = ''
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) {
      clickedHref = this.href
      clickedDownload = this.download
    })

    vm.exportData()

    expect(globalThis.URL.createObjectURL).toHaveBeenCalled()
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalled()
    expect(clickedHref).toContain('blob:url')
    expect(clickedDownload).toBe('000001.SZ_2024-01-01.csv')

    const { ElMessage } = await import('element-plus')
    expect(ElMessage.success).toHaveBeenCalledWith('导出成功')

    clickSpy.mockRestore()
  })
})
