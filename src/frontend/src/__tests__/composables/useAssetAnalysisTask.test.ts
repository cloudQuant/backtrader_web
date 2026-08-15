import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/assetResearch', () => ({
  assetResearchApi: {
    getTask: vi.fn(),
    getTaskResult: vi.fn(),
    cancelTask: vi.fn(),
    retryTask: vi.fn(),
  },
}))

import { assetResearchApi, type AssetResearchTask } from '@/api/assetResearch'
import { useAssetAnalysisTask } from '@/composables/useAssetAnalysisTask'

function task(taskId: string, status: AssetResearchTask['status']): AssetResearchTask {
  return {
    task_id: taskId,
    status,
    asset_type: 'futures',
    canonical_id: 'futures:CFFEX:IF2609:CNY',
    progress: status === 'SUCCEEDED' ? 100 : 10,
    created_at: '2026-08-01T10:00:00Z',
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

describe('useAssetAnalysisTask', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('discards a late response from a previous task and shows only the active result', async () => {
    const first = deferred<AssetResearchTask>()
    vi.mocked(assetResearchApi.getTask)
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(task('task-2', 'SUCCEEDED'))
    vi.mocked(assetResearchApi.getTaskResult).mockResolvedValueOnce({
      task_id: 'task-2',
      status: 'SUCCEEDED',
      prediction_id: 'prediction-2',
      published_decision: {
        asset_type: 'futures',
        market_view: 'NEUTRAL',
        normalized_direction: 'NEUTRAL',
        position_context: 'UNKNOWN',
        horizon_code: 'standard',
        quality_status: 'ELIGIBLE',
        recommendation: 'HOLD',
        actionability: 'RESEARCH_ONLY',
        trade_intent: 'NONE',
        reason_codes: ['MODEL_NOT_PROMOTED'],
        execution_disabled: true,
      },
    })

    const runtime = useAssetAnalysisTask({ intervalMs: 60_000 })
    const firstStart = runtime.start('task-1')
    const secondStart = runtime.start('task-2')

    await secondStart
    first.resolve(task('task-1', 'SUCCEEDED'))
    await firstStart

    expect(runtime.task.value?.task_id).toBe('task-2')
    expect(runtime.result.value?.prediction_id).toBe('prediction-2')
    expect(runtime.polling.value).toBe(false)
    runtime.dispose()
  })

  it('clears a completed report before starting a different task', async () => {
    vi.mocked(assetResearchApi.getTask)
      .mockResolvedValueOnce(task('task-1', 'SUCCEEDED'))
      .mockResolvedValueOnce(task('task-2', 'RUNNING'))
    vi.mocked(assetResearchApi.getTaskResult).mockResolvedValueOnce({
      task_id: 'task-1',
      status: 'SUCCEEDED',
      prediction_id: 'prediction-1',
    })

    const runtime = useAssetAnalysisTask({ intervalMs: 60_000 })
    await runtime.start('task-1')
    expect(runtime.result.value?.prediction_id).toBe('prediction-1')

    await runtime.start('task-2')
    expect(runtime.task.value?.task_id).toBe('task-2')
    expect(runtime.result.value).toBeNull()
    runtime.dispose()
  })

  it('pauses background polling while the page is hidden and refreshes on return', async () => {
    const hiddenDescriptor = Object.getOwnPropertyDescriptor(document, 'hidden')
    vi.mocked(assetResearchApi.getTask)
      .mockResolvedValueOnce(task('task-visibility', 'RUNNING'))
      .mockResolvedValueOnce(task('task-visibility', 'RUNNING'))

    const runtime = useAssetAnalysisTask({ intervalMs: 60_000 })
    await runtime.start('task-visibility')
    expect(runtime.polling.value).toBe(true)

    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(runtime.polling.value).toBe(false)

    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(runtime.polling.value).toBe(true))
    expect(assetResearchApi.getTask).toHaveBeenCalledTimes(2)

    runtime.dispose()
    if (hiddenDescriptor) {
      Object.defineProperty(document, 'hidden', hiddenDescriptor)
    } else {
      Reflect.deleteProperty(document, 'hidden')
    }
  })

  it('backs off transient polling failures and returns to the configured interval after recovery', async () => {
    vi.useFakeTimers()
    vi.mocked(assetResearchApi.getTask)
      .mockRejectedValueOnce(new Error('temporary network failure'))
      .mockRejectedValueOnce(new Error('temporary network failure'))
      .mockRejectedValueOnce(new Error('temporary network failure'))
      .mockRejectedValueOnce(new Error('temporary network failure'))
      .mockResolvedValueOnce(task('task-backoff', 'RUNNING'))
      .mockResolvedValueOnce(task('task-backoff', 'RUNNING'))

    const runtime = useAssetAnalysisTask({ intervalMs: 100 })
    try {
      await runtime.start('task-backoff')
      expect(runtime.polling.value).toBe(true)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(2_499)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(1)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(2)

      await vi.advanceTimersByTimeAsync(4_999)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(2)
      await vi.advanceTimersByTimeAsync(1)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(3)

      await vi.advanceTimersByTimeAsync(9_999)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(3)
      await vi.advanceTimersByTimeAsync(1)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(4)

      await vi.advanceTimersByTimeAsync(19_999)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(4)
      await vi.advanceTimersByTimeAsync(1)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(5)
      expect(runtime.task.value?.status).toBe('RUNNING')

      await vi.advanceTimersByTimeAsync(99)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(5)
      await vi.advanceTimersByTimeAsync(1)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(6)
    } finally {
      runtime.dispose()
      vi.useRealTimers()
    }
  })

  it('does not retry a deterministic client error', async () => {
    vi.useFakeTimers()
    vi.mocked(assetResearchApi.getTask).mockRejectedValueOnce({ response: { status: 404 } })

    const runtime = useAssetAnalysisTask({ intervalMs: 100 })
    try {
      await runtime.start('task-missing')
      expect(runtime.polling.value).toBe(false)

      await vi.advanceTimersByTimeAsync(20_000)
      expect(assetResearchApi.getTask).toHaveBeenCalledTimes(1)
    } finally {
      runtime.dispose()
      vi.useRealTimers()
    }
  })
})
