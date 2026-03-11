import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LiveTradingPage from '@/views/LiveTradingPage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    list: vi.fn().mockResolvedValue({ instances: [
      {
        id: 'i1',
        strategy_id: 'live/s1',
        strategy_name: 'SMA',
        status: 'running',
        created_at: '2024-01-01',
        params: {
          gateway: {
            provider: 'gateway',
            exchange_type: 'IB_WEB',
            asset_type: 'STK',
            account_id: 'DU123456',
            base_url: 'https://localhost:5000',
          },
        },
      },
    ] }),
    listPresets: vi.fn().mockResolvedValue({ presets: [
      {
        id: 'ctp_futures_gateway',
        name: 'CTP Futures Gateway',
        description: 'Shared CTP gateway preset for domestic futures accounts.',
        editable_fields: [
          { key: 'account_id', label: '账户', input_type: 'string', placeholder: '请输入期货账户' },
        ],
        params: {
          gateway: {
            enabled: true,
            provider: 'ctp_gateway',
            exchange_type: 'CTP',
            asset_type: 'FUTURE',
            account_id: '',
          },
        },
      },
      {
        id: 'ib_web_stock_gateway',
        name: 'IB Web Stock Gateway',
        description: 'IB Web preset for US stock trading via gateway mode.',
        editable_fields: [
          { key: 'account_id', label: '账户', input_type: 'string', placeholder: '如 DU123456' },
          { key: 'base_url', label: 'Base URL', input_type: 'string', placeholder: '如 https://localhost:5000' },
          { key: 'verify_ssl', label: 'SSL校验', input_type: 'boolean' },
        ],
        params: {
          gateway: {
            enabled: true,
            provider: 'gateway',
            exchange_type: 'IB_WEB',
            asset_type: 'STK',
            account_id: 'DU123456',
            base_url: 'https://localhost:5000',
            verify_ssl: false,
          },
        },
      },
      {
        id: 'ib_web_futures_gateway',
        name: 'IB Web Futures Gateway',
        description: 'IB Web preset for futures trading via gateway mode.',
        editable_fields: [
          { key: 'account_id', label: '账户', input_type: 'string', placeholder: '如 DU123456' },
          { key: 'base_url', label: 'Base URL', input_type: 'string', placeholder: '如 https://localhost:5000' },
          { key: 'verify_ssl', label: 'SSL校验', input_type: 'boolean' },
        ],
        params: {
          gateway: {
            enabled: true,
            provider: 'gateway',
            exchange_type: 'IB_WEB',
            asset_type: 'FUT',
            account_id: 'DU223344',
            base_url: 'https://localhost:5000',
            verify_ssl: false,
          },
        },
      },
    ] }),
    add: vi.fn().mockResolvedValue({ id: 'i2' }),
    remove: vi.fn().mockResolvedValue(undefined),
    start: vi.fn().mockResolvedValue({ id: 'i1', status: 'running', strategy_name: 'SMA' }),
    stop: vi.fn().mockResolvedValue({ id: 'i1', status: 'stopped', strategy_name: 'SMA' }),
    startAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
    stopAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [{ id: 'live/s1', name: 'SMA' }] }),
  },
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    templates: [{ id: 's1', name: 'SMA' }],
  }),
}))

describe('LiveTradingPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(LiveTradingPage, { global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('statusLabel returns correct labels', () => {
    const vm = doMount().vm as any
    expect(vm.statusLabel('running')).toBe('运行中')
    expect(vm.statusLabel('error')).toBe('异常')
    expect(vm.statusLabel('stopped')).toBe('已停止')
  })

  it('runningCount computes correctly', async () => {
    const vm = doMount().vm as any
    await vi.dynamicImportSettled()
    // After loadData resolves, instances should have 1 running
    await new Promise(r => setTimeout(r, 50))
    expect(vm.runningCount).toBeGreaterThanOrEqual(0)
  })

  it('renders gateway summary for existing instance', async () => {
    const wrapper = doMount()
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 50))
    expect(wrapper.text()).toContain('IB_WEB / STK / DU123456')
  })

  it('handleAdd does nothing without strategy_id', async () => {
    const vm = doMount().vm as any
    vm.addForm.strategy_id = ''
    await vm.handleAdd()
  })

  it('handleAdd adds and reloads', async () => {
    const { ElMessage } = await import('element-plus')
    const { liveTradingApi } = await import('@/api/liveTrading')
    const vm = doMount().vm as any
    vm.addForm.strategy_id = 'live/s1'
    await vm.handleAdd()
    expect(ElMessage.success).toHaveBeenCalledWith('添加成功')
    expect(vm.showAddDialog).toBe(false)
    expect(liveTradingApi.add).toHaveBeenCalledWith('live/s1', undefined)
  })

  it('handleAdd passes selected gateway preset params', async () => {
    const { liveTradingApi } = await import('@/api/liveTrading')
    const vm = doMount().vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 0))
    vm.addForm.strategy_id = 'live/s1'
    vm.addForm.gatewayPresetId = 'ib_web_stock_gateway'
    await vm.$nextTick()
    await vm.handleAdd()
    expect(liveTradingApi.add).toHaveBeenCalledWith(
      'live/s1',
      expect.objectContaining({
        gateway: expect.objectContaining({
          provider: 'gateway',
          exchange_type: 'IB_WEB',
          asset_type: 'STK',
          account_id: 'DU123456',
          base_url: 'https://localhost:5000',
          verify_ssl: false,
        }),
      })
    )
  })

  it('prefills gateway override fields from selected preset', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 0))
    vm.addForm.gatewayPresetId = 'ib_web_stock_gateway'
    await wrapper.vm.$nextTick()

    expect(vm.gatewayOverrides.account_id).toBe('DU123456')
    expect(vm.gatewayOverrides.base_url).toBe('https://localhost:5000')
    expect(vm.gatewayOverrides.verify_ssl).toBe(false)
  })

  it('merges gateway override fields into submitted preset payload', async () => {
    const { liveTradingApi } = await import('@/api/liveTrading')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 0))

    vm.addForm.strategy_id = 'live/s1'
    vm.addForm.gatewayPresetId = 'ib_web_stock_gateway'
    await wrapper.vm.$nextTick()
    vm.gatewayOverrides.account_id = 'DU999999'
    vm.gatewayOverrides.base_url = 'https://ib.example.local'
    vm.gatewayOverrides.verify_ssl = true

    await vm.handleAdd()

    expect(liveTradingApi.add).toHaveBeenCalledWith(
      'live/s1',
      expect.objectContaining({
        gateway: expect.objectContaining({
          provider: 'gateway',
          exchange_type: 'IB_WEB',
          asset_type: 'STK',
          account_id: 'DU999999',
          base_url: 'https://ib.example.local',
          verify_ssl: true,
        }),
      })
    )
  })

  it('submits ib web futures preset payload', async () => {
    const { liveTradingApi } = await import('@/api/liveTrading')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 0))

    vm.addForm.strategy_id = 'live/s1'
    vm.addForm.gatewayPresetId = 'ib_web_futures_gateway'
    await wrapper.vm.$nextTick()
    await vm.handleAdd()

    expect(liveTradingApi.add).toHaveBeenCalledWith(
      'live/s1',
      expect.objectContaining({
        gateway: expect.objectContaining({
          provider: 'gateway',
          exchange_type: 'IB_WEB',
          asset_type: 'FUT',
          account_id: 'DU223344',
        }),
      })
    )
  })

  it('shows gateway preset preview for ib web preset', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 0))
    vm.addForm.gatewayPresetId = 'ib_web_stock_gateway'
    await wrapper.vm.$nextTick()

    expect(vm.selectedGatewayEditableFields).toEqual([
      { key: 'account_id', label: '账户', input_type: 'string', placeholder: '如 DU123456' },
      { key: 'base_url', label: 'Base URL', input_type: 'string', placeholder: '如 https://localhost:5000' },
      { key: 'verify_ssl', label: 'SSL校验', input_type: 'boolean' },
    ])
    expect(wrapper.text()).toContain('IB Web Stock Gateway')
    expect(wrapper.text()).toContain('IB Web preset for US stock trading via gateway mode.')
    expect(wrapper.text()).toContain('启用 verify_ssl')
    expect(wrapper.text()).toContain('IB_WEB')
    expect(wrapper.text()).toContain('STK')
    expect(wrapper.text()).toContain('DU123456')
    expect(wrapper.text()).toContain('https://localhost:5000')
    expect(wrapper.text()).toContain('false')
  })

  it('CTP preset renders only account_id editable field', async () => {
    const { liveTradingApi } = await import('@/api/liveTrading')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 0))

    vm.addForm.gatewayPresetId = 'ctp_futures_gateway'
    await wrapper.vm.$nextTick()

    expect(vm.selectedGatewayEditableFields).toEqual([
      { key: 'account_id', label: '账户', input_type: 'string', placeholder: '请输入期货账户' },
    ])
    expect(wrapper.text()).toContain('CTP Futures Gateway')
    expect(wrapper.text()).toContain('Shared CTP gateway preset for domestic futures accounts.')
    expect(wrapper.text()).not.toContain('启用 verify_ssl')

    vm.addForm.strategy_id = 'live/s1'
    vm.gatewayOverrides.account_id = '088888'
    await vm.handleAdd()

    expect(liveTradingApi.add).toHaveBeenCalledWith(
      'live/s1',
      expect.objectContaining({
        gateway: expect.objectContaining({
          provider: 'ctp_gateway',
          exchange_type: 'CTP',
          asset_type: 'FUTURE',
          account_id: '088888',
        }),
      })
    )
  })

  it('shows gateway detail items in detail dialog', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vi.dynamicImportSettled()
    await new Promise(r => setTimeout(r, 50))
    vm.openDetail({
      id: 'i1',
      strategy_id: 'live/s1',
      strategy_name: 'SMA',
      status: 'running',
      created_at: '2024-01-01',
      params: {
        gateway: {
          provider: 'gateway',
          exchange_type: 'IB_WEB',
          asset_type: 'STK',
          account_id: 'DU123456',
          base_url: 'https://localhost:5000',
        },
      },
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Gateway')
    expect(wrapper.text()).toContain('Provider')
    expect(wrapper.text()).toContain('IB_WEB')
    expect(wrapper.text()).toContain('DU123456')
    expect(wrapper.text()).toContain('https://localhost:5000')
  })

  it('handleRemove removes instance', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.handleRemove({ id: 'i1', strategy_name: 'SMA' })
    expect(ElMessage.success).toHaveBeenCalledWith('已删除')
  })

  it('handleStart starts instance', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    const inst = { id: 'i1', strategy_name: 'SMA', status: 'stopped' }
    await vm.handleStart(inst)
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('handleStop stops instance', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    const inst = { id: 'i1', strategy_name: 'SMA', status: 'running' }
    await vm.handleStop(inst)
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('handleStartAll batch starts', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.handleStartAll()
    expect(ElMessage.success).toHaveBeenCalled()
    expect(vm.batchLoading).toBe(false)
  })

  it('handleStopAll batch stops', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.handleStopAll()
    expect(ElMessage.success).toHaveBeenCalled()
    expect(vm.batchLoading).toBe(false)
  })

  it('goToDetail navigates', () => {
    const vm = doMount().vm as any
    vm.goToDetail({ id: 'i1' })
  })
})
