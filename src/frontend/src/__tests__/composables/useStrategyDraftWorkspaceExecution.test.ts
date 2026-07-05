import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { KBStrategyDraft } from '@/api/kbChat'
import {
  useStrategyDraftWorkspaceExecution,
  type DraftWorkspaceExecutionState,
  type StrategyDraftWorkspaceExecutionApi,
  type StrategyDraftWorkspaceExecutionNotifier,
} from '@/composables/useStrategyDraftWorkspaceExecution'
import type { WorkspaceReportResponse } from '@/types/workspace'

const COMPLETE_STRATEGY_CODE = [
  'import backtrader as bt',
  '',
  'class Demo(bt.Strategy):',
  '    params = (("fast_period", 10), ("slow_period", 30))',
  '',
  '    def __init__(self):',
  '        self.fast_ma = bt.ind.SMA(self.datas[0].close, period=self.p.fast_period)',
  '        self.slow_ma = bt.ind.SMA(self.datas[0].close, period=self.p.slow_period)',
  '        self.cross = bt.ind.CrossOver(self.fast_ma, self.slow_ma)',
  '',
  '    def next(self):',
  '        if not self.position and self.cross > 0:',
  '            self.buy()',
  '        elif self.position and self.cross < 0:',
  '            self.close()',
].join('\n')

type ExposedWorkspaceExecutionVm =
  Omit<ReturnType<typeof useStrategyDraftWorkspaceExecution>, 'workspaceExecutions'>
  & { workspaceExecutions: Record<number, DraftWorkspaceExecutionState> }

const sampleDraft: KBStrategyDraft = {
  name: 'AI策略 - 双均线',
  description: '一个测试策略草案',
  code: COMPLETE_STRATEGY_CODE,
  params: {
    fast_period: { type: 'int', default: 10 },
  },
  category: 'trend',
  assumptions: ['默认使用 OHLCV 数据'],
  risk_points: ['需要验证样本外稳定性'],
  data_source: {
    type: 'csv',
    symbol: null,
    symbol_name: null,
    timeframe: '1d',
    timeframe_n: 1,
    start_date: null,
    end_date: null,
    adjustment: null,
  },
  backtest_defaults: {
    initial_cash: 100000,
    commission: 0.001,
    annual_days: 252,
    calc_method: 'simple',
    weight_mode: 'equal',
  },
  execution_plan: {
    workspace_type: 'research',
    group_name: 'AI策略 - 双均线',
    run_parallel: false,
  },
  rationale: '用于测试',
  next_steps: ['继续完善', '补参数'],
  suggested_symbol: null,
  suggested_timeframe: '1d',
}

const sampleReport: WorkspaceReportResponse = {
  workspace_id: 'ws-1',
  workspace_name: '研究工作区',
  summary: {
    total_units: 1,
    completed_units: 1,
    avg_total_return: 0.12,
    avg_annual_return: 0.18,
    avg_sharpe_ratio: 1.5,
    avg_max_drawdown: -0.08,
    avg_win_rate: 0.56,
    total_trades: 18,
    best_return_unit: null,
    worst_drawdown_unit: null,
    config: {
      calc_method: 'simple',
      annual_days: 252,
      weight_mode: 'equal',
    },
  },
  units: [],
}

function createHarness(
  api: StrategyDraftWorkspaceExecutionApi,
  notifier: StrategyDraftWorkspaceExecutionNotifier,
) {
  const Harness = defineComponent({
    setup(_, { expose }) {
      const composable = useStrategyDraftWorkspaceExecution({ api, notifier })
      expose(composable)
      return () => null
    },
  })

  return mount(Harness)
}

describe('useStrategyDraftWorkspaceExecution', () => {
  const apiMocks: StrategyDraftWorkspaceExecutionApi = {
    runUnits: vi.fn(),
    getUnitsStatus: vi.fn(),
    createReport: vi.fn(),
  }

  const notifierMocks: StrategyDraftWorkspaceExecutionNotifier = {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('records added execution with clean report state', async () => {
    const wrapper = createHarness(apiMocks, notifierMocks)
    const vm = wrapper.vm as unknown as ExposedWorkspaceExecutionVm

    vm.recordAddedExecution(1, {
      workspaceId: 'ws-1',
      workspaceName: '研究工作区',
      unitId: 'unit-1',
      strategyId: 'strategy-1',
      runStatus: 'idle',
      lastTaskId: null,
    })

    expect(vm.workspaceExecutions[1].workspaceId).toBe('ws-1')
    expect(vm.workspaceExecutions[1].report).toBeNull()
    expect(vm.workspaceExecutions[1].analysis).toBeNull()
  })

  it('auto-generates report and analysis after polling sees completed status', async () => {
    vi.mocked(apiMocks.getUnitsStatus).mockResolvedValue([
      {
        id: 'unit-1',
        run_status: 'completed',
        last_task_id: 'task-1',
      },
    ])
    vi.mocked(apiMocks.createReport).mockResolvedValue(sampleReport)

    const wrapper = createHarness(apiMocks, notifierMocks)
    const vm = wrapper.vm as unknown as ExposedWorkspaceExecutionVm

    vm.recordBacktestExecution(
      1,
      {
        workspaceId: 'ws-1',
        workspaceName: '研究工作区',
        unitId: 'unit-1',
        strategyId: 'strategy-1',
        runStatus: 'running',
        lastTaskId: 'task-1',
        report: null,
      },
      sampleDraft,
    )

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(apiMocks.getUnitsStatus).toHaveBeenCalledWith('ws-1')
    expect(apiMocks.createReport).toHaveBeenCalledWith('ws-1', {
      calc_method: 'simple',
      annual_days: 252,
      weight_mode: 'equal',
    })
    expect(vm.workspaceExecutions[1].runStatus).toBe('completed')
    expect(vm.workspaceExecutions[1].report?.workspace_id).toBe('ws-1')
    expect(vm.workspaceExecutions[1].analysis?.verdict).toContain('继续优化')
    expect(notifierMocks.success).toHaveBeenCalledWith('回测完成，报告已自动生成')
  })

  it('warns when generating report for unfinished execution', async () => {
    vi.mocked(apiMocks.getUnitsStatus).mockResolvedValue([
      {
        id: 'unit-1',
        run_status: 'running',
        last_task_id: 'task-1',
      },
    ])

    const wrapper = createHarness(apiMocks, notifierMocks)
    const vm = wrapper.vm as unknown as ReturnType<typeof useStrategyDraftWorkspaceExecution>

    vm.recordAddedExecution(1, {
      workspaceId: 'ws-1',
      workspaceName: '研究工作区',
      unitId: 'unit-1',
      strategyId: 'strategy-1',
      runStatus: 'running',
      lastTaskId: 'task-1',
    })

    await vm.generateReport(1, sampleDraft)

    expect(apiMocks.createReport).not.toHaveBeenCalled()
    expect(notifierMocks.warning).toHaveBeenCalledWith('回测尚未完成，请先刷新状态或稍后再试')
  })

  it('restores polling state and marks status unknown after automatic refresh fails', async () => {
    vi.mocked(apiMocks.getUnitsStatus).mockRejectedValue(new Error('network'))

    const wrapper = createHarness(apiMocks, notifierMocks)
    const vm = wrapper.vm as unknown as ExposedWorkspaceExecutionVm

    vm.recordBacktestExecution(
      1,
      {
        workspaceId: 'ws-1',
        workspaceName: '研究工作区',
        unitId: 'unit-1',
        strategyId: 'strategy-1',
        runStatus: 'running',
        lastTaskId: 'task-1',
        report: null,
      },
      sampleDraft,
    )

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(vm.workspaceExecutions[1].runStatus).toBe('status_unknown')
    expect(notifierMocks.warning).toHaveBeenCalledWith('自动刷新回测状态失败，可稍后手动刷新')
  })
})
