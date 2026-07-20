import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RiskControlPage from '@/views/RiskControlPage.vue'
import { elStubs } from '@/test/stubs'

const apiMocks = vi.hoisted(() => ({
  listRules: vi.fn(),
  createRule: vi.fn(),
  updateRule: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api', () => ({
  getErrorMessage: (_reason: unknown, fallback: string) => fallback,
}))

vi.mock('@/api/paperRuntime', () => ({
  paperRuntimeApi: apiMocks,
}))

describe('RiskControlPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listRules.mockResolvedValue([
      {
        id: 'rule-1',
        user_id: 'user-1',
        name: 'Drawdown cap',
        rule_type: 'max_drawdown',
        config: { max_pct: 10 },
        severity: 'critical',
        is_active: true,
        version: 1,
        created_at: '2026-07-18T00:00:00Z',
        updated_at: '2026-07-18T00:00:00Z',
      },
    ])
    apiMocks.createRule.mockResolvedValue({
      id: 'rule-2',
      user_id: 'user-1',
      name: 'Order cap',
      rule_type: 'max_order_size',
      config: {},
      severity: 'warning',
      is_active: true,
      version: 1,
      created_at: '2026-07-18T00:00:00Z',
      updated_at: '2026-07-18T00:00:00Z',
    })
    apiMocks.updateRule.mockResolvedValue({})
  })

  it('loads rules, creates a scoped rule, and persists active-state changes', async () => {
    const wrapper = mount(RiskControlPage, { global: { stubs: elStubs } })
    await flushPromises()

    expect(wrapper.text()).toContain('规则列表')
    expect(apiMocks.listRules).toHaveBeenCalledWith()

    const vm = wrapper.vm as any
    vm.form.name = 'Order cap'
    vm.form.ruleType = 'max_order_size'
    vm.form.instanceId = 'paper-1'
    await vm.createRule()
    await vm.toggleRule({ id: 'rule-1', is_active: false })

    expect(apiMocks.createRule).toHaveBeenCalledWith({
      name: 'Order cap',
      rule_type: 'max_order_size',
      instance_id: 'paper-1',
    })
    expect(apiMocks.updateRule).toHaveBeenCalledWith('rule-1', { is_active: false })
  })
})
