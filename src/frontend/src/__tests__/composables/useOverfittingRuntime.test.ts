import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { StrategyOverfittingTaskResult } from '@/api/strategy'
import { useOverfittingRuntime } from '@/composables/useOverfittingRuntime'

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getOverfittingTask: vi.fn(),
  },
}))

vi.mock('@/utils/session', () => ({
  getAccessToken: vi.fn(() => 'mock-token'),
}))

const WS_CONNECTING = 0
const WS_OPEN = 1
const WS_CLOSED = 3

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
  url: string

  constructor(url: string, protocols?: string | string[]) {
    this.url = url
    this.protocols = protocols ? (Array.isArray(protocols) ? protocols : [protocols]) : []
    MockWebSocket.instances.push(this)
    setTimeout(() => {
      this.readyState = WS_OPEN
      this.onopen?.()
    }, 0)
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = WS_CLOSED
  })

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  simulateError() {
    this.onerror?.(new Event('error'))
  }
}

vi.stubGlobal('WebSocket', MockWebSocket)

describe('useOverfittingRuntime', () => {
  let runtime: ReturnType<typeof useOverfittingRuntime>
  let currentResult = ref<StrategyOverfittingTaskResult | null>(null)

  beforeEach(() => {
    vi.clearAllMocks()
    MockWebSocket.clearInstances()
    currentResult = ref<StrategyOverfittingTaskResult | null>(null)
    runtime = useOverfittingRuntime({ currentResult })
  })

  it('connects websocket with auth token', async () => {
    runtime.startRuntime('ot-123')

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1)
    })

    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('/ws/overfitting/ot-123')
    expect(ws.protocols).toEqual(['access-token', 'mock-token'])
  })

  it('stores completed result from websocket event', async () => {
    runtime.startRuntime('ot-123')

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1)
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage({
      type: 'completed',
      task_id: 'ot-123',
      result: {
        task_id: 'ot-123',
        backtest_id: 'bt-1',
        status: 'completed',
        overall_level: 'low',
        robustness_score: 81,
        summary: '检测完成',
        methods: [],
        error_message: null,
      },
    })

    await vi.waitFor(() => {
      expect(runtime.loading.value).toBe(false)
      expect(currentResult.value?.task_id).toBe('ot-123')
      expect(currentResult.value?.robustness_score).toBe(81)
    })
  })

  it('falls back to polling when token is missing', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { getAccessToken } = await import('@/utils/session')
    vi.mocked(getAccessToken).mockReturnValue(null)
    vi.mocked(strategyApi.getOverfittingTask).mockResolvedValue({
      task_id: 'ot-123',
      backtest_id: 'bt-1',
      status: 'completed',
      overall_level: 'medium',
      robustness_score: 63,
      summary: '轮询完成',
      methods: [],
      error_message: null,
    })

    runtime = useOverfittingRuntime({ currentResult })
    runtime.startRuntime('ot-123')

    await vi.waitFor(() => {
      expect(strategyApi.getOverfittingTask).toHaveBeenCalledWith('ot-123')
      expect(currentResult.value?.summary).toBe('轮询完成')
      expect(runtime.loading.value).toBe(false)
    })

    expect(MockWebSocket.instances.length).toBe(0)
  })
})
