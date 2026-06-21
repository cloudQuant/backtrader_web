import { onBeforeUnmount, ref } from 'vue'

import {
  stockAnalysisApi,
  type StockAnalysisResult,
  type StockAnalysisTask,
} from '@/api/stockAnalysis'

const TERMINAL_STATUSES: Array<StockAnalysisTask['status']> = ['completed', 'failed', 'cancelled']

export function isStockAnalysisTerminalStatus(status?: StockAnalysisTask['status'] | null): boolean {
  return Boolean(status && TERMINAL_STATUSES.includes(status))
}

export function useStockAnalysisTask(taskId: string, options?: { intervalMs?: number }) {
  const task = ref<StockAnalysisTask | null>(null)
  const result = ref<StockAnalysisResult | null>(null)
  const loading = ref(false)
  const error = ref<unknown>(null)
  const polling = ref(false)
  let timer: number | null = null

  async function refreshTask() {
    loading.value = true
    error.value = null
    try {
      const nextTask = await stockAnalysisApi.getTask(taskId)
      task.value = nextTask
      if (nextTask.status === 'completed') {
        result.value = await stockAnalysisApi.getTaskResult(taskId)
      }
      if (isStockAnalysisTerminalStatus(nextTask.status)) {
        stopPolling()
      }
      return nextTask
    } catch (caught) {
      error.value = caught
      stopPolling()
      throw caught
    } finally {
      loading.value = false
    }
  }

  function startPolling() {
    if (polling.value) return
    polling.value = true
    void refreshTask()
    timer = window.setInterval(() => {
      void refreshTask()
    }, options?.intervalMs ?? 2500)
  }

  function stopPolling() {
    polling.value = false
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  onBeforeUnmount(stopPolling)

  return {
    task,
    result,
    loading,
    error,
    polling,
    refreshTask,
    startPolling,
    stopPolling,
  }
}
