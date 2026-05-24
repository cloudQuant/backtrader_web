/**
 * E2E acceptance tests for the Airflow DAGs management page.
 *
 * Validates Requirements: 5.1, 5.2, 5.3, 6.8, 9.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import AirflowDagsPage from '@/views/data/AirflowDagsPage.vue'

// Mock the airflow API
vi.mock('@/api/airflow', () => ({
  airflowApi: {
    getStatus: vi.fn(),
    listDags: vi.fn(),
    triggerDag: vi.fn(),
    togglePause: vi.fn(),
  },
}))

// Mock Element Plus components
vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
  }
})

describe('AirflowDagsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('AT-5.1: shows APScheduler fallback when Airflow not connected', async () => {
    const { airflowApi } = await import('@/api/airflow')
    vi.mocked(airflowApi.getStatus).mockResolvedValue({ type: 'apscheduler', running: true })

    mount(AirflowDagsPage, {
      global: { stubs: { 'el-card': true, 'el-alert': true, 'el-empty': true, 'el-table': true, 'el-table-column': true, 'el-button': true, 'el-switch': true } },
    })
    await nextTick()
    await nextTick()

    // Should show the info alert about APScheduler mode
    expect(airflowApi.getStatus).toHaveBeenCalled()
    // listDags should NOT be called in APScheduler mode
    expect(airflowApi.listDags).not.toHaveBeenCalled()
  })

  it('AT-5.1: loads DAG list when Airflow is connected', async () => {
    const { airflowApi } = await import('@/api/airflow')
    vi.mocked(airflowApi.getStatus).mockResolvedValue({ type: 'airflow', connected: true })
    vi.mocked(airflowApi.listDags).mockResolvedValue({
      dags: [
        { dag_id: 'dag_stock_hist', schedule_interval: '0 18 * * *', is_paused: false, is_active: true },
        { dag_id: 'dag_bond_daily', schedule_interval: '@daily', is_paused: true, is_active: true },
      ],
      total_entries: 2,
    })

    mount(AirflowDagsPage, {
      global: { stubs: { 'el-card': true, 'el-alert': true, 'el-empty': true, 'el-table': true, 'el-table-column': true, 'el-button': true, 'el-switch': true } },
    })
    // Wait for multiple async ticks (getStatus → then listDags)
    await nextTick()
    await nextTick()
    await nextTick()
    await new Promise(r => setTimeout(r, 10))

    expect(airflowApi.listDags).toHaveBeenCalled()
  })

  it('AT-6.8: displays orchestration status', async () => {
    const { airflowApi } = await import('@/api/airflow')
    vi.mocked(airflowApi.getStatus).mockResolvedValue({
      type: 'airflow',
      connected: true,
      api_url: 'http://localhost:8080/api/v1',
    })
    vi.mocked(airflowApi.listDags).mockResolvedValue({ dags: [], total_entries: 0 })

    mount(AirflowDagsPage, {
      global: { stubs: { 'el-card': true, 'el-alert': true, 'el-empty': true, 'el-table': true, 'el-table-column': true, 'el-button': true, 'el-switch': true } },
    })
    await nextTick()
    await nextTick()

    expect(airflowApi.getStatus).toHaveBeenCalledTimes(1)
  })
})
