import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import StrategyPage from '@/views/StrategyPage.vue'
import { stripStrategyMeta, getStrategyParamCount } from '@/constants/strategy'
import { elStubs } from '@/test/stubs'

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

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
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
          best_strategy_id: 's1',
          best_strategy_name: 'AI策略',
          research_workspace_id: 'research-ws',
          seed_strategy_id: null,
          continued_from_run_id: null,
          paper_workspace_id: null,
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
          direction: 'min',
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
        best_strategy_id: 's1',
        best_strategy_name: 'AI策略',
        research_workspace_id: 'research-ws',
        seed_strategy_id: null,
        continued_from_run_id: null,
        paper_workspace_id: null,
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
      pipeline: {
        current_stage: 'live_candidate',
        status: 'achieved',
        progress: 100,
        ready_for_live: true,
        steps: [],
      },
      next_actions: ['模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。'],
    }),
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
    expect(wrapper.text()).toContain('阶段 quality_achieved')
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
    }))
    const researchCalls = vi.mocked(strategyApi.runAIResearchLoop).mock.calls
    expect(researchCalls[researchCalls.length - 1]?.[0]).not.toHaveProperty('commission')
    expect(vm.aiResearchResult.achieved).toBe(true)
    expect(vm.aiResearchRuns[0].run_id).toBe('run-1')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('质量分')
    expect(wrapper.text()).toContain('100.00')
    expect(wrapper.find('[data-test="ai-research-gate-summary"]').text()).toContain('Sharpe')
    expect(wrapper.find('[data-test="ai-research-gate-summary"]').text()).toContain('1.20 / 1.00')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('样本外验证')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('passed')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('2024-01-16')
    expect(wrapper.find('[data-test="ai-research-oos-summary"]').text()).toContain('0.92 / 0.80')
    expect(wrapper.find('[data-test="ai-research-next-actions"]').text()).toContain('策略已通过验收')
    expect(wrapper.text()).toContain('进入模拟交易后优先验证成交、滑点、费用和样本外收益稳定性')
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
    })
    expect(vm.aiResearchResult.paper_trading.started).toBe(true)
    expect(vm.aiResearchResult.run_record.paper_trading_started).toBe(true)
    expect(vm.aiResearchRuns[0].run_id).toBe('run-1')
    expect(vm.aiResearchRuns[0].paper_trading_started).toBe(true)
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
      'ready_for_live_candidate'
    )
    expect(ElMessage.success).toHaveBeenCalledWith('AI投研流程已完成')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已启动')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已满足实盘候选条件')
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
    expect(wrapper.text()).toContain('阶段 paper_trading_failed')
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
      latest_iteration: { iteration: 1, sharpe_ratio: 1.2 },
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
      iterations: [],
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
      expect(strategyApi.listAIResearchRuns).toHaveBeenCalledWith(undefined, 100)
      expect(vm.aiResearchResult.run_id).toBe('restored-run')
      expect(vm.aiResearchResult.research_workspace.id).toBe('research-ws')
      expect(vm.aiResearchResult.run_record.paper_trading_started).toBe(true)
      expect(vm.aiResearchPaperStatusText).toBe('已启动')
      expect(vm.aiResearchCurrentPaperEnvironment[0].key).toBe('initial_cash')
      expect(vm.canOpenPaperFromCurrentResult).toBe(true)
      expect(vm.canViewBestStrategyFromCurrentResult).toBe(true)
      vi.mocked(strategyApi.get).mockClear()
      await vm.viewBestStrategyFromCurrentResult()
      await flushPromises()
      expect(strategyApi.get).toHaveBeenCalledWith('s1')
      expect(vm.viewDialogVisible).toBe(true)
      expect(vm.currentStrategy.id).toBe('s1')
      expect(strategyApi.runAIResearchLoop).not.toHaveBeenCalled()
    } finally {
      delete (strategyApi as any).submitAIResearchTask
      delete (strategyApi as any).getAIResearchTask
    }
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
        current_stage: 'paper_trading',
        progress: 100,
        current_iteration: 2,
        iteration_count: 2,
        max_iterations: 8,
        message: 'done',
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
      'needs_research_review'
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
          current_stage: 'backtesting',
          progress: 42,
          current_iteration: 2,
          iteration_count: 1,
          max_iterations: 3,
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
      current_stage: 'cancelled',
      progress: 35,
      current_iteration: 1,
      iteration_count: 0,
      max_iterations: 3,
      message: 'cancelled',
    })
    try {
      const vm = doMount().vm as any
      vm.aiResearchRunning = true
      vm.aiResearchTaskId = 'research-task-1'
      await vm.cancelAIResearchTask()

      expect((strategyApi as any).cancelAIResearchTask).toHaveBeenCalledWith('research-task-1')
      expect(vm.aiResearchRunning).toBe(false)
      expect(vm.aiResearchTaskStatus).toBe('cancelled')
      expect(vm.aiResearchTaskStage).toBe('cancelled')
      expect(ElMessage.success).toHaveBeenCalledWith('AI投研任务已取消')
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
      paper_trading_started: false,
      next_actions: [],
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
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
        paper_workspace_id: null,
        paper_unit_id: null,
        paper_trading_started: false,
        next_actions: [],
        started_at: '2026-06-27T00:00:00Z',
        completed_at: '2026-06-27T00:01:00Z',
        iterations: [],
      },
    ]
    vm.aiResearchRunsLoading = false

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
    await vm.startPaperFromResearchRecord(vm.aiResearchRuns[0])
    await flushPromises()

    expect(strategyApi.startAIResearchPaperTrading).toHaveBeenCalledWith('history-run', {
      research_workspace_id: 'research-ws',
    })
    expect(vm.aiResearchRuns[0].paper_trading_started).toBe(true)
    expect(vm.aiResearchRuns[0].paper_workspace_id).toBe('paper-ws')
    expect(vm.aiResearchRuns[0].paper_unit_id).toBe('paper-unit')
    expect(vm.aiResearchRuns[0].paper_handoff.paper_task_id).toBe('paper-task')
    expect(vm.aiResearchRuns[0].paper_monitoring_plan[0].key).toBe('rolling_sharpe')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已启动')
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
    expect(wrapper.text()).toContain('阶段 paper_trading')
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
      'ready_for_live_candidate'
    )
    expect(wrapper.find('[data-test="ai-research-paper-review-actions"]').text()).toContain(
      '模拟交易监控计划已全部通过'
    )
    expect(wrapper.text()).toContain('实盘候选')
    expect(wrapper.text()).toContain('复核 ready_for_live_candidate')
    expect(wrapper.text()).toContain('模拟交易滚动 Sharpe')
    expect(vm.aiResearchRuns[0].paper_review_status).toBe('ready_for_live_candidate')
    expect(vm.aiResearchRuns[0].paper_review_ready_for_live).toBe(true)
    expect(vm.aiResearchRuns[0].paper_reviewed_at).toBe('2026-06-27T00:02:00Z')
    expect(vm.aiResearchRuns[0].paper_review_evaluations[0].key).toBe('rolling_sharpe')
    expect(vm.aiResearchRuns[0].next_actions[0]).toContain('模拟交易监控计划已全部通过')
    expect(vm.aiResearchRuns[0].pipeline.current_stage).toBe('live_candidate')
    expect(wrapper.text()).toContain('阶段 live_candidate')
    expect(ElMessage.success).toHaveBeenCalledWith('模拟交易已满足实盘候选条件')
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
