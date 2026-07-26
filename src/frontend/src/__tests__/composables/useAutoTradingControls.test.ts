import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    getTradingAutoConfig: vi.fn(),
    updateTradingAutoConfig: vi.fn(),
    getTradingAutoSchedule: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import { ElMessage } from 'element-plus'

import { useAutoTradingControls } from '@/composables/useAutoTradingControls'
import { workspaceApi } from '@/api/workspace'

const api = workspaceApi as unknown as {
  getTradingAutoConfig: ReturnType<typeof vi.fn>
  updateTradingAutoConfig: ReturnType<typeof vi.fn>
  getTradingAutoSchedule: ReturnType<typeof vi.fn>
}

const WS = 'ws-1'

describe('useAutoTradingControls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('initialises with disabled state and empty schedule', () => {
    const c = useAutoTradingControls(() => WS)
    expect(c.autoTradingEnabled.value).toBe(false)
    expect(c.autoTradingLoading.value).toBe(false)
    expect(c.autoTradingSchedule.value).toEqual([])
    expect(c.autoTradingScheduleSummary.value).toBe('')
  })

  it('loadAutoTradingState populates enabled + schedule from API', async () => {
    api.getTradingAutoConfig.mockResolvedValue({ enabled: true })
    api.getTradingAutoSchedule.mockResolvedValue([
      { session: 'day', start: '09:00', stop: '15:00' },
    ])
    const c = useAutoTradingControls(() => WS)
    await c.loadAutoTradingState()
    expect(c.autoTradingEnabled.value).toBe(true)
    expect(c.autoTradingSchedule.value).toHaveLength(1)
    expect(c.autoTradingScheduleSummary.value).toBe('day 09:00-15:00')
    expect(api.getTradingAutoConfig).toHaveBeenCalledWith(WS)
  })

  it('loadAutoTradingState falls back to disabled/empty on API error', async () => {
    api.getTradingAutoConfig.mockRejectedValue(new Error('boom'))
    api.getTradingAutoSchedule.mockRejectedValue(new Error('boom'))
    const c = useAutoTradingControls(() => WS)
    await c.loadAutoTradingState()
    expect(c.autoTradingEnabled.value).toBe(false)
    expect(c.autoTradingSchedule.value).toEqual([])
  })

  it('handleEnableAutoTrading enables and shows success', async () => {
    api.updateTradingAutoConfig.mockResolvedValue({ enabled: true })
    api.getTradingAutoSchedule.mockResolvedValue([])
    const c = useAutoTradingControls(() => WS)
    c.handleEnableAutoTrading()
    await vi.waitFor(() => expect(c.autoTradingEnabled.value).toBe(true))
    expect(api.updateTradingAutoConfig).toHaveBeenCalledWith(WS, { enabled: true })
    expect(ElMessage.success).toHaveBeenCalled()
    expect(c.autoTradingLoading.value).toBe(false)
  })

  it('handleDisableAutoTrading disables', async () => {
    api.updateTradingAutoConfig.mockResolvedValue({ enabled: false })
    api.getTradingAutoSchedule.mockResolvedValue([])
    const c = useAutoTradingControls(() => WS)
    c.handleDisableAutoTrading()
    await vi.waitFor(() => expect(api.updateTradingAutoConfig).toHaveBeenCalledWith(WS, { enabled: false }))
    expect(c.autoTradingEnabled.value).toBe(false)
  })

  it('updateAutoTradingEnabled surfaces errors via ElMessage', async () => {
    api.updateTradingAutoConfig.mockRejectedValue(new Error('nope'))
    const c = useAutoTradingControls(() => WS)
    await c.updateAutoTradingEnabled(true)
    expect(ElMessage.error).toHaveBeenCalled()
    expect(c.autoTradingLoading.value).toBe(false)
  })

  it('handleAutoTradingSaved syncs from a saved payload', () => {
    const c = useAutoTradingControls(() => WS)
    c.handleAutoTradingSaved({
      config: { enabled: true } as never,
      schedule: [{ session: 'night', start: '21:00', stop: '23:00' }] as never,
    })
    expect(c.autoTradingEnabled.value).toBe(true)
    expect(c.autoTradingScheduleSummary.value).toBe('night 21:00-23:00')
  })
})
