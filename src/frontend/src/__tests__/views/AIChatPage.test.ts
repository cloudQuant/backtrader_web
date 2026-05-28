import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import AIChatPage from '@/views/AIChatPage.vue'
import { elStubs } from '@/test/stubs'

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerMocks.push }),
  useRoute: () => ({ query: {} }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

const strategyApiMocks = vi.hoisted(() => ({
  create: vi.fn(),
  addCopilotDraftToWorkspace: vi.fn(),
  backtestCopilotDraft: vi.fn(),
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    create: strategyApiMocks.create,
    addCopilotDraftToWorkspace: strategyApiMocks.addCopilotDraftToWorkspace,
    backtestCopilotDraft: strategyApiMocks.backtestCopilotDraft,
  },
}))

const workspaceApiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  runUnits: vi.fn(),
  getUnitsStatus: vi.fn(),
  createReport: vi.fn(),
}))

const aiObservabilityMocks = vi.hoisted(() => ({
  getMyAvailableModels: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    list: workspaceApiMocks.list,
    runUnits: workspaceApiMocks.runUnits,
    getUnitsStatus: workspaceApiMocks.getUnitsStatus,
    createReport: workspaceApiMocks.createReport,
  },
}))

vi.mock('@/api/aiObservability', () => ({
  aiObservabilityApi: {
    getMyAvailableModels: aiObservabilityMocks.getMyAvailableModels,
  },
}))

const mocks = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn().mockResolvedValue(undefined),
  fetchConversations: vi.fn().mockResolvedValue({ items: [] }),
  fetchHistory: vi.fn().mockResolvedValue(undefined),
  resetConversationState: vi.fn(),
  sendMessage: vi.fn().mockResolvedValue(undefined),
  knowledgeBases: [
    {
      id: 'kb-1',
      owner_id: 'user-1',
      name: '知识库1',
      description: '描述1',
      document_count: 1,
      is_public: false,
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    },
  ],
  documents: [
    {
      id: 'doc-1',
      knowledge_base_id: 'kb-1',
      title: '双均线策略',
      content: '双均线策略在上穿时开仓。',
      content_type: 'markdown',
      file_path: null,
      is_folder: false,
      parent_id: null,
      sort_order: 0,
      status: 'draft',
      index_status: 'not_indexed',
      indexed_at: null,
      metadata: null,
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    },
  ],
  conversations: [] as Array<{
    id: string
    knowledge_base_id: string
    title: string
    model_id: string | null
    created_at: string
    updated_at: string
  }>,
  messages: [
    { role: 'user', content: '开仓条件是什么？' },
    {
      role: 'assistant',
      content: '双均线策略在上穿时开仓。',
      citations: [
        {
          document_id: 'doc-1',
          document_title: '',
          chunk_id: '',
          chunk_index: 0,
          similarity: 0.95,
        },
      ],
      reasonCode: 'ai_not_configured',
      diagnosticMessage: '当前系统未配置生成式 AI 模型，已降级返回最相关的知识库片段。',
      strategyDraft: {
        name: 'AI策略 - 双均线',
        description: '一个测试策略草案',
        code: 'class Demo(bt.Strategy):\n    pass',
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
        rationale: '用于测试保存策略按钮',
        next_steps: ['继续完善'],
        suggested_symbol: null,
        suggested_timeframe: '1d',
      },
    },
  ],
}))

vi.mock('@/stores/knowledgeBase', () => ({
  useKnowledgeBaseStore: () => ({
    knowledgeBases: mocks.knowledgeBases,
    currentKnowledgeBase: mocks.knowledgeBases[0],
    documents: mocks.documents,
    loading: false,
    fetchKnowledgeBases: mocks.fetchKnowledgeBases,
    selectKnowledgeBase: vi.fn(),
  }),
}))

vi.mock('@/stores/kbChat', () => ({
  useKBChatStore: () => ({
    conversations: mocks.conversations,
    messages: mocks.messages,
    currentConversationId: null,
    loading: false,
    fetchConversations: mocks.fetchConversations,
    fetchHistory: mocks.fetchHistory,
    resetConversationState: mocks.resetConversationState,
    sendMessage: mocks.sendMessage,
  }),
}))

describe('AIChatPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useRealTimers()
    vi.clearAllMocks()
    mocks.fetchKnowledgeBases.mockResolvedValue(undefined)
    mocks.fetchConversations.mockResolvedValue({ items: [] })
    mocks.fetchHistory.mockResolvedValue(undefined)
    mocks.resetConversationState.mockReset()
    routerMocks.push.mockReset()
    strategyApiMocks.create.mockReset()
    strategyApiMocks.addCopilotDraftToWorkspace.mockReset()
    strategyApiMocks.backtestCopilotDraft.mockReset()
    workspaceApiMocks.list.mockReset()
    workspaceApiMocks.runUnits.mockReset()
    workspaceApiMocks.getUnitsStatus.mockReset()
    workspaceApiMocks.createReport.mockReset()
    aiObservabilityMocks.getMyAvailableModels.mockReset()
    aiObservabilityMocks.getMyAvailableModels.mockResolvedValue({
      providers: [],
      models: [
        { provider: 'ollama', model: 'ollama/llama3.1:8b', display_name: 'Ollama / ollama/llama3.1:8b' },
      ],
      preferences: { provider: null, model: null },
    })
    workspaceApiMocks.list.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'ws-1',
          user_id: 'user-1',
          name: '研究工作区',
          description: null,
          workspace_type: 'research',
          settings: {},
          trading_config: {},
          unit_count: 0,
          completed_count: 0,
          status: 'idle',
          created_at: '2026-04-23T00:00:00Z',
          updated_at: '2026-04-23T00:00:00Z',
        },
      ],
    })
    workspaceApiMocks.runUnits.mockResolvedValue({
      results: [{ unit_id: 'unit-1', task_id: 'task-1', status: 'running' }],
    })
    workspaceApiMocks.getUnitsStatus.mockResolvedValue([
      {
        id: 'unit-1',
        run_status: 'completed',
        last_task_id: 'task-1',
        metrics_snapshot: {},
        run_count: 1,
        last_run_time: null,
        bar_count: null,
        trading_instance_id: null,
        trading_snapshot: {},
        trading_mode: 'paper',
        lock_trading: false,
        lock_running: false,
        opt_status: null,
        opt_total: null,
        opt_completed: null,
        opt_progress: null,
        opt_elapsed_time: null,
        opt_remaining_time: null,
      },
    ])
    workspaceApiMocks.createReport.mockResolvedValue({
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
    })
  })

  it('loads knowledge bases on mount', () => {
    mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    expect(mocks.fetchKnowledgeBases).toHaveBeenCalled()
  })

  it('renders existing assistant response', () => {
    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    expect(wrapper.text()).toContain('双均线策略在上穿时开仓。')
    expect(wrapper.text()).toContain('参考文档')
    expect(wrapper.text()).toContain('1 条引用')
    expect(wrapper.text()).toContain('未配置')
    expect(wrapper.text()).toContain('未命名文档')
    expect(wrapper.text()).toContain('当前知识库有未索引文档')
    expect(wrapper.text()).toContain('前往重建索引')
    expect(wrapper.text()).toContain('快捷工具')
    expect(wrapper.text()).toContain('保存为策略')
  })

  it('renders conversation title in sidebar', () => {
    mocks.conversations.splice(0, mocks.conversations.length, {
      id: 'conv-1',
      knowledge_base_id: 'kb-1',
      title: '关于双均线的讨论',
      model_id: null,
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    })
    mocks.fetchConversations.mockResolvedValue({ items: [{ id: 'conv-1' }] })

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    expect(wrapper.text()).toContain('关于双均线的讨论')
  })

  it('loads conversation history when clicking a conversation title', async () => {
    mocks.conversations.splice(0, mocks.conversations.length, {
      id: 'conv-1',
      knowledge_base_id: 'kb-1',
      title: '关于双均线的讨论',
      model_id: null,
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    })
    mocks.fetchConversations.mockResolvedValue({ items: [{ id: 'conv-1' }] })

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    const conversationButton = wrapper.findAll('button').find(button => button.text().includes('关于双均线的讨论'))
    expect(conversationButton).toBeTruthy()
    await conversationButton!.trigger('click')

    expect(mocks.fetchHistory).toHaveBeenCalledWith('conv-1')
  })

  it('jumps to cited document from assistant message', async () => {
    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()
    const citationButton = wrapper.findAll('button').find(button => button.text().includes('未命名文档'))
    expect(citationButton).toBeTruthy()
    await citationButton!.trigger('click')

    expect(routerMocks.push).toHaveBeenCalledWith({
      path: '/knowledge-base/kb-1/documents/doc-1',
    })
  })

  it('renders welcome suggested prompts when there are no messages', () => {
    const originalMessages = [...mocks.messages]
    mocks.messages.splice(0, mocks.messages.length)

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    expect(wrapper.text()).toContain('从知识库开始提问')
    expect(wrapper.text()).toContain('这个知识库主要包含哪些内容？')
    expect(wrapper.text()).toContain('快捷工具')
    expect(wrapper.text()).toContain('总结知识库')

    mocks.messages.splice(0, mocks.messages.length, ...originalMessages)
  })

  it('passes assistant mode when sending a backtrader strategy request', async () => {
    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()
    const modeButton = wrapper.findAll('button').find(button => button.text().includes('Backtrader策略生成'))
    expect(modeButton).toBeTruthy()
    await modeButton!.trigger('click')
    await wrapper.find('textarea').setValue('请生成一个双均线策略')
    const sendButton = wrapper.findAll('button').find(button => button.text().includes('发送'))
    expect(sendButton).toBeTruthy()
    await sendButton!.trigger('click')

    expect(mocks.sendMessage).toHaveBeenCalledWith('kb-1', '请生成一个双均线策略', {
      assistantMode: 'backtrader_strategy',
      thinkingMode: false,
      modelId: undefined,
    })
  })

  it('passes selected session model when sending a message', async () => {
    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()
    const vm = wrapper.vm as any
    vm.selectedSessionModelKey = 'ollama::ollama/llama3.1:8b'
    await wrapper.find('textarea').setValue('请解释均线策略')
    const sendButton = wrapper.findAll('button').find(button => button.text().includes('发送'))
    expect(sendButton).toBeTruthy()
    await sendButton!.trigger('click')

    expect(aiObservabilityMocks.getMyAvailableModels).toHaveBeenCalled()
    expect(mocks.sendMessage).toHaveBeenCalledWith('kb-1', '请解释均线策略', {
      assistantMode: 'knowledge_qa',
      thinkingMode: false,
      modelId: 'ollama::ollama/llama3.1:8b',
    })
  })

  it('creates a strategy from assistant draft', async () => {
    strategyApiMocks.create.mockResolvedValue({
      id: 'strategy-1',
      user_id: 'user-1',
      name: 'AI策略 - 双均线',
      description: '一个测试策略草案',
      code: 'class Demo(bt.Strategy):\n    pass',
      params: {
        fast_period: { type: 'int', default: 10 },
      },
      category: 'trend',
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    })

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()
    const saveButton = wrapper.findAll('button').find(button => button.text().includes('保存为策略'))
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')

    expect(strategyApiMocks.create).toHaveBeenCalledWith({
      name: 'AI策略 - 双均线',
      description: '一个测试策略草案',
      code: 'class Demo(bt.Strategy):\n    pass',
      params: {
        fast_period: { type: 'int', default: 10 },
      },
      category: 'trend',
    })
  })

  it('adds an assistant draft to workspace', async () => {
    strategyApiMocks.addCopilotDraftToWorkspace.mockResolvedValue({
      workspace_id: 'ws-1',
      created_strategy: true,
      strategy: {
        id: 'strategy-1',
        user_id: 'user-1',
        name: 'AI策略 - 双均线',
        description: '一个测试策略草案',
        code: 'class Demo(bt.Strategy):\n    pass',
        params: {
          fast_period: { type: 'int', default: 10 },
        },
        category: 'trend',
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
      unit: {
        id: 'unit-1',
        workspace_id: 'ws-1',
        group_name: 'AI策略 - 双均线',
        strategy_id: 'strategy-1',
        strategy_name: 'AI策略 - 双均线',
        symbol: '600519.SH',
        symbol_name: '',
        timeframe: '1d',
        timeframe_n: 1,
        category: 'trend',
        sort_order: 0,
        data_config: {},
        unit_settings: {},
        params: { fast_period: 10 },
        optimization_config: {},
        trading_mode: 'paper',
        gateway_config: {},
        lock_trading: false,
        lock_running: false,
        trading_instance_id: null,
        trading_snapshot: {},
        run_status: 'idle',
        run_count: 0,
        last_run_time: null,
        last_task_id: null,
        last_optimization_task_id: null,
        bar_count: null,
        position_size: null,
        entry_price: null,
        last_price: null,
        pnl: null,
        pnl_pct: null,
        market_value: null,
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
    })

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()

    const addButton = wrapper.findAll('button').find(button => button.text().includes('添加到工作区'))
    expect(addButton).toBeTruthy()
    await addButton!.trigger('click')
    await flushPromises()

    expect(workspaceApiMocks.list).toHaveBeenCalledWith(0, 100, 'research')

    const symbolInput = wrapper.find('input[placeholder="例如 600519.SH"]')
    await symbolInput.setValue('600519.SH')

    const confirmButton = wrapper.findAll('button').find(button => button.text().includes('确认添加'))
    expect(confirmButton).toBeTruthy()
    await confirmButton!.trigger('click')

    expect(strategyApiMocks.addCopilotDraftToWorkspace).toHaveBeenCalledWith('ws-1', {
      strategy_draft: {
        name: 'AI策略 - 双均线',
        description: '一个测试策略草案',
        code: 'class Demo(bt.Strategy):\n    pass',
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
        rationale: '用于测试保存策略按钮',
        next_steps: ['继续完善'],
        suggested_symbol: null,
        suggested_timeframe: '1d',
      },
      strategy_id: null,
      symbol: '600519.SH',
      symbol_name: '',
      timeframe: '1d',
      timeframe_n: 1,
      group_name: 'AI策略 - 双均线',
    })
  })

  it('adds an assistant draft and starts backtest immediately', async () => {
    vi.useFakeTimers()
    strategyApiMocks.backtestCopilotDraft.mockResolvedValue({
      workspace_id: 'ws-1',
      created_strategy: true,
      strategy: {
        id: 'strategy-1',
        user_id: 'user-1',
        name: 'AI策略 - 双均线',
        description: '一个测试策略草案',
        code: 'class Demo(bt.Strategy):\n    pass',
        params: {
          fast_period: { type: 'int', default: 10 },
        },
        category: 'trend',
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
      unit: {
        id: 'unit-1',
        workspace_id: 'ws-1',
        group_name: 'AI策略 - 双均线',
        strategy_id: 'strategy-1',
        strategy_name: 'AI策略 - 双均线',
        symbol: '600519.SH',
        symbol_name: '',
        timeframe: '1d',
        timeframe_n: 1,
        category: 'trend',
        sort_order: 0,
        data_config: {},
        unit_settings: {},
        params: { fast_period: 10 },
        optimization_config: {},
        trading_mode: 'paper',
        gateway_config: {},
        lock_trading: false,
        lock_running: false,
        trading_instance_id: null,
        trading_snapshot: {},
        run_status: 'running',
        run_count: 0,
        last_run_time: null,
        last_task_id: 'task-1',
        last_optimization_task_id: null,
        bar_count: null,
        position_size: null,
        entry_price: null,
        last_price: null,
        pnl: null,
        pnl_pct: null,
        market_value: null,
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
      run_result: {
        unit_id: 'unit-1',
        task_id: 'task-1',
        status: 'running',
        error: null,
      },
      unit_status: null,
      report_ready: false,
      report: null,
    })

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()

    const addButton = wrapper.findAll('button').find(button => button.text().includes('添加到工作区'))
    expect(addButton).toBeTruthy()
    await addButton!.trigger('click')
    await flushPromises()

    const symbolInput = wrapper.find('input[placeholder="例如 600519.SH"]')
    await symbolInput.setValue('600519.SH')

    const confirmButton = wrapper.findAll('button').find(button => button.text().includes('添加并回测'))
    expect(confirmButton).toBeTruthy()
    await confirmButton!.trigger('click')

    expect(strategyApiMocks.backtestCopilotDraft).toHaveBeenCalledWith('ws-1', {
      strategy_draft: expect.any(Object),
      strategy_id: null,
      symbol: '600519.SH',
      symbol_name: '',
      timeframe: '1d',
      timeframe_n: 1,
      group_name: 'AI策略 - 双均线',
      parallel: false,
      report_config: {
        calc_method: 'simple',
        annual_days: 252,
        weight_mode: 'equal',
      },
    })
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(workspaceApiMocks.getUnitsStatus).toHaveBeenCalledWith('ws-1')
    expect(workspaceApiMocks.createReport).toHaveBeenCalledWith('ws-1', {
      calc_method: 'simple',
      annual_days: 252,
      weight_mode: 'equal',
    })
    expect(wrapper.text()).toContain('最新报告摘要')
    expect(wrapper.text()).toContain('AI复盘建议')

    vi.useRealTimers()
  })

  it('creates a workspace report for a completed draft unit', async () => {
    strategyApiMocks.addCopilotDraftToWorkspace.mockResolvedValue({
      workspace_id: 'ws-1',
      created_strategy: true,
      strategy: {
        id: 'strategy-1',
        user_id: 'user-1',
        name: 'AI策略 - 双均线',
        description: '一个测试策略草案',
        code: 'class Demo(bt.Strategy):\n    pass',
        params: {
          fast_period: { type: 'int', default: 10 },
        },
        category: 'trend',
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
      unit: {
        id: 'unit-1',
        workspace_id: 'ws-1',
        group_name: 'AI策略 - 双均线',
        strategy_id: 'strategy-1',
        strategy_name: 'AI策略 - 双均线',
        symbol: '600519.SH',
        symbol_name: '',
        timeframe: '1d',
        timeframe_n: 1,
        category: 'trend',
        sort_order: 0,
        data_config: {},
        unit_settings: {},
        params: { fast_period: 10 },
        optimization_config: {},
        trading_mode: 'paper',
        gateway_config: {},
        lock_trading: false,
        lock_running: false,
        trading_instance_id: null,
        trading_snapshot: {},
        run_status: 'idle',
        run_count: 0,
        last_run_time: null,
        last_task_id: null,
        last_optimization_task_id: null,
        bar_count: null,
        position_size: null,
        entry_price: null,
        last_price: null,
        pnl: null,
        pnl_pct: null,
        market_value: null,
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
    })

    const wrapper = mount(AIChatPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()

    const addButton = wrapper.findAll('button').find(button => button.text().includes('添加到工作区'))
    expect(addButton).toBeTruthy()
    await addButton!.trigger('click')
    await flushPromises()

    const symbolInput = wrapper.find('input[placeholder="例如 600519.SH"]')
    await symbolInput.setValue('600519.SH')

    const confirmButton = wrapper.findAll('button').find(button => button.text().includes('确认添加'))
    expect(confirmButton).toBeTruthy()
    await confirmButton!.trigger('click')
    await flushPromises()

    const reportButton = wrapper.findAll('button').find(button => button.text().includes('生成报告'))
    expect(reportButton).toBeTruthy()
    await reportButton!.trigger('click')
    await flushPromises()

    expect(workspaceApiMocks.createReport).toHaveBeenCalledWith('ws-1', {
      calc_method: 'simple',
      annual_days: 252,
      weight_mode: 'equal',
    })
    expect(wrapper.text()).toContain('AI复盘建议')
  })
})
