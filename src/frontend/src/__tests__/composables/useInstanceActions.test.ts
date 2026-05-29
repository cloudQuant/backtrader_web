/**
 * Unit tests for useInstanceActions (src/composables/useInstanceActions.ts).
 *
 * Covers status label resolution, strategy ID formatting, and the 5 action
 * handlers (start, stop, remove, startAll, stopAll) including their success
 * + error paths.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  formatStrategyId,
  statusLabel,
  useInstanceActions,
  type InstanceActionsApi,
  type InstanceInfo,
} from '@/composables/useInstanceActions'

vi.mock('@/api', () => ({
  getErrorMessage: vi.fn((_e: unknown, fallback: string) => fallback),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

interface TestInstance extends InstanceInfo {
  status: string
}

function buildInstance(overrides: Partial<TestInstance> = {}): TestInstance {
  return {
    id: 'inst-1',
    strategy_id: 'org/sample',
    strategy_name: 'Sample',
    status: 'running',
    ...overrides,
  }
}

function buildApi(): InstanceActionsApi<TestInstance> {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    remove: vi.fn(),
    startAll: vi.fn(),
    stopAll: vi.fn(),
    loadData: vi.fn().mockResolvedValue(undefined),
  }
}

describe('useInstanceActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('statusLabel', () => {
    it('returns localized label for known statuses', () => {
      // setup.ts uses the actual zh-CN locale via passthrough mock
      expect(statusLabel('running')).toBe('运行中')
      expect(statusLabel('stopped')).toBe('已停止')
      expect(statusLabel('error')).toBe('异常')
    })

    it('returns the raw status string for unknown values', () => {
      expect(statusLabel('starting')).toBe('starting')
      expect(statusLabel('')).toBe('')
    })
  })

  describe('formatStrategyId', () => {
    it('returns the suffix after the slash', () => {
      expect(formatStrategyId('org/strategy_name')).toBe('strategy_name')
    })

    it('returns the full id when no slash is present', () => {
      expect(formatStrategyId('plain_id')).toBe('plain_id')
    })

    it('returns empty string for undefined input', () => {
      expect(formatStrategyId(undefined)).toBe('')
    })

    it('returns empty string for empty input', () => {
      expect(formatStrategyId('')).toBe('')
    })
  })

  describe('handleStart', () => {
    it('calls api.start with the instance id and merges the updated payload', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      const inst = buildInstance({ status: 'stopped' })
      vi.mocked(api.start).mockResolvedValue({ ...inst, status: 'running' })

      const { actionLoading, handleStart } = useInstanceActions(api)
      await handleStart(inst)

      expect(api.start).toHaveBeenCalledWith('inst-1')
      expect(inst.status).toBe('running')
      expect(actionLoading.value['inst-1']).toBeUndefined()
      expect(ElMessage.success).toHaveBeenCalled()
    })

    it('reports start error via ElMessage.error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.start).mockRejectedValue(new Error('boom'))

      const { handleStart, actionLoading } = useInstanceActions(api)
      await handleStart(buildInstance())

      expect(ElMessage.error).toHaveBeenCalled()
      expect(actionLoading.value['inst-1']).toBeUndefined()
    })

    it('marks actionLoading during the in-flight start call', async () => {
      const api = buildApi()
      let resolveStart!: (v: TestInstance) => void
      vi.mocked(api.start).mockImplementation(
        () => new Promise<TestInstance>((resolve) => { resolveStart = resolve }),
      )

      const { handleStart, actionLoading } = useInstanceActions(api)
      const p = handleStart(buildInstance())

      expect(actionLoading.value['inst-1']).toBe('start')
      resolveStart(buildInstance({ status: 'running' }))
      await p
      expect(actionLoading.value['inst-1']).toBeUndefined()
    })
  })

  describe('handleStop', () => {
    it('calls api.stop and reports success', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      const inst = buildInstance()
      vi.mocked(api.stop).mockResolvedValue({ ...inst, status: 'stopped' })

      const { handleStop } = useInstanceActions(api)
      await handleStop(inst)

      expect(api.stop).toHaveBeenCalledWith('inst-1')
      expect(inst.status).toBe('stopped')
      expect(ElMessage.success).toHaveBeenCalled()
    })

    it('reports stop error via ElMessage.error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.stop).mockRejectedValue(new Error('cant stop'))

      const { handleStop } = useInstanceActions(api)
      await handleStop(buildInstance())

      expect(ElMessage.error).toHaveBeenCalled()
    })
  })

  describe('handleRemove', () => {
    it('calls api.remove + loadData and reports success', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.remove).mockResolvedValue({})

      const { handleRemove } = useInstanceActions(api)
      await handleRemove(buildInstance())

      expect(api.remove).toHaveBeenCalledWith('inst-1')
      expect(api.loadData).toHaveBeenCalled()
      expect(ElMessage.success).toHaveBeenCalled()
    })

    it('reports remove error via ElMessage.error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.remove).mockRejectedValue(new Error('nope'))

      const { handleRemove } = useInstanceActions(api)
      await handleRemove(buildInstance())

      expect(ElMessage.error).toHaveBeenCalled()
      expect(api.loadData).not.toHaveBeenCalled()
    })
  })

  describe('handleStartAll / handleStopAll', () => {
    it('handleStartAll invokes startAll and refreshes', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.startAll).mockResolvedValue({ success: 3, failed: 1 })

      const { handleStartAll, batchLoading } = useInstanceActions(api)
      const p = handleStartAll()
      expect(batchLoading.value).toBe(true)
      await p
      expect(batchLoading.value).toBe(false)
      expect(api.loadData).toHaveBeenCalled()
      expect(ElMessage.success).toHaveBeenCalled()
    })

    it('handleStartAll reports error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.startAll).mockRejectedValue(new Error('boom'))

      const { handleStartAll } = useInstanceActions(api)
      await handleStartAll()
      expect(ElMessage.error).toHaveBeenCalled()
    })

    it('handleStopAll invokes stopAll and refreshes', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.stopAll).mockResolvedValue({ success: 5, failed: 0 })

      const { handleStopAll } = useInstanceActions(api)
      await handleStopAll()
      expect(api.loadData).toHaveBeenCalled()
      expect(ElMessage.success).toHaveBeenCalled()
    })

    it('handleStopAll reports error', async () => {
      const { ElMessage } = await import('element-plus')
      const api = buildApi()
      vi.mocked(api.stopAll).mockRejectedValue(new Error('boom'))

      const { handleStopAll } = useInstanceActions(api)
      await handleStopAll()
      expect(ElMessage.error).toHaveBeenCalled()
    })
  })
})
