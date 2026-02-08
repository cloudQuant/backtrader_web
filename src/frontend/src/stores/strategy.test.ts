import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useStrategyStore } from './strategy'

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [{ id: '001', name: 'MA Cross', description: 'test', code: '', params: {}, category: 'trend' }], total: 1 }),
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
  })

  it('should fetch user strategies', async () => {
    const store = useStrategyStore()
    await store.fetchStrategies()
    expect(store.strategies.length).toBe(1)
  })
})
