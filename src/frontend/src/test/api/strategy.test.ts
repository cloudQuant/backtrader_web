import { describe, it, expect, vi, beforeEach } from 'vitest'
import { strategyApi } from '@/api/strategy'
import api from '@/api/index'

vi.mock('@/api/index', () => ({
  default: { post: vi.fn(), get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

describe('strategyApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('create', async () => {
    vi.mocked(api.post).mockResolvedValue({ id: 's1' })
    await strategyApi.create({ name: 'test', code: 'pass' } as any)
    expect(api.post).toHaveBeenCalledWith('/strategy/', { name: 'test', code: 'pass' })
  })

  it('get', async () => {
    vi.mocked(api.get).mockResolvedValue({ id: 's1' })
    await strategyApi.get('s1')
    expect(api.get).toHaveBeenCalledWith('/strategy/s1')
  })

  it('update', async () => {
    vi.mocked(api.put).mockResolvedValue({ id: 's1' })
    await strategyApi.update('s1', { name: 'new' })
    expect(api.put).toHaveBeenCalledWith('/strategy/s1', { name: 'new' })
  })

  it('delete', async () => {
    vi.mocked(api.delete).mockResolvedValue(undefined)
    await strategyApi.delete('s1')
    expect(api.delete).toHaveBeenCalledWith('/strategy/s1')
  })

  it('list with defaults', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 0, items: [] })
    await strategyApi.list()
    expect(api.get).toHaveBeenCalledWith('/strategy/', { params: { limit: 20, offset: 0, category: undefined } })
  })

  it('list with category', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 0, items: [] })
    await strategyApi.list(10, 5, 'trend')
    expect(api.get).toHaveBeenCalledWith('/strategy/', { params: { limit: 10, offset: 5, category: 'trend' } })
  })

  it('getTemplates', async () => {
    vi.mocked(api.get).mockResolvedValue({ templates: [], total: 0 })
    await strategyApi.getTemplates('mean_reversion')
    expect(api.get).toHaveBeenCalledWith('/strategy/templates', { params: { category: 'mean_reversion' } })
  })

  it('getTemplateDetail', async () => {
    vi.mocked(api.get).mockResolvedValue({ id: 't1' })
    await strategyApi.getTemplateDetail('t1')
    expect(api.get).toHaveBeenCalledWith('/strategy/templates/t1')
  })

  it('getTemplateReadme', async () => {
    vi.mocked(api.get).mockResolvedValue({ template_id: 't1', content: '# README' })
    await strategyApi.getTemplateReadme('t1')
    expect(api.get).toHaveBeenCalledWith('/strategy/templates/t1/readme')
  })

  it('getTemplateConfig', async () => {
    vi.mocked(api.get).mockResolvedValue({})
    await strategyApi.getTemplateConfig('t1')
    expect(api.get).toHaveBeenCalledWith('/strategy/templates/t1/config')
  })
})
