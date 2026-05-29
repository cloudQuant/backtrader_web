/**
 * Smoke tests for src/api/kbChat.ts (knowledge-base chat client).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('kbChatApi', () => {
  beforeEach(() => vi.clearAllMocks())

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
  })

  it('getHistory GETs with the conversation id in path', async () => {
    const { kbChatApi } = await import('@/api/kbChat')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)

    await kbChatApi.getHistory('conv-1')
    expect(get).toHaveBeenCalledWith('/kb-chat/history/conv-1')
  })

  it('send POSTs to /kb-chat/send with the request body', async () => {
    const { kbChatApi } = await import('@/api/kbChat')
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
    })
  })
})
