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

  it('hides flat positions returned by the API', async () => {
    const { workspaceApi } = await import('@/api/workspace')
    vi.mocked(workspaceApi.getTradingPositions).mockResolvedValueOnce({
      positions: [
        {
          unit_id: 'unit-flat',
          unit_name: 'Flat Unit',
          symbol: 'rb2601',
          symbol_name: '螺纹钢',
          trading_mode: 'paper',
          long_position: 0,
          short_position: 0,
          avg_price: 0,
          latest_price: 0,
          position_pnl: 0,
          market_value: 0,
        },
        {
          unit_id: 'unit-active',
          unit_name: 'Active Unit',
          symbol: 'IF2609',
          symbol_name: '沪深300',
          trading_mode: 'live',
          long_position: 1,
          short_position: 0,
          avg_price: 5000,
          latest_price: 5001,
          position_pnl: 265.5,
          market_value: 1500300,
          long_market_value: 1500400,
          short_market_value: 0,
          margin_value: 150030,
          multiplier: 300,
          margin_rate: 0.1,
          leverage: 10,
          commission: 34.5,
          gross_pnl: 300,
          position_source: 'gateway',
          asset_spec_source: 'ctp_gateway',
          valuation_status: 'confirmed',
          valuation_warnings: [],
        },
      ],
      total_long_value: 999999,
      total_short_value: 888888,
      total_pnl: 777,
    })
    const vm = mountDialog().vm as any

    await vm.loadPositions()

    expect(vm.positions).toHaveLength(1)
    expect(vm.positions[0].unit_id).toBe('unit-active')
    expect(vm.summary.total_long_value).toBe(1500400)
    expect(vm.summary.total_short_value).toBe(0)
    expect(vm.summary.total_pnl).toBe(265.5)
  })
})
