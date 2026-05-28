import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { strategyApi } from '@/api/strategy'
import { useStrategyStore } from '@/stores/strategy'

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [{ id: '001', name: 'MA Cross', description: 'test', code: '', params: {}, category: 'trend' }], total: 1 }),
    get: vi.fn().mockResolvedValue({ id: 's1', user_id: 'u1', name: 'My Strategy', code: 'code', params: {}, category: 'custom', created_at: '', updated_at: '' }),
    create: vi.fn().mockResolvedValue({ id: 's1', user_id: 'u1', name: 'My Strategy', code: 'code', params: {}, category: 'custom', created_at: '', updated_at: '' }),
    list: vi.fn().mockResolvedValue({ total: 1, items: [{ id: 's1', user_id: 'u1', name: 'My Strategy', code: 'code', params: {}, category: 'custom', created_at: '', updated_at: '' }] }),
    update: vi.fn().mockResolvedValue({ id: 's1', user_id: 'u1', name: 'Updated', code: 'code', params: {}, category: 'custom', created_at: '', updated_at: '' }),
    delete: vi.fn().mockResolvedValue({}),
  },
}))

describe('useStrategyStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('should start with empty state', () => {
    const store = useStrategyStore()
    expect(store.templates).toEqual([])
    expect(store.strategies).toEqual([])
  })

  it('should fetch templates', async () => {
    const store = useStrategyStore()
    await store.fetchTemplates()
    expect(store.templates.length).toBe(1)
    expect(store.templates[0].name).toBe('MA Cross')
    expect(store.loading).toBe(false)
  })

  it('should create strategy', async () => {
    const store = useStrategyStore()
    const result = await store.createStrategy({
      name: 'My Strategy',
      code: 'code',
      params: {},
      category: 'custom',
    })
    expect(result).toBeDefined()
    expect(result.name).toBe('My Strategy')
    expect(store.strategies).toHaveLength(1)
    expect(store.total).toBe(1)
  })

  it('should fetch user strategies', async () => {
    const store = useStrategyStore()
    await store.fetchStrategies()
    expect(store.strategies.length).toBe(1)
    expect(store.total).toBe(1)
  })

  it('should fetch and store current strategy detail', async () => {
    const store = useStrategyStore()
    const result = await store.fetchStrategy('s1')

    expect(strategyApi.get).toHaveBeenCalledWith('s1')
    expect(result?.id).toBe('s1')
    expect(store.currentStrategy?.id).toBe('s1')
  })

  it('should sync current strategy when updating tracked strategy', async () => {
    const store = useStrategyStore()
    await store.fetchStrategies()
    await store.fetchStrategy('s1')

    const updated = await store.updateStrategy('s1', { name: 'Updated' })

    expect(updated.name).toBe('Updated')
    expect(store.strategies[0].name).toBe('Updated')
    expect(store.currentStrategy?.name).toBe('Updated')
  })

  it('should clear current strategy and decrement total after deleting tracked strategy', async () => {
    const store = useStrategyStore()
    await store.fetchStrategies()
    await store.fetchStrategy('s1')

    await store.deleteStrategy('s1')

    expect(strategyApi.delete).toHaveBeenCalledWith('s1')
    expect(store.strategies).toEqual([])
    expect(store.currentStrategy).toBeNull()
    expect(store.total).toBe(0)
  })

  it('should reset loading after template fetch failure', async () => {
    vi.mocked(strategyApi.getTemplates).mockRejectedValueOnce(new Error('template failed'))
    const store = useStrategyStore()

    await expect(store.fetchTemplates()).rejects.toThrow('template failed')

    expect(store.loading).toBe(false)
  })
})
