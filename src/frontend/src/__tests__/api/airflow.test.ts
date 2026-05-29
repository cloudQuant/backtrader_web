/**
 * Smoke tests for src/api/airflow.ts (Airflow DAG management client).
 * Covers all 8 verbs delegating to the shared axios instance.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
  },
}))

describe('airflowApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getStatus GETs orchestration status', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({ type: 'airflow' } as never)
    await airflowApi.getStatus()
    expect(get).toHaveBeenCalledWith('/data/airflow/orchestration/status')
  })

  it('listDags GETs with default limit/offset', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({ dags: [], total_entries: 0 } as never)
    await airflowApi.listDags()
    expect(get).toHaveBeenCalledWith('/data/airflow/dags', { params: { limit: 100, offset: 0 } })
  })

  it('listDags GETs with custom limit/offset', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({ dags: [], total_entries: 0 } as never)
    await airflowApi.listDags(20, 40)
    expect(get).toHaveBeenCalledWith('/data/airflow/dags', { params: { limit: 20, offset: 40 } })
  })

  it('getDag GETs single DAG path', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await airflowApi.getDag('demo-dag')
    expect(get).toHaveBeenCalledWith('/data/airflow/dags/demo-dag')
  })

  it('triggerDag POSTs without conf when none provided', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)
    await airflowApi.triggerDag('demo-dag')
    expect(post).toHaveBeenCalledWith('/data/airflow/dags/demo-dag/trigger', undefined)
  })

  it('triggerDag POSTs with conf when provided', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)
    await airflowApi.triggerDag('demo-dag', { foo: 'bar' })
    expect(post).toHaveBeenCalledWith('/data/airflow/dags/demo-dag/trigger', { conf: { foo: 'bar' } })
  })

  it('togglePause PATCHes with the is_paused param', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const patch = vi.mocked(apiModule.patch).mockResolvedValue({} as never)
    await airflowApi.togglePause('demo-dag', true)
    expect(patch).toHaveBeenCalledWith('/data/airflow/dags/demo-dag/pause', undefined, {
      params: { is_paused: true },
    })
  })

  it('listDagRuns GETs with default limit', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await airflowApi.listDagRuns('demo-dag')
    expect(get).toHaveBeenCalledWith('/data/airflow/dags/demo-dag/runs', { params: { limit: 25 } })
  })

  it('getTaskInstances GETs the runs/tasks path', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await airflowApi.getTaskInstances('demo-dag', 'run-1')
    expect(get).toHaveBeenCalledWith('/data/airflow/dags/demo-dag/runs/run-1/tasks')
  })

  it('getTaskLog GETs with default try_number', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await airflowApi.getTaskLog('demo-dag', 'run-1', 'task-a')
    expect(get).toHaveBeenCalledWith(
      '/data/airflow/dags/demo-dag/runs/run-1/tasks/task-a/logs',
      { params: { try_number: 1 } },
    )
  })

  it('getTaskLog GETs with custom try_number', async () => {
    const { airflowApi } = await import('@/api/airflow')
    const apiModule = (await import('@/api')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    await airflowApi.getTaskLog('demo-dag', 'run-1', 'task-a', 3)
    expect(get).toHaveBeenCalledWith(
      '/data/airflow/dags/demo-dag/runs/run-1/tasks/task-a/logs',
      { params: { try_number: 3 } },
    )
  })
})
