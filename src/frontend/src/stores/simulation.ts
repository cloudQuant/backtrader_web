import { defineStore } from 'pinia'
import { ref } from 'vue'
import { simulationApi } from '@/api/simulation'
import type { SimulationInstanceInfo } from '@/api/simulation'

export const useSimulationStore = defineStore('simulation', () => {
  const instances = ref<SimulationInstanceInfo[]>([])
  const loading = ref(false)
  const total = ref(0)

  async function fetchInstances() {
    loading.value = true
    try {
      const response = await simulationApi.list()
      instances.value = response.instances
      total.value = response.total
    } finally {
      loading.value = false
    }
  }

  async function addInstance(
    strategy_id: string,
    params?: Record<string, unknown>
  ) {
    const instance = await simulationApi.add(strategy_id, params)
    instances.value.unshift(instance)
    return instance
  }

  async function removeInstance(instanceId: string) {
    await simulationApi.remove(instanceId)
    instances.value = instances.value.filter(i => i.id !== instanceId)
  }

  async function startInstance(instanceId: string) {
    const instance = await simulationApi.start(instanceId)
    const index = instances.value.findIndex(i => i.id === instanceId)
    if (index !== -1) {
      instances.value[index] = instance
    }
    return instance
  }

  async function stopInstance(instanceId: string) {
    const instance = await simulationApi.stop(instanceId)
    const index = instances.value.findIndex(i => i.id === instanceId)
    if (index !== -1) {
      instances.value[index] = instance
    }
    return instance
  }

  async function startAll() {
    const response = await simulationApi.startAll()
    await fetchInstances()
    return response
  }

  async function stopAll() {
    const response = await simulationApi.stopAll()
    await fetchInstances()
    return response
  }

  return {
    instances,
    loading,
    total,
    fetchInstances,
    addInstance,
    removeInstance,
    startInstance,
    stopInstance,
    startAll,
    stopAll,
  }
})
