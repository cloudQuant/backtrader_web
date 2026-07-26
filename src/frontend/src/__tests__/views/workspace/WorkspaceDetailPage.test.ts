import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => {
    if (!params) return key
    return `${key}:${JSON.stringify(params)}`
  } }),
}))

const route = {
  params: { id: 'workspace-1' },
  meta: { workspaceType: 'research' },
}

vi.mock('vue-router', () => ({
  useRoute: () => route,
}))

const fetchWorkspace = vi.fn().mockResolvedValue(undefined)
const fetchUnits = vi.fn().mockResolvedValue(undefined)

let storeState: any

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => storeState,
}))

import WorkspaceDetailPage from '@/views/workspace/WorkspaceDetailPage.vue'
import { elStubs } from '@/test/stubs'

function buildWorkspace(overrides: Record<string, unknown> = {}) {
  return {
    id: 'workspace-1',
    user_id: 'user-1',
    name: 'Alpha Research',
    description: 'A compact research workspace.',
    workspace_type: 'research',
    settings: { data_source: { type: 'mysql' } },
    trading_config: {},
    unit_count: 3,
    completed_count: 1,
    status: 'running',
    created_at: '2026-06-20T09:30:00Z',
    updated_at: '2026-07-01T02:20:00Z',
    ...overrides,
  }
}

function buildUnit(id: string, runStatus = 'idle', overrides: Record<string, unknown> = {}) {
  return {
    id,
    workspace_id: 'workspace-1',
    group_name: 'default',
    strategy_id: null,
    strategy_name: 'Trend',
    symbol: '000001.SZ',
    symbol_name: 'Ping An',
    timeframe: '1d',
    timeframe_n: 1,
    category: 'trend',
    sort_order: 0,
    data_config: {},
    unit_settings: {},
    params: {},
    optimization_config: {},
    trading_mode: 'paper',
    gateway_config: {},
    lock_trading: false,
    lock_running: false,
    trading_instance_id: null,
    trading_snapshot: {},
    run_status: runStatus,
    run_count: 1,
    last_run_time: null,
    last_task_id: null,
    last_optimization_task_id: null,
    bar_count: null,
    metrics_snapshot: {},
    created_at: '2026-06-20T09:30:00Z',
    updated_at: '2026-07-01T02:20:00Z',
    ...overrides,
  }
}

function doMount() {
  return mount(WorkspaceDetailPage, {
    global: {
      stubs: {
        ...elStubs,
        WorkspaceDataSourceDialog: true,
        WorkspaceOptimizationTab: { template: '<div data-test="optimization-tab">optimization</div>' },
        WorkspaceReportTab: { template: '<div data-test="report-tab">report</div>' },
        TradingWorkspaceUnitsTab: { template: '<div data-test="trading-units-tab">trading units</div>' },
        WorkspaceUnitsTab: {
          emits: ['switch-tab'],
          template: '<button data-test="units-tab" @click="$emit(\'switch-tab\', \'optimization\', \'unit-1\')">units</button>',
        },
      },
    },
  })
}

describe('WorkspaceDetailPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    route.params.id = 'workspace-1'
    route.meta.workspaceType = 'research'
    storeState = {
      loading: false,
      currentWorkspace: buildWorkspace(),
      units: [
        buildUnit('unit-1', 'running'),
        buildUnit('unit-2', 'completed'),
        buildUnit('unit-3', 'idle'),
      ],
      fetchWorkspace,
      fetchUnits,
    }
  })

  it('fetches workspace detail and units from the route id', async () => {
    doMount()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(fetchWorkspace).toHaveBeenCalledWith('workspace-1')
    expect(fetchUnits).toHaveBeenCalledWith('workspace-1')
  })

  it('renders the research workspace overview and metrics', () => {
    const wrapper = doMount()
    expect(wrapper.text()).toContain('Alpha Research')
    expect(wrapper.text()).toContain('A compact research workspace.')
    expect(wrapper.findAll('.workspace-detail-metric')).toHaveLength(4)
    expect(wrapper.text()).toContain('MySQL')
    expect(wrapper.find('[data-test="trading-detail-ops"]').exists()).toBe(false)
  })

  it('renders the trading runtime overview for trading workspaces', () => {
    route.meta.workspaceType = 'trading'
    storeState.currentWorkspace = buildWorkspace({
      name: 'Live Ops',
      description: '',
      workspace_type: 'trading',
      settings: {},
      status: 'running',
    })
    storeState.units = [
      buildUnit('unit-1', 'running', {
        trading_mode: 'live',
        gateway_config: { preset_id: 'ctp-sim' },
        trading_instance_id: 'instance-1',
        trading_snapshot: {
          instance_status: 'running',
          today_pnl: 120.5,
          updated_at: '2026-07-01T03:20:00Z',
        },
      }),
      buildUnit('unit-2', 'completed', {
        trading_mode: 'paper',
        gateway_config: {},
        trading_snapshot: {
          instance_status: 'stopped',
          today_pnl: -20,
          updated_at: '2026-07-01T03:00:00Z',
        },
      }),
      buildUnit('unit-3', 'idle', {
        trading_mode: 'live',
        gateway_config: { name: 'ibkr' },
        lock_running: true,
        trading_snapshot: {
          instance_status: 'idle',
          today_pnl: 0,
          updated_at: '2026-07-01T02:50:00Z',
        },
      }),
    ]

    const wrapper = doMount()
    expect(wrapper.find('[data-test="trading-detail-ops"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="trading-units-tab"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="units-tab"]').exists()).toBe(false)
    expect(wrapper.findAll('.trading-detail-ops-card')).toHaveLength(4)
    expect(wrapper.text()).toContain('workspaceDetail.tradingOpsTitle')
    expect(wrapper.text()).toContain('workspaceDetail.tradingReadinessReview')
    expect(wrapper.text()).toContain('+100.50')
  })

  it('opens the optimization tab when a unit tab requests it', async () => {
    const wrapper = doMount()
    await wrapper.get('[data-test="units-tab"]').trigger('click')
    expect((wrapper.vm as any).activeTab).toBe('optimization')
    expect((wrapper.vm as any).showOptTab).toBe(true)
    expect(wrapper.find('[data-test="optimization-tab"]').exists()).toBe(true)
  })

  it('shows the not-found empty state', () => {
    storeState.currentWorkspace = null
    storeState.units = []
    const wrapper = doMount()
    expect(wrapper.find('.workspace-detail-empty').exists()).toBe(true)
  })
})
