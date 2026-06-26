import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
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
          min_total_trades: 1,
          max_iterations: 3,
          iteration_count: 2,
          best_iteration: 2,
          best_sharpe: 1.2,
          best_metrics: { sharpe_ratio: 1.2 },
          best_strategy_id: 's1',
          best_strategy_name: 'AI策略',
          research_workspace_id: 'research-ws',
          paper_workspace_id: null,
          paper_unit_id: null,
          paper_trading_started: false,
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
      best_metrics: { sharpe_ratio: 1.2 },
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
          passed: true,
          improvement_notes: [],
        },
      ],
      best_strategy: { id: 's1', name: 'AI策略', description: 'd', code: 'code', category: 'trend', params: {} },
      paper_trading: null,
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
        min_total_trades: 1,
        max_iterations: 3,
        iteration_count: 1,
        best_iteration: 1,
        best_sharpe: 1.2,
        best_metrics: { sharpe_ratio: 1.2 },
        best_strategy_id: 's1',
        best_strategy_name: 'AI策略',
        research_workspace_id: 'research-ws',
        paper_workspace_id: null,
        paper_unit_id: null,
        paper_trading_started: false,
        started_at: '2026-06-27T00:00:00Z',
        completed_at: '2026-06-27T00:01:00Z',
        iterations: [],
      },
      message: 'ok',
    }),
  },
}))

vi.mock('@/components/common/MonacoEditor.vue', () => ({
  default: { template: '<div />' },
}))

describe('StrategyPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const doMount = () => mount(StrategyPage, { global: { stubs: elStubs } })

  it('mounts without error', () => {
    expect(doMount().exists()).toBe(true)
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
    const vm = doMount().vm as any
    vm.aiResearchForm.prompt = '生成一个趋势策略'
    vm.aiResearchForm.symbol = '000001.SZ'
    await vm.runAIResearchLoop()
    expect(strategyApi.runAIResearchLoop).toHaveBeenCalledWith(expect.objectContaining({
      prompt: '生成一个趋势策略',
      symbol: '000001.SZ',
      target_sharpe: 1,
    }))
    expect(vm.aiResearchResult.achieved).toBe(true)
    expect(vm.aiResearchRuns[0].run_id).toBe('run-1')
    expect(ElMessage.success).toHaveBeenCalledWith('AI投研流程已完成')
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
      status: 'achieved',
      achieved: true,
      target_sharpe: 1.5,
      min_total_trades: 3,
      max_iterations: 4,
      iteration_count: 2,
      best_iteration: 2,
      best_sharpe: 1.6,
      best_metrics: {},
      research_workspace_id: 'research-ws',
      paper_trading_started: false,
      started_at: '2026-06-27T00:00:00Z',
      completed_at: '2026-06-27T00:01:00Z',
      iterations: [],
    })
    expect(vm.aiResearchForm.prompt).toBe('历史趋势策略')
    expect(vm.aiResearchForm.symbol).toBe('600000.SH')
    expect(vm.aiResearchForm.target_sharpe).toBe(1.5)
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
