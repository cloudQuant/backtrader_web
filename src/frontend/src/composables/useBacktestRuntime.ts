import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getErrorMessage } from '@/api/index'
import { backtestApi } from '@/api/backtest'
import type { BacktestResult, BacktestRuntimeEvent } from '@/types'
import { getAccessToken } from '@/utils/session'

const WS_TOKEN_PROTOCOL = 'access-token'
const POLL_BASE_DELAY_MS = 1000
const POLL_MAX_DELAY_MS = 5000
const POLL_MAX_ATTEMPTS = 60

interface UseBacktestRuntimeOptions {
  currentResult: Ref<BacktestResult | null>
  fetchResult: (taskId: string) => Promise<BacktestResult | null>
  refreshResults: () => Promise<void>
}

export function useBacktestRuntime(options: UseBacktestRuntimeOptions) {
  const loading = ref(false)
  const currentTaskId = ref('')
  const progressInfo = ref({ progress: 0, message: '' })

  let ws: WebSocket | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let pollingStarted = false
  let pollAbortController: AbortController | null = null

  function createBacktestWebSocketProtocols(): string[] {
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

  function parseRuntimeEvent(payload: string): BacktestRuntimeEvent | null {
    try {
      const parsed = JSON.parse(payload) as unknown
      if (!parsed || typeof parsed !== 'object' || !('type' in parsed)) {
        return null
      }
      return parsed as BacktestRuntimeEvent
    } catch {
      return null
    }
  }

  function closeWebSocket() {
    // Abort any active polling
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

  async function finishWithResult(taskId: string) {
    const result = await options.fetchResult(taskId)
    if (!result) {
      throw new Error('回测完成但未找到结果')
    }
    options.currentResult.value = result
    await options.refreshResults()
    loading.value = false
    currentTaskId.value = ''
    closeWebSocket()
    ElMessage.success('回测完成')
  }

  function finishAsFailed(message: string) {
    loading.value = false
    currentTaskId.value = ''
    closeWebSocket()
    ElMessage.error(`回测失败: ${message}`)
  }

  function finishAsCancelled() {
    loading.value = false
    currentTaskId.value = ''
    closeWebSocket()
    ElMessage.warning('回测已取消')
  }

  function startPollingFallback(taskId: string): void {
    if (pollingStarted || !loading.value) {
      return
    }
    pollingStarted = true
    void pollResult(taskId)
  }

  function connectWebSocket(taskId: string) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/backtest/${taskId}`
    const protocols = createBacktestWebSocketProtocols()
    pollingStarted = false
    ws = protocols.length > 0 ? new WebSocket(wsUrl, protocols) : new WebSocket(wsUrl)

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
          message: data.message || '回测任务已提交',
        }
        return
      }
      if (data.type === 'progress') {
        progressInfo.value = {
          progress: typeof data.progress === 'number' ? data.progress : progressInfo.value.progress,
          message: typeof data.message === 'string' ? data.message : '回测运行中...',
        }
        return
      }
      if (data.type === 'completed') {
        progressInfo.value = {
          progress: typeof data.progress === 'number' ? data.progress : 100,
          message: typeof data.message === 'string' ? data.message : '回测完成',
        }
        await finishWithResult(taskId)
        return
      }
      if (data.type === 'failed') {
        const message = typeof data.error === 'string'
          ? data.error
          : typeof data.message === 'string'
            ? data.message
            : '未知错误'
        finishAsFailed(message)
        return
      }
      if (data.type === 'cancelled') {
        finishAsCancelled()
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
  }

  async function pollResult(taskId: string) {
    pollAbortController = new AbortController()
    const { signal } = pollAbortController
    let attempts = 0

    while (attempts < POLL_MAX_ATTEMPTS && loading.value && !signal.aborted) {
      try {
        const statusResp = await backtestApi.getStatus(taskId)
        if (statusResp.status === 'completed') {
          await finishWithResult(taskId)
          return
        }
        if (statusResp.status === 'failed') {
          const result = await options.fetchResult(taskId).catch(() => null)
          finishAsFailed(result?.error_message || '未知错误')
          return
        }
        if (statusResp.status === 'cancelled') {
          finishAsCancelled()
          return
        }
        progressInfo.value = {
          progress: Math.min(progressInfo.value.progress + 5, 95),
          message: '正在获取回测进度...',
        }
      } catch (e: unknown) {
        if (signal.aborted) return
        if (attempts >= POLL_MAX_ATTEMPTS - 1) {
          loading.value = false
          currentTaskId.value = ''
          closeWebSocket()
          ElMessage.error(getErrorMessage(e, '回测结果查询失败'))
          return
        }
      }

      try {
        await sleep(getPollingDelayMs(attempts), signal)
      } catch {
        // Aborted — exit silently
        return
      }
      attempts++
    }

    if (loading.value && !signal.aborted) {
      loading.value = false
      currentTaskId.value = ''
      closeWebSocket()
      ElMessage.warning('回测超时，请稍后查看结果')
    }
  }

  async function cancelBacktest() {
    if (!currentTaskId.value) {
      return
    }
    try {
      await backtestApi.cancel(currentTaskId.value)
      loading.value = false
      currentTaskId.value = ''
      closeWebSocket()
      ElMessage.success('已取消回测任务')
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, '取消失败'))
    }
  }

  function startRuntime(taskId: string) {
    loading.value = true
    currentTaskId.value = taskId
    progressInfo.value = { progress: 0, message: '提交任务中...' }
    connectWebSocket(taskId)
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
    cancelBacktest,
    closeWebSocket,
    connectWebSocket,
    disposeRuntime,
    pollResult,
    startPollingFallback,
    startRuntime,
    stopRuntime,
  }
}
