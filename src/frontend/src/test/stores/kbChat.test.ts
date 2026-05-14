import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { kbChatApi } from '@/api/kbChat'
import { useKBChatStore } from '@/stores/kbChat'

vi.mock('@/api/kbChat', () => ({
  kbChatApi: {
    listConversations: vi.fn(),
    getHistory: vi.fn(),
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
      assistant_mode: 'backtrader_strategy',
      thinking_mode: true,
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
          created_at: '2026-04-23T00:00:01Z',
        },
      ],
    })

    const store = useKBChatStore()
    await store.fetchHistory('conv-1')

    expect(store.currentConversationId).toBe('conv-1')
    expect(store.messages).toHaveLength(2)
    expect(store.messages[1].content).toBe('历史回答')
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
})
