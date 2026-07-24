/**
 * Smoke tests for src/api/kbChat.ts (knowledge-base chat client).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    delete: vi.fn(),
    post: vi.fn(),
  },
}))

describe('kbChatApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('listConversations GETs with knowledge_base_id and optional params', async () => {
    const { kbChatApi } = await import('@/api/kbChat')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)

    await kbChatApi.listConversations('kb-1')
    expect(get).toHaveBeenCalledWith('/kb-chat/conversations', {
      params: { knowledge_base_id: 'kb-1' },
    })

    await kbChatApi.listConversations('kb-1', { skip: 10, limit: 20 })
    expect(get).toHaveBeenCalledWith('/kb-chat/conversations', {
      params: { knowledge_base_id: 'kb-1', skip: 10, limit: 20 },
    })

    await kbChatApi.listConversations(null)
    expect(get).toHaveBeenCalledWith('/kb-chat/conversations', {
      params: {},
    })
  })

  it('getHistory GETs with the conversation id in path', async () => {
    const { kbChatApi } = await import('@/api/kbChat')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)

    await kbChatApi.getHistory('conv-1')
    expect(get).toHaveBeenCalledWith('/kb-chat/history/conv-1')
  })

  it('deleteConversation DELETEs the selected conversation', async () => {
    const { kbChatApi } = await import('@/api/kbChat')
    const apiModule = (await import('@/api/index')).default
    const remove = vi.mocked(apiModule.delete).mockResolvedValue({ message: 'Conversation deleted' } as never)

    await kbChatApi.deleteConversation('conv-1')

    expect(remove).toHaveBeenCalledWith('/kb-chat/conversations/conv-1')
  })

  it('send POSTs to /kb-chat/send with the request body and extended timeout', async () => {
    const { KB_CHAT_SEND_TIMEOUT_MS, kbChatApi } = await import('@/api/kbChat')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)

    await kbChatApi.send({
      knowledge_base_id: 'kb-1',
      question: 'what is X?',
      conversation_id: 'conv-1',
      model_id: 'gpt-4',
      assistant_mode: 'knowledge_qa',
      thinking_mode: true,
    })
    expect(post).toHaveBeenCalledWith('/kb-chat/send', {
      knowledge_base_id: 'kb-1',
      question: 'what is X?',
      conversation_id: 'conv-1',
      model_id: 'gpt-4',
      assistant_mode: 'knowledge_qa',
      thinking_mode: true,
    }, {
      timeout: KB_CHAT_SEND_TIMEOUT_MS,
    })
  })

  it('send omits knowledge_base_id when assistant mode does not need one', async () => {
    const { KB_CHAT_SEND_TIMEOUT_MS, kbChatApi } = await import('@/api/kbChat')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)

    await kbChatApi.send({
      question: 'generate a dual moving average strategy',
      assistant_mode: 'backtrader_strategy',
    })
    expect(post).toHaveBeenCalledWith('/kb-chat/send', {
      question: 'generate a dual moving average strategy',
      conversation_id: undefined,
      model_id: undefined,
      assistant_mode: 'backtrader_strategy',
      thinking_mode: undefined,
    }, {
      timeout: KB_CHAT_SEND_TIMEOUT_MS,
    })
  })
})
