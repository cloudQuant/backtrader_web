import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    getTradingAutoConfig: vi.fn().mockResolvedValue({
      enabled: true,
      buffer_minutes: 10,
      scope: 'live',
      sessions: [{ name: 'day', open: '09:00', close: '15:00' }],
    }),
    getTradingAutoSchedule: vi.fn().mockResolvedValue([]),
    updateTradingAutoConfig: vi.fn().mockResolvedValue({ enabled: true }),
    updateTradingAutoSchedule: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import AutoTradingConfigDialog from '@/components/workspace/AutoTradingConfigDialog.vue'
import { elStubs } from '@/test/stubs'

function doMount(props: Record<string, unknown> = {}) {
  return mount(AutoTradingConfigDialog, {
    props: { modelValue: false, workspaceId: 'ws-1', ...props },
    global: { stubs: elStubs },
  })
}

describe('AutoTradingConfigDialog', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('mounts with a default config', () => {
    const vm = doMount().vm as any
    expect(vm.form.enabled).toBe(false)
    expect(vm.form.sessions.length).toBeGreaterThanOrEqual(1)
  })

  it('scopeLabel maps the scope to a label', () => {
    const vm = doMount().vm as any
    vm.form.scope = 'all'
    expect(vm.scopeLabel).toBe('workspaceDialogs.sessionScopeAll')
    vm.form.scope = 'live'
    expect(vm.scopeLabel).toBe('workspaceDialogs.sessionScopeLive')
  })

  it('addSession appends and removeSession keeps at least one', () => {
    const vm = doMount().vm as any
    const before = vm.form.sessions.length
    vm.addSession()
    expect(vm.form.sessions.length).toBe(before + 1)
    // remove down to one
    while (vm.form.sessions.length > 1) {
      vm.removeSession(vm.form.sessions.length - 1)
    }
    expect(vm.form.sessions.length).toBe(1)
    vm.removeSession(0) // should be a no-op at length 1
    expect(vm.form.sessions.length).toBe(1)
  })

  it('normalizeSessions fills blank names with an indexed default', () => {
    const vm = doMount().vm as any
    vm.form.sessions = [{ name: '', open: '09:00', close: '15:00' }]
    const normalized = vm.normalizeSessions()
    expect(normalized[0].name).toContain('workspaceDialogs.sessionTime')
  })

  it('assignForm copies a config into the reactive form', () => {
    const vm = doMount().vm as any
    vm.assignForm({
      enabled: true,
      buffer_minutes: 30,
      scope: 'simulation',
      sessions: [{ name: 'n', open: '10:00', close: '11:00' }],
    })
    expect(vm.form.enabled).toBe(true)
    expect(vm.form.buffer_minutes).toBe(30)
    expect(vm.form.scope).toBe('simulation')
  })

  it('loads config when the dialog opens', async () => {
    const wrapper = doMount({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await new Promise(r => setTimeout(r, 0))
    const vm = wrapper.vm as any
    expect(vm.form.enabled).toBe(true)
    expect(vm.form.scope).toBe('live')
  })
})
