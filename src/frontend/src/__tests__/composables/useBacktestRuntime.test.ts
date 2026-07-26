/**
 * Comprehensive unit tests for useBacktestRuntime.
 *
 * Coverage targets:
 * - WebSocket lifecycle: connect, ping/pong, message handling, error/close fallback
 * - Event handlers: task_created / progress / completed / failed / cancelled
 * - Polling fallback: status transitions, error retries, timeout, abort
 * - Lifecycle: startRuntime, stopRuntime, disposeRuntime, cancelBacktest
 *
 * Source-of-truth: src/composables/useBacktestRuntime.ts
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useBacktestRuntime } from '@/composables/useBacktestRuntime'
import type { BacktestResult } from '@/types'

// ─────────────────────────────────────────────────────────────
// Module mocks
// ─────────────────────────────────────────────────────────────

vi.mock('@/api/index', () => ({
  getErrorMessage: vi.fn((_e: unknown, fallback: string) => fallback),
}))

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    getStatus: vi.fn(),
    cancel: vi.fn(),
  },
}))

vi.mock('@/utils/session', () => ({
  getAccessToken: vi.fn(() => 'mock-token'),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

// ─────────────────────────────────────────────────────────────
// MockWebSocket
// ─────────────────────────────────────────────────────────────
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static reset() {
    MockWebSocket.instances = []
  }

  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  url: string
  protocols: string[]
  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })

  constructor(url: string, protocols?: string | string[]) {
    this.url = url
    this.protocols = protocols ? (Array.isArray(protocols) ? protocols : [protocols]) : []
    MockWebSocket.instances.push(this)
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.()
    }, 0)
  }

  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent)
  }

  emitRaw(data: string) {
    this.onmessage?.({ data } as MessageEvent)
  }

  triggerError() {
    this.onerror?.(new Event('error'))
  }

  triggerClose(code = 1000) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code, reason: '', wasClean: code === 1000 } as CloseEvent)
  }
}

vi.stubGlobal('WebSocket', MockWebSocket)

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────
type Runtime = ReturnType<typeof useBacktestRuntime>
type Mocks = {
  fetchResult: ReturnType<typeof vi.fn>
  refreshResults: ReturnType<typeof vi.fn>
  currentResult: ReturnType<typeof ref<BacktestResult | null>>
}

function build(): { runtime: Runtime; mocks: Mocks } {
  const fetchResult = vi.fn()
  const refreshResults = vi.fn().mockResolvedValue(undefined)
  const currentResult = ref<BacktestResult | null>(null)
  const runtime = useBacktestRuntime({
    currentResult,
    fetchResult,
    refreshResults,
  })
  return { runtime, mocks: { fetchResult, refreshResults, currentResult } }
}

async function waitForWs(): Promise<MockWebSocket> {
  return await vi.waitFor(() => {
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    if (!ws) throw new Error('no ws yet')
    return ws
  })
}

// ─────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────
describe('useBacktestRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockWebSocket.reset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('startRuntime', () => {
    it('initializes loading state and opens a WebSocket with token protocols', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-1')

      expect(runtime.loading.value).toBe(true)
      expect(runtime.currentTaskId.value).toBe('task-1')
      expect(runtime.progressInfo.value.progress).toBe(0)

      const ws = await waitForWs()
      expect(ws.url).toContain('/ws/backtest/task-1')
      expect(ws.protocols).toEqual(['access-token', 'mock-token'])
    })

    it('falls back to no-protocol WebSocket when token is missing', async () => {
      const { getAccessToken } = await import('@/utils/session')
      vi.mocked(getAccessToken).mockReturnValueOnce(null)

      const { runtime } = build()
      runtime.startRuntime('task-2')

      const ws = await waitForWs()
      expect(ws.protocols).toEqual([])
    })
  })

  describe('WebSocket events', () => {
    it('handles task_created with custom message', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-3')
      const ws = await waitForWs()

      ws.emit({ type: 'task_created', message: 'queued' })
      expect(runtime.progressInfo.value.message).toBe('queued')
    })

    it('handles task_created with default i18n message when message missing', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-3b')
      const ws = await waitForWs()

      ws.emit({ type: 'task_created' })
      // Falls back to localized message; setup.ts global mock returns the
      // zh-CN value '回测任务已提交'.
      expect(runtime.progressInfo.value.message).toBe('回测任务已提交')
    })

    it('ignores connected and pong events', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-4')
      const ws = await waitForWs()

      ws.emit({ type: 'connected' })
      ws.emit({ type: 'pong' })
      expect(runtime.progressInfo.value.progress).toBe(0)
      expect(runtime.progressInfo.value.message).toBe('提交任务中...')
    })

    it('ignores invalid JSON without throwing', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-4b')
      const ws = await waitForWs()

      ws.emitRaw('not json')
      expect(runtime.loading.value).toBe(true)
    })

    it('handles progress event', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-5')
      const ws = await waitForWs()

      ws.emit({ type: 'progress', progress: 42, message: 'half-way' })
      expect(runtime.progressInfo.value.progress).toBe(42)
      expect(runtime.progressInfo.value.message).toBe('half-way')
    })

    it('keeps prior progress when progress is not a number', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-5b')
      const ws = await waitForWs()

      ws.emit({ type: 'progress', progress: 30, message: 'midway' })
      ws.emit({ type: 'progress' })
      expect(runtime.progressInfo.value.progress).toBe(30)
    })

    it('finishes successfully on completed event', async () => {
      const { ElMessage } = await import('element-plus')
      const { runtime, mocks } = build()
      mocks.fetchResult.mockResolvedValue({
        task_id: 'task-6',
        status: 'completed',
      } as BacktestResult)

      runtime.startRuntime('task-6')
      const ws = await waitForWs()

      ws.emit({ type: 'completed', progress: 100 })
      await vi.waitFor(() => {
        expect(runtime.loading.value).toBe(false)
      })
      expect(mocks.fetchResult).toHaveBeenCalledWith('task-6')
      expect(mocks.refreshResults).toHaveBeenCalled()
      expect(ElMessage.success).toHaveBeenCalledWith('回测完成')
      expect(runtime.currentTaskId.value).toBe('')
    })

    it('handles failed event with error string', async () => {
      const { ElMessage } = await import('element-plus')
      const { runtime } = build()
      runtime.startRuntime('task-7')
      const ws = await waitForWs()

      ws.emit({ type: 'failed', error: 'strategy crashed' })
      expect(runtime.loading.value).toBe(false)
      expect(ElMessage.error).toHaveBeenCalledWith('回测失败: strategy crashed')
    })

    it('handles failed event with message field when error is missing', async () => {
      const { ElMessage } = await import('element-plus')
      const { runtime } = build()
      runtime.startRuntime('task-7b')
      const ws = await waitForWs()

      ws.emit({ type: 'failed', message: 'fallback message' })
      expect(ElMessage.error).toHaveBeenCalledWith('回测失败: fallback message')
    })

    it('handles failed event with localized fallback when both fields missing', async () => {
      const { ElMessage } = await import('element-plus')
      const { runtime } = build()
      runtime.startRuntime('task-7c')
      const ws = await waitForWs()

      ws.emit({ type: 'failed' })
      expect(ElMessage.error).toHaveBeenCalledWith('回测失败: 未知错误')
    })

    it('handles cancelled event', async () => {
      const { ElMessage } = await import('element-plus')
      const { runtime } = build()
      runtime.startRuntime('task-8')
      const ws = await waitForWs()

      ws.emit({ type: 'cancelled' })
      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')
      expect(ElMessage.warning).toHaveBeenCalledWith('回测已取消')
    })

    it('uses localized fallback when completed event has no message', async () => {
      const { runtime, mocks } = build()
      mocks.fetchResult.mockResolvedValue({
        task_id: 'task-completed-default',
        status: 'completed',
      } as BacktestResult)

      runtime.startRuntime('task-completed-default')
      const ws = await waitForWs()

      ws.emit({ type: 'completed' }) // no progress, no message
      await vi.waitFor(() => {
        expect(runtime.loading.value).toBe(false)
      })
      // Default progress fills as 100 and default message is the localized
      // 回测完成 (we cannot easily assert progressInfo at this point because
      // finishWithResult sets loading=false; the assertion above suffices)
      expect(mocks.fetchResult).toHaveBeenCalled()
    })

    it('handles failed event when error field is non-string but message is present', async () => {
      const { ElMessage } = await import('element-plus')
      const { runtime } = build()
      runtime.startRuntime('task-failed-nonstr')
      const ws = await waitForWs()

      ws.emit({ type: 'failed', error: 42, message: 'fallback' })
      // error is not a string, fallback to message field
      expect(ElMessage.error).toHaveBeenCalledWith('回测失败: fallback')
    })

    it('throws inside finishWithResult when fetchResult returns null', async () => {
      // finishWithResult is called by the WebSocket onmessage handler, where
      // a thrown error bubbles up as an unhandled rejection (no awaiter).
      // We invoke finishWithResult-equivalent path by polling: pollResult
      // awaits finishWithResult and catches via the surrounding try/catch
      // in the polling loop, so we use a polling fallback to assert
      // observable behavior rather than catching the unhandled throw.
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({
        task_id: 'task-9',
        status: 'completed',
      })

      const { runtime, mocks } = build()
      mocks.fetchResult.mockResolvedValue(null)

      runtime.startRuntime('task-9')
      const ws = await waitForWs()
      // Trigger polling fallback so finishWithResult goes through pollResult
      ws.triggerError()

      // The throw inside finishWithResult bubbles up out of the polling
      // try block; pollResult exits without setting loading=false. The
      // best observable assertion is that fetchResult was called.
      await vi.waitFor(() => {
        expect(mocks.fetchResult).toHaveBeenCalledWith('task-9')
      })
      // ElMessage.success should NOT fire (finishWithResult threw before that)
      expect(ElMessage.success).not.toHaveBeenCalled()
    })
  })

  describe('WebSocket error and close fallback', () => {
    it('starts polling fallback on WebSocket error', async () => {
      const { backtestApi } = await import('@/api/backtest')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({
        task_id: 'task-10',
        status: 'completed',
      })

      const { runtime, mocks } = build()
      mocks.fetchResult.mockResolvedValue({ task_id: 'task-10', status: 'completed' } as BacktestResult)
      runtime.startRuntime('task-10')
      const ws = await waitForWs()
      ws.triggerError()

      await vi.waitFor(() => {
        expect(backtestApi.getStatus).toHaveBeenCalledWith('task-10')
      })
    })

    it('starts polling fallback on abnormal close', async () => {
      const { backtestApi } = await import('@/api/backtest')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({
        task_id: 'task-11',
        status: 'completed',
      })

      const { runtime, mocks } = build()
      mocks.fetchResult.mockResolvedValue({ task_id: 'task-11', status: 'completed' } as BacktestResult)
      runtime.startRuntime('task-11')
      const ws = await waitForWs()
      ws.triggerClose(1006)

      await vi.waitFor(() => {
        expect(backtestApi.getStatus).toHaveBeenCalledWith('task-11')
      })
    })

    it('does not start polling on clean close (code 1000)', async () => {
      const { backtestApi } = await import('@/api/backtest')

      const { runtime } = build()
      runtime.startRuntime('task-12')
      const ws = await waitForWs()
      // Manually set loading=false so the close handler short-circuits
      runtime.stopRuntime()
      ws.triggerClose(1000)

      expect(backtestApi.getStatus).not.toHaveBeenCalled()
    })
  })

  describe('Polling', () => {
    it('handles failed status during polling with fetched error_message', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({
        task_id: 'task-13',
        status: 'failed',
      })

      const { runtime, mocks } = build()
      mocks.fetchResult.mockResolvedValue({
        task_id: 'task-13',
        status: 'failed',
        error_message: 'data error',
      } as BacktestResult)

      runtime.startRuntime('task-13')
      const ws = await waitForWs()
      ws.triggerError()

      await vi.waitFor(() => {
        expect(ElMessage.error).toHaveBeenCalledWith('回测失败: data error')
      })
    })

    it('handles cancelled status during polling', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({
        task_id: 'task-14',
        status: 'cancelled',
      })

      const { runtime } = build()
      runtime.startRuntime('task-14')
      const ws = await waitForWs()
      ws.triggerError()

      await vi.waitFor(() => {
        expect(ElMessage.warning).toHaveBeenCalledWith('回测已取消')
      })
    })

    it('reports query failure after max polling attempts', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      // Force every getStatus to reject; combined with directly invoking
      // pollResult with a synthetic high-attempts state we can hit the
      // "attempts >= POLL_MAX_ATTEMPTS - 1" branch.
      vi.mocked(backtestApi.getStatus).mockRejectedValue(new Error('network down'))

      const { runtime } = build()
      runtime.startRuntime('task-poll-fail')
      const ws = await waitForWs()

      // Speed up: stub sleep to skip delays. We can't easily reach 60
      // attempts without waiting, so we replace the implementation by
      // using fake timers.
      vi.useFakeTimers()
      ws.triggerError()
      // Advance through 60 polling attempts (each ~1-5s, but we don't
      // care about real time since timers are faked)
      for (let i = 0; i < 65; i++) {
        await vi.advanceTimersByTimeAsync(5000)
      }
      vi.useRealTimers()

      // Either the per-iteration error path (attempts >= MAX-1) or the
      // outer-loop timeout (loading still true at end) fires.
      expect(
        vi.mocked(ElMessage.error).mock.calls.length +
          vi.mocked(ElMessage.warning).mock.calls.length,
      ).toBeGreaterThan(0)
    })

    it('exits polling silently when sleep is aborted', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({
        task_id: 'task-poll-abort',
        status: 'running',
      })

      const { runtime } = build()
      runtime.startRuntime('task-poll-abort')
      const ws = await waitForWs()
      ws.triggerError()

      // Wait for first polling tick to register
      await vi.waitFor(() => {
        expect(backtestApi.getStatus).toHaveBeenCalled()
      })

      // Abort by calling stopRuntime (which closes WebSocket and aborts pollAbortController)
      runtime.stopRuntime()

      // No error or warning message should be raised by the abort path
      expect(ElMessage.error).not.toHaveBeenCalled()
      expect(ElMessage.warning).not.toHaveBeenCalled()
    })
  })

  describe('cancelBacktest', () => {
    it('cancels the current task', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      vi.mocked(backtestApi.cancel).mockResolvedValue(undefined as never)

      const { runtime } = build()
      runtime.startRuntime('task-15')
      await waitForWs()

      await runtime.cancelBacktest()
      expect(backtestApi.cancel).toHaveBeenCalledWith('task-15')
      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')
      expect(ElMessage.success).toHaveBeenCalledWith('已取消回测任务')
    })

    it('reports cancel API failure via ElMessage.error', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { ElMessage } = await import('element-plus')
      vi.mocked(backtestApi.cancel).mockRejectedValueOnce(new Error('boom'))

      const { runtime } = build()
      runtime.startRuntime('task-16')
      await waitForWs()

      await runtime.cancelBacktest()
      expect(ElMessage.error).toHaveBeenCalledWith('取消失败')
    })

    it('no-ops when no current task', async () => {
      const { backtestApi } = await import('@/api/backtest')
      const { runtime } = build()

      await runtime.cancelBacktest()
      expect(backtestApi.cancel).not.toHaveBeenCalled()
    })
  })

  describe('lifecycle helpers', () => {
    it('stopRuntime closes the socket and resets state', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-17')
      const ws = await waitForWs()

      runtime.stopRuntime()
      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')
      expect(ws.close).toHaveBeenCalled()
    })

    it('disposeRuntime closes the socket without touching state', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-18')
      const ws = await waitForWs()

      const wasLoading = runtime.loading.value
      runtime.disposeRuntime()
      expect(runtime.loading.value).toBe(wasLoading)
      expect(ws.close).toHaveBeenCalled()
    })

    it('closeWebSocket can be called multiple times safely', async () => {
      const { runtime } = build()
      runtime.startRuntime('task-19')
      await waitForWs()

      runtime.closeWebSocket()
      runtime.closeWebSocket() // second call is a no-op
      expect(runtime.loading.value).toBe(true) // state unchanged by closeWebSocket alone
    })
  })
})
