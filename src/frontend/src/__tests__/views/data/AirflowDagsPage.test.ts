import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

import type { AirflowDAG, AirflowDAGRun } from '@/api/airflow'
import { elStubs } from '@/test/stubs'

const fixtures = vi.hoisted(() => {
  const dags: AirflowDAG[] = [
    {
      dag_id: 'dag_stock_hist',
      description: 'Daily A-share history pipeline',
      schedule_interval: '0 18 * * *',
      is_paused: false,
      is_active: true,
      tags: [{ name: 'market-data' }],
    },
    {
      dag_id: 'dag_bond_daily',
      description: 'Bond valuation refresh',
      schedule_interval: '@daily',
      is_paused: true,
      is_active: true,
      tags: [{ name: 'fixed-income' }],
    },
  ]

  const runs: AirflowDAGRun[] = [
    {
      dag_run_id: 'manual__2026-07-01T09:00:00',
      dag_id: 'dag_stock_hist',
      state: 'success',
      start_date: '2026-07-01T09:00:00Z',
      end_date: '2026-07-01T09:05:00Z',
      conf: { symbol: '000001' },
    },
  ]

  return { dags, runs }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (params?.count !== undefined) return `${key}:${params.count}`
      if (params?.backend !== undefined) return `${key}:${params.backend}`
      return key
    },
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/airflow', () => ({
  airflowApi: {
    getStatus: vi.fn(),
    listDags: vi.fn(),
    triggerDag: vi.fn(),
    togglePause: vi.fn(),
    listDagRuns: vi.fn(),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

import { ElMessage } from 'element-plus'
import AirflowDagsPage from '@/views/data/AirflowDagsPage.vue'
import { airflowApi } from '@/api/airflow'

const api = airflowApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function doMount() {
  return mount(AirflowDagsPage, { global: { stubs: elStubs } })
}

describe('AirflowDagsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.getStatus.mockResolvedValue({ type: 'airflow', connected: true })
    api.listDags.mockResolvedValue({ dags: fixtures.dags, total_entries: fixtures.dags.length })
    api.triggerDag.mockResolvedValue({
      dag_run_id: 'manual__2026-07-01T10:00:00',
      dag_id: 'dag_stock_hist',
      state: 'queued',
    })
    api.togglePause.mockResolvedValue({ ...fixtures.dags[0], is_paused: true })
    api.listDagRuns.mockResolvedValue({ dag_runs: fixtures.runs, total_entries: fixtures.runs.length })
  })

  it('shows APScheduler fallback when Airflow is not connected', async () => {
    api.getStatus.mockResolvedValue({ type: 'apscheduler', running: true })

    const wrapper = doMount()
    await flushPromises()

    expect(api.getStatus).toHaveBeenCalled()
    expect(api.listDags).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="airflow-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="airflow-metrics"]').findAll('.airflow-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="airflow-empty"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('dataPages.airflowEmptyTitle')
    expect(wrapper.text()).toContain('dataPages.airflowBackendApSched')
  })

  it('loads and renders the redesigned DAG workbench', async () => {
    const wrapper = doMount()
    await flushPromises()

    expect(api.listDags).toHaveBeenCalled()
    expect(wrapper.find('[data-test="airflow-workbench"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="airflow-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="airflow-mobile-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="airflow-metrics"]').findAll('.airflow-metric')).toHaveLength(4)
    expect(wrapper.text()).toContain('dag_stock_hist')
    expect(wrapper.text()).toContain('dag_bond_daily')
    expect(wrapper.text()).toContain('dataPages.airflowWorkbenchKicker')
  })

  it('filters DAGs by pause state and search keyword', async () => {
    const wrapper = doMount()
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      statusFilter: 'all' | 'running' | 'paused'
      dagSearch: string
    }
    vm.statusFilter = 'paused'
    await nextTick()

    expect(wrapper.text()).not.toContain('dag_stock_hist')
    expect(wrapper.text()).toContain('dag_bond_daily')

    vm.statusFilter = 'all'
    vm.dagSearch = 'stock'
    await nextTick()

    expect(wrapper.text()).toContain('dag_stock_hist')
    expect(wrapper.text()).not.toContain('dag_bond_daily')
  })

  it('runs DAG actions and opens recent run history', async () => {
    const vm = doMount().vm as unknown as {
      triggerDag: (dagId: string) => Promise<void>
      togglePause: (dagId: string, isPaused: boolean) => Promise<void>
      viewRuns: (dag: AirflowDAG) => Promise<void>
      dagRuns: AirflowDAGRun[]
    }
    await flushPromises()

    await vm.triggerDag('dag_stock_hist')
    await vm.togglePause('dag_bond_daily', false)
    await vm.viewRuns(fixtures.dags[0])

    expect(api.triggerDag).toHaveBeenCalledWith('dag_stock_hist')
    expect(api.togglePause).toHaveBeenCalledWith('dag_bond_daily', false)
    expect(api.listDagRuns).toHaveBeenCalledWith('dag_stock_hist')
    expect(vm.dagRuns).toHaveLength(1)
    expect(ElMessage.success).toHaveBeenCalledWith('dataPages.airflowDagTriggered')
    expect(ElMessage.success).toHaveBeenCalledWith('dataPages.airflowResumeSucceeded')
  })
})
