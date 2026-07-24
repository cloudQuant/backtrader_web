import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { kbChatApi } from '@/api/kbChat'
import { useKBChatStore } from '@/stores/kbChat'

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

vi.mock('@/api/kbChat', () => ({
  kbChatApi: {
    listConversations: vi.fn(),
    getHistory: vi.fn(),
    deleteConversation: vi.fn(),
    send: vi.fn(),
  },
}))

describe('useKBChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchConversations should populate conversations', async () => {
    vi.mocked(kbChatApi.listConversations).mockResolvedValue({
      items: [
        {
          id: 'conv-1',
          knowledge_base_id: 'kb-1',
          title: '新对话',
          model_id: null,
          created_at: '2026-04-23T00:00:00Z',
          updated_at: '2026-04-23T00:00:00Z',
        },
      ],
      total: 1,
    })

    const store = useKBChatStore()
    await store.fetchConversations('kb-1')

    expect(store.conversations).toHaveLength(1)
    expect(store.conversations[0].id).toBe('conv-1')
  })

  it('deleteConversation removes the active session and clears its messages', async () => {
    const store = useKBChatStore()
    store.conversations = [
      {
        id: 'conv-1',
        knowledge_base_id: 'kb-1',
        title: '待删除会话',
        model_id: null,
        created_at: '2026-04-23T00:00:00Z',
        updated_at: '2026-04-23T00:00:00Z',
      },
      {
        id: 'conv-2',
        knowledge_base_id: 'kb-1',
        title: '保留会话',
        model_id: null,
        created_at: '2026-04-24T00:00:00Z',
        updated_at: '2026-04-24T00:00:00Z',
      },
    ]
    store.currentConversationId = 'conv-1'
    store.messages = [{ role: 'user', content: '需要删除的内容' }]
    vi.mocked(kbChatApi.deleteConversation).mockResolvedValue({ message: 'Conversation deleted' })

    await store.deleteConversation('conv-1')

    expect(kbChatApi.deleteConversation).toHaveBeenCalledWith('conv-1')
    expect(store.conversations.map(conversation => conversation.id)).toEqual(['conv-2'])
    expect(store.currentConversationId).toBeNull()
    expect(store.messages).toEqual([])
  })

  it('sendMessage should append assistant response', async () => {
    vi.mocked(kbChatApi.send).mockResolvedValue({
      conversation_id: 'conv-1',
      answer: '双均线策略在上穿时开仓。',
      citations: [
        {
          document_id: 'doc-1',
          document_title: '双均线策略',
          chunk_id: 'chunk-1',
          chunk_index: 0,
          similarity: 1,
        },
      ],
      context_chunks_used: 1,
      tokens_used: 10,
      model_id: null,
      assistant_mode: 'backtrader_strategy',
      strategy_draft: {
        name: 'AI策略 - 双均线',
        description: '测试草案',
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
        rationale: '测试生成',
        next_steps: ['继续完善'],
        suggested_symbol: null,
        suggested_timeframe: '1d',
      },
      reasoning: null,
      reason_code: 'ai_not_configured',
      diagnostic_message: '当前系统未配置生成式 AI 模型，已降级返回最相关的知识库片段。',
    })

    const store = useKBChatStore()
    await store.sendMessage('kb-1', '开仓条件是什么？', {
      assistantMode: 'backtrader_strategy',
      thinkingMode: true,
    })

    expect(store.messages).toHaveLength(2)
    expect(store.messages[0].role).toBe('user')
    expect(store.messages[1].role).toBe('assistant')
    expect(store.messages[1].content).toContain('开仓')
    expect(store.messages[1].assistantMode).toBe('backtrader_strategy')
    expect(store.messages[1].strategyDraft?.name).toContain('AI策略')
    expect(store.messages[1].reasonCode).toBe('ai_not_configured')
    expect(store.messages[1].diagnosticMessage).toContain('未配置')
    expect(kbChatApi.send).toHaveBeenCalledWith({
      knowledge_base_id: 'kb-1',
      question: '开仓条件是什么？',
      conversation_id: null,
      model_id: undefined,
      assistant_mode: 'backtrader_strategy',
      thinking_mode: true,
    })
  })

  it('sendMessage should pass session model override', async () => {
    vi.mocked(kbChatApi.send).mockResolvedValue({
      conversation_id: 'conv-1',
      answer: '使用会话模型回答',
      citations: [],
      context_chunks_used: 0,
      tokens_used: 1,
      model_id: 'ollama/llama3.1:8b',
    })

    const store = useKBChatStore()
    await store.sendMessage('kb-1', '测试模型覆盖', {
      modelId: 'ollama::ollama/llama3.1:8b',
    })

    expect(kbChatApi.send).toHaveBeenCalledWith({
      knowledge_base_id: 'kb-1',
      question: '测试模型覆盖',
      conversation_id: null,
      model_id: 'ollama::ollama/llama3.1:8b',
      assistant_mode: undefined,
      thinking_mode: undefined,
    })
  })

  it('sendMessage should allow assistant modes without a knowledge base', async () => {
    vi.mocked(kbChatApi.send).mockResolvedValue({
      conversation_id: 'conv-standalone',
      answer: '已生成策略草案',
      citations: [],
      context_chunks_used: 0,
      tokens_used: 0,
      model_id: null,
      assistant_mode: 'backtrader_strategy',
      strategy_draft: null,
    })

    const store = useKBChatStore()
    await store.sendMessage(null, '生成双均线策略', {
      assistantMode: 'backtrader_strategy',
    })

    expect(kbChatApi.send).toHaveBeenCalledWith({
      question: '生成双均线策略',
      conversation_id: null,
      model_id: undefined,
      assistant_mode: 'backtrader_strategy',
      thinking_mode: undefined,
    })
    expect(kbChatApi.listConversations).toHaveBeenCalledWith(null)
  })

  it('fetchHistory should restore assistant mode and strategy draft metadata', async () => {
    vi.mocked(kbChatApi.getHistory).mockResolvedValue({
      conversation_id: 'conv-1',
      messages: [
        {
          id: 'msg-1',
          conversation_id: 'conv-1',
          role: 'assistant',
          content: '已生成策略草稿',
          assistant_mode: 'backtrader_strategy',
          strategy_draft: {
            name: 'AI策略 - 双均线',
            description: '测试草案',
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
            rationale: '用于测试历史恢复',
            next_steps: ['继续完善'],
            suggested_symbol: null,
            suggested_timeframe: '1d',
          },
          created_at: '2026-04-23T00:00:00Z',
        },
      ],
    })

    const store = useKBChatStore()
    await store.fetchHistory('conv-1')

    expect(store.messages[0].assistantMode).toBe('backtrader_strategy')
    expect(store.messages[0].strategyDraft?.name).toBe('AI策略 - 双均线')
  })

  it('sendMessage should keep stock analysis cards', async () => {
    vi.mocked(kbChatApi.send).mockResolvedValue({
      conversation_id: 'conv-stock',
      answer: '已完成 000001.SZ 的股票分析',
      citations: [],
      context_chunks_used: 0,
      tokens_used: 0,
      model_id: null,
      assistant_mode: 'stock_analysis',
      stock_analysis_task: {
        task_id: 'task-1',
        symbol: '000001.SZ',
        status: 'completed',
        progress: 100,
        current_step: 'completed',
        message: '股票分析已完成',
      },
      stock_analysis_report: {
        report_id: 'report-1',
        symbol: '000001.SZ',
        summary: '风险经理终审摘要',
        decision_label: '持有',
        risk_level: '中等',
        confidence_score: 0.68,
        export_formats: ['markdown', 'html', 'docx', 'pdf'],
      },
    } as any)

    const store = useKBChatStore()
    await store.sendMessage(null, '分析 000001.SZ', {
      assistantMode: 'stock_analysis',
    })

    expect(store.messages[1].assistantMode).toBe('stock_analysis')
    expect(store.messages[1].stockAnalysisTask?.task_id).toBe('task-1')
    expect(store.messages[1].stockAnalysisReport?.report_id).toBe('report-1')
  })

  it('sendMessage should pass stock analysis params', async () => {
    vi.mocked(kbChatApi.send).mockResolvedValue({
      conversation_id: 'conv-stock',
      answer: '已创建股票分析任务',
      citations: [],
      context_chunks_used: 0,
      tokens_used: 0,
      model_id: null,
      assistant_mode: 'stock_analysis',
      stock_analysis_task: {
        task_id: 'task-1',
        symbol: '000001.SZ',
        status: 'running',
        progress: 30,
      },
      stock_analysis_report: null,
    } as any)

    const store = useKBChatStore()
    await store.sendMessage(null, '分析 000001.SZ', {
      assistantMode: 'stock_analysis',
      stockAnalysisParams: {
        symbol: '000001.SZ',
        market_type: 'A股',
        analysis_date: '2026-06-15',
        research_depth: '标准',
        selected_modules: ['market', 'news', 'fundamentals', 'risk'],
        include_sentiment: false,
        include_risk: true,
        language: 'zh-CN',
      },
    })

    expect(kbChatApi.send).toHaveBeenCalledWith({
      question: '分析 000001.SZ',
      conversation_id: null,
      model_id: undefined,
      assistant_mode: 'stock_analysis',
      thinking_mode: undefined,
      stock_analysis_params: {
        symbol: '000001.SZ',
        market_type: 'A股',
        analysis_date: '2026-06-15',
        research_depth: '标准',
        selected_modules: ['market', 'news', 'fundamentals', 'risk'],
        include_sentiment: false,
        include_risk: true,
        language: 'zh-CN',
      },
    })
  })

  it('fetchHistory should populate messages and current conversation id', async () => {
    vi.mocked(kbChatApi.getHistory).mockResolvedValue({
      conversation_id: 'conv-1',
      messages: [
        {
          id: 'msg-1',
          conversation_id: 'conv-1',
          role: 'user',
          content: '历史问题',
          citations: null,
          tokens_used: null,
          model_id: null,
          reasoning: null,
          stock_analysis_task: null,
          stock_analysis_report: null,
          created_at: '2026-04-23T00:00:00Z',
        },
        {
          id: 'msg-2',
          conversation_id: 'conv-1',
          role: 'assistant',
          content: '历史回答',
          citations: [],
          tokens_used: 8,
          model_id: null,
          reasoning: null,
          stock_analysis_task: {
            task_id: 'task-1',
            symbol: '000001.SZ',
            status: 'completed',
            progress: 100,
          },
          stock_analysis_report: {
            report_id: 'report-1',
            symbol: '000001.SZ',
            summary: '历史股票分析',
            decision_label: '持有',
            risk_level: '中等',
            export_formats: ['markdown', 'html', 'docx', 'pdf'],
          },
          created_at: '2026-04-23T00:00:01Z',
        },
      ],
    })

    const store = useKBChatStore()
    await store.fetchHistory('conv-1')

    expect(store.currentConversationId).toBe('conv-1')
    expect(store.messages).toHaveLength(2)
    expect(store.messages[1].content).toBe('历史回答')
    expect(store.messages[1].stockAnalysisReport?.report_id).toBe('report-1')
  })

  it('fetchHistory should tolerate missing messages array', async () => {
    vi.mocked(kbChatApi.getHistory).mockResolvedValue({
      conversation_id: 'conv-1',
    } as any)

    const store = useKBChatStore()
    await store.fetchHistory('conv-1')

    expect(store.currentConversationId).toBe('conv-1')
    expect(store.messages).toEqual([])
  })

  it('sendMessage should keep assistant response when conversation refresh fails', async () => {
    vi.mocked(kbChatApi.send).mockResolvedValue({
      conversation_id: 'conv-1',
      answer: '已生成回答',
    } as any)
    vi.mocked(kbChatApi.listConversations).mockRejectedValue(new Error('list failed'))

    const store = useKBChatStore()
    await store.sendMessage('kb-1', '测试兼容')

    expect(store.currentConversationId).toBe('conv-1')
    expect(store.messages).toHaveLength(2)
    expect(store.messages[1]).toMatchObject({
      role: 'assistant',
      content: '已生成回答',
    })
  })

  it('sendMessage should append fallback assistant error when request fails', async () => {
    vi.mocked(kbChatApi.send).mockRejectedValue(new Error('boom'))
    const store = useKBChatStore()

    await expect(store.sendMessage('kb-1', '测试失败')).rejects.toThrow('boom')
    expect(store.messages.at(-1)?.role).toBe('assistant')
    expect(store.messages.at(-1)?.content).toContain('boom')
  })

  it('sendMessage should append friendly assistant error when request times out', async () => {
    vi.mocked(kbChatApi.send).mockRejectedValue(
      Object.assign(new Error('timeout of 120000ms exceeded'), { code: 'ECONNABORTED' }),
    )
    const store = useKBChatStore()

    await expect(store.sendMessage('kb-1', '测试超时')).rejects.toThrow('timeout')
    expect(store.messages.at(-1)?.role).toBe('assistant')
    expect(store.messages.at(-1)?.content).toContain('超时')
  })
})
