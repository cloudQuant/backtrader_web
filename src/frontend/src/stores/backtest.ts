import { defineStore } from 'pinia'
import { ref } from 'vue'
import { backtestApi } from '@/api/backtest'
import type { BacktestRequest, BacktestResult } from '@/types'

export const useBacktestStore = defineStore('backtest', () => {
  const results = ref<BacktestResult[]>([])
  const currentResult = ref<BacktestResult | null>(null)
  const loading = ref(false)
  const total = ref(0)

  async function runBacktest(request: BacktestRequest) {
    loading.value = true
    try {
      const response = await backtestApi.run(request)
      return response
    } finally {
      loading.value = false
    }
  }

  async function fetchResult(taskId: string) {
    loading.value = true
    try {
      currentResult.value = await backtestApi.getResult(taskId)
      return currentResult.value
    } finally {
      loading.value = false
    }
  }

  async function fetchResults(limit = 20, offset = 0) {
    loading.value = true
    try {
      const response = await backtestApi.list(limit, offset)
      results.value = response.items
      total.value = response.total
    } finally {
      loading.value = false
    }
  }

  async function deleteResult(taskId: string) {
    await backtestApi.delete(taskId)
    results.value = results.value.filter(r => r.task_id !== taskId)
  }

  return {
    results,
    currentResult,
    loading,
    total,
    runBacktest,
    fetchResult,
    fetchResults,
    deleteResult,
  }
})
