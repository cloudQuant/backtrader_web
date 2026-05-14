import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { knowledgeBaseApi } from '@/api/knowledgeBase'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

vi.mock('@/api/knowledgeBase', () => ({
  knowledgeBaseApi: {
    list: vi.fn(),
    listDocuments: vi.fn(),
    createDocument: vi.fn(),
  },
}))

describe('useKnowledgeBaseStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchKnowledgeBases should populate list', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1,
      skip: 0,
      limit: 20,
      items: [
        {
          id: 'kb-1',
          owner_id: 'user-1',
          name: '知识库1',
          description: '描述',
          document_count: 0,
          is_public: false,
          created_at: '2026-04-23T00:00:00Z',
          updated_at: '2026-04-23T00:00:00Z',
        },
      ],
    })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()

    expect(store.knowledgeBases).toHaveLength(1)
    expect(store.knowledgeBases[0].id).toBe('kb-1')
  })

  it('selectKnowledgeBase should load documents', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1,
      skip: 0,
      limit: 20,
      items: [
        {
          id: 'kb-1',
          owner_id: 'user-1',
          name: '知识库1',
          description: '描述',
          document_count: 1,
          is_public: false,
          created_at: '2026-04-23T00:00:00Z',
          updated_at: '2026-04-23T00:00:00Z',
        },
      ],
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'doc-1',
          knowledge_base_id: 'kb-1',
          title: '文档1',
          content: '内容',
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
    })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')

    expect(store.currentKnowledgeBase?.id).toBe('kb-1')
    expect(store.documents).toHaveLength(1)
    expect(store.documents[0].id).toBe('doc-1')
  })

  it('createDocument should create and refresh current knowledge base documents', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1,
      skip: 0,
      limit: 20,
      items: [
        {
          id: 'kb-1',
          owner_id: 'user-1',
          name: '知识库1',
          description: '描述',
          document_count: 2,
          is_public: false,
          created_at: '2026-04-23T00:00:00Z',
          updated_at: '2026-04-23T00:00:00Z',
        },
      ],
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({
      total: 2,
      items: [
        {
          id: 'doc-1',
          knowledge_base_id: 'kb-1',
          title: '文档1',
          content: '内容',
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
        {
          id: 'doc-2',
          knowledge_base_id: 'kb-1',
          title: '新文档',
          content: '新内容',
          content_type: 'markdown',
          file_path: null,
          is_folder: false,
          parent_id: null,
          sort_order: 1,
          status: 'draft',
          index_status: 'not_indexed',
          indexed_at: null,
          metadata: null,
          created_at: '2026-04-23T00:00:00Z',
          updated_at: '2026-04-23T00:00:00Z',
        },
      ],
    })
    vi.mocked(knowledgeBaseApi.createDocument).mockResolvedValue({
      id: 'doc-2',
      knowledge_base_id: 'kb-1',
      title: '新文档',
      content: '新内容',
      content_type: 'markdown',
      file_path: null,
      is_folder: false,
      parent_id: null,
      sort_order: 1,
      status: 'draft',
      index_status: 'not_indexed',
      indexed_at: null,
      metadata: null,
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    const created = await store.createDocument({
      title: '新文档',
      content: '新内容',
      content_type: 'markdown',
      is_folder: false,
      parent_id: null,
    })

    expect(created?.id).toBe('doc-2')
    expect(knowledgeBaseApi.createDocument).toHaveBeenCalledWith('kb-1', expect.objectContaining({ title: '新文档' }))
    expect(store.documents).toHaveLength(2)
  })
})
