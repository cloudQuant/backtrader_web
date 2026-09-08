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

  it('submits trusted v2 research with an idempotency key', async () => {
    vi.mocked(api.post).mockResolvedValue({ run: { id: 'run-v2' }, task: { id: 'task-v2' } })
    await strategyApi.submitTrustedAIResearchRun(
      {
        hypothesis_version_id: 'hypothesis-v2',
        dataset_snapshot_id: 'dataset-v2',
        experiment_epoch_id: 'epoch-v2',
        profile_id: 'dev-single-process',
        profile_version: 'v1',
        promotion_policy_version: 'promotion-v1',
        request_json: { hypothesis_content_hash: 'a'.repeat(64) },
        precheck_id: 'precheck-v2',
      },
      'trusted-submit-1'
    )
    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/runs',
      expect.objectContaining({ hypothesis_version_id: 'hypothesis-v2' }),
      { headers: { 'Idempotency-Key': 'trusted-submit-1' }, signal: undefined }
    )
  })

  it('submits a trusted v2 dataset using only an opaque server receipt', async () => {
    vi.mocked(api.post).mockResolvedValue({ id: 'dataset-v2' })
    await strategyApi.createTrustedAIResearchDataset({
      dataset_policy_version: 'dataset-policy-v1',
      partition_kind: 'DISCOVERY',
      instrument_manifest: { symbols: ['RB0'] },
      split_manifest: {},
      source_manifest: {},
      execution_policy: {},
      point_in_time_cutoff: '2026-09-05T00:00:00Z',
      object_receipt_id: 'fixture-receipt-discovery-v1',
      license_tags: ['fixture-permitted'],
    })

    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/datasets',
      expect.objectContaining({ object_receipt_id: 'fixture-receipt-discovery-v1' }),
      { signal: undefined },
    )
    const requestBody = vi.mocked(api.post).mock.calls[0]?.[1] as Record<string, unknown>
    expect(requestBody).not.toHaveProperty('storage_reference')
  })

  it('reads trusted v2 task observability through opaque cursors', async () => {
    const signal = new AbortController().signal
    vi.mocked(api.get).mockResolvedValue({ items: [], next_cursor: null })

    await strategyApi.listTrustedAIResearchTasks('opaque-task-cursor', 25, signal)
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/v2/tasks', {
      params: { cursor: 'opaque-task-cursor', limit: 25 },
      signal,
    })

    await strategyApi.getTrustedAIResearchTask('task-v2', signal)
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/v2/tasks/task-v2', { signal })

    await strategyApi.listTrustedAIResearchTaskEvents(
      'task-v2',
      'opaque-event-cursor',
      10,
      signal,
    )
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/v2/tasks/task-v2/events', {
      params: { cursor: 'opaque-event-cursor', limit: 10 },
      signal,
    })
  })

  it('leaves trusted v2 epoch family derivation to the server', async () => {
    vi.mocked(api.post).mockResolvedValue({ id: 'epoch-v2' })
    await strategyApi.createTrustedAIResearchEpoch({
      hypothesis_version_id: 'hypothesis-v2',
      search_budget: { max_trials: 3 },
      dataset_policy_version: 'dataset-policy-v1',
    })
    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/epochs',
      {
        hypothesis_version_id: 'hypothesis-v2',
        search_budget: { max_trials: 3 },
        dataset_policy_version: 'dataset-policy-v1',
      },
      { signal: undefined }
    )
  })

  it('freezes an owner-scoped trusted v2 candidate with only its expected hash', async () => {
    const signal = new AbortController().signal
    vi.mocked(api.post).mockResolvedValue({
      id: 'candidate-v2',
      run_id: 'run-v2',
      candidate_hash: 'a'.repeat(64),
      freeze_status: 'FROZEN',
    })

    await strategyApi.freezeTrustedAIResearchCandidate(
      'candidate-v2',
      { expected_candidate_hash: 'a'.repeat(64) },
      signal,
    )

    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/candidates/candidate-v2/freeze',
      { expected_candidate_hash: 'a'.repeat(64) },
      { signal },
    )
  })

  it('requests and reads one owner-scoped holdout command without client authority fields', async () => {
    const signal = new AbortController().signal
    vi.mocked(api.post).mockResolvedValue({ id: 'holdout-command-v2', status: 'QUEUED' })
    vi.mocked(api.get).mockResolvedValue({ id: 'holdout-command-v2', status: 'QUEUED' })

    await strategyApi.requestTrustedAIResearchHoldout(
      'candidate-v2',
      'a'.repeat(64),
      'holdout-request-operation-1',
      signal,
    )
    await strategyApi.getTrustedAIResearchHoldout('holdout-command-v2', signal)

    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/candidates/candidate-v2/holdout-evaluation',
      { expected_candidate_hash: 'a'.repeat(64) },
      {
        headers: { 'Idempotency-Key': 'holdout-request-operation-1' },
        signal,
      },
    )
    expect(api.get).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/holdout-evaluations/holdout-command-v2',
      { signal },
    )
  })

  it('submitAIResearchTask', async () => {
    vi.mocked(api.post).mockResolvedValue({ task_id: 'task-1', status: 'pending' })
    await strategyApi.submitAIResearchTask({
      prompt: 'build a trend strategy',
      symbol: '000001.SZ',
      target_sharpe: 1,
    })
    expect(api.post).toHaveBeenCalledWith('/strategy/ai-research/tasks', {
      prompt: 'build a trend strategy',
      symbol: '000001.SZ',
      target_sharpe: 1,
    })
  })

  it('getAIResearchTask', async () => {
    vi.mocked(api.get).mockResolvedValue({ task_id: 'task-1', status: 'completed' })
    await strategyApi.getAIResearchTask('task-1')
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/tasks/task-1')
  })

  it('listAIResearchTasks', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 1, items: [] })
    await strategyApi.listAIResearchTasks(true, 5)
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/tasks', {
      params: { active_only: true, limit: 5 },
    })
  })

  it('cancelAIResearchTask', async () => {
    vi.mocked(api.post).mockResolvedValue({ task_id: 'task-1', status: 'cancelled' })
    await strategyApi.cancelAIResearchTask('task-1')
    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/tasks/task-1/cancel',
      undefined
    )
  })

  it('listAIResearchRuns', async () => {
    vi.mocked(api.get).mockResolvedValue({ total: 1, items: [] })
    await strategyApi.listAIResearchRuns('research-ws', 5)
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/runs', {
      params: { research_workspace_id: 'research-ws', limit: 5 },
    })
  })

  it('getAIResearchRun', async () => {
    vi.mocked(api.get).mockResolvedValue({ run_id: 'run-1' })
    await strategyApi.getAIResearchRun('run-1', 'research-ws')
    expect(api.get).toHaveBeenCalledWith('/strategy/ai-research/runs/run-1', {
      params: { research_workspace_id: 'research-ws' },
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

  it('reviewAIResearchPaperTrading', async () => {
    vi.mocked(api.get).mockResolvedValue({ status: 'ready_for_live_candidate' })
    await strategyApi.reviewAIResearchPaperTrading('run-1', 'research-ws')
    expect(api.get).toHaveBeenCalledWith(
      '/strategy/ai-research/runs/run-1/paper-trading/review',
      {
        params: { research_workspace_id: 'research-ws' },
      }
    )
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
