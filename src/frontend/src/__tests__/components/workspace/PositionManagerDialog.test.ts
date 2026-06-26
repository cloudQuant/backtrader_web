import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import PositionManagerDialog from '@/components/workspace/PositionManagerDialog.vue'
import { elStubs } from '@/test/stubs'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn() },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: ref('zh-CN') }),
}))

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    getTradingPositions: vi.fn().mockResolvedValue({
      positions: [],
      total_long_value: 0,
      total_short_value: 0,
      total_pnl: 0,
    }),
  },
}))

describe('PositionManagerDialog', () => {
  const mountDialog = () => mount(PositionManagerDialog, {
    props: {
      modelValue: false,
      workspaceId: 'workspace-1',
    },
    global: { stubs: elStubs },
  })

  it('preserves micro nonzero position quantities when formatting', () => {
    const vm = mountDialog().vm as any

    expect(vm.formatQuantity(0.00004)).toBe('0.00004')
    expect(vm.formatQuantity(-0.00004)).toBe('-0.00004')
    expect(vm.formatQuantity(1.23456)).toBe('1.2346')
    expect(vm.formatQuantity(0)).toBe('-')
  })
})
