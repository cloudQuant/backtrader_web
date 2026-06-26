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
    await strategyApi.getTemplates('mean_reversion' as unknown as undefined)
    expect(api.get).toHaveBeenCalledWith('/strategy/templates', { params: { strategy_type: 'mean_reversion' } })
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

  it('createScore', async () => {
    vi.mocked(api.post).mockResolvedValue({ backtest_id: 't1' })
    await strategyApi.createScore({ backtest_id: 't1' })
    expect(api.post).toHaveBeenCalledWith('/strategy/score', { backtest_id: 't1' })
  })

  it('getScore', async () => {
    vi.mocked(api.get).mockResolvedValue({ backtest_id: 't1' })
    await strategyApi.getScore('t1')
    expect(api.get).toHaveBeenCalledWith('/strategy/score/t1')
  })

  it('runAIResearchLoop', async () => {
    vi.mocked(api.post).mockResolvedValue({ achieved: true })
    await strategyApi.runAIResearchLoop({
      prompt: 'build a trend strategy',
      symbol: '000001.SZ',
      target_sharpe: 1,
    })
    expect(api.post).toHaveBeenCalledWith('/strategy/ai-research/run', {
      prompt: 'build a trend strategy',
      symbol: '000001.SZ',
      target_sharpe: 1,
    })
  })

  it('listAIResearchRuns', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 1, items: [] })
    await strategyApi.listAIResearchRuns('research-ws', 5)
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/runs', {
      params: { research_workspace_id: 'research-ws', limit: 5 },
    })
  })

  it('startAIResearchPaperTrading', async () => {
    vi.mocked(api.post).mockResolvedValue({ started: true })
    await strategyApi.startAIResearchPaperTrading('run-1', {
      research_workspace_id: 'research-ws',
    })
    expect(api.post).toHaveBeenCalledWith('/strategy/ai-research/runs/run-1/paper-trading', {
      research_workspace_id: 'research-ws',
    })
  })

  it('createOverfittingTask', async () => {
    vi.mocked(api.post).mockResolvedValue({ task_id: 'ot-1' })
    await strategyApi.createOverfittingTask('t1', { methods: ['monte_carlo'] })
    expect(api.post).toHaveBeenCalledWith('/strategy/overfitting/t1', { methods: ['monte_carlo'] })
  })

  it('getOverfittingTask', async () => {
    vi.mocked(api.get).mockResolvedValue({ task_id: 'ot-1' })
    await strategyApi.getOverfittingTask('ot-1')
    expect(api.get).toHaveBeenCalledWith('/strategy/overfitting/task/ot-1')
  })

  it('explainStrategy', async () => {
    vi.mocked(api.post).mockResolvedValue({ code_hash: 'abc123' })
    await strategyApi.explainStrategy({ code: 'class Demo: pass', strategy_name: 'Demo' })
    expect(api.post).toHaveBeenCalledWith('/strategy/explain', {
      code: 'class Demo: pass',
      strategy_name: 'Demo',
    })
  })

  it('getCachedExplanation', async () => {
    vi.mocked(api.get).mockResolvedValue({ code_hash: 'abc123' })
    await strategyApi.getCachedExplanation('abc123')
    expect(api.get).toHaveBeenCalledWith('/strategy/explain/cached/abc123')
  })
})
