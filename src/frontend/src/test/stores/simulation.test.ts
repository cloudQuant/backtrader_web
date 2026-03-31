import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/simulation', () => ({
  simulationApi: {
    list: vi.fn().mockResolvedValue({ instances: [
      { id: 'sim1', strategy_id: 's1', strategy_name: 'SMA', status: 'running' },
    ], total: 1 }),
    add: vi.fn().mockResolvedValue({ id: 'sim2', strategy_id: 's2', strategy_name: 'RSI', status: 'stopped' }),
    remove: vi.fn().mockResolvedValue(undefined),
    start: vi.fn().mockResolvedValue({ id: 'sim1', strategy_id: 's1', strategy_name: 'SMA', status: 'running' }),
    stop: vi.fn().mockResolvedValue({ id: 'sim1', strategy_id: 's1', strategy_name: 'SMA', status: 'stopped' }),
    startAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
    stopAll: vi.fn().mockResolvedValue({ success: 1, failed: 0 }),
  },
}))

import { useSimulationStore } from '@/stores/simulation'
import { simulationApi } from '@/api/simulation'

describe('useSimulationStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchInstances loads instances', async () => {
    const store = useSimulationStore()
    await store.fetchInstances()
    expect(store.instances).toHaveLength(1)
    expect(store.total).toBe(1)
    expect(store.loading).toBe(false)
  })

  it('addInstance adds to front of list', async () => {
    const store = useSimulationStore()
    await store.fetchInstances()
    const instance = await store.addInstance('s2')
    expect(instance.id).toBe('sim2')
    expect(store.instances[0].id).toBe('sim2')
  })

  it('removeInstance removes from list', async () => {
    const store = useSimulationStore()
    await store.fetchInstances()
    const countBefore = store.instances.length
    await store.removeInstance('sim1')
    expect(simulationApi.remove).toHaveBeenCalledWith('sim1')
    expect(store.instances.length).toBeLessThan(countBefore)
    expect(store.instances.find(i => i.id === 'sim1')).toBeUndefined()
  })

  it('startInstance updates instance status', async () => {
    const store = useSimulationStore()
    await store.fetchInstances()
    const result = await store.startInstance('sim1')
    expect(result.status).toBe('running')
  })

  it('stopInstance updates instance status', async () => {
    const store = useSimulationStore()
    await store.fetchInstances()
    const result = await store.stopInstance('sim1')
    expect(result.status).toBe('stopped')
  })

  it('startAll calls API and refetches', async () => {
    const store = useSimulationStore()
    const result = await store.startAll()
    expect(result.success).toBe(1)
    expect(simulationApi.startAll).toHaveBeenCalled()
    expect(simulationApi.list).toHaveBeenCalled()
  })

  it('stopAll calls API and refetches', async () => {
    const store = useSimulationStore()
    const result = await store.stopAll()
    expect(result.success).toBe(1)
    expect(simulationApi.stopAll).toHaveBeenCalled()
    expect(simulationApi.list).toHaveBeenCalled()
  })

  it('loading is set during fetchInstances', async () => {
    const store = useSimulationStore()
    const fetchPromise = store.fetchInstances()
    expect(store.loading).toBe(true)
    await fetchPromise
    expect(store.loading).toBe(false)
  })
})
