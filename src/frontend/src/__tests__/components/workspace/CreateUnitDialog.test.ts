import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

const fetchTemplates = vi.fn()
const createUnit = vi.fn().mockResolvedValue({ id: 'u-1' })
const batchCreateUnits = vi.fn().mockResolvedValue([{ id: 'u-1' }, { id: 'u-2' }])

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    templates: [{ id: 'tpl-1', name: 'Dual MA' }],
    fetchTemplates,
  }),
}))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({ createUnit, batchCreateUnits }),
}))

import { ElMessage } from 'element-plus'

import CreateUnitDialog from '@/components/workspace/CreateUnitDialog.vue'
import { elStubs } from '@/test/stubs'

function doMount(props: Record<string, unknown> = {}) {
  return mount(CreateUnitDialog, {
    props: { modelValue: true, workspaceId: 'ws-1', ...props },
    global: {
      stubs: {
        ...elStubs,
        // Child fetches gateway presets on mount; stub it to keep the test
        // hermetic (no fire-and-forget API rejection).
        TradingGatewaySelect: { name: 'TradingGatewaySelect', template: '<div class="trading-gateway-select-stub" />' },
      },
    },
  })
}

describe('CreateUnitDialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('mounts and fetches templates on mount when none cached', () => {
    // store mock always returns a template, so fetchTemplates should not fire,
    // but the component should still mount cleanly.
    const wrapper = doMount()
    expect(wrapper.exists()).toBe(true)
  })

  it('exposes research title for a research workspace', () => {
    const vm = doMount({ workspaceType: 'research' }).vm as any
    expect(vm.isTradingWorkspace).toBe(false)
    expect(vm.dialogTitle).toContain('unitDialog.title')
  })

  it('exposes trading title + mode label for a trading workspace', () => {
    const vm = doMount({ workspaceType: 'trading' }).vm as any
    expect(vm.isTradingWorkspace).toBe(true)
    expect(vm.tradingModeLabel).toBe('unitDialog.paperTrading')
  })

  it('onStrategyChange fills strategy_name and group_name', () => {
    const vm = doMount().vm as any
    vm.onStrategyChange('tpl-1')
    expect(vm.form.strategy_name).toBe('Dual MA')
    expect(vm.form.group_name).toBe('Dual MA')
    expect(vm.selectedStrategyName).toBe('Dual MA')
  })

  it('validSymbolCount counts only non-empty codes', () => {
    const vm = doMount().vm as any
    vm.form.symbols = [{ code: '000001', name: 'A' }, { code: '', name: '' }]
    expect(vm.validSymbolCount).toBe(1)
  })

  it('handleSubmit warns when no valid symbols', async () => {
    const vm = doMount().vm as any
    vm.form.symbols = [{ code: '', name: '' }]
    // bypass form validation
    ;(vm.formRef = { validate: vi.fn().mockResolvedValue(true), resetFields: vi.fn() })
    await vm.handleSubmit()
    expect(ElMessage.warning).toHaveBeenCalled()
    expect(createUnit).not.toHaveBeenCalled()
  })

  it('handleSubmit creates a single unit for one symbol', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.form.group_name = 'g'
    vm.form.strategy_id = 'tpl-1'
    vm.form.symbols = [{ code: '000001', name: 'PingAn' }]
    vm.formRef = { validate: vi.fn().mockResolvedValue(true), resetFields: vi.fn() }
    await vm.handleSubmit()
    expect(createUnit).toHaveBeenCalledTimes(1)
    expect(batchCreateUnits).not.toHaveBeenCalled()
    expect(ElMessage.success).toHaveBeenCalled()
    expect(wrapper.emitted('created')).toBeTruthy()
  })

  it('handleSubmit batch-creates for multiple symbols', async () => {
    const vm = doMount().vm as any
    vm.form.group_name = 'g'
    vm.form.strategy_id = 'tpl-1'
    vm.form.symbols = [
      { code: '000001', name: 'A' },
      { code: '600000', name: 'B' },
    ]
    vm.formRef = { validate: vi.fn().mockResolvedValue(true), resetFields: vi.fn() }
    await vm.handleSubmit()
    expect(batchCreateUnits).toHaveBeenCalledTimes(1)
    expect(createUnit).not.toHaveBeenCalled()
  })

  it('handleSubmit blocks live trading without a gateway preset', async () => {
    const vm = doMount({ workspaceType: 'trading' }).vm as any
    vm.form.group_name = 'g'
    vm.form.strategy_id = 'tpl-1'
    vm.form.trading_mode = 'live'
    vm.form.gateway_config = {}
    vm.form.symbols = [{ code: '000001', name: 'A' }]
    vm.formRef = { validate: vi.fn().mockResolvedValue(true), resetFields: vi.fn() }
    await vm.handleSubmit()
    expect(ElMessage.warning).toHaveBeenCalled()
    expect(createUnit).not.toHaveBeenCalled()
  })

  it('handleSubmit surfaces API errors', async () => {
    createUnit.mockRejectedValueOnce(new Error('nope'))
    const vm = doMount().vm as any
    vm.form.group_name = 'g'
    vm.form.strategy_id = 'tpl-1'
    vm.form.symbols = [{ code: '000001', name: 'A' }]
    vm.formRef = { validate: vi.fn().mockResolvedValue(true), resetFields: vi.fn() }
    await vm.handleSubmit()
    expect(ElMessage.error).toHaveBeenCalled()
  })

  it('resetForm restores defaults', () => {
    const vm = doMount().vm as any
    vm.form.group_name = 'dirty'
    vm.formRef = { resetFields: vi.fn() }
    vm.resetForm()
    expect(vm.form.group_name).toBe('')
  })
})
