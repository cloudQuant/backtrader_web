import { defineStore } from 'pinia'
import { ref } from 'vue'
import { strategyApi } from '@/api/strategy'
import type { Strategy, StrategyCreate, StrategyTemplate } from '@/types'

export const useStrategyStore = defineStore('strategy', () => {
  const strategies = ref<Strategy[]>([])
  const templates = ref<StrategyTemplate[]>([])
  const currentStrategy = ref<Strategy | null>(null)
  const loading = ref(false)
  const total = ref(0)

  async function fetchStrategies(limit = 20, offset = 0, category?: string) {
    loading.value = true
    try {
      const response = await strategyApi.list(limit, offset, category)
      strategies.value = response.items
      total.value = response.total
    } finally {
      loading.value = false
    }
  }

  async function fetchTemplates() {
    const response = await strategyApi.getTemplates()
    templates.value = response.templates
  }

  async function createStrategy(data: StrategyCreate) {
    const strategy = await strategyApi.create(data)
    strategies.value.unshift(strategy)
    return strategy
  }

  async function updateStrategy(id: string, data: Partial<StrategyCreate>) {
    const strategy = await strategyApi.update(id, data)
    const index = strategies.value.findIndex(s => s.id === id)
    if (index !== -1) {
      strategies.value[index] = strategy
    }
    return strategy
  }

  async function deleteStrategy(id: string) {
    await strategyApi.delete(id)
    strategies.value = strategies.value.filter(s => s.id !== id)
  }

  async function fetchStrategy(id: string) {
    currentStrategy.value = await strategyApi.get(id)
    return currentStrategy.value
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
