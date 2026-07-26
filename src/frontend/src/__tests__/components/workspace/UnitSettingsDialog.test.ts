import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const updateUnit = vi.fn().mockResolvedValue(undefined)
vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({ updateUnit }),
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import UnitSettingsDialog from '@/components/workspace/UnitSettingsDialog.vue'
import { ElMessage } from 'element-plus'
import { elStubs } from '@/test/stubs'

const unit = {
  id: 'u-1',
  unit_settings: { initial_cash: 500000, long_margin_rate: 10, slippage_unit: 'price' },
} as never

function doMount(props: Record<string, unknown> = {}) {
  return mount(UnitSettingsDialog, {
    props: { modelValue: true, workspaceId: 'ws-1', unit, ...props },
    global: { stubs: elStubs },
  })
}

describe('UnitSettingsDialog', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('mounts cleanly', () => {
    expect(doMount().exists()).toBe(true)
  })

  it('dialogTitle differs for research vs trading', () => {
    expect((doMount({ workspaceType: 'trading' }).vm as any).dialogTitle).toContain(
      'workspaceDialogs.strategyTrading',
    )
  })

  it('initForm hydrates from unit_settings with fallbacks', () => {
    const vm = doMount().vm as any
    vm.initForm()
    expect(vm.form.initial_cash).toBe(500000)
    expect(vm.form.long_margin_rate).toBe(10)
    expect(vm.form.slippage_unit).toBe('price')
    expect(vm.form.short_margin_rate).toBe(8) // default fallback
  })

  it('initForm uses defaults when no unit_settings', () => {
    const vm = doMount({ unit: { id: 'u-2', unit_settings: {} } }).vm as any
    vm.initForm()
    expect(vm.form.initial_cash).toBe(1000000)
    expect(vm.form.margin_rate_method).toBe('percent')
  })

  it('handleSave persists settings and emits', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await vm.handleSave()
    expect(updateUnit).toHaveBeenCalledWith('ws-1', 'u-1', expect.objectContaining({
      unit_settings: expect.any(Object),
    }))
    expect(ElMessage.success).toHaveBeenCalled()
    expect(wrapper.emitted('saved')).toBeTruthy()
  })
})
