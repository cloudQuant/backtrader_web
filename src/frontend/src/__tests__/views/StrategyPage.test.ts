import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StrategyPage from '@/views/StrategyPage.vue'
import { stripStrategyMeta, getStrategyParamCount } from '@/constants/strategy'
import { elStubs } from '@/test/stubs'
import type { AIStrategyResearchRunRecord } from '@/api/strategy'

const strategyTemplates = vi.hoisted(() => [
  { id: 't1', name: 'SMA', category: 'trend', description: 'test', params: {} },
  ...Array.from({ length: 119 }, (_, index) => ({
    id: `tool-${index + 2}`,
    name: `Strategy Tool ${index + 2}`,
    category: 'custom',
    description: 'generated tool',
    params: {},
  })),
])
const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/stores/strategy', () => ({
  useStrategyStore: () => ({
    fetchTemplates: vi.fn().mockResolvedValue(undefined),
    fetchStrategies: vi.fn().mockResolvedValue(undefined),
    createStrategy: vi.fn().mockResolvedValue({ id: 's1' }),
    updateStrategy: vi.fn().mockResolvedValue(undefined),
    deleteStrategy: vi.fn().mockResolvedValue(undefined),
    templates: strategyTemplates,
    strategies: [],
    total: 0,
    categories: [],
  }),
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    get: vi.fn().mockResolvedValue({
      id: 's1',
      user_id: 'u1',
      name: 'AI策略',
      description: 'history strategy',
      code: 'class HistoryStrategy: pass',
      params: {},
      category: 'trend',
      created_at: '2026-06-27T00:00:00Z',
      updated_at: '2026-06-27T00:00:00Z',
    }),
    getTemplateReadme: vi.fn().mockResolvedValue({ content: '# README' }),
    getTemplateConfig: vi.fn().mockResolvedValue({}),
    listAIResearchRuns: vi.fn().mockResolvedValue({
      total: 1,
      items: [
        {
          run_id: 'history-run',
          prompt: '历史趋势策略',
          symbol: '000001.SZ',
          symbol_name: '平安银行',
          timeframe: '1d',
          timeframe_n: 1,
          status: 'achieved',
          achieved: true,
          target_sharpe: 1,
          quality_gates: {
            target_sharpe: 1,
            min_total_trades: 1,
            out_of_sample_validation: true,
            out_of_sample_ratio: 0.25,
          },
          min_total_trades: 1,
          max_iterations: 3,
          iteration_count: 2,
          best_iteration: 2,
          best_sharpe: 1.2,
          best_quality_score: 100,
          best_quality_gate_evaluations: [
            { key: 'sharpe', label: 'Sharpe', actual: 1.2, target: 1, direction: 'min', passed: true, score: 1 },
          ],
          best_metrics: { sharpe_ratio: 1.2 },
          asset_specs: {
            '000001.SZ': {
              symbol: '000001.SZ',
              multiplier: 1,
              commission_rate: 0.0008,
              source: 'local_stock_defaults',
            },
          },
          backtest_environment: {
            initial_cash: 100000,
            commission: 0.0008,
            annual_days: 252,
            asset_spec_source: 'local_stock_defaults',
          },
          best_strategy_id: 's1',
          best_strategy_name: 'AI策略',
          research_workspace_id: 'research-ws',
          seed_strategy_id: null,
          continued_from_run_id: null,
          paper_workspace_id: null,
          paper_workspace_name: null,
          paper_unit_id: null,
          paper_trading_started: false,
          paper_monitoring_plan: [],
          next_actions: ['继续跟踪模拟交易'],
          started_at: '2026-06-27T00:00:00Z',
          completed_at: '2026-06-27T00:01:00Z',
          iterations: [],
        },
      ],
    }),
    runAIResearchLoop: vi.fn().mockResolvedValue({
      run_id: 'run-1',
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      best_iteration: 1,
      best_quality_score: 100,
      best_quality_gate_evaluations: [
        { key: 'sharpe', label: 'Sharpe', actual: 1.2, target: 1, direction: 'min', passed: true, score: 1 },
        {
          key: 'total_trades',
          label: 'Total trades',
          actual: 4,
          target: 1,
          direction: 'min',
          passed: true,
          score: 1,
        },
      ],
      best_diagnostics: { summary: '第 1 轮已通过全部质量门槛，可进入模拟交易候选。', promotion_ready: true },
      best_metrics: { sharpe_ratio: 1.2 },
      paper_monitoring_plan: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min' as const,
          threshold: 0.6,
          action: '低于阈值时暂停放大资金',
        },
      ],
      research_workspace: {
        id: 'research-ws',
        user_id: 'u1',
        name: 'AI投研',
        description: null,
        workspace_type: 'research',
        settings: {},
        trading_config: {},
        unit_count: 1,
        completed_count: 1,
        status: 'completed',
        created_at: '2026-06-27T00:00:00Z',
        updated_at: '2026-06-27T00:00:00Z',
      },
      iterations: [
        {
          iteration: 1,
          strategy: { id: 's1', name: 'AI策略', description: 'd', code: 'code', category: 'trend', params: {} },
          unit: {
            id: 'u1',
            workspace_id: 'research-ws',
            group_name: 'AI策略',
            strategy_id: 's1',
            strategy_name: 'AI策略',
            symbol: '000001.SZ',
            symbol_name: '平安银行',
            timeframe: '1d',
            timeframe_n: 1,
            category: 'trend',
            sort_order: 1,
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
            run_status: 'completed',
            run_count: 1,
            last_run_time: null,
            last_task_id: 'task-1',
            last_optimization_task_id: null,
            bar_count: 100,
            metrics_snapshot: { sharpe_ratio: 1.2 },
            created_at: '2026-06-27T00:00:00Z',
            updated_at: '2026-06-27T00:00:00Z',
          },
          run_result: { unit_id: 'u1', task_id: 'task-1', status: 'completed' },
          unit_status: { id: 'u1', run_status: 'completed', metrics_snapshot: { sharpe_ratio: 1.2 } },
          metrics: { sharpe_ratio: 1.2 },
          sharpe_ratio: 1.2,
          total_trades: 4,
          validation_status: 'passed',
          validation_window: {
            train_start: '2024-01-01',
            train_end: '2024-01-15',
            validation_start: '2024-01-16',
            validation_end: '2024-01-20',
          },
          validation_metrics: { sharpe_ratio: 0.92, total_trades: 3 },
          validation_gate_evaluations: [
            {
              key: 'out_of_sample_sharpe',
              label: 'Out-of-sample Sharpe',
              actual: 0.92,
              target: 0.8,
              direction: 'min',
              passed: true,
              score: 1,
            },
          ],
          validation_failures: [],
          validation_failure_reason: null,
          quality_score: 100,
          quality_gate_evaluations: [
            { key: 'sharpe', label: 'Sharpe', actual: 1.2, target: 1, direction: 'min', passed: true, score: 1 },
          ],
          passed: true,
          quality_gate_failures: [],
          diagnostics: {
            summary: '第 1 轮已通过全部质量门槛，可进入模拟交易候选。',
            iteration_progress: {
              status: 'baseline',
              previous_iteration: null,
              summary: '首轮回测作为后续自动改进的基准。',
            },
            improvement_plan: ['进入模拟交易后优先验证成交、滑点、费用和样本外收益稳定性。'],
            promotion_ready: true,
          },
          improvement_plan: ['进入模拟交易后优先验证成交、滑点、费用和样本外收益稳定性。'],
          improvement_notes: [],
          next_actions: ['该轮已通过全部验收门槛，可作为进入模拟交易的候选版本。'],
        },
      ],
      best_strategy: { id: 's1', name: 'AI策略', description: 'd', code: 'code', category: 'trend', params: {} },
      paper_trading: null,
      next_actions: ['策略已通过验收，可手动进入模拟交易或安排样本外验证。'],
      run_record: {
        run_id: 'run-1',
        prompt: '生成一个趋势策略',
        symbol: '000001.SZ',
        symbol_name: '',
        timeframe: '1d',
        timeframe_n: 1,
        status: 'achieved',
        achieved: true,
        target_sharpe: 1,
        quality_gates: {
          target_sharpe: 1,
          min_total_trades: 1,
          out_of_sample_validation: true,
          out_of_sample_ratio: 0.25,
          min_out_of_sample_sharpe: 0.8,
          min_out_of_sample_trades: 2,
        },
        min_total_trades: 1,
        max_iterations: 3,
        iteration_count: 1,
        best_iteration: 1,
        best_sharpe: 1.2,
        best_quality_score: 100,
        best_quality_gate_evaluations: [
          { key: 'sharpe', label: 'Sharpe', actual: 1.2, target: 1, direction: 'min', passed: true, score: 1 },
        ],
        best_diagnostics: { summary: '第 1 轮已通过全部质量门槛，可进入模拟交易候选。', promotion_ready: true },
        best_metrics: { sharpe_ratio: 1.2 },
        asset_specs: {
          '000001.SZ': {
            symbol: '000001.SZ',
            multiplier: 1,
            commission_rate: 0.0008,
            source: 'local_stock_defaults',
          },
        },
        backtest_environment: {
          initial_cash: 100000,
          commission: 0.0008,
          annual_days: 252,
          asset_spec_source: 'local_stock_defaults',
        },
        best_strategy_id: 's1',
        best_strategy_name: 'AI策略',
        research_workspace_id: 'research-ws',
        seed_strategy_id: null,
        continued_from_run_id: null,
        paper_workspace_id: null,
        paper_workspace_name: null,
        paper_unit_id: null,
        paper_trading_started: false,
        paper_monitoring_plan: [],
        next_actions: ['策略已通过验收，可手动进入模拟交易或安排样本外验证。'],
        started_at: '2026-06-27T00:00:00Z',
        completed_at: '2026-06-27T00:01:00Z',
        iterations: [],
      },
      message: 'ok',
    }),
    startAIResearchPaperTrading: vi.fn().mockResolvedValue({
      workspace: {
        id: 'paper-ws',
        user_id: 'u1',
        name: 'AI模拟交易',
        description: null,
        workspace_type: 'trading',
        settings: {},
        trading_config: {},
        unit_count: 1,
        completed_count: 0,
        status: 'running',
        created_at: '2026-06-27T00:00:00Z',
        updated_at: '2026-06-27T00:00:00Z',
      },
      unit: {
        id: 'paper-unit',
        workspace_id: 'paper-ws',
        group_name: 'AI策略',
        strategy_id: 's1',
        strategy_name: 'AI策略',
        symbol: '000001.SZ',
        symbol_name: '平安银行',
        timeframe: '1d',
        timeframe_n: 1,
        category: 'trend',
        sort_order: 1,
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
        run_status: 'running',
        run_count: 1,
        last_run_time: null,
        last_task_id: 'paper-task',
        last_optimization_task_id: null,
        bar_count: null,
        metrics_snapshot: {},
        created_at: '2026-06-27T00:00:00Z',
        updated_at: '2026-06-27T00:00:00Z',
      },
      run_result: { unit_id: 'paper-unit', task_id: 'paper-task', status: 'running' },
      started: true,
      handoff: {
        run_id: 'history-run',
        paper_task_id: 'paper-task',
        backtest_environment: {
          initial_cash: 100000,
          commission: 0.002,
          multiplier: 300,
          margin: 0.1,
          annual_days: 244,
          calc_method: 'simple',
          weight_mode: 'equal',
          asset_spec_source: 'local_futures_commission',
          start_date: '2024-01-01',
          end_date: '2024-12-31',
        },
        paper_monitoring_plan: [
          {
            key: 'rolling_sharpe',
            label: '模拟交易滚动 Sharpe',
            metric: 'rolling_sharpe',
            window: '30 trading days',
            direction: 'min',
            threshold: 0.6,
            action: '继续观察',
          },
        ],
      },
    }),
    reviewAIResearchPaperTrading: vi.fn().mockResolvedValue({
      run_id: 'history-run',
      research_workspace_id: 'research-ws',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      monitoring_plan: [],
      evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: 0.72,
          source: 'unit_status.metrics_snapshot',
          status: 'passed',
          passed: true,
          action: '继续观察',
        },
      ],
      ready_for_live: true,
      status: 'ready_for_live_candidate',
      reviewed_at: '2026-06-27T00:02:00Z',
      live_readiness_expires_at: '2026-07-04T00:02:00Z',
      live_readiness_checklist: [
        {
          key: 'paper_monitoring_passed',
          label: '模拟监控通过',
          status: 'passed',
          evidence: '模拟交易滚动 Sharpe 0.72 / 0.60，来源 unit_status.metrics_snapshot',
          action: '继续监控同一组指标。',
        },
        {
          key: 'human_approval_required',
          label: '人工实盘审批',
          status: 'pending_manual_confirmation',
          evidence: '模拟复核已达到实盘候选状态。',
          action: '确认账户权限和上线窗口后再切换实盘。',
        },
      ],
      pipeline: {
        current_stage: 'live_candidate',
        status: 'achieved',
        progress: 100,
        ready_for_live: true,
        live_readiness_expires_at: '2026-07-04T00:02:00Z',
        live_readiness_checklist: [
          {
            key: 'paper_monitoring_passed',
            label: '模拟监控通过',
            status: 'passed',
            evidence: '模拟交易滚动 Sharpe 0.72 / 0.60，来源 unit_status.metrics_snapshot',
            action: '继续监控同一组指标。',
          },
        ],
        steps: [],
      },
      next_actions: ['模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。'],
    }),
    buildAIResearchLiveHandoff: vi.fn().mockImplementation((
      runId: string,
      researchWorkspaceId?: string | null
    ) => Promise.resolve({
      run_id: runId,
      research_workspace_id: researchWorkspaceId || 'research-ws',
      generated_at: '2026-06-27T00:03:00Z',
      ready_for_live: true,
      status: 'ready_for_approval',
      approval_required: true,
      expires_at: '2026-07-04T00:02:00Z',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      best_strategy_id: 's1',
      best_strategy_name: 'AI策略',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      timeframe: '1d',
      timeframe_n: 1,
      target_sharpe: 1,
      best_sharpe: 1.2,
      best_metrics: { sharpe_ratio: 1.2, total_trades: 5 },
      asset_specs: {
        '000001.SZ': {
          symbol: '000001.SZ',
          multiplier: 1,
          commission_rate: 0.0008,
        },
      },
      backtest_environment: {
        initial_cash: 100000,
        commission: 0.0008,
      },
      paper_review_status: 'ready_for_live_candidate',
      paper_reviewed_at: '2026-06-27T00:02:00Z',
      paper_review_evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: 0.72,
          source: 'unit_status.metrics_snapshot',
          status: 'passed',
          passed: true,
          action: '继续观察',
        },
      ],
      paper_monitoring_plan: [],
      live_readiness_checklist: [
        {
          key: 'paper_monitoring_passed',
          label: '模拟监控通过',
          status: 'passed',
          evidence: '模拟交易滚动 Sharpe 0.72 / 0.60，来源 unit_status.metrics_snapshot',
          action: '继续监控同一组指标。',
        },
        {
          key: 'human_approval_required',
          label: '人工实盘审批',
          status: 'pending_manual_confirmation',
          evidence: '模拟复核已达到实盘候选状态。',
          action: '确认账户权限和上线窗口后再切换实盘。',
        },
      ],
      approvals_required: [
        {
          key: 'human_approval_required',
          label: '人工实盘审批',
          status: 'pending_manual_confirmation',
          evidence: '模拟复核已达到实盘候选状态。',
          action: '确认账户权限和上线窗口后再切换实盘。',
        },
      ],
      deployment_blockers: [],
      handoff: {
        gateway_config: {
          api_key: '***',
          params: { secret_key: '***', exchange: 'sim' },
        },
      },
      pipeline: {
        current_stage: 'live_handoff',
        status: 'ready_for_approval',
        progress: 100,
        ready_for_live: true,
        live_handoff_status: 'ready_for_approval',
        live_handoff_ready_for_live: true,
        live_handoff_approval_required: true,
        live_handoff_blocker_count: 0,
        steps: [{ key: 'live_handoff', label: '实盘交接', status: 'running' }],
      },
      next_actions: ['提交人工实盘审批，审批通过后再切换实盘账户。'],
    })),
    approveAIResearchLiveHandoff: vi.fn().mockImplementation((
      runId: string,
      payload: { decision: 'approved' | 'rejected' },
      researchWorkspaceId?: string | null
    ) => Promise.resolve({
      run_id: runId,
      research_workspace_id: researchWorkspaceId || 'research-ws',
      generated_at: '2026-06-27T00:04:00Z',
      ready_for_live: true,
      status: payload.decision === 'approved' ? 'approved_for_live' : 'approval_rejected',
      approval_required: true,
      expires_at: '2026-07-04T00:02:00Z',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      best_strategy_id: 's1',
      best_strategy_name: 'AI策略',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      timeframe: '1d',
      timeframe_n: 1,
      target_sharpe: 1,
      best_sharpe: 1.2,
      best_metrics: { sharpe_ratio: 1.2, total_trades: 5 },
      asset_specs: {
        '000001.SZ': {
          symbol: '000001.SZ',
          multiplier: 1,
          commission_rate: 0.0008,
        },
      },
      backtest_environment: {
        initial_cash: 100000,
        commission: 0.0008,
      },
      paper_review_status: 'ready_for_live_candidate',
      paper_reviewed_at: '2026-06-27T00:02:00Z',
      paper_review_evaluations: [],
      paper_monitoring_plan: [],
      live_readiness_checklist: [],
      approvals_required: [],
      deployment_blockers: [],
      approval_status: payload.decision,
      approval: {
        run_id: runId,
        research_workspace_id: researchWorkspaceId || 'research-ws',
        decision: payload.decision,
        approved: payload.decision === 'approved',
        decided_at: '2026-06-27T00:04:00Z',
        decided_by: 'web',
        comment: payload.decision === 'approved' ? '前端人工审批通过' : '前端人工驳回',
        account_confirmed: payload.decision === 'approved',
        risk_limit_confirmed: payload.decision === 'approved',
        deployment_window: payload.decision === 'approved' ? '人工审批通过后执行' : null,
        handoff_status_at_decision: 'ready_for_approval',
        blockers: [],
      },
      handoff: {
        gateway_config: {
          api_key: '***',
          params: { secret_key: '***', exchange: 'sim' },
        },
      },
      pipeline: {
        current_stage: 'live_handoff',
        status: payload.decision === 'approved' ? 'approved_for_live' : 'approval_rejected',
        progress: 100,
        ready_for_live: true,
        live_handoff_status: payload.decision === 'approved' ? 'approved_for_live' : 'approval_rejected',
        live_handoff_approval_status: payload.decision,
        live_handoff_approved: payload.decision === 'approved',
        live_handoff_approved_at: payload.decision === 'approved' ? '2026-06-27T00:04:00Z' : null,
        live_handoff_rejected_at: payload.decision === 'rejected' ? '2026-06-27T00:04:00Z' : null,
        steps: [
          {
            key: 'live_handoff',
            label: '实盘交接',
            status: payload.decision === 'approved' ? 'completed' : 'failed',
          },
        ],
      },
      next_actions: payload.decision === 'approved'
        ? ['实盘交接包已通过人工审批，可在上线窗口内执行实盘切换前检查。']
        : ['实盘交接包已被人工驳回，需处理审批意见后重新进入模拟复核或继续投研。'],
    })),
    prepareAIResearchLiveTrading: vi.fn().mockImplementation((
      runId: string,
      payload: {
        research_workspace_id?: string | null
        trading_workspace_id?: string | null
        live_workspace_name?: string | null
        gateway_config?: Record<string, unknown>
      }
    ) => Promise.resolve({
      workspace: {
        id: payload.trading_workspace_id || 'live-ws',
        user_id: 'u1',
        name: payload.live_workspace_name || 'AI实盘准备',
        description: null,
        workspace_type: 'trading',
        settings: {},
        trading_config: {},
        unit_count: 1,
        completed_count: 0,
        status: 'idle',
        created_at: '2026-06-27T00:05:00Z',
        updated_at: '2026-06-27T00:05:00Z',
      },
      unit: {
        id: 'live-unit',
        workspace_id: payload.trading_workspace_id || 'live-ws',
        group_name: 'AI策略',
        strategy_id: 's1',
        strategy_name: 'AI策略',
        symbol: '000001.SZ',
        symbol_name: '平安银行',
        timeframe: '1d',
        timeframe_n: 1,
        category: 'trend',
        sort_order: 1,
        data_config: { ai_research_run_id: runId },
        unit_settings: {},
        params: {},
        optimization_config: {},
        trading_mode: 'live',
        gateway_config: payload.gateway_config || {},
        lock_trading: true,
        lock_running: true,
        trading_instance_id: null,
        trading_snapshot: {},
        run_status: 'idle',
        run_count: 0,
        last_run_time: null,
        last_task_id: null,
        last_optimization_task_id: null,
        bar_count: null,
        metrics_snapshot: {},
        created_at: '2026-06-27T00:05:00Z',
        updated_at: '2026-06-27T00:05:00Z',
      },
      prepared: true,
      handoff: {
        run_id: runId,
        research_workspace_id: payload.research_workspace_id || 'research-ws',
        live_workspace_id: payload.trading_workspace_id || 'live-ws',
        live_workspace_name: payload.live_workspace_name || 'AI实盘准备',
        live_unit_id: 'live-unit',
        live_unit_locked: true,
        live_trading_prepared_at: '2026-06-27T00:05:00Z',
      },
      next_actions: [
        '已创建锁定的实盘交易单元，需人工核对网关凭据、账户权限和风控限额后再解锁运行。',
        '实盘单元 live-unit 当前默认锁定交易/运行，不会自动下单。',
      ],
    })),
  },
}))

vi.mock('@/components/common/MonacoEditor.vue', () => ({
  default: { template: '<div />' },
}))

describe('StrategyPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(StrategyPage, { global: { stubs: elStubs } })

  it('mounts without error', async () => {
    const wrapper = doMount()
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('阶段 质量达标')
  })

  it('getCategoryLabel returns correct labels', () => {
    const vm = doMount().vm as any
    expect(vm.getCategoryLabel('trend')).toBe('趋势')
    expect(vm.getCategoryLabel('mean_reversion')).toBe('均值回归')
    expect(vm.getCategoryLabel('volatility')).toBe('波动率')
    expect(vm.getCategoryLabel('unknown')).toBe('unknown')
  })

  it('getCategoryType returns correct types', () => {
    const vm = doMount().vm as any
    // trend maps to '' in source, but '' || 'info' = 'info' in JS
    expect(vm.getCategoryType('trend')).toBe('info')
    expect(vm.getCategoryType('mean_reversion')).toBe('success')
    expect(vm.getCategoryType('volatility')).toBe('warning')
    expect(vm.getCategoryType('unknown')).toBe('info')
  })

  it('stripStrategyMeta strips after pipe', () => {
    expect(stripStrategyMeta('hello | world')).toBe('hello')
    expect(stripStrategyMeta('no pipe')).toBe('no pipe')
    expect(stripStrategyMeta(undefined)).toBe('')
  })

  it('getStrategyParamCount returns param count', () => {
    expect(getStrategyParamCount({ a: 1, b: 2 })).toBe(2)
    expect(getStrategyParamCount({})).toBe(0)
    expect(getStrategyParamCount(undefined)).toBe(0)
  })

  it('filteredTemplates returns all when no filter', () => {
    const vm = doMount().vm as any
    expect(vm.filteredTemplates.length).toBe(120)
    expect(vm.displayedTemplates.length).toBe(120)
  })

  it('filteredTemplates filters by category', () => {
    const vm = doMount().vm as any
    vm.categoryFilter = 'nonexistent'
    expect(vm.filteredTemplates.length).toBe(0)
    vm.categoryFilter = 'trend'
    expect(vm.filteredTemplates.length).toBe(1)
  })

  it('filteredTemplates filters by keyword', () => {
    const vm = doMount().vm as any
    vm.searchKeyword = 'SMA'
    expect(vm.filteredTemplates.length).toBe(1)
    vm.searchKeyword = 'nonexistent'
    expect(vm.filteredTemplates.length).toBe(0)
  })

  it('openTemplateDetail loads readme', async () => {
    const vm = doMount().vm as any
    await vm.openTemplateDetail({ id: 't1', name: 'SMA', params: {}, description: 'test', category: 'trend' })
    expect(vm.detailVisible).toBe(true)
    expect(vm.readmeContent).toBe('# README')
  })

  it('goBacktest navigates', () => {
    const vm = doMount().vm as any
    vm.detailVisible = true
    vm.goBacktest({ id: 't1' })
    expect(vm.detailVisible).toBe(false)
  })

  it('showCreateDialog resets form', () => {
    const vm = doMount().vm as any
    vm.showCreateDialog()
    expect(vm.dialogVisible).toBe(true)
    expect(vm.isEdit).toBe(false)
  })

  it('editStrategy populates form', () => {
    const vm = doMount().vm as any
    vm.editStrategy({ id: 's1', name: 'My Strat', description: 'desc', code: 'code', category: 'custom' })
    expect(vm.dialogVisible).toBe(true)
    expect(vm.isEdit).toBe(true)
    expect(vm.editingId).toBe('s1')
  })

  it('viewStrategy sets current strategy', () => {
    const vm = doMount().vm as any
    const s = { id: 's1', name: 'test', code: 'code' }
    vm.viewStrategy(s)
    expect(vm.viewDialogVisible).toBe(true)
    expect(vm.currentStrategy).toEqual(s)
  })

  it('useTemplate populates form from template', () => {
    const vm = doMount().vm as any
    vm.useTemplate({ id: 't1', name: 'SMA', description: 'desc | meta', code: 'code', category: 'trend', params: {} })
    expect(vm.dialogVisible).toBe(true)
    expect(vm.form.name).toBe('SMA (副本)')
    expect(vm.form.code).toBe('code')
  })

  it('shows latest running AI research diagnostics in task progress', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchTaskId = 'task-diagnostics'
    vm.aiResearchTaskStage = 'improving'
    vm.aiResearchTaskProgress = 55
    vm.aiResearchTaskLatestIteration = {
      iteration: 2,
      sharpe_ratio: 0.42,
      total_trades: 1,
      failure_reason: 'Sharpe 0.420 below target 1.000',
      quality_gate_failures: ['Only 1 trades, below minimum 5'],
      diagnostics: {
        summary: '第 2 轮未达标，系统将扩大信号覆盖并收紧风险。',
        weaknesses: ['有效交易样本数不足'],
        improvement_plan: ['放宽入场过滤以增加有效交易', '降低单笔风险预算'],
      },
      improvement_plan: ['放宽入场过滤以增加有效交易'],
      next_actions: ['系统将基于本轮失败原因生成下一版策略。'],
    }
    await wrapper.vm.$nextTick()

    const diagnostics = wrapper.find('[data-test="ai-research-task-latest-diagnostics"]').text()
    expect(diagnostics).toContain('最近诊断')
    expect(diagnostics).toContain('第 2 轮未达标')
    expect(diagnostics).toContain('Sharpe 0.420 below target 1.000')
    expect(diagnostics).toContain('Only 1 trades, below minimum 5')
    expect(diagnostics).toContain('有效交易样本数不足')
    expect(diagnostics).toContain('改稿 放宽入场过滤以增加有效交易')
    expect(diagnostics).toContain('改稿 降低单笔风险预算')
    expect(diagnostics).toContain('下一步 系统将基于本轮失败原因生成下一版策略。')
  })

  it('runs AI research loop from form input', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'
    vm.aiResearchForm.knowledge_base_id = 'kb-quant'
    vm.aiResearchForm.thinking_mode = true
    vm.aiResearchForm.use_max_drawdown_limit = true
    vm.aiResearchForm.max_drawdown_limit = 12
    vm.aiResearchForm.use_min_total_return = true
    vm.aiResearchForm.min_total_return = 8
    vm.aiResearchForm.out_of_sample_ratio_pct = 25
    vm.aiResearchForm.use_min_out_of_sample_sharpe = true
    vm.aiResearchForm.min_out_of_sample_sharpe = 0.8
    vm.aiResearchForm.use_min_out_of_sample_trades = true
    vm.aiResearchForm.min_out_of_sample_trades = 2
    vm.aiResearchForm.backtest_timeout_seconds = 900
    vm.aiResearchForm.poll_interval_seconds = 2.5
    vm.aiResearchForm.paper_workspace_name = 'AI模拟-趋势'
    vm.aiResearchForm.trading_workspace_id = 'paper-ws-existing'
    vm.aiResearchForm.gateway_config_json = '{"name":"paper_gateway","params":{"exchange":"sim"}}'
    vm.aiResearchForm.live_workspace_name = 'AI实盘-趋势'
    vm.aiResearchForm.live_trading_workspace_id = 'live-ws-existing'
    vm.aiResearchForm.live_gateway_config_json = (
      '{"name":"ctp_live","params":{"broker_id":"9999","exchange":"sim-live"}}'
    )
    await vm.runAIResearchLoop()
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '生成一个趋势策略',
      symbol: '000001.SZ',
      knowledge_base_id: 'kb-quant',
      thinking_mode: true,
      target_sharpe: 1,
      max_drawdown_limit: 12,
      min_total_return: 8,
      min_annual_return: null,
      min_win_rate: null,
      out_of_sample_validation: true,
      out_of_sample_ratio: 0.25,
      min_out_of_sample_sharpe: 0.8,
      min_out_of_sample_trades: 2,
      backtest_timeout_seconds: 900,
      poll_interval_seconds: 2.5,
      paper_workspace_name: 'AI模拟-趋势',
      trading_workspace_id: 'paper-ws-existing',
      gateway_config: {
        name: 'paper_gateway',
        params: { exchange: 'sim' },
      },
    }))
    const researchCalls = vi.mocked(strategyApi.runAIResearchLoop).mock.calls
    expect(researchCalls[researchCalls.length - 1]?.[0]).not.toHaveProperty('commission')
    expect(vm.aiResearchResult.achieved).toBe(true)
    expect(vm.aiResearchRuns[0].run_id).toBe('run-1')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('质量分')
    expect(wrapper.text()).toContain('100.00')
    expect(wrapper.find('[data-test="ai-research-iteration-progress"]').text()).toContain('基准')
    expect(wrapper.find('[data-test="ai-research-iteration-progress"]').text()).toContain(
      '首轮回测作为后续自动改进的基准'
    )
    expect(wrapper.find('[data-test="ai-research-gate-summary"]').text()).toContain('Sharpe')
    expect(wrapper.find('[data-test="ai-research-gate-summary"]').text()).toContain('1.20 / 1.00')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('样本外验证')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('passed')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('2024-01-16')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('0.92 / 0.80')
    expect(wrapper.find('[data-test="ai-research-next-actions"]').text()).toContain('策略已通过验收')
    expect(wrapper.text()).toContain('进入模拟交易后优先验证成交、滑点、费用和样本外收益稳定性')
    const currentRuntimeEnv = wrapper.find('[data-test="ai-research-current-runtime-env"]').text()
    expect(currentRuntimeEnv).toContain('回测环境')
    expect(currentRuntimeEnv).toContain('手续费 0.000800')
    expect(currentRuntimeEnv).toContain('资产来源 local_stock_defaults')
    const bestScriptButton = wrapper.findAll('button').find(
      button => button.text().includes('查看最佳脚本')
    )
    expect(bestScriptButton).toBeTruthy()
    await bestScriptButton!.trigger('click')
    expect(vm.viewDialogVisible).toBe(true)
    expect(vm.currentStrategy.id).toBe('s1')
    const iterationScriptButton = wrapper.findAll('button').find(
      button => button.text().trim() === '查看脚本'
    )
    expect(iterationScriptButton).toBeTruthy()
    await iterationScriptButton!.trigger('click')
    expect(vm.currentStrategy.name).toBe('AI策略')
    const currentStartPaperButton = wrapper.findAll('button').find(
      button => button.text().includes('启动模拟')
    )
    expect(currentStartPaperButton).toBeTruthy()
    await currentStartPaperButton!.trigger('click')
    await flushPromises()
    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('run-1', {
      research_workspace_id: 'research-ws',
      paper_workspace_name: 'AI模拟-趋势',
      trading_workspace_id: 'paper-ws-existing',
      gateway_config: {
        name: 'paper_gateway',
        params: { exchange: 'sim' },
      },
    })
    expect(vm.aiResearchResult.paper_trading.started).toBe(true)
    expect(vm.aiResearchResult.run_record.paper_trading_started).toBe(true)
    expect(vm.aiResearchResult.run_record.paper_workspace_name).toBe('AI模拟交易')
    expect(vm.aiResearchRuns[0].run_id).toBe('run-1')
    expect(vm.aiResearchRuns[0].paper_trading_started).toBe(true)
    expect(vm.aiResearchRuns[0].paper_workspace_name).toBe('AI模拟交易')
    const currentPaperEnv = wrapper.find('[data-test="ai-research-current-paper-env"]').text()
    expect(currentPaperEnv).toContain('模拟环境')
    expect(currentPaperEnv).toContain('手续费 0.002000')
    expect(currentPaperEnv).toContain('合约乘数 300.00')
    expect(currentPaperEnv).toContain('资产来源 local_futures_commission')
    const currentReviewButton = wrapper.findAll('button').find(
      button => button.text().includes('复核模拟')
    )
    expect(currentReviewButton).toBeTruthy()
    await currentReviewButton!.trigger('click')
    await flushPromises()
    expect(strategyApi.reviewAIResearchPaperTrading).toHaveBeenCalledWith('run-1', 'research-ws')
    expect(vm.aiResearchResult.run_record.paper_review_status).toBe('ready_for_live_candidate')
    expect(vm.aiResearchRuns[0].paper_review_status).toBe('ready_for_live_candidate')
    expect(wrapper.find('[data-test="ai-research-current-paper-review"]').text()).toContain(
      '实盘候选'
    )
    expect(wrapper.find('[data-test="ai-research-current-paper-review"]').text()).toContain(
      '候选有效期'
    )
    expect(wrapper.find('[data-test="ai-research-current-live-readiness"]').text()).toContain(
      '人工实盘审批 待人工确认'
    )
    expect(strategyApi.buildAIResearchLiveHandoff).toHaveBeenCalledWith('run-1', 'research-ws')
    expect(vm.aiResearchResult.pipeline.current_stage).toBe('live_handoff')
    expect(vm.aiResearchResult.run_record.pipeline.current_stage).toBe('live_handoff')
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('live_handoff')
    const liveHandoff = wrapper.find('[data-test="ai-research-current-live-handoff"]').text()
    expect(liveHandoff).toContain('可提交审批')
    expect(liveHandoff).toContain('需要人工审批')
    expect(liveHandoff).toContain('资产规格已随交接包固化')
    expect(wrapper.find('[data-test="ai-research-current-live-handoff-approvals"]').text()).toContain(
      '人工实盘审批 待人工确认'
    )
    const approveButton = wrapper.findAll('button').find(
      button => button.text().includes('批准交接')
    )
    expect(approveButton).toBeTruthy()
    await approveButton!.trigger('click')
    await flushPromises()
    expect(strategyApi.approveAIResearchLiveHandoff).toHaveBeenCalledWith(
      'run-1',
      expect.objectContaining({
        decision: 'approved',
        account_confirmed: true,
        risk_limit_confirmed: true,
      }),
      'research-ws'
    )
    expect(wrapper.find('[data-test="ai-research-current-live-handoff"]').text()).toContain(
      '已批准实盘'
    )
    expect(wrapper.find('[data-test="ai-research-current-live-handoff-approval"]').text()).toContain(
      '已批准'
    )
    expect(vm.aiResearchResult.run_record.live_handoff.status).toBe('approved_for_live')
    expect(vm.aiResearchResult.run_record.live_handoff_approval.approved).toBe(true)
    const prepareButton = wrapper.findAll('button').find(
      button => button.text().includes('准备实盘单元')
    )
    expect(prepareButton).toBeTruthy()
    await prepareButton!.trigger('click')
    await flushPromises()
    expect(strategyApi.prepareAIResearchLiveTrading).toHaveBeenCalledWith('run-1', {
      research_workspace_id: 'research-ws',
      trading_workspace_id: 'live-ws-existing',
      live_workspace_name: 'AI实盘-趋势',
      gateway_config: {
        name: 'ctp_live',
        params: { broker_id: '9999', exchange: 'sim-live' },
      },
    })
    expect(vm.aiResearchResult.run_record.live_trading_prepared).toBe(true)
    expect(vm.aiResearchResult.run_record.live_unit_id).toBe('live-unit')
    expect(vm.aiResearchResult.run_record.pipeline.current_stage).toBe('live_trading_prepare')
    expect(vm.aiResearchResult.run_record.pipeline.steps.at(-1)?.key).toBe('live_trading_prepare')
    expect(wrapper.find('[data-test="ai-research-current-live-prepare-status"]').text()).toContain(
      'live-unit 已准备，默认锁定'
    )
    const openLiveButton = wrapper.findAll('button').find(
      button => button.text().includes('打开实盘工作区')
    )
    expect(openLiveButton).toBeTruthy()
    await openLiveButton!.trigger('click')
    expect(routerPush).toHaveBeenCalledWith({
      name: 'TradingWorkspaceDetail',
      params: { id: 'live-ws-existing' },
    })
    expect(wrapper.find('[data-test="ai-research-pipeline"]').text()).toContain('实盘交接')
    expect(wrapper.find('[data-test="ai-research-pipeline"]').text()).toContain('实盘准备')
    expect(wrapper.find('[data-test="ai-research-pipeline"]').text()).toContain('已完成')
    expect(ElMessage.success).toHaveBeenCalledWith('AI投研流程已完成')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已启动')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已满足实盘候选条件')
    expect(ElMessage.success).toHaveBeenCalledWith('实盘交接包已生成')
    expect(ElMessage.success).toHaveBeenCalledWith('实盘交接已审批通过')
    expect(ElMessage.success).toHaveBeenCalledWith('实盘交易单元已准备，默认锁定等待人工上线')
  })

  it('warns and keeps continuation available when AI research misses target', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    const baseRecord = baseResult.run_record!
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    vi.mocked(strategyApi.runAIResearchLoop).mockResolvedValueOnce({
      ...baseResult,
      status: 'max_iterations_reached',
      achieved: false,
      best_quality_score: 72,
      best_diagnostics: {
        summary: '第 1 轮未达到目标 Sharpe，需要继续改进。',
        promotion_ready: false,
        improvement_plan: ['继续降低回撤并提高收益稳定性。'],
      },
      best_metrics: { sharpe_ratio: 0.72, total_trades: 4 },
      next_actions: ['下一轮改稿应直接针对：Sharpe 0.720 below target 1.000'],
      run_record: {
        ...baseRecord,
        status: 'max_iterations_reached',
        achieved: false,
        best_sharpe: 0.72,
        best_quality_score: 72,
        best_diagnostics: {
          summary: '第 1 轮未达到目标 Sharpe，需要继续改进。',
          promotion_ready: false,
          improvement_plan: ['继续降低回撤并提高收益稳定性。'],
        },
        best_metrics: { sharpe_ratio: 0.72, total_trades: 4 },
        next_actions: ['下一轮改稿应直接针对：Sharpe 0.720 below target 1.000'],
      },
    })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'
    await vm.runAIResearchLoop()
    await wrapper.vm.$nextTick()

    expect(vm.aiResearchResult.achieved).toBe(false)
    expect(vm.aiResearchResult.status).toBe('max_iterations_reached')
    expect(vm.canContinueResearchFromCurrentRunRecord).toBe(true)
    expect(wrapper.text()).toContain('继续投研')
    expect(wrapper.find('[data-test="ai-research-next-actions"]').text()).toContain(
      '下一轮改稿应直接针对'
    )
    expect(ElMessage.warning).toHaveBeenCalledWith('AI投研未达标，已保存结果，可继续投研')
    expect(ElMessage.success).not.toHaveBeenCalledWith('AI投研流程已完成')
  })

  it('shows iteration progress regression details', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'
    await vm.runAIResearchLoop()
    const first = vm.aiResearchResult.iterations[0]
    vm.aiResearchResult = {
      ...vm.aiResearchResult,
      iterations: [
        first,
        {
          ...first,
          iteration: 2,
          sharpe_ratio: 0.6,
          total_trades: 3,
          quality_score: 60,
          metrics: { sharpe_ratio: 0.6, total_trades: 3 },
          diagnostics: {
            summary: '第 2 轮未通过质量门槛。',
            iteration_progress: {
              status: 'regressed',
              previous_iteration: 1,
              sharpe_delta: -0.6,
              quality_score_delta: -40,
              total_trades_delta: -1,
              summary: '本轮自动改稿相对上一轮退化，下一轮应回退激进改动。',
            },
            improvement_plan: ['本轮自动改稿相对上一轮退化，优先回退激进参数变化。'],
            promotion_ready: false,
          },
          improvement_plan: ['本轮自动改稿相对上一轮退化，优先回退激进参数变化。'],
          passed: false,
          failure_reason: 'Sharpe 0.600 below target 1.000',
          quality_gate_failures: ['Sharpe 0.600 below target 1.000'],
        },
      ],
    }
    await wrapper.vm.$nextTick()

    const progress = wrapper.findAll('[data-test="ai-research-iteration-progress"]')
    expect(progress).toHaveLength(2)
    expect(progress[1].text()).toContain('退化')
    expect(progress[1].text()).toContain('对比第 1 轮')
    expect(progress[1].text()).toContain('Sharpe -0.60')
    expect(progress[1].text()).toContain('质量分 -40.00')
    expect(progress[1].text()).toContain('本轮自动改稿相对上一轮退化')
  })

  it('shows initial paper monitoring review from completed AI research run', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    const monitoredPipeline = {
      current_stage: 'live_candidate',
      status: 'achieved',
      progress: 80,
      ready_for_live: false,
      paper_trading_error: null,
      steps: [
        {
          key: 'paper_review',
          label: '模拟复核',
          status: 'running',
          review_status: 'monitoring',
        },
      ],
    }
    vi.mocked(strategyApi.runAIResearchLoop).mockResolvedValueOnce({
      ...baseResult,
      pipeline: monitoredPipeline,
      run_record: {
        ...baseResult.run_record!,
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'paper-unit',
        paper_trading_started: true,
        paper_monitoring_plan: baseResult.paper_monitoring_plan,
        paper_review_status: 'monitoring',
        paper_review_ready_for_live: false,
        paper_reviewed_at: '2026-06-27T00:02:00Z',
        paper_review_evaluations: [
          {
            key: 'rolling_sharpe',
            label: '模拟交易滚动 Sharpe',
            metric: 'rolling_sharpe',
            window: '30 trading days',
            direction: 'min',
            threshold: 0.6,
            actual: null,
            source: null,
            status: 'pending',
            passed: false,
            action: '低于阈值时暂停放大资金',
          },
        ],
        paper_review_next_actions: [
          '继续收集模拟交易数据，等待以下指标形成有效样本：模拟交易滚动 Sharpe',
        ],
        pipeline: monitoredPipeline,
      },
    } as any)
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'

    await vm.runAIResearchLoop()
    await flushPromises()

    const review = wrapper.find('[data-test="ai-research-current-paper-review"]')
    expect(review.exists()).toBe(true)
    expect(review.text()).toContain('继续观察')
    expect(review.text()).toContain('模拟交易滚动 Sharpe')
    const pipeline = wrapper.find('[data-test="ai-research-pipeline"]')
    expect(pipeline.text()).toContain('AI投研流水线')
    expect(pipeline.text()).toContain('模拟复核')
    expect(pipeline.text()).toContain('进行中')
    expect(pipeline.text()).toContain('复核 继续观察')
    expect(wrapper.find('[data-test="ai-research-current-paper-review-actions"]').text()).toContain(
      '继续收集模拟交易数据'
    )
    expect(vm.aiResearchResult.run_record.paper_review_status).toBe('monitoring')
    expect(vm.aiResearchRuns[0].paper_review_status).toBe('monitoring')
  })

  it('shows paper review status and actions even when monitoring evaluations are missing', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    const missingUnitPipeline = {
      current_stage: 'paper_review',
      status: 'achieved',
      progress: 80,
      ready_for_live: false,
      paper_trading_error: null,
      steps: [
        {
          key: 'paper_review',
          label: '模拟复核',
          status: 'running',
          review_status: 'paper_unit_missing',
        },
      ],
    }
    const nextActions = [
      '未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。',
    ]
    vi.mocked(strategyApi.runAIResearchLoop).mockResolvedValueOnce({
      ...baseResult,
      pipeline: missingUnitPipeline,
      next_actions: nextActions,
      run_record: {
        ...baseResult.run_record!,
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'deleted-paper-unit',
        paper_trading_started: true,
        paper_monitoring_plan: [],
        paper_review_status: 'paper_unit_missing',
        paper_review_ready_for_live: false,
        paper_reviewed_at: '2026-06-27T00:02:00Z',
        paper_review_evaluations: [],
        paper_review_next_actions: nextActions,
        pipeline: missingUnitPipeline,
        next_actions: nextActions,
      },
    } as any)
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'

    await vm.runAIResearchLoop()
    await flushPromises()

    const review = wrapper.find('[data-test="ai-research-current-paper-review"]')
    expect(review.exists()).toBe(true)
    expect(review.text()).toContain('模拟单元缺失')
    expect(review.text()).toContain('检查模拟')
    expect(wrapper.find('[data-test="ai-research-current-paper-review-actions"]').text()).toContain(
      '未找到模拟交易单元'
    )
    expect(vm.aiResearchResult.run_record.paper_review_status).toBe('paper_unit_missing')
    expect(vm.aiResearchResult.run_record.paper_review_evaluations).toEqual([])
  })

  it('shows paper trading start failure as retryable current result', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    const failedPipeline = {
      current_stage: 'paper_trading_failed',
      status: 'achieved',
      progress: 60,
      ready_for_live: false,
      paper_trading_error: 'Failed to create paper trading unit',
      steps: [
        {
          key: 'paper_trading',
          label: '启动模拟交易',
          status: 'failed',
          error: 'Failed to create paper trading unit',
        },
      ],
    }
    vi.mocked(strategyApi.runAIResearchLoop).mockResolvedValueOnce({
      ...baseResult,
      paper_trading: null,
      pipeline: failedPipeline,
      next_actions: ['模拟交易启动错误：Failed to create paper trading unit'],
      run_record: {
        ...baseResult.run_record!,
        paper_trading_started: false,
        paper_workspace_id: null,
        paper_unit_id: null,
        pipeline: failedPipeline,
        next_actions: ['模拟交易启动错误：Failed to create paper trading unit'],
      },
    })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'

    await vm.runAIResearchLoop()
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('模拟启动失败')
    const retryPaperButton = wrapper.findAll('button').find(button => button.text().includes('重试模拟'))
    expect(retryPaperButton).toBeTruthy()
    expect(wrapper.find('[data-test="ai-research-next-actions"]').text()).toContain(
      '模拟交易启动错误：Failed to create paper trading unit'
    )
    expect(wrapper.text()).toContain('阶段 模拟启动失败')
    expect(wrapper.text()).toContain('模拟错误 Failed to create paper trading unit')
    expect(vm.aiResearchRuns[0].pipeline.paper_trading_error).toBe(
      'Failed to create paper trading unit'
    )

    const continueButton = wrapper.findAll('button').find(
      button => button.text().includes('继续改进')
    )
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()

    expect(vm.aiResearchForm.continuation_source).toBe('paper_trading_failed')
    expect(wrapper.text()).toContain('从模拟启动失败继续')
    expect(strategyApi.runAIResearchLoop).toHaveBeenLastCalledWith(expect.objectContaining({
      prompt: '生成一个趋势策略',
      symbol: '000001.SZ',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 's1',
      continue_from_run_id: 'run-1',
    }))
  })

  it('runs AI research through async task polling when task API is available', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'research-task-1',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      current_stage: 'backtesting',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      asset_specs: {
        'IF2409.CFE': {
          symbol: 'IF2409.CFE',
          source: 'task_exchange_specs',
          multiplier: 300,
          margin_rate: 0.1,
          commission_rate: 0.000023,
        },
      },
      backtest_environment: {
        initial_cash: 100000,
        commission: 0.000023,
        multiplier: 300,
        margin: 0.1,
        asset_spec_source: 'task_exchange_specs',
      },
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: '000001.SZ',
        timeframe: '1d',
        timeframe_n: 1,
        gateway_config: {
          name: 'paper_gateway',
          params: {
            exchange: 'sim',
            mode: 'paper',
          },
        },
      },
      message: 'submitted',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'research-task-1',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      run_id: 'run-1',
      current_stage: 'paper_trading',
      progress: 100,
      current_iteration: 1,
      iteration_count: 1,
      max_iterations: 3,
      asset_specs: {
        'IF2409.CFE': {
          symbol: 'IF2409.CFE',
          source: 'task_exchange_specs',
          multiplier: 300,
          margin_rate: 0.1,
          commission_rate: 0.000023,
        },
      },
      backtest_environment: {
        initial_cash: 100000,
        commission: 0.000023,
        multiplier: 300,
        margin: 0.1,
        asset_spec_source: 'task_exchange_specs',
      },
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: '000001.SZ',
        timeframe: '1d',
        timeframe_n: 1,
        gateway_config: {
          name: 'paper_gateway',
          params: {
            exchange: 'sim',
            mode: 'paper',
          },
        },
      },
      latest_iteration: {
        iteration: 1,
        sharpe_ratio: 0.8,
        total_trades: 4,
        diagnostics: {
          iteration_progress: {
            status: 'regressed',
            previous_iteration: 0,
            sharpe_delta: -0.2,
            summary: '自动改稿退化。',
          },
        },
      },
      pipeline: {
        current_stage: 'paper_trading',
        status: 'running',
        progress: 100,
        ready_for_live: false,
        steps: [
          { key: 'draft', label: '策略生成', status: 'completed' },
          {
            key: 'backtest_loop',
            label: '自动回测迭代',
            status: 'completed',
            iteration_count: 1,
            max_iterations: 3,
          },
          { key: 'quality_gate', label: '质量门槛', status: 'completed' },
          { key: 'paper_trading', label: '模拟交易', status: 'running' },
          { key: 'paper_review', label: '模拟复核', status: 'pending' },
        ],
      },
      message: 'done',
      result: baseResult,
    })
    try {
      const wrapper = doMount()
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '生成一个趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      await vm.runAIResearchLoop()

      expect((strategyApi as any).submitAIResearchTask).toHaveBeenCalledWith(expect.objectContaining({
        prompt: '生成一个趋势策略',
        symbol: '000001.SZ',
      }))
      expect((strategyApi as any).getAIResearchTask).toHaveBeenCalledWith('research-task-1')
      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
      expect(vm.aiResearchTaskId).toBe('research-task-1')
      expect(vm.aiResearchTaskStatus).toBe('completed')
      expect(vm.aiResearchTaskStage).toBe('paper_trading')
      expect(vm.aiResearchTaskProgress).toBe(100)
      expect(vm.aiResearchTaskIteration).toBe(1)
      expect(vm.aiResearchResult.achieved).toBe(true)
      const taskProgress = wrapper.find('[data-test="ai-research-task-progress"]').text()
      expect(taskProgress).toContain('最近第 1 轮')
      expect(taskProgress).toContain('退化')
      expect(taskProgress).toContain('Sharpe -0.20')
      expect(taskProgress).toContain('自动回测迭代 已完成 1/3 轮')
      expect(taskProgress).toContain('模拟交易 进行中')
      const taskRuntime = wrapper.find('[data-test="ai-research-task-runtime"]').text()
      expect(taskRuntime).toContain('运行环境')
      expect(taskRuntime).toContain('手续费 0.000023')
      expect(taskRuntime).toContain('合约乘数 300.00')
      expect(taskRuntime).toContain('保证金 0.1000')
      expect(taskRuntime).toContain('资产来源 task_exchange_specs')
      expect(taskRuntime).toContain('网关 paper_gateway')
      expect(taskRuntime).toContain('交易所 sim')
      expect(taskRuntime).toContain('模式 paper')
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('shows live trading preparation from completed async task summary', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    const livePipeline = {
      current_stage: 'live_trading_prepare',
      status: 'approved_for_live',
      progress: 100,
      ready_for_live: true,
      live_trading_prepared: true,
      live_trading_prepared_at: '2026-06-27T00:05:00Z',
      live_workspace_id: 'live-ws',
      live_unit_id: 'live-unit',
      live_unit_locked: true,
      steps: [
        { key: 'live_handoff', label: '实盘交接', status: 'completed' },
        {
          key: 'live_trading_prepare',
          label: '实盘准备',
          status: 'completed',
          live_trading_prepared: true,
          live_workspace_id: 'live-ws',
          live_unit_id: 'live-unit',
          live_unit_locked: true,
          prepared_at: '2026-06-27T00:05:00Z',
        },
      ],
    }
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'live-task-1',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      current_stage: 'live_handoff',
      progress: 92,
      current_iteration: 2,
      iteration_count: 2,
      max_iterations: 3,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      message: 'handoff',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'live-task-1',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:05:00Z',
      run_id: 'run-1',
      current_stage: 'live_trading_prepare',
      progress: 100,
      current_iteration: 2,
      iteration_count: 2,
      max_iterations: 3,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      live_workspace_id: 'live-ws',
      live_unit_id: 'live-unit',
      live_trading_prepared: true,
      live_trading_prepared_at: '2026-06-27T00:05:00Z',
      pipeline: livePipeline,
      message: 'live prepared',
      result: {
        ...baseResult,
        pipeline: livePipeline,
        run_record: {
          ...baseResult.run_record!,
          live_workspace_id: 'live-ws',
          live_workspace_name: 'AI实盘准备',
          live_unit_id: 'live-unit',
          live_trading_prepared: true,
          live_trading_prepared_at: '2026-06-27T00:05:00Z',
          pipeline: livePipeline,
        },
      },
    })
    try {
      const wrapper = doMount()
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '生成一个趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      await vm.runAIResearchLoop()

      expect((strategyApi as any).getAIResearchTask).toHaveBeenCalledWith('live-task-1')
      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
      expect(vm.aiResearchTaskStage).toBe('live_trading_prepare')
      expect(vm.aiResearchResult.run_record.live_trading_prepared).toBe(true)
      const taskProgress = wrapper.find('[data-test="ai-research-task-progress"]').text()
      expect(taskProgress).toContain('阶段 实盘准备')
      expect(taskProgress).toContain('模拟已启动')
      expect(taskProgress).toContain('模拟单元 paper-unit')
      expect(taskProgress).toContain('实盘已准备')
      expect(taskProgress).toContain('实盘单元 live-unit')
      expect(taskProgress).toContain('实盘准备 已完成')
      expect(taskProgress).toContain('live prepared')
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('restores live trading preparation from task pipeline summary when history lookup fails', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const livePipeline = {
      current_stage: 'live_trading_prepare',
      status: 'approved_for_live',
      progress: 100,
      ready_for_live: true,
      live_trading_prepared: true,
      live_workspace_id: 'live-ws',
      live_unit_id: 'live-unit',
      live_unit_locked: true,
      steps: [
        { key: 'live_handoff', label: '实盘交接', status: 'completed' },
        {
          key: 'live_trading_prepare',
          label: '实盘准备',
          status: 'completed',
          live_trading_prepared: true,
          live_workspace_id: 'live-ws',
          live_unit_id: 'live-unit',
          live_unit_locked: true,
          prepared_at: '2026-06-27T00:05:00Z',
        },
      ],
    }
    const approval = {
      run_id: 'pipeline-summary-run',
      research_workspace_id: 'research-ws',
      decision: 'approved',
      approved: true,
      decided_at: '2026-06-27T00:04:00Z',
      decided_by: 'risk-manager',
      comment: '批准小资金实盘验证',
      account_confirmed: true,
      risk_limit_confirmed: true,
      deployment_window: '2026-06-28 09:30',
      handoff_status_at_decision: 'ready_for_approval',
      blockers: [],
    }
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'pipeline-summary-task',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      research_workspace_id: 'research-ws',
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: 'IF2409.CFE',
        symbol_name: '沪深300股指期货',
        timeframe: '1h',
        timeframe_n: 1,
        target_sharpe: 1,
      },
      current_stage: 'live_handoff',
      progress: 95,
      current_iteration: 2,
      iteration_count: 2,
      max_iterations: 3,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      message: 'handoff',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'pipeline-summary-task',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:05:00Z',
      run_id: 'pipeline-summary-run',
      research_workspace_id: 'research-ws',
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: 'IF2409.CFE',
        symbol_name: '沪深300股指期货',
        timeframe: '1h',
        timeframe_n: 1,
        target_sharpe: 1,
      },
      current_stage: 'live_trading_prepare',
      progress: 100,
      current_iteration: 2,
      iteration_count: 2,
      max_iterations: 3,
      run_status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      best_iteration: 2,
      best_sharpe: 1.09,
      best_quality_score: 100,
      best_metrics: { sharpe_ratio: 1.09, total_trades: 12 },
      best_strategy_id: 'pipeline-strategy',
      best_strategy_name: 'Pipeline恢复策略',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_review_status: 'ready_for_live_candidate',
      paper_review_ready_for_live: true,
      live_handoff_approval: approval,
      live_handoff: {
        run_id: 'pipeline-summary-run',
        research_workspace_id: 'research-ws',
        generated_at: '2026-06-27T00:03:00Z',
        ready_for_live: true,
        status: 'approved_for_live',
        approval_required: true,
        expires_at: '2026-07-04T00:03:00Z',
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'paper-unit',
        best_strategy_id: 'pipeline-strategy',
        best_strategy_name: 'Pipeline恢复策略',
        symbol: 'IF2409.CFE',
        symbol_name: '沪深300股指期货',
        timeframe: '1h',
        timeframe_n: 1,
        target_sharpe: 1,
        best_sharpe: 1.09,
        best_metrics: { sharpe_ratio: 1.09, total_trades: 12 },
        asset_specs: {},
        backtest_environment: {},
        paper_review_status: 'ready_for_live_candidate',
        paper_reviewed_at: '2026-06-27T00:02:00Z',
        paper_review_evaluations: [],
        paper_monitoring_plan: [],
        live_readiness_checklist: [],
        approvals_required: [],
        deployment_blockers: [],
        approval_status: 'approved',
        approval,
        handoff: {},
        pipeline: livePipeline,
        next_actions: ['实盘交易单元已准备，默认锁定等待人工上线。'],
      },
      pipeline: livePipeline,
      next_actions: ['实盘交易单元已准备，默认锁定等待人工上线。'],
      latest_iteration: {
        iteration: 2,
        strategy_snapshot: {
          id: 'pipeline-strategy',
          name: 'Pipeline恢复策略',
          description: '从任务 pipeline 摘要恢复的策略脚本',
          code: 'import backtrader as bt\nclass PipelineRestoredStrategy(bt.Strategy):\n    pass\n',
          params: {},
          category: 'trend',
          created_at: '2026-06-27T00:00:10Z',
          updated_at: '2026-06-27T00:05:00Z',
        },
        metrics: { sharpe_ratio: 1.09, total_trades: 12 },
        sharpe_ratio: 1.09,
        total_trades: 12,
        passed: true,
      },
      message: 'live prepared',
    })
    try {
      const wrapper = doMount()
      await flushPromises()
      vi.mocked(strategyApi.listAIResearchRuns).mockRejectedValueOnce(new Error('history unavailable'))
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '生成一个趋势策略'
      vm.aiResearchForm.symbol = 'IF2409.CFE'
      await vm.runAIResearchLoop()

      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
      expect(vm.aiResearchResult.run_id).toBe('pipeline-summary-run')
      expect(vm.aiResearchResult.run_record.live_workspace_id).toBe('live-ws')
      expect(vm.aiResearchResult.run_record.live_unit_id).toBe('live-unit')
      expect(vm.aiResearchResult.run_record.live_trading_prepared).toBe(true)
      expect(vm.aiResearchResult.run_record.live_trading_prepared_at).toBe(
        '2026-06-27T00:05:00Z'
      )
      expect(vm.aiResearchResult.run_record.live_handoff.status).toBe('approved_for_live')
      expect(wrapper.find('[data-test="ai-research-current-live-prepare-status"]').text()).toContain(
        'live-unit 已准备'
      )
      expect(wrapper.find('[data-test="ai-research-current-live-prepare-actions"]').exists()).toBe(
        false
      )
      const taskProgress = wrapper.find('[data-test="ai-research-task-progress"]').text()
      expect(taskProgress).toContain('实盘已准备')
      expect(taskProgress).toContain('实盘单元 live-unit')
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('shows timeout-cancelled backtest from async task summary', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    vi.mocked(strategyApi.listAIResearchRuns).mockClear()
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({ total: 0, items: [] })
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'timeout-research-task',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: '000001.SZ',
        target_sharpe: 1,
        min_total_trades: 1,
        max_iterations: 3,
        backtest_timeout_seconds: 600,
      },
      current_stage: 'backtesting',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'running',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'timeout-research-task',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:10:00Z',
      run_id: 'timeout-run',
      research_workspace_id: 'research-ws',
      current_stage: 'backtest_timeout',
      run_status: 'timeout',
      achieved: false,
      progress: 100,
      current_iteration: 1,
      iteration_count: 1,
      max_iterations: 3,
      best_iteration: 1,
      best_sharpe: 0,
      best_quality_score: 0,
      best_metrics: { sharpe_ratio: 0, total_trades: 0 },
      cancelled_backtest_task_id: 'timeout-backtest-task',
      child_cancelled: true,
      latest_iteration: {
        iteration: 1,
        strategy: {
          id: 'strategy-timeout',
          name: '超时策略',
          description: 'timeout strategy from task summary',
          code: 'class TimeoutStrategy: pass',
          params: { fast_period: 10 },
          category: 'trend',
          created_at: '2026-06-27T00:00:00Z',
          updated_at: '2026-06-27T00:00:00Z',
        },
        unit: {
          id: 'unit-timeout',
          workspace_id: 'research-ws',
          group_name: '超时策略',
          strategy_id: 'strategy-timeout',
          strategy_name: '超时策略',
          symbol: '000001.SZ',
          symbol_name: '平安银行',
          timeframe: '1d',
          timeframe_n: 1,
          category: 'trend',
          run_status: 'timeout',
          last_task_id: 'timeout-backtest-task',
        },
        run_result: {
          unit_id: 'unit-timeout',
          task_id: 'timeout-backtest-task',
          status: 'timeout',
        },
        sharpe_ratio: 0,
        total_trades: 0,
        unit_status: {
          id: 'unit-timeout',
          run_status: 'timeout',
          last_task_id: 'timeout-backtest-task',
          metrics_snapshot: { sharpe_ratio: 0, total_trades: 0 },
          run_count: 1,
          trading_mode: 'paper',
          trading_snapshot: {
            backtest_timeout_task_id: 'timeout-backtest-task',
            backtest_timeout_cancel_requested: true,
          },
        },
      },
      pipeline: {
        current_stage: 'backtest_timeout',
        status: 'timeout',
        progress: 100,
        ready_for_live: false,
        steps: [
          { key: 'draft', label: '策略生成', status: 'completed' },
          { key: 'backtest_loop', label: '自动回测迭代', status: 'failed' },
        ],
      },
      next_actions: ['回测等待超时，可提高 backtest_timeout_seconds 后继续投研。'],
      message: 'Backtest timed out',
    })
    try {
      const wrapper = doMount()
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '生成一个趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      await vm.runAIResearchLoop()
      await wrapper.vm.$nextTick()

      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
      expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 100)
      expect(vm.aiResearchTaskStatus).toBe('completed')
      expect(vm.aiResearchTaskStage).toBe('backtest_timeout')
      expect(vm.aiResearchResult.status).toBe('timeout')
      expect(vm.aiResearchCancelledBacktestTaskId).toBe('timeout-backtest-task')
      expect(vm.canContinueResearchFromCurrentRunRecord).toBe(true)
      expect(vm.aiResearchResult.iterations[0].strategy.id).toBe('strategy-timeout')
      expect(vm.aiResearchResult.iterations[0].strategy.code).toContain('TimeoutStrategy')
      expect(vm.aiResearchResult.iterations[0].unit.id).toBe('unit-timeout')
      expect(vm.aiResearchResult.iterations[0].run_result.task_id).toBe('timeout-backtest-task')
      expect(vm.aiResearchResult.iterations[0].unit_status.run_status).toBe('timeout')
      expect(vm.aiResearchResult.iterations[0].unit_status.last_task_id).toBe(
        'timeout-backtest-task'
      )
      expect(
        vm.aiResearchResult.iterations[0].unit_status.trading_snapshot
          .backtest_timeout_task_id
      ).toBe('timeout-backtest-task')
      expect(wrapper.find('[data-test="ai-research-task-progress"]').text()).toContain(
        '已取消回测 timeout-backtest-task'
      )
      expect(ElMessage.warning).toHaveBeenCalledWith('AI投研回测超时，已保存结果，可继续投研')
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('restores cancelled async task result from persisted run history', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'cancelled-poll-task',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      current_stage: 'backtesting',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'submitted',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'cancelled-poll-task',
      status: 'cancelled',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      run_id: 'cancelled-poll-run',
      research_workspace_id: 'research-ws',
      current_stage: 'cancelled',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'cancelled',
    })
    try {
      const wrapper = doMount()
      await flushPromises()
      const vm = wrapper.vm as any
      vi.mocked(strategyApi.listAIResearchRuns).mockClear()
      vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
        total: 1,
        items: [
          {
            run_id: 'cancelled-poll-run',
            prompt: '轮询取消的趋势策略',
            symbol: '000001.SZ',
            symbol_name: '平安银行',
            timeframe: '1d',
            timeframe_n: 1,
            status: 'cancelled',
            achieved: false,
            target_sharpe: 1,
            quality_gates: { target_sharpe: 1, min_total_trades: 1 },
            min_total_trades: 1,
            max_iterations: 3,
            iteration_count: 0,
            best_iteration: null,
            best_sharpe: 0,
            best_quality_score: 0,
            best_quality_gate_evaluations: [],
            best_diagnostics: {
              summary: 'AI投研任务在首轮回测产生结果前取消，已保存待回测策略草案。',
              failure_categories: ['cancelled', 'draft_only'],
              promotion_ready: false,
            },
            best_metrics: {},
            best_strategy_id: 'saved-strategy-1',
            best_strategy_name: '待回测策略',
            research_workspace_id: 'research-ws',
            seed_strategy_id: null,
            continued_from_run_id: null,
            paper_workspace_id: null,
            paper_unit_id: null,
            paper_trading_started: false,
            paper_monitoring_plan: [],
            paper_handoff: {},
            paper_review_status: null,
            paper_review_ready_for_live: false,
            paper_reviewed_at: null,
            paper_review_evaluations: [],
            paper_review_next_actions: [],
            live_readiness_checklist: [],
            live_readiness_expires_at: null,
            pipeline: {
              current_stage: 'cancelled',
              status: 'cancelled',
              progress: 20,
              ready_for_live: false,
              steps: [],
            },
            next_actions: ['AI投研任务已取消，已保存当前待回测策略草案。'],
            started_at: '2026-06-27T00:00:00Z',
            completed_at: '2026-06-27T00:01:00Z',
            iterations: [],
          },
        ],
      } as any)
      vm.aiResearchForm.prompt = '轮询取消的趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      await vm.runAIResearchLoop()

      expect((strategyApi as any).getAIResearchTask).toHaveBeenCalledWith('cancelled-poll-task')
      expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 100)
      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
      expect(vm.aiResearchResult.run_id).toBe('cancelled-poll-run')
      expect(vm.aiResearchResult.status).toBe('cancelled')
      expect(vm.aiResearchTaskStatus).toBe('cancelled')
      expect(vm.aiResearchRuns[0].run_id).toBe('cancelled-poll-run')
      expect(vm.canContinueResearchFromCurrentRunRecord).toBe(true)
      expect(ElMessage.success).toHaveBeenCalledWith('AI投研任务已取消')
      expect(ElMessage.error).not.toHaveBeenCalled()
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('restores completed async task result from persisted run history when result is missing', async () => {
    const { strategyApi } = await import('@/api/strategy')
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'research-task-without-result',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      current_stage: 'backtesting',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'submitted',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'research-task-without-result',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      run_id: 'restored-run',
      research_workspace_id: 'research-ws',
      current_stage: 'paper_trading',
      progress: 100,
      current_iteration: 1,
      iteration_count: 1,
      max_iterations: 3,
      latest_iteration: { iteration: 1, sharpe_ratio: 1.2 },
      message: 'done',
      result: null,
    })
    const restoredRecord = {
      run_id: 'restored-run',
      prompt: '恢复的趋势策略',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 1,
      best_iteration: 1,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [
        { key: 'sharpe', label: 'Sharpe', actual: 1.2, target: 1, direction: 'min', passed: true, score: 1 },
      ],
      best_metrics: { sharpe_ratio: 1.2 },
      best_strategy_id: 's1',
      best_strategy_name: 'AI策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_monitoring_plan: [],
      paper_handoff: {
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'paper-unit',
        backtest_environment: { initial_cash: 100000, commission: 0.001 },
      },
      pipeline: {
        current_stage: 'paper_trading',
        status: 'achieved',
        progress: 90,
        ready_for_live: false,
        steps: [],
      },
      next_actions: ['继续跟踪模拟交易'],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [
        {
          iteration: 1,
          strategy_id: 's1',
          strategy_name: 'AI策略',
          strategy_snapshot: {
            id: 's1',
            name: 'AI策略快照',
            description: '历史快照脚本',
            code: 'import backtrader as bt\nclass SnapshotStrategy(bt.Strategy):\n    pass\n',
            params: {},
            category: 'trend',
            created_at: '2026-06-27T00:00:00Z',
            updated_at: '2026-06-27T00:01:00Z',
          },
          unit_id: 'unit-1',
          unit_snapshot: {
            id: 'unit-1',
            workspace_id: 'research-ws',
            group_name: 'AI策略',
            strategy_id: 's1',
            strategy_name: 'AI策略',
            symbol: '000001.SZ',
            symbol_name: '平安银行',
            timeframe: '1d',
            timeframe_n: 1,
            category: 'trend',
            data_config: { symbol: '000001.SZ' },
            unit_settings: { initial_cash: 100000, commission: 0.001 },
            params: {},
            optimization_config: {},
            gateway_config: {},
            trading_mode: 'paper',
          },
          task_id: 'task-1',
          run_status: 'completed',
          metrics: { sharpe_ratio: 1.2, total_trades: 5 },
          sharpe_ratio: 1.2,
          total_trades: 5,
          quality_score: 100,
          quality_gate_evaluations: [
            { key: 'sharpe', label: 'Sharpe', actual: 1.2, target: 1, direction: 'min', passed: true, score: 1 },
          ],
          passed: true,
          quality_gate_failures: [],
          improvement_notes: ['第一轮达标'],
          next_actions: ['进入模拟交易'],
        },
      ],
    }
    try {
      const wrapper = doMount()
      await flushPromises()
      vi.mocked(strategyApi.listAIResearchRuns).mockClear()
      vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
        total: 1,
        items: [restoredRecord],
      } as any)
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '恢复的趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      await vm.runAIResearchLoop()

      expect((strategyApi as any).getAIResearchTask).toHaveBeenCalledWith('research-task-without-result')
      expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 100)
      expect(vm.aiResearchResult.run_id).toBe('restored-run')
      expect(vm.aiResearchResult.research_workspace.id).toBe('research-ws')
      expect(vm.aiResearchResult.run_record.paper_trading_started).toBe(true)
      expect(vm.aiResearchResult.paper_trading.started).toBe(true)
      expect(vm.aiResearchResult.paper_trading.workspace.id).toBe('paper-ws')
      expect(vm.aiResearchResult.paper_trading.unit.id).toBe('paper-unit')
      expect(vm.aiResearchResult.paper_trading.unit.data_config.ai_research_run_id).toBe('restored-run')
      expect(vm.aiResearchResult.paper_trading.handoff.backtest_environment.commission).toBe(0.001)
      expect(vm.aiResearchResult.iterations).toHaveLength(1)
      expect(vm.aiResearchResult.iterations[0].strategy.id).toBe('s1')
      expect(vm.aiResearchResult.iterations[0].strategy.name).toBe('AI策略快照')
      expect(vm.aiResearchResult.iterations[0].unit.id).toBe('unit-1')
      expect(vm.aiResearchResult.iterations[0].sharpe_ratio).toBe(1.2)
      expect(vm.aiResearchPaperStatusText).toBe('已启动')
      expect(vm.aiResearchCurrentPaperEnvironment[0].key).toBe('initial_cash')
      expect(vm.canOpenPaperFromCurrentResult).toBe(true)
      expect(vm.canViewBestStrategyFromCurrentResult).toBe(true)
      vi.mocked(strategyApi.get).mockClear()
      await wrapper.vm.$nextTick()
      const iterationScriptButton = wrapper.findAll('button').find(
        button => button.text().trim() === '查看脚本'
      )
      expect(iterationScriptButton).toBeTruthy()
      await iterationScriptButton!.trigger('click')
      await flushPromises()
      expect(strategyApi.get).not.toHaveBeenCalled()
      expect(vm.currentStrategy.name).toBe('AI策略快照')
      expect(vm.currentStrategy.code).toContain('SnapshotStrategy')
      await vm.viewBestStrategyFromCurrentResult()
      await flushPromises()
      expect(strategyApi.get).not.toHaveBeenCalled()
      expect(vm.viewDialogVisible).toBe(true)
      expect(vm.currentStrategy.id).toBe('s1')
      expect(vm.currentStrategy.code).toContain('SnapshotStrategy')
      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('restores paper trading context from run history without iteration snapshots', async () => {
    const wrapper = doMount()
    await flushPromises()
    const vm = wrapper.vm as any
    const restoredRecord: AIStrategyResearchRunRecord = {
      run_id: 'paper-only-run',
      prompt: '恢复模拟交易状态',
      symbol: 'IF2409.CFE',
      symbol_name: '沪深300期货',
      timeframe: '1m',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 1,
      best_iteration: 1,
      best_sharpe: 1.18,
      best_quality_score: 96,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 1.18, total_pnl: 3200 },
      asset_specs: {
        'IF2409.CFE': {
          symbol: 'IF2409.CFE',
          multiplier: 200,
          margin_rate: 0.2,
          commission_rate: 0.001,
          source: 'stale-local',
        },
      },
      backtest_environment: {
        initial_cash: 100000,
        commission: 0.001,
        multiplier: 200,
        margin: 0.2,
        asset_spec_source: 'stale-local',
      },
      best_strategy_id: 'futures-strategy',
      best_strategy_name: '期货趋势策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: 'paper-ws',
      paper_workspace_name: '期货模拟',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_monitoring_plan: [],
      paper_handoff: {
        paper_task_id: 'paper-task',
        paper_run_status: 'completed',
        asset_specs: {
          'IF2409.CFE': {
            symbol: 'IF2409.CFE',
            multiplier: 300,
            margin_rate: 0.12,
            commission_rate: 0.000023,
            source: 'exchange',
          },
        },
        backtest_environment: {
          initial_cash: 500000,
          commission: 0.000023,
          multiplier: 300,
          margin: 0.12,
          asset_spec_source: 'exchange',
        },
        gateway_config: {
          gateway_type: 'ctp',
          params: { broker_id: '9999' },
        },
      },
      paper_review_status: null,
      paper_review_ready_for_live: false,
      paper_reviewed_at: null,
      paper_review_evaluations: [],
      paper_review_next_actions: [],
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      pipeline: {
        current_stage: 'paper_trading',
        status: 'achieved',
        progress: 90,
        ready_for_live: false,
        steps: [],
      },
      next_actions: ['继续跟踪模拟交易'],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    }

    const result = vm.researchResultFromRunRecord(restoredRecord)

    expect(result.iterations).toHaveLength(0)
    expect(result.paper_trading.started).toBe(true)
    expect(result.paper_trading.workspace.id).toBe('paper-ws')
    expect(result.paper_trading.unit.id).toBe('paper-unit')
    expect(result.paper_trading.unit.strategy_id).toBe('futures-strategy')
    expect(result.paper_trading.unit.run_status).toBe('completed')
    expect(result.paper_trading.run_result.task_id).toBe('paper-task')
    expect(result.paper_trading.unit.data_config.ai_research_run_id).toBe('paper-only-run')
    expect(result.paper_trading.unit.data_config.asset_specs['IF2409.CFE'].multiplier).toBe(300)
    expect(result.paper_trading.unit.data_config.asset_specs['IF2409.CFE'].source).toBe('exchange')
    expect(result.paper_trading.unit.data_config.backtest_environment.commission).toBe(0.000023)
    expect(result.paper_trading.unit.unit_settings.commission).toBe(0.000023)
    expect(result.paper_trading.unit.unit_settings.asset_spec_source).toBe('exchange')
    expect(result.paper_trading.unit.unit_settings.asset_specs['IF2409.CFE'].margin_rate).toBe(0.12)
    expect(result.paper_trading.unit.gateway_config.params.broker_id).toBe('9999')
    expect(result.paper_trading.unit.metrics_snapshot.total_pnl).toBe(3200)
  })

  it('keeps polling long async AI research tasks beyond the old fixed attempt cap', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation(((handler: TimerHandler) => {
      if (typeof handler === 'function') handler()
      return 0
    }) as typeof window.setTimeout)
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'long-research-task',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: '000001.SZ',
        symbol_name: '平安银行',
        timeframe: '1d',
        timeframe_n: 1,
      },
      current_stage: 'backtesting',
      progress: 12,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 8,
      message: 'submitted',
    })
    let polls = 0
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockImplementation(async () => {
      polls += 1
      if (polls < 245) {
        return {
          task_id: 'long-research-task',
          status: 'running',
          submitted_at: '2026-06-27T00:00:00Z',
          request_snapshot: {
            prompt: '生成一个趋势策略',
            symbol: '000001.SZ',
            symbol_name: '平安银行',
            timeframe: '1d',
            timeframe_n: 1,
          },
          current_stage: 'backtesting',
          progress: 12 + Math.min(polls, 80) / 2,
          current_iteration: 1,
          iteration_count: 0,
          max_iterations: 8,
          message: 'running',
        }
      }
      return {
        task_id: 'long-research-task',
        status: 'completed',
        submitted_at: '2026-06-27T00:00:00Z',
        completed_at: '2026-06-27T00:30:00Z',
        run_id: 'run-1',
        request_snapshot: {
          prompt: '生成一个趋势策略',
          symbol: '000001.SZ',
          symbol_name: '平安银行',
          timeframe: '1d',
          timeframe_n: 1,
        },
        current_stage: 'paper_trading',
        progress: 100,
        current_iteration: 2,
        iteration_count: 2,
        max_iterations: 8,
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'paper-unit',
        paper_trading_started: true,
        paper_monitoring_plan: [
          {
            key: 'rolling_sharpe',
            label: '模拟交易滚动 Sharpe',
            metric: 'rolling_sharpe',
            window: '30 trading days',
            direction: 'min',
            threshold: 0.6,
            action: '继续观察',
          },
        ],
        paper_handoff: {
          paper_task_id: 'paper-task',
        },
        paper_review_status: 'monitoring',
        paper_review_ready_for_live: false,
        pipeline: {
          current_stage: 'paper_review',
          status: 'monitoring',
          progress: 96,
          ready_for_live: false,
          steps: [],
        },
        next_actions: ['继续跟踪模拟交易'],
        message: 'done',
        latest_iteration: {
          iteration: 2,
          sharpe_ratio: 1.12,
          total_trades: 18,
        },
        result: baseResult,
      }
    })
    try {
      const wrapper = doMount()
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '生成一个趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      vm.aiResearchForm.max_iterations = 8
      await vm.runAIResearchLoop()

      expect((strategyApi as any).getAIResearchTask).toHaveBeenCalledTimes(245)
      expect(vm.aiResearchTaskStatus).toBe('completed')
      expect(vm.aiResearchResult.achieved).toBe(true)
      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
      const taskProgress = wrapper.find('[data-test="ai-research-task-progress"]').text()
      expect(taskProgress).toContain('任务进度')
      expect(taskProgress).toContain('目标 生成一个趋势策略')
      expect(taskProgress).toContain('标的 000001.SZ 平安银行')
      expect(taskProgress).toContain('周期 1d')
      expect(taskProgress).toContain('阶段 模拟交易')
      expect(taskProgress).toContain('100%')
      expect(taskProgress).toContain('done')
      expect(taskProgress).toContain('模拟已启动')
      expect(taskProgress).toContain('模拟单元 paper-unit')
      expect(taskProgress).toContain('最近第 2 轮')
      expect(taskProgress).toContain('Sharpe 1.12')
      expect(taskProgress).toContain('交易 18.00')
    } finally {
      setTimeoutSpy.mockRestore()
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('restores completed async AI research result from task summary when history lookup fails', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation(((handler: TimerHandler) => {
      if (typeof handler === 'function') handler()
      return 0
    }) as typeof window.setTimeout)
    ;(strategyApi as any).submitAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'summary-task',
      status: 'running',
      submitted_at: '2026-06-27T00:00:00Z',
      research_workspace_id: 'research-ws',
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: 'IF2409.CFE',
        symbol_name: '沪深300股指期货',
        timeframe: '1h',
        timeframe_n: 1,
        start_date: '2024-01-01',
        end_date: '2024-06-30',
        target_sharpe: 1,
        min_total_trades: 4,
        initial_cash: 200000,
        commission: 0.000023,
        paper_workspace_name: '摘要模拟工作区',
      },
      current_stage: 'backtesting',
      progress: 40,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'running',
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'summary-task',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      started_at: '2026-06-27T00:00:10Z',
      completed_at: '2026-06-27T00:20:00Z',
      run_id: 'summary-run',
      research_workspace_id: 'research-ws',
      request_snapshot: {
        prompt: '生成一个趋势策略',
        symbol: 'IF2409.CFE',
        symbol_name: '沪深300股指期货',
        timeframe: '1h',
        timeframe_n: 1,
        start_date: '2024-01-01',
        end_date: '2024-06-30',
        target_sharpe: 1,
        min_total_trades: 4,
        initial_cash: 200000,
        commission: 0.000023,
        paper_workspace_name: '摘要模拟工作区',
      },
      current_stage: 'paper_review',
      progress: 100,
      current_iteration: 2,
      iteration_count: 2,
      max_iterations: 3,
      run_status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      best_iteration: 2,
      best_sharpe: 1.18,
      best_quality_score: 100,
      best_quality_gate_evaluations: [
        {
          key: 'sharpe',
          label: 'Sharpe',
          actual: 1.18,
          target: 1,
          direction: 'min',
          passed: true,
          score: 1,
        },
      ],
      best_diagnostics: {
        summary: '任务摘要诊断：已通过质量门槛',
        promotion_ready: true,
        improvement_plan: ['进入模拟交易后优先验证成交、滑点和费用。'],
      },
      best_metrics: { sharpe_ratio: 1.18, total_trades: 9 },
      best_strategy_id: 'summary-strategy',
      best_strategy_name: '摘要恢复策略',
      asset_specs: {
        'IF2409.CFE': {
          symbol: 'IF2409.CFE',
          source: 'task_summary_exchange_specs',
          multiplier: 300,
          margin_rate: 0.1,
          commission_rate: 0.000023,
        },
      },
      backtest_environment: {
        initial_cash: 200000,
        commission: 0.000023,
        annual_days: 244,
        calc_method: 'log',
        weight_mode: 'value',
        multiplier: 300,
        margin: 0.1,
        asset_spec_source: 'task_summary_exchange_specs',
      },
      paper_workspace_id: 'paper-ws',
      paper_workspace_name: '任务摘要模拟工作区',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_monitoring_plan: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          action: '继续观察',
        },
      ],
      paper_handoff: {
        paper_task_id: 'paper-task',
      },
      paper_review_status: 'ready_for_live_candidate',
      paper_review_ready_for_live: true,
      paper_reviewed_at: '2026-06-27T00:02:00Z',
      paper_review_evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: 0.82,
          source: 'unit_status.metrics_snapshot',
          status: 'passed',
          passed: true,
          action: '继续观察',
        },
      ],
      paper_review_next_actions: ['模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。'],
      live_readiness_checklist: [
        {
          key: 'paper_monitoring_passed',
          label: '模拟监控通过',
          status: 'passed',
          evidence: '模拟交易滚动 Sharpe 0.82 / 0.6，来源 unit_status.metrics_snapshot',
          action: '继续监控同一组指标。',
        },
        {
          key: 'human_approval_required',
          label: '人工实盘审批',
          status: 'pending_manual_confirmation',
          evidence: '模拟复核已达到实盘候选状态。',
          action: '确认账户权限和上线窗口后再切换实盘。',
        },
      ],
      live_readiness_expires_at: '2026-07-04T00:02:00Z',
      pipeline: {
        current_stage: 'live_candidate',
        status: 'achieved',
        progress: 100,
        ready_for_live: true,
        live_readiness_expires_at: '2026-07-04T00:02:00Z',
        steps: [],
      },
      next_actions: ['模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。'],
      latest_iteration: {
        iteration: 2,
        strategy_id: 'summary-strategy',
        strategy_name: '摘要恢复策略',
        strategy_snapshot: {
          id: 'summary-strategy',
          name: '摘要恢复策略',
          description: '从任务摘要恢复的 AI 生成策略脚本',
          code: 'import backtrader as bt\nclass SummaryRestoredStrategy(bt.Strategy):\n    pass\n',
          params: {},
          category: 'trend',
          created_at: '2026-06-27T00:00:10Z',
          updated_at: '2026-06-27T00:20:00Z',
        },
        sharpe_ratio: 1.18,
        total_trades: 9,
        metrics: { sharpe_ratio: 1.18, total_trades: 9 },
        passed: true,
      },
      message: 'summary done',
    })
    try {
      const wrapper = doMount()
      await flushPromises()
      vi.mocked(strategyApi.listAIResearchRuns).mockRejectedValueOnce(new Error('history unavailable'))
      const vm = wrapper.vm as any
      vm.aiResearchForm.prompt = '生成一个趋势策略'
      vm.aiResearchForm.symbol = '000001.SZ'
      await vm.runAIResearchLoop()

      expect(vm.aiResearchResult.run_id).toBe('summary-run')
      expect(vm.aiResearchResult.status).toBe('achieved')
      expect(vm.aiResearchResult.achieved).toBe(true)
      expect(vm.aiResearchResult.run_record.prompt).toBe('生成一个趋势策略')
      expect(vm.aiResearchResult.run_record.symbol).toBe('IF2409.CFE')
      expect(vm.aiResearchResult.run_record.symbol_name).toBe('沪深300股指期货')
      expect(vm.aiResearchResult.run_record.timeframe).toBe('1h')
      expect(vm.aiResearchResult.run_record.start_date).toBe('2024-01-01')
      expect(vm.aiResearchResult.run_record.end_date).toBe('2024-06-30')
      expect(vm.aiResearchResult.run_record.initial_cash).toBe(200000)
      expect(vm.aiResearchResult.run_record.commission).toBe(0.000023)
      expect(vm.aiResearchResult.run_record.asset_specs['IF2409.CFE'].multiplier).toBe(300)
      expect(vm.aiResearchResult.run_record.asset_specs['IF2409.CFE'].source).toBe(
        'task_summary_exchange_specs'
      )
      expect(vm.aiResearchResult.run_record.backtest_environment.commission).toBe(0.000023)
      expect(vm.aiResearchResult.run_record.backtest_environment.multiplier).toBe(300)
      expect(vm.aiResearchResult.run_record.backtest_environment.asset_spec_source).toBe(
        'task_summary_exchange_specs'
      )
      expect(vm.aiResearchResult.run_record.min_total_trades).toBe(4)
      expect(vm.aiResearchResult.run_record.paper_workspace_name).toBe('任务摘要模拟工作区')
      expect(vm.aiResearchResult.best_iteration).toBe(2)
      expect(vm.aiResearchResult.best_metrics.sharpe_ratio).toBe(1.18)
      expect(vm.aiResearchResult.best_quality_gate_evaluations[0].key).toBe('sharpe')
      expect(vm.aiResearchResult.run_record.best_quality_gate_evaluations[0].passed).toBe(true)
      expect(vm.aiResearchResult.best_diagnostics.summary).toBe('任务摘要诊断：已通过质量门槛')
      expect(vm.aiResearchResult.run_record.best_diagnostics.promotion_ready).toBe(true)
      expect(vm.aiResearchResult.run_record.best_strategy_id).toBe('summary-strategy')
      expect(vm.aiResearchResult.best_strategy.id).toBe('summary-strategy')
      expect(vm.aiResearchResult.best_strategy.code).toContain('SummaryRestoredStrategy')
      const diagnostics = wrapper.find('[data-test="ai-research-best-diagnostics"]').text()
      expect(diagnostics).toContain('投研诊断')
      expect(diagnostics).toContain('可晋级')
      expect(diagnostics).toContain('任务摘要诊断：已通过质量门槛')
      expect(diagnostics).toContain('进入模拟交易后优先验证成交、滑点和费用')
      expect(vm.aiResearchResult.paper_trading.started).toBe(true)
      expect(vm.aiResearchResult.paper_trading.workspace.name).toBe('任务摘要模拟工作区')
      expect(vm.aiResearchResult.paper_trading.unit.id).toBe('paper-unit')
      expect(vm.aiResearchResult.paper_monitoring_plan[0].key).toBe('rolling_sharpe')
      expect(vm.aiResearchResult.pipeline.current_stage).toBe('live_candidate')
      expect(vm.aiResearchResult.run_record.paper_review_status).toBe('ready_for_live_candidate')
      expect(vm.aiResearchResult.run_record.paper_review_ready_for_live).toBe(true)
      expect(vm.aiResearchResult.run_record.paper_reviewed_at).toBe('2026-06-27T00:02:00Z')
      expect(vm.aiResearchResult.run_record.paper_review_evaluations[0].status).toBe('passed')
      expect(vm.aiResearchResult.run_record.live_readiness_checklist[0].key).toBe(
        'paper_monitoring_passed'
      )
      expect(vm.aiResearchResult.run_record.live_readiness_expires_at).toBe(
        '2026-07-04T00:02:00Z'
      )
      expect(vm.aiResearchResult.next_actions).toEqual([
        '模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。',
      ])
      const taskProgress = wrapper.find('[data-test="ai-research-task-progress"]').text()
      expect(taskProgress).toContain('模拟已启动')
      expect(taskProgress).toContain('模拟单元 paper-unit')
      const runtimeEnvironment = wrapper.find('[data-test="ai-research-current-runtime-env"]').text()
      expect(runtimeEnvironment).toContain('合约乘数 300.00')
      expect(runtimeEnvironment).toContain('资产来源 task_summary_exchange_specs')
      const paperReview = wrapper.find('[data-test="ai-research-current-paper-review"]').text()
      expect(paperReview).toContain('实盘候选')
      expect(paperReview).toContain('模拟交易滚动 Sharpe 0.82 / 0.60')
      expect(paperReview).toContain('候选有效期')
      expect(wrapper.find('[data-test="ai-research-current-live-readiness"]').text()).toContain(
        '人工实盘审批 待人工确认'
      )
      vi.mocked(strategyApi.get).mockClear()
      await vm.viewBestStrategyFromCurrentResult()
      await flushPromises()
      expect(strategyApi.get).not.toHaveBeenCalled()
      expect(vm.viewDialogVisible).toBe(true)
      expect(vm.currentStrategy.code).toContain('SummaryRestoredStrategy')
    } finally {
      setTimeoutSpy.mockRestore()
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('continues research from current result when paper review fails', async () => {
    const { strategyApi } = await import('@/api/strategy')
    vi.mocked(strategyApi.reviewAIResearchPaperTrading).mockResolvedValueOnce({
      run_id: 'run-1',
      research_workspace_id: 'research-ws',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      monitoring_plan: [],
      evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: 0.2,
          source: 'unit_status.metrics_snapshot',
          status: 'failed',
          passed: false,
          action: '回到研究工作区降低过拟合并收紧风险预算',
        },
      ],
      ready_for_live: false,
      status: 'needs_research_review',
      reviewed_at: '2026-06-27T00:02:00Z',
      pipeline: {
        current_stage: 'paper_review',
        status: 'needs_review',
        progress: 80,
        ready_for_live: false,
        paper_unit_locked: true,
        paper_unit_stopped: true,
        paper_review_lock: {
          run_id: 'run-1',
          research_workspace_id: 'research-ws',
          paper_workspace_id: 'paper-ws',
          paper_unit_id: 'paper-unit',
          status: 'needs_research_review',
          reviewed_at: '2026-06-27T00:02:00Z',
          stop_results: [{ unit_id: 'paper-unit', cancelled: true }],
          next_actions: ['回到研究工作区降低过拟合并收紧风险预算'],
          reason: 'AI paper review failed; trading and running are locked until research review.',
        },
        steps: [],
      },
      next_actions: ['回到研究工作区降低过拟合并收紧风险预算'],
    })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'
    await vm.runAIResearchLoop()
    const startPaperButton = wrapper.findAll('button').find(button => button.text().includes('启动模拟'))
    expect(startPaperButton).toBeTruthy()
    await startPaperButton!.trigger('click')
    await flushPromises()
    const reviewButton = wrapper.findAll('button').find(button => button.text().includes('复核模拟'))
    expect(reviewButton).toBeTruthy()
    await reviewButton!.trigger('click')
    await flushPromises()

    expect(vm.aiResearchResult.run_record.paper_review_status).toBe('needs_research_review')
    expect(wrapper.find('[data-test="ai-research-current-paper-review"]').text()).toContain(
      '需要重新投研'
    )
    const lockPanel = wrapper.find('[data-test="ai-research-current-paper-review-lock"]')
    expect(lockPanel.text()).toContain('模拟单元保护')
    expect(lockPanel.text()).toContain('paper-unit 需要重新投研，已自动停止并锁定')
    expect(lockPanel.text()).toContain('停止结果 paper-unit 已取消')
    expect(vm.aiResearchResult.run_record.paper_handoff.paper_review_lock.paper_unit_id).toBe(
      'paper-unit'
    )
    expect(vm.aiResearchResult.next_actions[0]).toBe('回到研究工作区降低过拟合并收紧风险预算')
    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续改进'))
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()

    expect(vm.aiResearchForm.continuation_source).toBe('paper_review')
    expect(strategyApi.runAIResearchLoop).toHaveBeenLastCalledWith(expect.objectContaining({
      prompt: '生成一个趋势策略',
      symbol: '000001.SZ',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 's1',
      continue_from_run_id: 'run-1',
    }))
  })

  it('continues research from current result when live candidate review expires', async () => {
    const { strategyApi } = await import('@/api/strategy')
    vi.mocked(strategyApi.reviewAIResearchPaperTrading).mockResolvedValueOnce({
      run_id: 'run-1',
      research_workspace_id: 'research-ws',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      monitoring_plan: [],
      evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: 0.8,
          source: 'unit_status.metrics_snapshot',
          status: 'passed',
          passed: true,
          action: '继续观察',
        },
      ],
      ready_for_live: false,
      status: 'live_readiness_expired',
      reviewed_at: '2026-06-27T00:02:00Z',
      live_readiness_checklist: [
        {
          key: 'live_candidate_expired',
          label: '候选有效期',
          status: 'expired',
          evidence: '实盘候选有效期已在 2026-06-27T00:02:00Z 截止。',
          action: '重新复核模拟交易。',
        },
      ],
      live_readiness_expires_at: '2026-06-27T00:02:00Z',
      pipeline: {
        current_stage: 'paper_review',
        status: 'achieved',
        progress: 80,
        ready_for_live: false,
        steps: [],
      },
      next_actions: ['实盘候选复核已过期，重新复核模拟交易指标后再进入实盘审批。'],
    })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'
    await vm.runAIResearchLoop()
    const startPaperButton = wrapper.findAll('button').find(button => button.text().includes('启动模拟'))
    expect(startPaperButton).toBeTruthy()
    await startPaperButton!.trigger('click')
    await flushPromises()
    const reviewButton = wrapper.findAll('button').find(button => button.text().includes('复核模拟'))
    expect(reviewButton).toBeTruthy()
    await reviewButton!.trigger('click')
    await flushPromises()

    expect(vm.aiResearchResult.run_record.paper_review_status).toBe('live_readiness_expired')
    expect(wrapper.find('[data-test="ai-research-current-paper-review"]').text()).toContain(
      '重新复核'
    )
    expect(wrapper.find('[data-test="ai-research-current-live-readiness"]').text()).toContain(
      '候选有效期 已过期'
    )
    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续改进'))
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()

    expect(vm.aiResearchForm.continuation_source).toBe('paper_review')
    expect(strategyApi.runAIResearchLoop).toHaveBeenLastCalledWith(expect.objectContaining({
      prompt: '生成一个趋势策略',
      symbol: '000001.SZ',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 's1',
      continue_from_run_id: 'run-1',
    }))
  })

  it('restores an active AI research task on mount', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    ;(strategyApi as any).listAIResearchTasks = vi.fn().mockResolvedValue({
      total: 1,
      items: [
        {
          task_id: 'restore-task-1',
          status: 'running',
          submitted_at: '2026-06-27T00:00:00Z',
          request_snapshot: {
            prompt: '恢复中的趋势策略',
            symbol: 'IF2409.CFE',
            symbol_name: '沪深300股指期货',
            timeframe: '1h',
            timeframe_n: 1,
            start_date: '2024-01-01',
            end_date: '2024-06-30',
            target_sharpe: 1.3,
            min_total_trades: 5,
            max_drawdown_limit: 12,
            max_iterations: 6,
            out_of_sample_validation: true,
            out_of_sample_ratio: 0.3,
            min_out_of_sample_sharpe: 0.8,
            min_out_of_sample_trades: 2,
            initial_cash: 300000,
            commission: 0.000023,
            backtest_timeout_seconds: 1200,
            poll_interval_seconds: 3,
            paper_workspace_name: '恢复模拟工作区',
            start_paper_trading: true,
            gateway_config: {
              name: 'paper_gateway',
              params: { broker_id: '9999', exchange: 'CFFEX' },
            },
          },
          current_stage: 'backtesting',
          progress: 42,
          current_iteration: 2,
          iteration_count: 1,
          max_iterations: 6,
          current_backtest_task_id: 'bt-task-1',
          message: 'running',
        },
      ],
    })
    ;(strategyApi as any).getAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'restore-task-1',
      status: 'completed',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      run_id: 'run-1',
      current_stage: 'paper_trading',
      progress: 100,
      current_iteration: 2,
      iteration_count: 2,
      max_iterations: 3,
      current_backtest_task_id: null,
      message: 'done',
      result: baseResult,
    })
    try {
      const wrapper = doMount()
      await flushPromises()
      await flushPromises()
      const vm = wrapper.vm as any

      expect((strategyApi as any).listAIResearchTasks).toHaveBeenCalledWith(true, 5)
      expect((strategyApi as any).getAIResearchTask).toHaveBeenCalledWith('restore-task-1')
      expect(vm.aiResearchTaskId).toBe('restore-task-1')
      expect(vm.aiResearchTaskStatus).toBe('completed')
      expect(vm.aiResearchTaskStage).toBe('paper_trading')
      expect(vm.aiResearchResult.achieved).toBe(true)
      expect(vm.aiResearchTaskPollTimeoutMs(undefined, {
        task_id: 'timeout-task',
        status: 'running',
        submitted_at: '2026-06-27T00:00:00Z',
        current_stage: 'backtesting',
        progress: 0,
        iteration_count: 0,
        max_iterations: 6,
        request_snapshot: {
          backtest_timeout_seconds: 1200,
          out_of_sample_validation: true,
        },
        message: 'running',
      })).toBe(14640000)
      expect(vm.aiResearchForm.prompt).toBe('恢复中的趋势策略')
      expect(vm.aiResearchForm.symbol).toBe('IF2409.CFE')
      expect(vm.aiResearchForm.symbol_name).toBe('沪深300股指期货')
      expect(vm.aiResearchForm.timeframe).toBe('1h')
      expect(vm.aiResearchForm.start_date).toBe('2024-01-01')
      expect(vm.aiResearchForm.end_date).toBe('2024-06-30')
      expect(vm.aiResearchForm.target_sharpe).toBe(1.3)
      expect(vm.aiResearchForm.min_total_trades).toBe(5)
      expect(vm.aiResearchForm.use_max_drawdown_limit).toBe(true)
      expect(vm.aiResearchForm.max_drawdown_limit).toBe(12)
      expect(vm.aiResearchForm.max_iterations).toBe(6)
      expect(vm.aiResearchForm.out_of_sample_ratio_pct).toBe(30)
      expect(vm.aiResearchForm.use_min_out_of_sample_sharpe).toBe(true)
      expect(vm.aiResearchForm.use_min_out_of_sample_trades).toBe(true)
      expect(vm.aiResearchForm.initial_cash).toBe(300000)
      expect(vm.aiResearchForm.use_manual_commission).toBe(true)
      expect(vm.aiResearchForm.commission).toBe(0.000023)
      expect(vm.aiResearchForm.backtest_timeout_seconds).toBe(1200)
      expect(vm.aiResearchForm.poll_interval_seconds).toBe(3)
      expect(vm.aiResearchForm.paper_workspace_name).toBe('恢复模拟工作区')
      expect(JSON.parse(vm.aiResearchForm.gateway_config_json)).toEqual({
        name: 'paper_gateway',
        params: { broker_id: '9999', exchange: 'CFFEX' },
      })
    } finally {
      delete (strategyApi as any).listAIResearchTasks
      delete (strategyApi as any).getAIResearchTask
    }
  })

  it('cancels a running AI research task', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    ;(strategyApi as any).cancelAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'research-task-1',
      status: 'cancelled',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      run_id: 'cancelled-run',
      research_workspace_id: 'research-ws',
      current_stage: 'cancelled',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      cancelled_backtest_task_id: 'child-backtest-task',
      child_cancelled: true,
      message: 'cancelled',
    })
    try {
      const wrapper = doMount()
      const vm = wrapper.vm as any
      vm.aiResearchRunning = true
      vm.aiResearchTaskId = 'research-task-1'
      vi.mocked(strategyApi.listAIResearchRuns).mockClear()
      vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({ total: 0, items: [] })
      await vm.cancelAIResearchTask()
      await wrapper.vm.$nextTick()

      expect((strategyApi as any).cancelAIResearchTask).toHaveBeenCalledWith('research-task-1')
      expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 20)
      expect(vm.aiResearchRunning).toBe(false)
      expect(vm.aiResearchTaskStatus).toBe('cancelled')
      expect(vm.aiResearchTaskStage).toBe('cancelled')
      expect(vm.aiResearchCancelledBacktestTaskId).toBe('child-backtest-task')
      expect(wrapper.find('[data-test="ai-research-task-progress"]').text()).toContain(
        '已取消回测 child-backtest-task'
      )
      expect(ElMessage.success).toHaveBeenCalledWith('AI投研任务已取消，当前回测任务已同步取消')
    } finally {
      delete (strategyApi as any).cancelAIResearchTask
    }
  })

  it('restores cancelled AI research record after task cancellation', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const cancelledRecord: AIStrategyResearchRunRecord = {
      run_id: 'cancelled-run',
      prompt: '取消中的趋势策略',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'cancelled',
      achieved: false,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 0,
      best_iteration: null,
      best_sharpe: 0,
      best_quality_score: 0,
      best_quality_gate_evaluations: [],
      best_diagnostics: {
        summary: 'AI投研任务在首轮回测产生结果前取消，已保存待回测策略草案。',
        failure_categories: ['cancelled', 'draft_only'],
        promotion_ready: false,
      },
      best_metrics: {},
      asset_specs: {},
      backtest_environment: { initial_cash: 100000, commission: 0.001 },
      best_strategy_id: 'saved-strategy-1',
      best_strategy_name: '待回测策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: null,
      paper_unit_id: null,
      paper_trading_started: false,
      paper_monitoring_plan: [],
      paper_handoff: {},
      paper_review_status: null,
      paper_review_ready_for_live: false,
      paper_reviewed_at: null,
      paper_review_evaluations: [],
      paper_review_next_actions: [],
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      pipeline: {
        current_stage: 'cancelled',
        status: 'cancelled',
        progress: 20,
        ready_for_live: false,
        paper_trading_error: null,
        live_readiness_checklist: [],
        live_readiness_expires_at: null,
        steps: [
          { key: 'draft', label: '策略生成', status: 'completed' },
          {
            key: 'backtest_loop',
            label: '自动回测迭代',
            status: 'cancelled',
            iteration_count: 0,
            max_iterations: 3,
          },
        ],
      },
      next_actions: ['AI投研任务已取消，已保存当前待回测策略草案。'],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    }
    ;(strategyApi as any).cancelAIResearchTask = vi.fn().mockResolvedValue({
      task_id: 'research-task-1',
      status: 'cancelled',
      submitted_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      run_id: 'cancelled-run',
      research_workspace_id: 'research-ws',
      current_stage: 'cancelled',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'cancelled',
    })
    try {
      const wrapper = doMount()
      const vm = wrapper.vm as any
      vm.aiResearchRunning = true
      vm.aiResearchTaskId = 'research-task-1'
      vi.mocked(strategyApi.listAIResearchRuns).mockClear()
      vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
        total: 1,
        items: [cancelledRecord],
      })
      await vm.cancelAIResearchTask()
      await flushPromises()

      expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 20)
      expect(vm.aiResearchResult.run_id).toBe('cancelled-run')
      expect(vm.aiResearchResult.status).toBe('cancelled')
      expect(vm.aiResearchResult.run_record.best_strategy_id).toBe('saved-strategy-1')
      expect(vm.aiResearchRuns[0].run_id).toBe('cancelled-run')
      expect(vm.canContinueResearchFromCurrentRunRecord).toBe(true)
      await vm.continueResearchFromCurrentRunRecord()
      await flushPromises()
      expect(vm.aiResearchForm.continuation_source).toBe('research_cancelled')
      expect(strategyApi.runAIResearchLoop).toHaveBeenLastCalledWith(expect.objectContaining({
        continue_from_run_id: 'cancelled-run',
        seed_strategy_id: 'saved-strategy-1',
      }))
    } finally {
      delete (strategyApi as any).cancelAIResearchTask
    }
  })

  it('uses AI research run history to refill the form', () => {
    const vm = doMount().vm as any
    vm.useAIResearchRecord({
      run_id: 'history-run',
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1h',
      timeframe_n: 1,
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      initial_cash: 250000,
      commission: 0.000023,
      annual_days: 244,
      calc_method: 'log',
      weight_mode: 'value',
      backtest_environment: {
        initial_cash: 250000,
        commission: 0.000023,
        commission_source: 'user_override',
      },
      knowledge_base_id: 'kb-history',
      thinking_mode: true,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1.5,
      quality_gates: {
        target_sharpe: 1.5,
        min_total_trades: 3,
        max_drawdown_limit: 15,
        min_win_rate: 55,
        out_of_sample_validation: true,
        out_of_sample_ratio: 0.3,
        min_out_of_sample_sharpe: 0.9,
        min_out_of_sample_trades: 4,
      },
      min_total_trades: 3,
      max_iterations: 4,
      backtest_timeout_seconds: 1200,
      poll_interval_seconds: 3,
      iteration_count: 2,
      best_iteration: 2,
      best_sharpe: 1.6,
      best_quality_score: 98,
      best_quality_gate_evaluations: [],
      best_metrics: {},
      best_strategy_id: 'best-strategy',
      best_strategy_name: '历史最佳策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: 'paper-history-ws',
      paper_workspace_name: '历史模拟工作区',
      paper_trading_started: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [
        {
          iteration: 2,
          strategy_id: 'best-strategy',
          unit_snapshot: {
            gateway_config: {
              name: 'paper_gateway',
              params: { exchange: 'CFFEX' },
            },
          },
        },
      ],
    })
    expect(vm.aiResearchForm.prompt).toBe('历史趋势策略')
    expect(vm.aiResearchForm.symbol).toBe('600000.SH')
    expect(vm.aiResearchForm.start_date).toBe('2024-01-01')
    expect(vm.aiResearchForm.end_date).toBe('2024-12-31')
    expect(vm.aiResearchForm.initial_cash).toBe(250000)
    expect(vm.aiResearchForm.use_manual_commission).toBe(true)
    expect(vm.aiResearchForm.commission).toBe(0.000023)
    expect(vm.aiResearchForm.knowledge_base_id).toBe('kb-history')
    expect(vm.aiResearchForm.thinking_mode).toBe(true)
    expect(vm.aiResearchForm.target_sharpe).toBe(1.5)
    expect(vm.aiResearchForm.use_max_drawdown_limit).toBe(true)
    expect(vm.aiResearchForm.max_drawdown_limit).toBe(15)
    expect(vm.aiResearchForm.use_min_win_rate).toBe(true)
    expect(vm.aiResearchForm.min_win_rate).toBe(55)
    expect(vm.aiResearchForm.backtest_timeout_seconds).toBe(1200)
    expect(vm.aiResearchForm.poll_interval_seconds).toBe(3)
    expect(vm.aiResearchForm.paper_workspace_name).toBe('历史模拟工作区')
    expect(vm.aiResearchForm.trading_workspace_id).toBe('paper-history-ws')
    expect(JSON.parse(vm.aiResearchForm.gateway_config_json)).toEqual({
      name: 'paper_gateway',
      params: { exchange: 'CFFEX' },
    })
    expect(vm.aiResearchForm.out_of_sample_validation).toBe(true)
    expect(vm.aiResearchForm.out_of_sample_ratio_pct).toBe(30)
    expect(vm.aiResearchForm.use_min_out_of_sample_sharpe).toBe(true)
    expect(vm.aiResearchForm.min_out_of_sample_sharpe).toBe(0.9)
    expect(vm.aiResearchForm.use_min_out_of_sample_trades).toBe(true)
    expect(vm.aiResearchForm.min_out_of_sample_trades).toBe(4)
    expect(vm.aiResearchForm.research_workspace_id).toBe('research-ws')
    expect(vm.aiResearchForm.seed_strategy_id).toBe('best-strategy')
    expect(vm.aiResearchForm.continue_from_run_id).toBe('history-run')
  })

  it('refills gateway config from paper handoff when iteration snapshot is missing', () => {
    const vm = doMount().vm as any
    vm.aiResearchForm.trading_workspace_id = 'stale-paper-ws'
    vm.useAIResearchRecord({
      run_id: 'handoff-gateway-run',
      prompt: '历史期货策略',
      symbol: 'IF2409.CFE',
      symbol_name: '沪深300期货',
      timeframe: '1m',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 1,
      best_iteration: 1,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 1.2 },
      best_strategy_id: 'futures-strategy',
      best_strategy_name: '期货趋势策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: 'paper-ws',
      paper_workspace_name: '期货模拟',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_monitoring_plan: [],
      paper_handoff: {
        gateway_config: {
          name: 'paper_gateway',
          params: { exchange: 'CFFEX', asset_type: 'future' },
        },
      },
      paper_review_status: null,
      paper_review_ready_for_live: false,
      paper_reviewed_at: null,
      paper_review_evaluations: [],
      paper_review_next_actions: [],
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      pipeline: {
        current_stage: 'paper_trading',
        status: 'achieved',
        progress: 90,
        ready_for_live: false,
        steps: [],
      },
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    } as AIStrategyResearchRunRecord)

    expect(JSON.parse(vm.aiResearchForm.gateway_config_json)).toEqual({
      name: 'paper_gateway',
      params: { exchange: 'CFFEX', asset_type: 'future' },
    })
    expect(vm.aiResearchForm.trading_workspace_id).toBe('paper-ws')
    expect(vm.aiResearchForm.seed_strategy_id).toBe('futures-strategy')
    expect(vm.aiResearchForm.continue_from_run_id).toBe('handoff-gateway-run')
  })

  it('does not refill gateway config from redacted paper handoff credentials', () => {
    const vm = doMount().vm as any
    vm.aiResearchForm.gateway_config_json = '{"name":"previous","params":{"exchange":"old"}}'
    vm.aiResearchForm.trading_workspace_id = 'stale-paper-ws'
    vm.useAIResearchRecord({
      run_id: 'redacted-handoff-run',
      prompt: '历史期货策略',
      symbol: 'IF2409.CFE',
      symbol_name: '沪深300期货',
      timeframe: '1m',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 1,
      best_iteration: 1,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 1.2 },
      best_strategy_id: 'futures-strategy',
      best_strategy_name: '期货趋势策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: null,
      paper_workspace_name: '期货模拟',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_monitoring_plan: [],
      paper_handoff: {
        gateway_config: {
          name: 'paper_gateway',
          api_key: '***',
          params: {
            exchange: 'CFFEX',
            secret_key: '***',
            broker_id: '9999',
          },
        },
      },
      paper_review_status: null,
      paper_review_ready_for_live: false,
      paper_reviewed_at: null,
      paper_review_evaluations: [],
      paper_review_next_actions: [],
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      pipeline: {
        current_stage: 'paper_trading',
        status: 'achieved',
        progress: 90,
        ready_for_live: false,
        steps: [],
      },
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    } as AIStrategyResearchRunRecord)

    expect(vm.aiResearchForm.gateway_config_json).toBe('')
    expect(vm.aiResearchForm.trading_workspace_id).toBe('')
    expect(vm.aiResearchForm.seed_strategy_id).toBe('futures-strategy')
    expect(vm.aiResearchForm.continue_from_run_id).toBe('redacted-handoff-run')
  })

  it('continues AI research from a strategy snapshot when best strategy id is missing', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record: AIStrategyResearchRunRecord = {
      run_id: 'snapshot-run',
      prompt: '历史快照策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'max_iterations_reached',
      achieved: false,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 1,
      best_iteration: 1,
      best_sharpe: 0.8,
      best_quality_score: 80,
      best_quality_gate_evaluations: [],
      best_metrics: {},
      best_strategy_id: null,
      best_strategy_name: '历史快照策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_trading_started: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [
        {
          iteration: 1,
          strategy_snapshot: {
            name: '历史快照策略',
            code: 'class AIGeneratedStrategy(bt.Strategy):\n    pass\n',
            params: {},
            category: 'custom',
          },
          metrics: { sharpe_ratio: 0.8, total_trades: 2 },
        },
      ],
    }
    vm.aiResearchRuns = [record]
    vm.aiResearchRunsLoading = false

    await wrapper.vm.$nextTick()
    expect(vm.canContinueResearchFromRunRecord(record)).toBe(true)
    vm.useAIResearchRecord(record)
    expect(vm.aiResearchForm.seed_strategy_id).toBe('snapshot-run-strategy')
    expect(vm.aiResearchForm.continue_from_run_id).toBe('snapshot-run')

    await vm.continueResearchFromRecord(record)
    await flushPromises()
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '历史快照策略',
      symbol: '600000.SH',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 'snapshot-run-strategy',
      continue_from_run_id: 'snapshot-run',
    }))
  })

  it('uses the highest quality strategy snapshot when best iteration is missing', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record = {
      run_id: 'snapshot-run',
      prompt: '历史快照策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'max_iterations_reached',
      achieved: false,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 2,
      best_iteration: null,
      best_sharpe: 0.72,
      best_quality_score: 72,
      best_quality_gate_evaluations: [],
      best_metrics: {},
      best_strategy_id: null,
      best_strategy_name: null,
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_trading_started: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [
        {
          iteration: 1,
          strategy_id: 'snapshot-weak',
          strategy_snapshot: {
            id: 'snapshot-weak',
            name: '低质量快照策略',
            code: 'class WeakSnapshotStrategy(bt.Strategy):\n    pass\n',
            params: {},
            category: 'custom',
          },
          metrics: { sharpe_ratio: 0.2, total_trades: 1 },
          sharpe_ratio: 0.2,
          total_trades: 1,
          quality_score: 20,
          passed: false,
        },
        {
          iteration: 2,
          strategy_id: 'snapshot-strong',
          strategy_snapshot: {
            id: 'snapshot-strong',
            name: '高质量快照策略',
            code: 'class StrongSnapshotStrategy(bt.Strategy):\n    pass\n',
            params: {},
            category: 'custom',
          },
          metrics: { sharpe_ratio: 0.72, total_trades: 5 },
          sharpe_ratio: 0.72,
          total_trades: 5,
          quality_score: 72,
          passed: false,
        },
      ],
    }

    vm.useAIResearchRecord(record)
    expect(vm.aiResearchForm.seed_strategy_id).toBe('snapshot-strong')
    expect(vm.aiResearchForm.continue_from_run_id).toBe('snapshot-run')

    await vm.viewStrategyFromResearchRecord(record)
    await flushPromises()
    expect(strategyApi.get).not.toHaveBeenCalled()
    expect(vm.currentStrategy.id).toBe('snapshot-strong')
    expect(vm.currentStrategy.code).toContain('StrongSnapshotStrategy')
  })

  it('runs AI research continuation from selected history record', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record = {
      run_id: 'history-run',
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'max_iterations_reached',
      achieved: false,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 3,
      best_iteration: 3,
      best_sharpe: 0.8,
      best_quality_score: 90,
      best_quality_gate_evaluations: [],
      best_metrics: {},
      commission: 0.000023,
      backtest_environment: {
        commission: 0.000023,
        commission_source: 'asset_specs_or_default',
      },
      best_strategy_id: 'best-strategy',
      best_strategy_name: '历史最佳策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_trading_started: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    }
    vm.aiResearchRuns = [record]
    vm.aiResearchRunsLoading = false

    await wrapper.vm.$nextTick()
    expect(vm.canContinueResearchFromRunRecord(record)).toBe(true)
    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续投研'))
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('从未达标结果继续')
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 'best-strategy',
      continue_from_run_id: 'history-run',
    }))
    const call = vi.mocked(strategyApi.runAIResearchLoop).mock.calls.at(-1)?.[0]
    expect(call).not.toHaveProperty('commission')
  })

  it('continues AI research from a cancelled run with completed iterations', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record = {
      run_id: 'cancelled-run',
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'cancelled',
      achieved: false,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 1,
      best_iteration: 1,
      best_sharpe: 0.7,
      best_quality_score: 80,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 0.7 },
      best_strategy_id: 'cancelled-best-strategy',
      best_strategy_name: '取消前最佳策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_trading_started: false,
      pipeline: {
        current_stage: 'cancelled',
        status: 'cancelled',
        progress: 40,
        ready_for_live: false,
        steps: [],
      },
      next_actions: ['AI投研任务已取消，已保存取消前完成的回测迭代。'],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [{ iteration: 1 }],
    }
    vm.aiResearchRuns = [record]
    vm.aiResearchRunsLoading = false

    await wrapper.vm.$nextTick()
    expect(vm.canContinueResearchFromRunRecord(record)).toBe(true)
    expect(wrapper.text()).toContain('阶段 已取消')
    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续投研'))
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()
    expect(vm.aiResearchForm.continuation_source).toBe('research_cancelled')
    expect(wrapper.text()).toContain('从已取消任务继续')
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 'cancelled-best-strategy',
      continue_from_run_id: 'cancelled-run',
    }))
  })

  it('shows expired live candidate records as requiring paper review', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchRuns = [{
      run_id: 'expired-live-run',
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 2,
      best_iteration: 2,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 1.2 },
      best_strategy_id: 'best-strategy',
      best_strategy_name: '最佳策略',
      research_workspace_id: 'research-ws',
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_review_status: 'live_readiness_expired',
      paper_review_ready_for_live: false,
      paper_reviewed_at: '2026-06-20T00:02:00Z',
      paper_review_evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: 0.8,
          source: 'unit_status.metrics_snapshot',
          status: 'passed',
          passed: true,
          action: '继续观察',
        },
      ],
      live_readiness_checklist: [
        {
          key: 'live_candidate_expired',
          label: '候选有效期',
          status: 'expired',
          evidence: '实盘候选有效期已在 2026-06-27T00:02:00Z 截止。',
          action: '重新复核模拟交易。',
        },
      ],
      live_readiness_expires_at: '2026-06-27T00:02:00Z',
      paper_review_next_actions: ['实盘候选复核已过期，重新复核模拟交易指标后再进入实盘审批。'],
      pipeline: {
        current_stage: 'paper_review',
        status: 'achieved',
        progress: 80,
        ready_for_live: false,
        live_readiness_expires_at: '2026-06-27T00:02:00Z',
        steps: [],
      },
      next_actions: ['实盘候选复核已过期，重新复核模拟交易指标后再进入实盘审批。'],
      started_at: '2026-06-20T00:00:00Z',
      completed_at: '2026-06-20T00:01:00Z',
      iterations: [],
    }]
    vm.aiResearchRunsLoading = false

    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('复核 实盘候选已过期')
    expect(wrapper.text()).toContain('候选有效期')
    expect(wrapper.find('[data-test="ai-research-paper-review"]').text()).toContain('重新复核')
    expect(wrapper.find('[data-test="ai-research-live-readiness"]').text()).toContain(
      '候选有效期 已过期'
    )
    expect(wrapper.findAll('button').some(button => button.text().includes('复核模拟'))).toBe(true)
    expect(vm.canContinueResearchFromPaperIssue(vm.aiResearchRuns[0])).toBe(true)
    vm.useAIResearchRecord(vm.aiResearchRuns[0])
    expect(vm.aiResearchForm.continuation_source).toBe('paper_review')
    expect(vm.aiResearchForm.seed_strategy_id).toBe('best-strategy')
    expect(vm.aiResearchForm.continue_from_run_id).toBe('expired-live-run')
    expect(wrapper.findAll('button').some(button => button.text().includes('继续改进'))).toBe(true)
  })

  it('continues AI research from a saved draft after backtest submission failed', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record = {
      run_id: 'backtest-failed-run',
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'backtest_submission_failed',
      achieved: false,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 0,
      best_iteration: null,
      best_sharpe: 0,
      best_quality_score: 0,
      best_quality_gate_evaluations: [],
      best_metrics: {},
      best_strategy_id: 'saved-draft-strategy',
      best_strategy_name: '保存草案 - 待回测',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_trading_started: false,
      pipeline: {
        current_stage: 'backtest_failed',
        status: 'backtest_submission_failed',
        progress: 20,
        ready_for_live: false,
        steps: [],
      },
      next_actions: ['修复提交问题后，可从本次记录继续自动投研。'],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    }
    vm.aiResearchRuns = [record]
    vm.aiResearchRunsLoading = false

    await wrapper.vm.$nextTick()
    expect(vm.canContinueResearchFromRunRecord(record)).toBe(true)
    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续投研'))
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('从未达标结果继续')
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 'saved-draft-strategy',
      continue_from_run_id: 'backtest-failed-run',
    }))
  })

  it('marks continuation as paper-review feedback when previous paper review failed', async () => {
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.useAIResearchRecord({
      run_id: 'paper-failed-run',
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      symbol_name: '浦发银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 2,
      best_iteration: 2,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [],
      best_metrics: {},
      best_strategy_id: 'best-strategy',
      best_strategy_name: '历史最佳策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_trading_started: true,
      paper_review_status: 'needs_research_review',
      paper_review_ready_for_live: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    })

    await wrapper.vm.$nextTick()
    expect(vm.aiResearchForm.continuation_source).toBe('paper_review')
    expect(wrapper.text()).toContain('从模拟复核反馈继续')
  })

  it('starts paper trading from an achieved history record', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record = {
      run_id: 'history-run',
      prompt: '历史趋势策略',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 2,
      best_iteration: 2,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 1.2 },
      best_strategy_id: 's1',
      best_strategy_name: 'AI策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: null,
      paper_workspace_name: '历史模拟工作区',
      paper_unit_id: null,
      paper_trading_started: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    }
    const refreshedRecord: AIStrategyResearchRunRecord = {
      ...record,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      paper_handoff: {
        run_id: 'history-run',
        paper_task_id: 'paper-task',
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'paper-unit',
      },
      paper_monitoring_plan: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min' as const,
          threshold: 0.6,
          action: '继续观察',
        },
      ],
      paper_review_status: 'monitoring',
      paper_review_ready_for_live: false,
      paper_reviewed_at: '2026-06-27T00:02:00Z',
      paper_review_evaluations: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          actual: null,
          source: null,
          status: 'pending',
          passed: false,
          action: '低于阈值时暂停放大资金',
        },
      ],
      paper_review_next_actions: [
        '继续收集模拟交易数据，等待以下指标形成有效样本：模拟交易滚动 Sharpe',
      ],
      pipeline: {
        current_stage: 'paper_review',
        status: 'achieved',
        progress: 80,
        ready_for_live: false,
        steps: [],
      },
      next_actions: [
        '继续收集模拟交易数据，等待以下指标形成有效样本：模拟交易滚动 Sharpe',
      ],
    }
    vm.aiResearchRuns = [record]
    vm.aiResearchRunsLoading = false
    vi.mocked(strategyApi.listAIResearchRuns).mockClear()
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [refreshedRecord],
    })

    await wrapper.vm.$nextTick()
    expect(vm.canStartPaperFromRecord(vm.aiResearchRuns[0])).toBe(true)
    const historyScriptButton = wrapper.findAll('button').find(
      button => button.text().includes('查看脚本')
    )
    expect(historyScriptButton).toBeTruthy()
    await historyScriptButton!.trigger('click')
    await flushPromises()
    expect(strategyApi.get).toHaveBeenCalledWith('s1')
    expect(vm.viewDialogVisible).toBe(true)
    expect(vm.currentStrategy.code).toContain('HistoryStrategy')
    vm.aiResearchForm.trading_workspace_id = 'paper-ws-existing'
    vm.aiResearchForm.gateway_config_json = '{"name":"paper_gateway","params":{"exchange":"history"}}'
    await vm.startPaperFromResearchRecord(record)
    await flushPromises()

    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('history-run', {
      research_workspace_id: 'research-ws',
      trading_workspace_id: 'paper-ws-existing',
      paper_workspace_name: '历史模拟工作区',
      gateway_config: {
        name: 'paper_gateway',
        params: { exchange: 'history' },
      },
    })
    expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 20)
    expect(vm.aiResearchRuns[0].paper_trading_started).toBe(true)
    expect(vm.aiResearchRuns[0].paper_workspace_id).toBe('paper-ws')
    expect(vm.aiResearchRuns[0].paper_unit_id).toBe('paper-unit')
    expect(vm.aiResearchRuns[0].paper_handoff.paper_task_id).toBe('paper-task')
    expect(vm.aiResearchRuns[0].paper_monitoring_plan[0].key).toBe('rolling_sharpe')
    expect(vm.aiResearchRuns[0].paper_review_status).toBe('monitoring')
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('paper_review')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已启动')
  })

  it('restarts paper trading from history when the previous paper unit is missing', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    vm.aiResearchRuns = [
      {
        run_id: 'history-run',
        prompt: '历史趋势策略',
        symbol: '000001.SZ',
        symbol_name: '平安银行',
        timeframe: '1d',
        timeframe_n: 1,
        status: 'achieved',
        achieved: true,
        target_sharpe: 1,
        quality_gates: { target_sharpe: 1, min_total_trades: 1 },
        min_total_trades: 1,
        max_iterations: 3,
        iteration_count: 2,
        best_iteration: 2,
        best_sharpe: 1.2,
        best_quality_score: 100,
        best_quality_gate_evaluations: [],
        best_metrics: { sharpe_ratio: 1.2 },
        best_strategy_id: 's1',
        best_strategy_name: 'AI策略',
        research_workspace_id: 'research-ws',
        seed_strategy_id: null,
        continued_from_run_id: null,
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'deleted-paper-unit',
        paper_trading_started: true,
        paper_review_status: 'paper_unit_missing',
        paper_review_ready_for_live: false,
        paper_review_next_actions: [
          '未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。',
        ],
        next_actions: [
          '未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。',
        ],
        started_at: '2026-06-27T00:00:00Z',
        completed_at: '2026-06-27T00:01:00Z',
        iterations: [],
      },
    ]
    vm.aiResearchRunsLoading = false
    vi.mocked(strategyApi.listAIResearchRuns).mockClear()
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [
        {
          ...vm.aiResearchRuns[0],
          paper_workspace_id: 'paper-ws',
          paper_unit_id: 'paper-unit',
          paper_trading_started: true,
          paper_review_status: 'monitoring',
          paper_review_ready_for_live: false,
          paper_review_evaluations: [
            {
              key: 'rolling_sharpe',
              label: '模拟交易滚动 Sharpe',
              metric: 'rolling_sharpe',
              window: '30 trading days',
              direction: 'min' as const,
              threshold: 0.6,
              actual: null,
              source: null,
              status: 'pending',
              passed: false,
              action: '低于阈值时暂停放大资金',
            },
          ],
          paper_handoff: {
            run_id: 'history-run',
            paper_workspace_id: 'paper-ws',
            paper_unit_id: 'paper-unit',
            paper_task_id: 'paper-task',
          },
          pipeline: {
            current_stage: 'paper_review',
            status: 'achieved',
            progress: 80,
            ready_for_live: false,
            steps: [],
          },
        },
      ],
    })

    await wrapper.vm.$nextTick()
    expect(vm.canStartPaperFromRecord(vm.aiResearchRuns[0])).toBe(true)
    expect(vm.canReviewPaperFromRecord(vm.aiResearchRuns[0])).toBe(false)
    const restartButton = wrapper.findAll('button').find(button => button.text().includes('重启模拟'))
    expect(restartButton).toBeTruthy()
    await restartButton!.trigger('click')
    await flushPromises()

    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('history-run', {
      research_workspace_id: 'research-ws',
    })
    expect(vm.aiResearchRuns[0].paper_trading_started).toBe(true)
    expect(vm.aiResearchRuns[0].paper_unit_id).toBe('paper-unit')
    expect(vm.aiResearchRuns[0].paper_handoff.paper_task_id).toBe('paper-task')
  })

  it('keeps a usable local paper state when history refresh fails after restart', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    const record: AIStrategyResearchRunRecord = {
      run_id: 'history-run',
      prompt: '历史趋势策略',
      symbol: '000001.SZ',
      symbol_name: '平安银行',
      timeframe: '1d',
      timeframe_n: 1,
      status: 'achieved',
      achieved: true,
      target_sharpe: 1,
      quality_gates: { target_sharpe: 1, min_total_trades: 1 },
      min_total_trades: 1,
      max_iterations: 3,
      iteration_count: 2,
      best_iteration: 2,
      best_sharpe: 1.2,
      best_quality_score: 100,
      best_quality_gate_evaluations: [],
      best_metrics: { sharpe_ratio: 1.2 },
      best_strategy_id: 's1',
      best_strategy_name: 'AI策略',
      research_workspace_id: 'research-ws',
      seed_strategy_id: null,
      continued_from_run_id: null,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'deleted-paper-unit',
      paper_trading_started: true,
      paper_review_status: 'paper_unit_missing',
      paper_review_ready_for_live: false,
      paper_review_next_actions: [
        '未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。',
      ],
      pipeline: {
        current_stage: 'paper_review',
        status: 'achieved',
        progress: 80,
        ready_for_live: false,
        paper_trading_error: null,
        steps: [],
      },
      next_actions: [
        '未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。',
      ],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    }
    vm.aiResearchRuns = [record]
    vm.aiResearchRunsLoading = false
    vi.mocked(strategyApi.listAIResearchRuns).mockClear()
    vi.mocked(strategyApi.listAIResearchRuns).mockRejectedValueOnce(
      new Error('history unavailable')
    )

    await vm.startPaperFromResearchRecord(record)
    await flushPromises()

    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('history-run', {
      research_workspace_id: 'research-ws',
    })
    expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 20)
    const updatedRecord = vm.aiResearchRuns[0]
    expect(updatedRecord.paper_trading_started).toBe(true)
    expect(updatedRecord.paper_workspace_id).toBe('paper-ws')
    expect(updatedRecord.paper_unit_id).toBe('paper-unit')
    expect(updatedRecord.paper_review_status).toBeNull()
    expect(updatedRecord.paper_review_evaluations).toEqual([])
    expect(updatedRecord.pipeline.current_stage).toBe('paper_trading')
    expect(updatedRecord.pipeline.steps.find((step: any) => step.key === 'paper_review').status).toBe('pending')
    expect(vm.canStartPaperFromRecord(updatedRecord)).toBe(false)
    expect(vm.canReviewPaperFromRecord(updatedRecord)).toBe(true)
  })

  it('syncs current result when refreshed run record starts paper trading', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()
    const baseRecord: AIStrategyResearchRunRecord = {
      ...baseResult.run_record!,
      run_id: 'refresh-current-run',
      paper_workspace_id: null,
      paper_workspace_name: null,
      paper_unit_id: null,
      paper_trading_started: false,
      paper_handoff: {},
      paper_monitoring_plan: [],
      pipeline: {
        current_stage: 'quality_achieved',
        status: 'achieved',
        progress: 60,
        ready_for_live: false,
        steps: [],
      },
      next_actions: ['策略已通过验收，可进入模拟交易。'],
    }
    vm.aiResearchResult = {
      ...baseResult,
      run_id: 'refresh-current-run',
      paper_trading: null,
      pipeline: baseRecord.pipeline,
      next_actions: baseRecord.next_actions,
      run_record: baseRecord,
    }

    const refreshedRecord: AIStrategyResearchRunRecord = {
      ...baseRecord,
      paper_workspace_id: 'paper-ws-refresh',
      paper_workspace_name: '刷新模拟工作区',
      paper_unit_id: 'paper-unit-refresh',
      paper_trading_started: true,
      paper_monitoring_plan: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          action: '低于阈值时暂停放大资金',
        },
      ],
      paper_handoff: {
        run_id: 'refresh-current-run',
        paper_workspace_id: 'paper-ws-refresh',
        paper_workspace_name: '刷新模拟工作区',
        paper_unit_id: 'paper-unit-refresh',
        paper_task_id: 'paper-task-refresh',
        paper_run_status: 'running',
        backtest_environment: {
          initial_cash: 100000,
          commission: 0.0005,
          asset_spec_source: 'refresh_gateway',
        },
      },
      pipeline: {
        current_stage: 'paper_review',
        status: 'achieved',
        progress: 80,
        ready_for_live: false,
        steps: [
          { key: 'paper_trading', label: '模拟交易', status: 'completed' },
          { key: 'paper_review', label: '模拟复核', status: 'pending' },
        ],
      },
      next_actions: ['继续收集模拟交易数据'],
    }

    vm.applyResearchRunRecordToCurrentResult(refreshedRecord)
    await wrapper.vm.$nextTick()

    expect(vm.aiResearchResult.paper_trading.started).toBe(true)
    expect(vm.aiResearchResult.paper_trading.workspace.id).toBe('paper-ws-refresh')
    expect(vm.aiResearchResult.paper_trading.workspace.name).toBe('刷新模拟工作区')
    expect(vm.aiResearchResult.paper_trading.unit.id).toBe('paper-unit-refresh')
    expect(vm.aiResearchResult.paper_trading.run_result.task_id).toBe('paper-task-refresh')
    expect(vm.aiResearchResult.paper_trading.handoff.backtest_environment.commission).toBe(0.0005)
    expect(vm.aiResearchResult.run_record.paper_trading_started).toBe(true)
    expect(vm.aiResearchResult.pipeline.current_stage).toBe('paper_review')
    expect(vm.aiResearchResult.next_actions[0]).toBe('继续收集模拟交易数据')
    expect(vm.aiResearchResult.best_strategy.id).toBe('s1')
    expect(vm.canOpenPaperFromCurrentResult).toBe(true)
    expect(vm.canReviewPaperFromCurrentResult).toBe(true)
    expect(vm.canStartPaperFromCurrentResult).toBe(false)
  })

  it('refreshes run record when starting paper trading from history fails', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()
    vi.mocked(strategyApi.listAIResearchRuns).mockClear()
    vi.mocked(strategyApi.startAIResearchPaperTrading).mockRejectedValueOnce(
      new Error('Failed to create paper trading unit')
    )

    const record = {
      ...vm.aiResearchRuns[0],
      run_id: 'history-run',
      paper_trading_started: false,
      paper_workspace_id: null,
      paper_unit_id: null,
      pipeline: {
        current_stage: 'quality_achieved',
        status: 'achieved',
        progress: 60,
        ready_for_live: false,
        paper_trading_error: null,
        steps: [],
      },
      next_actions: [],
    }
    const failedPipeline = {
      current_stage: 'paper_trading_failed',
      status: 'achieved',
      progress: 60,
      ready_for_live: false,
      paper_trading_error: 'Failed to create paper trading unit',
      steps: [
        {
          key: 'paper_trading',
          label: '模拟交易',
          status: 'failed',
          error: 'Failed to create paper trading unit',
        },
      ],
    }
    const failedRecord = {
      ...record,
      pipeline: failedPipeline,
      next_actions: ['模拟交易启动错误：Failed to create paper trading unit'],
    }
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [failedRecord],
    })
    vm.aiResearchRuns = [record]
    vm.aiResearchResult = {
      ...baseResult,
      run_id: 'history-run',
      paper_trading: null,
      pipeline: record.pipeline,
      next_actions: [],
      run_record: record,
    }

    await vm.startPaperFromResearchRecord(record)
    await flushPromises()

    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('history-run', {
      research_workspace_id: 'research-ws',
    })
    expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 20)
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('paper_trading_failed')
    expect(vm.aiResearchResult.pipeline.current_stage).toBe('paper_trading_failed')
    expect(vm.aiResearchResult.next_actions[0]).toContain('模拟交易启动错误')
    expect(vm.canContinueResearchFromPaperIssue(vm.aiResearchRuns[0])).toBe(true)
    expect(ElMessage.error).toHaveBeenCalledWith('AI投研流程失败')
  })

  it('marks paper trading as failed when start response is not started', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    const baseResult = await strategyApi.runAIResearchLoop({ prompt: 'seed', symbol: '000001.SZ' })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()
    vi.mocked(strategyApi.listAIResearchRuns).mockClear()
    vi.mocked(strategyApi.startAIResearchPaperTrading).mockResolvedValueOnce({
      workspace: {
        id: 'paper-ws',
      },
      unit: {
        id: 'paper-unit',
      },
      run_result: { unit_id: 'paper-unit', task_id: 'paper-task', status: 'failed' },
      started: false,
      handoff: {
        run_id: 'history-run',
        paper_workspace_id: 'paper-ws',
        paper_unit_id: 'paper-unit',
        paper_task_id: 'paper-task',
        paper_run_status: 'failed',
        paper_monitoring_plan: [
          {
            key: 'rolling_sharpe',
            label: '模拟交易滚动 Sharpe',
            metric: 'rolling_sharpe',
            window: '30 trading days',
            direction: 'min',
            threshold: 0.6,
            action: '继续观察',
          },
        ],
      },
    } as any)

    const record = {
      ...vm.aiResearchRuns[0],
      run_id: 'history-run',
      paper_trading_started: false,
      paper_workspace_id: null,
      paper_unit_id: null,
      pipeline: {
        current_stage: 'quality_achieved',
        status: 'achieved',
        progress: 60,
        ready_for_live: false,
        paper_trading_error: null,
        steps: [],
      },
      next_actions: [],
    }
    const failedPipeline = {
      current_stage: 'paper_trading_failed',
      status: 'achieved',
      progress: 92,
      ready_for_live: false,
      paper_trading_error: 'Paper trading run finished with status failed',
      steps: [
        {
          key: 'paper_trading',
          label: '模拟交易',
          status: 'failed',
          error: 'Paper trading run finished with status failed',
        },
      ],
    }
    const failedRecord = {
      ...record,
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_handoff: {
        paper_task_id: 'paper-task',
        paper_run_status: 'failed',
      },
      paper_monitoring_plan: [
        {
          key: 'rolling_sharpe',
          label: '模拟交易滚动 Sharpe',
          metric: 'rolling_sharpe',
          window: '30 trading days',
          direction: 'min',
          threshold: 0.6,
          action: '继续观察',
        },
      ],
      pipeline: failedPipeline,
      next_actions: ['模拟交易启动错误：Paper trading run finished with status failed'],
    }
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [failedRecord],
    })
    vm.aiResearchRuns = [record]
    vm.aiResearchResult = {
      ...baseResult,
      run_id: 'history-run',
      paper_trading: null,
      pipeline: record.pipeline,
      next_actions: [],
      run_record: record,
    }

    await vm.startPaperFromResearchRecord(record)
    await flushPromises()

    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('history-run', {
      research_workspace_id: 'research-ws',
    })
    expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith('research-ws', 20)
    expect(vm.aiResearchRuns[0].paper_trading_started).toBe(false)
    expect(vm.aiResearchRuns[0].paper_workspace_id).toBe('paper-ws')
    expect(vm.aiResearchRuns[0].paper_unit_id).toBe('paper-unit')
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('paper_trading_failed')
    expect(vm.aiResearchResult.paper_trading.started).toBe(false)
    expect(vm.aiResearchResult.pipeline.current_stage).toBe('paper_trading_failed')
    expect(vm.canContinueResearchFromPaperIssue(vm.aiResearchRuns[0])).toBe(true)
    expect(ElMessage.error).toHaveBeenCalledWith('模拟交易启动失败')
  })

  it('reviews paper trading from an achieved history record', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [
        {
          run_id: 'history-run',
          prompt: '历史趋势策略',
          symbol: '000001.SZ',
          symbol_name: '平安银行',
          timeframe: '1d',
          timeframe_n: 1,
          status: 'achieved',
          achieved: true,
          target_sharpe: 1,
          quality_gates: { target_sharpe: 1, min_total_trades: 1 },
          min_total_trades: 1,
          max_iterations: 3,
          iteration_count: 2,
          best_iteration: 2,
          best_sharpe: 1.2,
          best_quality_score: 100,
          best_quality_gate_evaluations: [],
          best_metrics: { sharpe_ratio: 1.2 },
          asset_specs: {
            IF2609: {
              symbol: 'IF2609',
              multiplier: 300,
              margin_rate: 0.1,
              commission_rate: 0.000023,
              source: 'local_futures_commission',
            },
          },
          backtest_environment: {
            initial_cash: 250000,
            commission: 0.000023,
            multiplier: 300,
            margin: 0.1,
            asset_spec_source: 'local_futures_commission',
          },
          best_strategy_id: 's1',
          best_strategy_name: 'AI策略',
          research_workspace_id: 'research-ws',
          seed_strategy_id: null,
          continued_from_run_id: null,
          paper_workspace_id: 'paper-ws',
          paper_unit_id: 'paper-unit',
          paper_trading_started: true,
          paper_handoff: {
            backtest_environment: {
              initial_cash: 200000,
              commission: 0.0015,
              multiplier: 100,
              asset_spec_source: 'paper_gateway',
            },
          },
          pipeline: {
            current_stage: 'paper_trading',
            status: 'achieved',
            progress: 80,
            ready_for_live: false,
            steps: [],
          },
          next_actions: [],
          started_at: '2026-06-27T00:00:00Z',
          completed_at: '2026-06-27T00:01:00Z',
          iterations: [],
        },
      ],
    })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()

    await wrapper.vm.$nextTick()
    expect(vm.canReviewPaperFromRecord(vm.aiResearchRuns[0])).toBe(true)
    expect(wrapper.text()).toContain('阶段 模拟交易')
    const historyRuntimeEnv = wrapper.find('[data-test="ai-research-history-runtime-env"]').text()
    expect(historyRuntimeEnv).toContain('回测环境')
    expect(historyRuntimeEnv).toContain('资产 IF2609')
    expect(historyRuntimeEnv).toContain('初始资金 250000.00')
    expect(historyRuntimeEnv).toContain('手续费 0.000023')
    expect(historyRuntimeEnv).toContain('合约乘数 300.00')
    const historyPaperEnv = wrapper.find('[data-test="ai-research-history-paper-env"]').text()
    expect(historyPaperEnv).toContain('模拟环境')
    expect(historyPaperEnv).toContain('初始资金 200000.00')
    expect(historyPaperEnv).toContain('手续费 0.001500')
    expect(historyPaperEnv).toContain('资产来源 paper_gateway')
    const reviewButton = wrapper.findAll('button').find(button => button.text().includes('复核模拟'))
    expect(reviewButton).toBeTruthy()
    await reviewButton!.trigger('click')
    await flushPromises()

    expect(strategyApi.reviewAIResearchPaperTrading).toHaveBeenCalledWith(
      'history-run',
      'research-ws'
    )
    expect(wrapper.find('[data-test="ai-research-paper-review"]').text()).toContain(
      '实盘候选'
    )
    expect(wrapper.find('[data-test="ai-research-paper-review-actions"]').text()).toContain(
      '模拟交易监控计划已全部通过'
    )
    expect(wrapper.find('[data-test="ai-research-live-readiness"]').text()).toContain(
      '模拟监控通过 已通过'
    )
    expect(wrapper.text()).toContain('实盘候选')
    expect(wrapper.text()).toContain('复核 实盘候选')
    expect(wrapper.text()).toContain('模拟交易滚动 Sharpe')
    expect(vm.aiResearchRuns[0].paper_review_status).toBe('ready_for_live_candidate')
    expect(vm.aiResearchRuns[0].paper_review_ready_for_live).toBe(true)
    expect(vm.aiResearchRuns[0].paper_reviewed_at).toBe('2026-06-27T00:02:00Z')
    expect(vm.aiResearchRuns[0].paper_review_evaluations[0].key).toBe('rolling_sharpe')
    expect(vm.aiResearchRuns[0].next_actions[0]).toContain('提交人工实盘审批')
    expect(strategyApi.buildAIResearchLiveHandoff).toHaveBeenCalledWith(
      'history-run',
      'research-ws'
    )
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('live_handoff')
    expect(wrapper.text()).toContain('阶段 实盘交接')
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-panel"]').text()).toContain(
      '可提交审批'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-panel"]').text()).toContain(
      '资产规格已随交接包固化'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-approvals"]').text()).toContain(
      '人工实盘审批 待人工确认'
    )
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已满足实盘候选条件')
    expect(ElMessage.success).toHaveBeenCalledWith('实盘交接包已生成')
  })

  it('uses live handoff embedded in paper review without rebuilding it', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const { ElMessage } = await import('element-plus')
    const embeddedHandoff = await strategyApi.buildAIResearchLiveHandoff(
      'history-run',
      'research-ws'
    )
    const embeddedReview = {
      ...(await strategyApi.reviewAIResearchPaperTrading('history-run', 'research-ws')),
      live_handoff: embeddedHandoff,
      pipeline: embeddedHandoff.pipeline,
      next_actions: embeddedHandoff.next_actions,
    }
    vi.mocked(strategyApi.buildAIResearchLiveHandoff).mockClear()
    vi.mocked(strategyApi.reviewAIResearchPaperTrading).mockClear()
    vi.mocked(strategyApi.reviewAIResearchPaperTrading).mockResolvedValueOnce(embeddedReview)

    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()
    const record = {
      ...vm.aiResearchRuns[0],
      paper_workspace_id: 'paper-ws',
      paper_unit_id: 'paper-unit',
      paper_trading_started: true,
      pipeline: {
        current_stage: 'paper_trading',
        status: 'achieved',
        progress: 80,
        ready_for_live: false,
        steps: [],
      },
    }
    vm.aiResearchRuns = [record]
    await wrapper.vm.$nextTick()

    await vm.reviewPaperFromResearchRecord(record)
    await flushPromises()

    expect(strategyApi.reviewAIResearchPaperTrading).toHaveBeenCalledWith(
      'history-run',
      'research-ws'
    )
    expect(strategyApi.buildAIResearchLiveHandoff).not.toHaveBeenCalled()
    expect(vm.aiResearchRuns[0].live_handoff.status).toBe('ready_for_approval')
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('live_handoff')
    expect(vm.aiResearchRuns[0].next_actions[0]).toContain('提交人工实盘审批')
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-panel"]').text()).toContain(
      '可提交审批'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-approvals"]').text()).toContain(
      '人工实盘审批 待人工确认'
    )
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已满足实盘候选条件')
    expect(ElMessage.success).toHaveBeenCalledWith('实盘交接包已生成')
  })

  it('shows persisted paper trading review from run history after reload', async () => {
    const { strategyApi } = await import('@/api/strategy')
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [
        {
          run_id: 'history-reviewed-run',
          prompt: '已复核趋势策略',
          symbol: '000001.SZ',
          symbol_name: '平安银行',
          timeframe: '1d',
          timeframe_n: 1,
          status: 'achieved',
          achieved: true,
          target_sharpe: 1,
          quality_gates: { target_sharpe: 1, min_total_trades: 1 },
          min_total_trades: 1,
          max_iterations: 3,
          iteration_count: 2,
          best_iteration: 2,
          best_sharpe: 1.2,
          best_quality_score: 100,
          best_quality_gate_evaluations: [],
          best_metrics: { sharpe_ratio: 1.2 },
          best_strategy_id: 's1',
          best_strategy_name: 'AI策略',
          research_workspace_id: 'research-ws',
          seed_strategy_id: null,
          continued_from_run_id: null,
          paper_workspace_id: 'paper-ws',
          paper_unit_id: 'paper-unit',
          paper_trading_started: true,
          paper_monitoring_plan: [],
          paper_handoff: {},
          paper_review_status: 'ready_for_live_candidate',
          paper_review_ready_for_live: true,
          paper_reviewed_at: '2026-06-27T00:02:00Z',
          live_readiness_expires_at: '2026-07-04T00:02:00Z',
          paper_review_evaluations: [
            {
              key: 'rolling_sharpe',
              label: '模拟交易滚动 Sharpe',
              metric: 'rolling_sharpe',
              actual: 1.12,
              threshold: 1,
              passed: true,
              status: 'passed',
              direction: 'min',
              window: '2026-06-27',
              action: 'continue',
            },
          ],
          live_readiness_checklist: [
            {
              key: 'human_approval_required',
              label: '人工实盘审批',
              status: 'pending_manual_confirmation',
              evidence: '模拟复核已达到实盘候选状态。',
              action: '确认账户权限和上线窗口后再切换实盘。',
            },
          ],
          paper_review_next_actions: ['模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。'],
          live_handoff: {
            run_id: 'history-reviewed-run',
            research_workspace_id: 'research-ws',
            generated_at: '2026-06-27T00:03:00Z',
            ready_for_live: true,
            status: 'ready_for_approval',
            approval_required: true,
            expires_at: '2026-07-04T00:02:00Z',
            paper_workspace_id: 'paper-ws',
            paper_unit_id: 'paper-unit',
            best_strategy_id: 's1',
            best_strategy_name: 'AI策略',
            symbol: '000001.SZ',
            symbol_name: '平安银行',
            timeframe: '1d',
            timeframe_n: 1,
            target_sharpe: 1,
            best_sharpe: 1.2,
            best_metrics: { sharpe_ratio: 1.2 },
            asset_specs: {
              '000001.SZ': { symbol: '000001.SZ', multiplier: 1, commission_rate: 0.0008 },
            },
            backtest_environment: { initial_cash: 100000, commission: 0.0008 },
            paper_review_status: 'ready_for_live_candidate',
            paper_reviewed_at: '2026-06-27T00:02:00Z',
            paper_review_evaluations: [],
            paper_monitoring_plan: [],
            live_readiness_checklist: [
              {
                key: 'human_approval_required',
                label: '人工实盘审批',
                status: 'pending_manual_confirmation',
                evidence: '模拟复核已达到实盘候选状态。',
                action: '确认账户权限和上线窗口后再切换实盘。',
              },
            ],
            approvals_required: [
              {
                key: 'human_approval_required',
                label: '人工实盘审批',
                status: 'pending_manual_confirmation',
                evidence: '模拟复核已达到实盘候选状态。',
                action: '确认账户权限和上线窗口后再切换实盘。',
              },
            ],
            deployment_blockers: [],
            handoff: { gateway_config: { api_key: '***' } },
            pipeline: {
              current_stage: 'live_handoff',
              status: 'ready_for_approval',
              progress: 100,
              ready_for_live: true,
              live_handoff_status: 'ready_for_approval',
              steps: [{ key: 'live_handoff', label: '实盘交接', status: 'running' }],
            },
            next_actions: ['实盘交接包已生成，等待人工审批账户权限、风险限额和上线窗口。'],
          },
          pipeline: {
            current_stage: 'live_handoff',
            status: 'ready_for_approval',
            progress: 100,
            ready_for_live: true,
            live_handoff_status: 'ready_for_approval',
            live_readiness_expires_at: '2026-07-04T00:02:00Z',
            live_readiness_checklist: [
              {
                key: 'human_approval_required',
                label: '人工实盘审批',
                status: 'pending_manual_confirmation',
                evidence: '模拟复核已达到实盘候选状态。',
                action: '确认账户权限和上线窗口后再切换实盘。',
              },
            ],
            steps: [{ key: 'live_handoff', label: '实盘交接', status: 'running' }],
          },
          next_actions: ['模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。'],
          started_at: '2026-06-27T00:00:00Z',
          completed_at: '2026-06-27T00:01:00Z',
          iterations: [],
        },
      ],
    })

    const wrapper = doMount()
    await flushPromises()

    expect(strategyApi.reviewAIResearchPaperTrading).not.toHaveBeenCalled()
    expect(strategyApi.buildAIResearchLiveHandoff).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="ai-research-paper-review"]').text()).toContain(
      '实盘候选'
    )
    expect(wrapper.find('[data-test="ai-research-paper-review"]').text()).toContain(
      '模拟交易滚动 Sharpe'
    )
    expect(wrapper.find('[data-test="ai-research-paper-review"]').text()).toContain(
      '候选有效期'
    )
    expect(wrapper.find('[data-test="ai-research-live-readiness"]').text()).toContain(
      '人工实盘审批 待人工确认'
    )
    expect(wrapper.find('[data-test="ai-research-paper-review-actions"]').text()).toContain(
      '模拟交易监控计划已全部通过'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-panel"]').text()).toContain(
      '可提交审批'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-panel"]').text()).toContain(
      '资产规格已随交接包固化'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-approvals"]').text()).toContain(
      '人工实盘审批 待人工确认'
    )
    const historyApproveButton = wrapper.findAll('button').find(
      button => button.text().includes('批准交接')
    )
    expect(historyApproveButton).toBeTruthy()
    await historyApproveButton!.trigger('click')
    await flushPromises()
    expect(strategyApi.approveAIResearchLiveHandoff).toHaveBeenCalledWith(
      'history-reviewed-run',
      expect.objectContaining({
        decision: 'approved',
        account_confirmed: true,
        risk_limit_confirmed: true,
      }),
      'research-ws'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-panel"]').text()).toContain(
      '已批准实盘'
    )
    expect(wrapper.find('[data-test="ai-research-history-live-handoff-approval"]').text()).toContain(
      '已批准'
    )
    expect(wrapper.text()).toContain('阶段 实盘交接')
    expect(wrapper.text()).toContain('实盘交接')
  })

  it('continues research directly from a failed paper review record', async () => {
    const { strategyApi } = await import('@/api/strategy')
    vi.mocked(strategyApi.listAIResearchRuns).mockResolvedValueOnce({
      total: 1,
      items: [
        {
          run_id: 'paper-failed-run',
          prompt: '历史趋势策略',
          symbol: '600000.SH',
          symbol_name: '浦发银行',
          timeframe: '1d',
          timeframe_n: 1,
          status: 'achieved',
          achieved: true,
          target_sharpe: 1,
          quality_gates: { target_sharpe: 1, min_total_trades: 1 },
          min_total_trades: 1,
          max_iterations: 3,
          iteration_count: 2,
          best_iteration: 2,
          best_sharpe: 1.2,
          best_quality_score: 100,
          best_quality_gate_evaluations: [],
          best_metrics: { sharpe_ratio: 1.2 },
          best_strategy_id: 'best-strategy',
          best_strategy_name: '历史最佳策略',
          research_workspace_id: 'research-ws',
          seed_strategy_id: null,
          continued_from_run_id: null,
          paper_workspace_id: 'paper-ws',
          paper_unit_id: 'paper-unit',
          paper_trading_started: true,
          paper_review_status: 'needs_research_review',
          paper_review_ready_for_live: false,
          paper_reviewed_at: '2026-06-27T00:02:00Z',
          paper_review_evaluations: [
            {
              key: 'rolling_sharpe',
              label: '模拟交易滚动 Sharpe',
              metric: 'rolling_sharpe',
              window: '30 trading days',
              direction: 'min',
              threshold: 0.6,
              actual: 0.2,
              source: 'unit_status.metrics_snapshot',
              status: 'failed',
              passed: false,
              action: '回到研究工作区降低过拟合并收紧风险预算',
            },
          ],
          pipeline: {
            current_stage: 'paper_review',
            status: 'needs_review',
            progress: 80,
            ready_for_live: false,
            paper_unit_locked: true,
            paper_unit_stopped: true,
            paper_review_lock: {
              run_id: 'paper-failed-run',
              research_workspace_id: 'research-ws',
              paper_workspace_id: 'paper-ws',
              paper_unit_id: 'paper-unit',
              status: 'needs_research_review',
              reviewed_at: '2026-06-27T00:02:00Z',
              stop_results: [{ unit_id: 'paper-unit', cancelled: true }],
              next_actions: ['回到研究工作区降低过拟合并收紧风险预算'],
            },
            steps: [],
          },
          next_actions: ['回到研究工作区降低过拟合并收紧风险预算'],
          started_at: '2026-06-27T00:00:00Z',
          completed_at: '2026-06-27T00:01:00Z',
          iterations: [],
        },
      ],
    })
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()

    expect(wrapper.text()).toContain('继续改进')
    const lockPanel = wrapper.find('[data-test="ai-research-paper-review-lock"]')
    expect(lockPanel.text()).toContain('模拟单元保护')
    expect(lockPanel.text()).toContain('paper-unit 需要重新投研，已自动停止并锁定')
    expect(lockPanel.text()).toContain('停止结果 paper-unit 已取消')
    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续改进'))
    expect(continueButton).toBeTruthy()
    await continueButton!.trigger('click')
    await flushPromises()

    expect(vm.aiResearchForm.continuation_source).toBe('paper_review')
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '历史趋势策略',
      symbol: '600000.SH',
      research_workspace_id: 'research-ws',
      seed_strategy_id: 'best-strategy',
      continue_from_run_id: 'paper-failed-run',
    }))
  })

  it('continues research directly from a rejected live handoff record', async () => {
    const { strategyApi } = await import('@/api/strategy')
    const wrapper = doMount()
    const vm = wrapper.vm as any
    await flushPromises()
    vi.mocked(strategyApi.runAIResearchLoop).mockClear()
    const record = {
      ...vm.aiResearchRuns[0],
      run_id: 'live-rejected-run',
      achieved: true,
      best_strategy_id: 's1',
      paper_review_status: 'ready_for_live_candidate',
      paper_review_ready_for_live: true,
      live_handoff: {
        run_id: 'live-rejected-run',
        research_workspace_id: 'research-ws',
        generated_at: '2026-06-27T00:03:00Z',
        ready_for_live: true,
        status: 'approval_rejected',
        approval_required: true,
        approval_status: 'rejected',
        approval: {
          run_id: 'live-rejected-run',
          research_workspace_id: 'research-ws',
          decision: 'rejected',
          approved: false,
          decided_at: '2026-06-27T00:04:00Z',
          decided_by: 'risk-manager',
          comment: '单笔风险过高，先降低仓位。',
          account_confirmed: false,
          risk_limit_confirmed: false,
          handoff_status_at_decision: 'ready_for_approval',
          blockers: [],
        },
        approvals_required: [],
        deployment_blockers: [],
        pipeline: {
          current_stage: 'live_handoff',
          status: 'approval_rejected',
          progress: 100,
          ready_for_live: true,
          live_handoff_status: 'approval_rejected',
        },
        next_actions: ['驳回意见：单笔风险过高，先降低仓位。'],
      },
      live_handoff_approval: {
        run_id: 'live-rejected-run',
        research_workspace_id: 'research-ws',
        decision: 'rejected',
        approved: false,
        decided_at: '2026-06-27T00:04:00Z',
        decided_by: 'risk-manager',
        comment: '单笔风险过高，先降低仓位。',
        account_confirmed: false,
        risk_limit_confirmed: false,
        handoff_status_at_decision: 'ready_for_approval',
        blockers: [],
      },
      pipeline: {
        current_stage: 'live_handoff',
        status: 'approval_rejected',
        progress: 100,
        ready_for_live: true,
        live_handoff_status: 'approval_rejected',
        live_handoff_approval_status: 'rejected',
        steps: [],
      },
      next_actions: ['驳回意见：单笔风险过高，先降低仓位。'],
    }
    vm.aiResearchRuns = [record]
    await wrapper.vm.$nextTick()

    expect(vm.continuationSourceForRecord(record)).toBe('live_handoff_rejected')
    expect(vm.canContinueResearchFromPaperReview(record)).toBe(true)
    await vm.continueResearchFromRecord(record)
    await flushPromises()

    expect(vm.aiResearchForm.continuation_source).toBe('live_handoff_rejected')
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      research_workspace_id: 'research-ws',
      seed_strategy_id: 's1',
      continue_from_run_id: 'live-rejected-run',
    }))
  })

  it('saveStrategy warns when name/code empty', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    vm.form.name = ''
    vm.form.code = ''
    await vm.saveStrategy()
    expect(ElMessage.warning).toHaveBeenCalledWith('请填写策略名称和代码')
  })

  it('saveStrategy creates new strategy', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    vm.isEdit = false
    vm.form.name = 'test'
    vm.form.code = 'code'
    await vm.saveStrategy()
    expect(ElMessage.success).toHaveBeenCalledWith('策略已创建')
    expect(vm.dialogVisible).toBe(false)
  })

  it('saveStrategy updates existing strategy', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    vm.isEdit = true
    vm.editingId = 's1'
    vm.form.name = 'test'
    vm.form.code = 'code'
    await vm.saveStrategy()
    expect(ElMessage.success).toHaveBeenCalledWith('策略已更新')
  })

  it('deleteStrategy calls store', async () => {
    const { ElMessage } = await import('element-plus')
    const vm = doMount().vm as any
    await vm.deleteStrategy('s1')
    expect(ElMessage.success).toHaveBeenCalledWith('删除成功')
  })

  it('paramTableData returns entries from detail template', () => {
    const vm = doMount().vm as any
    vm.detailTemplate = { id: 't1', params: { fast: { default: 5, type: 'int', description: 'fast' } } }
    expect(vm.paramTableData.length).toBe(1)
    expect(vm.paramTableData[0].name).toBe('fast')
  })

  it('paramTableData returns empty when no detail', () => {
    const vm = doMount().vm as any
    vm.detailTemplate = null
    expect(vm.paramTableData).toEqual([])
  })
})
