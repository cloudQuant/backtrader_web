import { getCurrentScope, onScopeDispose, ref } from 'vue'

import {
  assetResearchApi,
  type AssetResearchResult,
  type AssetResearchTask,
} from '@/api/assetResearch'

const TERMINAL_STATUSES: AssetResearchTask['status'][] = [
  'SUCCEEDED',
  'FAILED',
  'CANCELLED',
]
const DEFAULT_POLL_INTERVAL_MS = 2_500
const TRANSIENT_FAILURE_BACKOFF_MS = [2_500, 5_000, 10_000, 20_000]

export function isAssetAnalysisTerminalStatus(status?: AssetResearchTask['status'] | null): boolean {
  return Boolean(status && TERMINAL_STATUSES.includes(status))
}

function isTransientPollingError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return true
  }

  const response = (error as { response?: unknown }).response
  if (!response || typeof response !== 'object') {
    return true
  }

  const status = (response as { status?: unknown }).status
  return typeof status !== 'number' || status === 408 || status === 429 || status >= 500
}

/**
 * Keeps a single public analysis task attached to the active asset selection.
 *
 * A response for an earlier selection must never replace the current report:
 * users can change a contract or currency pair while a prior request is still
 * in flight. Generation checks also prevent timer callbacks from reviving a
 * completed or cancelled task.
 */
export function useAssetAnalysisTask(options?: { intervalMs?: number }) {
  const task = ref<AssetResearchTask | null>(null)
  const result = ref<AssetResearchResult | null>(null)
  const loading = ref(false)
  const error = ref<unknown>(null)
  const polling = ref(false)
  const activeTaskId = ref<string | null>(null)

  let timer: number | null = null
  let generation = 0
  let consecutivePollingFailures = 0
  const refreshingTaskIds = new Set<string>()

  function isCurrent(taskId: string, requestGeneration: number): boolean {
    return activeTaskId.value === taskId && generation === requestGeneration
  }

  function stopPolling() {
    polling.value = false
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  function reset() {
    generation += 1
    stopPolling()
    consecutivePollingFailures = 0
    activeTaskId.value = null
    task.value = null
    result.value = null
    error.value = null
    loading.value = false
  }

  function isPageHidden(): boolean {
    return typeof document !== 'undefined' && document.hidden
  }

  function startPolling() {
    if (
      !activeTaskId.value ||
      polling.value ||
      isPageHidden() ||
      isAssetAnalysisTerminalStatus(task.value?.status)
    ) {
      return
    }
    polling.value = true
    timer = window.setInterval(() => {
      void refreshTask()
    }, options?.intervalMs ?? DEFAULT_POLL_INTERVAL_MS)
  }

  function schedulePollingRetry() {
    if (
      !activeTaskId.value ||
      isPageHidden() ||
      isAssetAnalysisTerminalStatus(task.value?.status)
    ) {
      return
    }

    const delay =
      TRANSIENT_FAILURE_BACKOFF_MS[
        Math.min(consecutivePollingFailures, TRANSIENT_FAILURE_BACKOFF_MS.length - 1)
      ]
    consecutivePollingFailures += 1
    polling.value = true
    timer = window.setTimeout(() => {
      timer = null
      polling.value = false
      void refreshTask()
    }, delay)
  }

  async function refreshTask(): Promise<AssetResearchTask | null> {
    const taskId = activeTaskId.value
    const requestGeneration = generation
    if (!taskId || refreshingTaskIds.has(taskId)) {
      return task.value
    }

    refreshingTaskIds.add(taskId)
    loading.value = true
    error.value = null
    try {
      const nextTask = await assetResearchApi.getTask(taskId)
      if (!isCurrent(taskId, requestGeneration)) {
        return null
      }

      task.value = nextTask
      consecutivePollingFailures = 0
      if (nextTask.status === 'SUCCEEDED') {
        const nextResult = await assetResearchApi.getTaskResult(taskId)
        if (!isCurrent(taskId, requestGeneration)) {
          return null
        }
        result.value = nextResult
      }
      if (isAssetAnalysisTerminalStatus(nextTask.status)) {
        stopPolling()
      } else {
        startPolling()
      }
      return nextTask
    } catch (caught) {
      if (isCurrent(taskId, requestGeneration)) {
        error.value = caught
        stopPolling()
        if (isTransientPollingError(caught)) {
          schedulePollingRetry()
        }
      }
      return null
    } finally {
      refreshingTaskIds.delete(taskId)
      if (isCurrent(taskId, requestGeneration)) {
        loading.value = false
      }
    }
  }

  async function start(taskId: string): Promise<AssetResearchTask | null> {
    reset()
    activeTaskId.value = taskId
    loading.value = true
    return refreshTask()
  }

  async function cancel(): Promise<AssetResearchTask | null> {
    const taskId = activeTaskId.value
    if (!taskId) return null

    const requestGeneration = ++generation
    stopPolling()
    consecutivePollingFailures = 0
    loading.value = true
    error.value = null
    try {
      const nextTask = await assetResearchApi.cancelTask(taskId)
      if (!isCurrent(taskId, requestGeneration)) {
        return null
      }
      task.value = nextTask
      if (isAssetAnalysisTerminalStatus(nextTask.status)) {
        result.value = null
      }
      return nextTask
    } catch (caught) {
      if (isCurrent(taskId, requestGeneration)) {
        error.value = caught
      }
      return null
    } finally {
      if (isCurrent(taskId, requestGeneration)) {
        loading.value = false
      }
    }
  }

  async function retry(): Promise<AssetResearchTask | null> {
    const taskId = activeTaskId.value
    if (!taskId) return null

    const requestGeneration = ++generation
    stopPolling()
    consecutivePollingFailures = 0
    task.value = null
    result.value = null
    error.value = null
    loading.value = true
    try {
      const nextTask = await assetResearchApi.retryTask(taskId)
      if (!isCurrent(taskId, requestGeneration)) {
        return null
      }
      activeTaskId.value = nextTask.task_id
      generation += 1
      return refreshTask()
    } catch (caught) {
      if (isCurrent(taskId, requestGeneration)) {
        error.value = caught
      }
      return null
    } finally {
      if (activeTaskId.value === taskId && generation === requestGeneration) {
        loading.value = false
      }
    }
  }

  function onVisibilityChange() {
    if (isPageHidden()) {
      stopPolling()
      return
    }
    if (activeTaskId.value && !isAssetAnalysisTerminalStatus(task.value?.status)) {
      void refreshTask()
    }
  }

  function dispose() {
    generation += 1
    stopPolling()
    consecutivePollingFailures = 0
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  if (getCurrentScope()) {
    onScopeDispose(dispose)
  }

  return {
    task,
    result,
    loading,
    error,
    polling,
    activeTaskId,
    start,
    refreshTask,
    startPolling,
    stopPolling,
    cancel,
    retry,
    reset,
    dispose,
  }
}
