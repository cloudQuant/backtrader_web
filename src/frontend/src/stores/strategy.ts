import { defineStore } from 'pinia'
import { ref } from 'vue'
import { strategyApi } from '@/api/strategy'
import type { Strategy, StrategyCreate, StrategyTemplate, StrategyType } from '@/types'

export const useStrategyStore = defineStore('strategy', () => {
  const strategies = ref<Strategy[]>([])
  const templates = ref<StrategyTemplate[]>([])
  const currentStrategy = ref<Strategy | null>(null)
  const loading = ref(false)
  const total = ref(0)

  async function withLoading<T>(operation: () => Promise<T>): Promise<T> {
    loading.value = true
    try {
      return await operation()
    } finally {
      loading.value = false
    }
  }

  async function fetchStrategies(limit = 20, offset = 0, category?: string) {
    await withLoading(async () => {
      const response = await strategyApi.list(limit, offset, category)
      strategies.value = response.items
      total.value = response.total
    })
  }

  async function fetchTemplates(strategyType?: StrategyType) {
    await withLoading(async () => {
      const response = await strategyApi.getTemplates(strategyType)
      templates.value = response.templates
    })
  }

  async function createStrategy(data: StrategyCreate) {
    return await withLoading(async () => {
      const strategy = await strategyApi.create(data)
      strategies.value.unshift(strategy)
      total.value += 1
      return strategy
    })
  }

  async function updateStrategy(id: string, data: Partial<StrategyCreate>) {
    return await withLoading(async () => {
      const strategy = await strategyApi.update(id, data)
      strategies.value = strategies.value.map(s => s.id === id ? strategy : s)
      if (currentStrategy.value?.id === id) {
        currentStrategy.value = strategy
      }
      return strategy
    })
  }

  async function deleteStrategy(id: string) {
    await withLoading(async () => {
      await strategyApi.delete(id)
      const nextStrategies = strategies.value.filter(s => s.id !== id)
      if (nextStrategies.length !== strategies.value.length) {
        total.value = Math.max(0, total.value - 1)
      }
      strategies.value = nextStrategies
      if (currentStrategy.value?.id === id) {
        currentStrategy.value = null
      }
    })
  }

  async function fetchStrategy(id: string) {
    return await withLoading(async () => {
      currentStrategy.value = await strategyApi.get(id)
      return currentStrategy.value
    })
  }

  return {
    strategies,
    templates,
    currentStrategy,
    loading,
    total,
    fetchStrategies,
    fetchTemplates,
    createStrategy,
    updateStrategy,
    deleteStrategy,
    fetchStrategy,
  }
})
