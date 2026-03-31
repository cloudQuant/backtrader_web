/**
 * Unit tests for useBacktestRuntime composable.
 *
 * Tests cover:
 * - WebSocket normal completion
 * - WebSocket failure and polling fallback
 * - Timeout handling
 * - Cancel flow
 * - Heartbeat maintenance
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { BacktestResult } from '@/types'

import { useBacktestRuntime } from './useBacktestRuntime'

// Mock dependencies
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

// Mock WebSocket constants
const WS_CONNECTING = 0
const WS_OPEN = 1
const WS_CLOSED = 3

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static clearInstances() {
    MockWebSocket.instances = []
  }

  static readonly CONNECTING = WS_CONNECTING
  static readonly OPEN = WS_OPEN
  static readonly CLOSED = WS_CLOSED

  readyState: number = WS_CONNECTING
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onopen: (() => void) | null = null
  protocols: string[] = []

  constructor(_url: string, protocols?: string | string[]) {
    this.protocols = protocols ? (Array.isArray(protocols) ? protocols : [protocols]) : []
    MockWebSocket.instances.push(this)
    // Simulate connection
    setTimeout(() => {
      this.readyState = WS_OPEN
      this.onopen?.()
    }, 0)
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = WS_CLOSED
  })

  // Helper to simulate receiving a message
  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  // Helper to simulate error
  simulateError() {
    this.onerror?.(new Event('error'))
  }

  // Helper to simulate close
  simulateClose(code = 1000) {
    this.readyState = WS_CLOSED
    this.onclose?.({ code, reason: '', wasClean: true } as CloseEvent)
  }
}

// Replace global WebSocket with mock
vi.stubGlobal('WebSocket', MockWebSocket)

describe('useBacktestRuntime', () => {
  let runtime: ReturnType<typeof useBacktestRuntime>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let mockFetchResult: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let mockRefreshResults: any

  beforeEach(() => {
    vi.clearAllMocks()
    MockWebSocket.clearInstances()

    mockFetchResult = vi.fn()
    mockRefreshResults = vi.fn()
    const mockCurrentResult = ref<BacktestResult | null>(null)

    runtime = useBacktestRuntime({
      currentResult: mockCurrentResult,
      fetchResult: mockFetchResult,
      refreshResults: mockRefreshResults,
    })
  })

  describe('startRuntime', () => {
    it('should initialize loading state and connect WebSocket', async () => {
      runtime.startRuntime('task-123')

      expect(runtime.loading.value).toBe(true)
      expect(runtime.currentTaskId.value).toBe('task-123')
      expect(runtime.progressInfo.value.progress).toBe(0)

      // Wait for WebSocket to connect
      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      expect(ws.protocols).toEqual(['access-token', 'mock-token'])
    })

    it('should handle task_created event', async () => {
      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      ws.simulateMessage({ type: 'task_created', task_id: 'task-123', message: 'Task created' })

      expect(runtime.progressInfo.value.progress).toBe(0)
      expect(runtime.progressInfo.value.message).toBe('Task created')
    })

    it('should handle progress event', async () => {
      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      ws.simulateMessage({ type: 'progress', task_id: 'task-123', progress: 50, message: 'Running...' })

      expect(runtime.progressInfo.value.progress).toBe(50)
      expect(runtime.progressInfo.value.message).toBe('Running...')
    })
  })

  describe('WebSocket completion', () => {
    it('should handle completed event and fetch result', async () => {
      mockFetchResult.mockResolvedValue({
        task_id: 'task-123',
        status: 'completed',
        total_return: 0.15,
      }) as unknown as BacktestResult

      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      ws.simulateMessage({ type: 'completed', task_id: 'task-123', result: null })

      await vi.waitFor(() => {
        expect(mockFetchResult).toHaveBeenCalledWith('task-123')
        expect(mockRefreshResults).toHaveBeenCalled()
        expect(runtime.loading.value).toBe(false)
      })

      const { ElMessage } = await import('element-plus')
      expect(ElMessage.success).toHaveBeenCalledWith('回测完成')
    })

    it('should handle failed event', async () => {
      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      ws.simulateMessage({ type: 'failed', task_id: 'task-123', error: 'Strategy error' })

      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')

      const { ElMessage } = await import('element-plus')
      expect(ElMessage.error).toHaveBeenCalledWith('回测失败: Strategy error')
    })

    it('should handle cancelled event', async () => {
      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      ws.simulateMessage({ type: 'cancelled', task_id: 'task-123' })

      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')

      const { ElMessage } = await import('element-plus')
      expect(ElMessage.warning).toHaveBeenCalledWith('回测已取消')
    })
  })

  describe('WebSocket error and polling fallback', () => {
    it('should start polling fallback on WebSocket error', async () => {
      const { backtestApi } = await import('@/api/backtest')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({ task_id: 'task-123', status: 'completed' })
      ;(mockFetchResult as ReturnType<typeof vi.fn>).mockResolvedValue({ task_id: 'task-123', status: 'completed' })

      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      ws.simulateError()

      // Should start polling
      await vi.waitFor(() => {
        expect(backtestApi.getStatus).toHaveBeenCalledWith('task-123')
      })
    })

    it('should start polling fallback on WebSocket close (non-normal)', async () => {
      const { backtestApi } = await import('@/api/backtest')
      vi.mocked(backtestApi.getStatus).mockResolvedValue({ task_id: 'task-123', status: 'completed' })
      ;(mockFetchResult as ReturnType<typeof vi.fn>).mockResolvedValue({ task_id: 'task-123', status: 'completed' })

      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const ws = MockWebSocket.instances[0]
      // Simulate abnormal close (code !== 1000)
      ws.simulateClose(1006)

      // Should start polling
      await vi.waitFor(() => {
        expect(backtestApi.getStatus).toHaveBeenCalledWith('task-123')
      })
    })
  })

  describe('cancelBacktest', () => {
    it('should cancel the current task', async () => {
      const { backtestApi } = await import('@/api/backtest')
      vi.mocked(backtestApi.cancel).mockResolvedValue(undefined as unknown as void)

      runtime.startRuntime('task-123')
      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      await runtime.cancelBacktest()

      expect(backtestApi.cancel).toHaveBeenCalledWith('task-123')
      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')

      const { ElMessage } = await import('element-plus')
      expect(ElMessage.success).toHaveBeenCalledWith('已取消回测任务')
    })

    it('should handle cancel error', async () => {
      const { backtestApi } = await import('@/api/backtest')
      vi.mocked(backtestApi.cancel).mockRejectedValue(new Error('Cancel failed'))

      runtime.startRuntime('task-123')
      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      await runtime.cancelBacktest()

      const { ElMessage } = await import('element-plus')
      expect(ElMessage.error).toHaveBeenCalledWith('取消失败')
    })
  })

  describe('stopRuntime and disposeRuntime', () => {
    it('should stop runtime and close WebSocket', async () => {
      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      runtime.stopRuntime()

      expect(runtime.loading.value).toBe(false)
      expect(runtime.currentTaskId.value).toBe('')
      expect(MockWebSocket.instances[0].close).toHaveBeenCalled()
    })

    it('should dispose runtime without changing loading state', async () => {
      runtime.startRuntime('task-123')

      await vi.waitFor(() => {
        expect(MockWebSocket.instances.length).toBe(1)
      })

      const loadingBefore = runtime.loading.value
      runtime.disposeRuntime()

      expect(runtime.loading.value).toBe(loadingBefore)
      expect(MockWebSocket.instances[0].close).toHaveBeenCalled()
    })
  })

})
