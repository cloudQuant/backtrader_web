import { ref, type Ref } from 'vue'

import { strategyApi, type StrategyOverfittingTaskResult } from '@/api/strategy'
import { getAccessToken } from '@/utils/session'

const WS_TOKEN_PROTOCOL = 'access-token'
const POLL_BASE_DELAY_MS = 1000
const POLL_MAX_DELAY_MS = 5000
const POLL_MAX_ATTEMPTS = 60

interface UseOverfittingRuntimeOptions {
  currentResult: Ref<StrategyOverfittingTaskResult | null>
}

interface OverfittingRuntimeEvent {
  type: string
  task_id?: string
  progress?: number
  message?: string
  error?: string
  result?: StrategyOverfittingTaskResult | null
}

export function useOverfittingRuntime(options: UseOverfittingRuntimeOptions) {
  const loading = ref(false)
  const currentTaskId = ref('')
  const progressInfo = ref({ progress: 0, message: '' })

  let ws: WebSocket | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let pollingStarted = false
  let pollAbortController: AbortController | null = null

  function createWebSocketProtocols(): string[] {
    const token = getAccessToken()
    if (!token) {
      return []
    }
    return [WS_TOKEN_PROTOCOL, token]
  }

  function getPollingDelayMs(attempt: number): number {
    return Math.min(POLL_BASE_DELAY_MS * 2 ** attempt, POLL_MAX_DELAY_MS)
  }

  function sleep(ms: number, signal?: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(signal.reason)
        return
      }
      const timer = window.setTimeout(resolve, ms)
      signal?.addEventListener('abort', () => {
        clearTimeout(timer)
        reject(signal.reason)
      }, { once: true })
    })
  }

  function parseRuntimeEvent(payload: string): OverfittingRuntimeEvent | null {
    try {
      const parsed = JSON.parse(payload) as unknown
      if (!parsed || typeof parsed !== 'object' || !('type' in parsed)) {
        return null
      }
      return parsed as OverfittingRuntimeEvent
    } catch {
      return null
    }
  }

  function closeWebSocket() {
    if (pollAbortController) {
      pollAbortController.abort()
      pollAbortController = null
    }
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (ws) {
      ws.onclose = null
      ws.onerror = null
      ws.onmessage = null
      ws.close()
      ws = null
    }
  }

  function finishWithResult(result: StrategyOverfittingTaskResult) {
    options.currentResult.value = result
    loading.value = false
    currentTaskId.value = ''
    closeWebSocket()
  }

  function finishAsFailed(message: string) {
    progressInfo.value = {
      progress: progressInfo.value.progress,
      message,
    }
    loading.value = false
    currentTaskId.value = ''
    closeWebSocket()
  }

  function startPollingFallback(taskId: string): void {
    if (pollingStarted || !loading.value) {
      return
    }
    pollingStarted = true
    void pollResult(taskId)
  }

  function connectWebSocket(taskId: string): boolean {
    if (typeof window === 'undefined' || typeof window.WebSocket === 'undefined') {
      return false
    }
    const protocols = createWebSocketProtocols()
    if (protocols.length === 0) {
      return false
    }
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/overfitting/${taskId}`
    pollingStarted = false
    ws = new WebSocket(wsUrl, protocols)

    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 30000)

    ws.onmessage = async (event) => {
      const data = parseRuntimeEvent(event.data)
      if (!data || data.type === 'pong' || data.type === 'connected') {
        return
      }
      if (data.type === 'task_created') {
        progressInfo.value = {
          progress: 0,
          message: typeof data.message === 'string' ? data.message : '过拟合检测任务已提交',
        }
        return
      }
      if (data.type === 'progress') {
        progressInfo.value = {
          progress: typeof data.progress === 'number' ? data.progress : progressInfo.value.progress,
          message: typeof data.message === 'string' ? data.message : '过拟合检测运行中...',
        }
        return
      }
      if (data.type === 'completed') {
        progressInfo.value = {
          progress: typeof data.progress === 'number' ? data.progress : 100,
          message: typeof data.message === 'string' ? data.message : '过拟合检测完成',
        }
        if (data.result) {
          finishWithResult(data.result)
          return
        }
        const result = await strategyApi.getOverfittingTask(taskId)
        finishWithResult(result)
        return
      }
      if (data.type === 'failed') {
        finishAsFailed(typeof data.error === 'string' ? data.error : (data.message || '过拟合检测失败'))
      }
    }

    ws.onerror = () => {
      closeWebSocket()
      startPollingFallback(taskId)
    }

    ws.onclose = (event) => {
      if (!loading.value || event.code === 1000) {
        return
      }
      closeWebSocket()
      startPollingFallback(taskId)
    }

    return true
  }

  async function pollResult(taskId: string) {
    pollAbortController = new AbortController()
    const { signal } = pollAbortController
    let attempts = 0

    while (attempts < POLL_MAX_ATTEMPTS && loading.value && !signal.aborted) {
      try {
        const result = await strategyApi.getOverfittingTask(taskId)
        if (result.status === 'completed') {
          finishWithResult(result)
          return
        }
        if (result.status === 'failed' || result.status === 'cancelled') {
          finishAsFailed(result.error_message || result.summary || '过拟合检测失败')
          return
        }
        options.currentResult.value = result
        progressInfo.value = {
          progress: Math.min(progressInfo.value.progress + 5, 95),
          message: result.summary || '正在获取过拟合检测进度...',
        }
      } catch {
        if (signal.aborted) {
          return
        }
      }

      try {
        await sleep(getPollingDelayMs(attempts), signal)
      } catch {
        return
      }
      attempts++
    }

    if (loading.value && !signal.aborted) {
      finishAsFailed('过拟合检测超时，请稍后刷新结果')
    }
  }

  function startRuntime(taskId: string) {
    loading.value = true
    currentTaskId.value = taskId
    progressInfo.value = { progress: 0, message: '过拟合检测任务已提交' }
    const connected = connectWebSocket(taskId)
    if (!connected) {
      startPollingFallback(taskId)
    }
  }

  function stopRuntime() {
    loading.value = false
    currentTaskId.value = ''
    closeWebSocket()
  }

  function disposeRuntime() {
    closeWebSocket()
  }

  return {
    loading,
    currentTaskId,
    progressInfo,
    startRuntime,
    stopRuntime,
    disposeRuntime,
  }
}
