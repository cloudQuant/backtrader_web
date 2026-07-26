import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { knowledgeBaseApi } from '@/api/knowledgeBase'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

vi.mock('@/api/knowledgeBase', () => ({
  knowledgeBaseApi: {
    list: vi.fn(),
    listDocuments: vi.fn(),
    getDocument: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    createDocument: vi.fn(),
    updateDocument: vi.fn(),
    deleteDocument: vi.fn(),
  },
}))

const baseKb = {
  id: 'kb-1',
  owner_id: 'user-1',
  name: '知识库1',
  description: '描述',
  document_count: 0,
  is_public: false,
  created_at: '2026-04-23T00:00:00Z',
  updated_at: '2026-04-23T00:00:00Z',
}

const baseDoc = {
  id: 'doc-1',
  knowledge_base_id: 'kb-1',
  title: '文档1',
  content: '内容',
  content_type: 'markdown' as const,
  file_path: null,
  is_folder: false,
  parent_id: null,
  sort_order: 0,
  status: 'draft' as const,
  index_status: 'not_indexed' as const,
  indexed_at: null,
  metadata: null,
  created_at: '2026-04-23T00:00:00Z',
  updated_at: '2026-04-23T00:00:00Z',
}

const baseDocSummary = {
  id: 'doc-1',
  knowledge_base_id: 'kb-1',
  title: '文档1',
  content_type: 'markdown' as const,
  file_path: null,
  is_folder: false,
  parent_id: null,
  sort_order: 0,
  status: 'draft' as const,
  index_status: 'not_indexed' as const,
  indexed_at: null,
  metadata: null,
  has_content: true,
  content_length: 2,
  created_at: '2026-04-23T00:00:00Z',
  updated_at: '2026-04-23T00:00:00Z',
}

describe('useKnowledgeBaseStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    // Reset implementations between tests too — some tests use
    // mockImplementation() which persists across vi.clearAllMocks().
    vi.mocked(knowledgeBaseApi.list).mockReset()
    vi.mocked(knowledgeBaseApi.listDocuments).mockReset()
    vi.mocked(knowledgeBaseApi.getDocument).mockReset()
    vi.mocked(knowledgeBaseApi.update).mockReset()
    vi.mocked(knowledgeBaseApi.delete).mockReset()
    vi.mocked(knowledgeBaseApi.createDocument).mockReset()
    vi.mocked(knowledgeBaseApi.updateDocument).mockReset()
    vi.mocked(knowledgeBaseApi.deleteDocument).mockReset()
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

    expect(knowledgeBaseApi.list).toHaveBeenCalledWith({ limit: 100 })
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
          ...baseDocSummary,
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

  it('fetchDocumentDetail should load and cache the selected document body', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1,
      skip: 0,
      limit: 20,
      items: [{ ...baseKb }],
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({
      total: 2,
      items: [
        { ...baseDocSummary },
        { ...baseDocSummary, id: 'doc-2', title: '文档2' },
      ],
    })
    vi.mocked(knowledgeBaseApi.getDocument).mockResolvedValue({ ...baseDoc, content: '完整正文' })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    const detail = await store.fetchDocumentDetail('doc-1')

    expect(knowledgeBaseApi.getDocument).toHaveBeenCalledWith('kb-1', 'doc-1')
    expect(detail?.content).toBe('完整正文')
    expect(store.currentDocument?.content).toBe('完整正文')
    expect(store.documents[0].content).toBe('完整正文')
    expect(store.documents[1].title).toBe('文档2')

    store.clearCurrentDocument()
    expect(store.currentDocument).toBeNull()
  })

  it('fetchDocumentDetail returns null without a selected knowledge base', async () => {
    const store = useKnowledgeBaseStore()

    const detail = await store.fetchDocumentDetail('doc-1')

    expect(detail).toBeNull()
    expect(store.currentDocument).toBeNull()
    expect(store.documentDetailLoading).toBe(false)
    expect(knowledgeBaseApi.getDocument).not.toHaveBeenCalled()
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
          ...baseDocSummary,
        },
        {
          ...baseDocSummary,
          id: 'doc-2',
          title: '新文档',
          sort_order: 1,
          content_length: 3,
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

  it('selectKnowledgeBase sets currentKnowledgeBase to null when not found', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1, skip: 0, limit: 20, items: [{ ...baseKb }],
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({ total: 0, items: [] })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('does-not-exist')
    expect(store.currentKnowledgeBase).toBeNull()
  })

  it('updateKnowledgeBase refetches list and updates currentKnowledgeBase when matching id', async () => {
    vi.mocked(knowledgeBaseApi.list)
      .mockResolvedValueOnce({ total: 1, skip: 0, limit: 20, items: [{ ...baseKb }] })
      .mockResolvedValueOnce({
        total: 1,
        skip: 0,
        limit: 20,
        items: [{ ...baseKb, name: '已更新' }],
      })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({ total: 0, items: [] })
    vi.mocked(knowledgeBaseApi.update).mockResolvedValue({ ...baseKb, name: '已更新' })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    const result = await store.updateKnowledgeBase('kb-1', { name: '已更新' })

    expect(result.name).toBe('已更新')
    expect(knowledgeBaseApi.update).toHaveBeenCalledWith('kb-1', { name: '已更新' })
    expect(store.currentKnowledgeBase?.name).toBe('已更新')
  })

  it('updateKnowledgeBase does not change currentKnowledgeBase when ids differ', async () => {
    const otherKb = { ...baseKb, id: 'kb-2', name: '其他' }
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 2, skip: 0, limit: 20, items: [{ ...baseKb }, otherKb],
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({ total: 0, items: [] })
    vi.mocked(knowledgeBaseApi.update).mockResolvedValue(otherKb)

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    await store.updateKnowledgeBase('kb-2', { name: '改其他' })
    // current still kb-1
    expect(store.currentKnowledgeBase?.id).toBe('kb-1')
  })

  it('deleteKnowledgeBase clears current and selects first remaining', async () => {
    const kb2 = { ...baseKb, id: 'kb-2', name: 'kb2' }
    vi.mocked(knowledgeBaseApi.list)
      .mockResolvedValueOnce({ total: 2, skip: 0, limit: 20, items: [{ ...baseKb }, kb2] })
      .mockResolvedValueOnce({ total: 1, skip: 0, limit: 20, items: [kb2] })
      .mockResolvedValueOnce({ total: 1, skip: 0, limit: 20, items: [kb2] })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({ total: 0, items: [] })
    vi.mocked(knowledgeBaseApi.delete).mockResolvedValue(undefined as never)

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    const ok = await store.deleteKnowledgeBase('kb-1')

    expect(ok).toBe(true)
    expect(knowledgeBaseApi.delete).toHaveBeenCalledWith('kb-1')
    // After delete, store falls back to first remaining
    expect(store.currentKnowledgeBase?.id).toBe('kb-2')
  })

  it('deleteKnowledgeBase clears documents when no kb remains', async () => {
    let listCallCount = 0
    vi.mocked(knowledgeBaseApi.list).mockImplementation(async () => {
      listCallCount++
      if (listCallCount <= 1) {
        return { total: 1, skip: 0, limit: 20, items: [{ ...baseKb }] }
      }
      return { total: 0, skip: 0, limit: 20, items: [] }
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({
      total: 1,
      items: [{ ...baseDocSummary }],
    })
    vi.mocked(knowledgeBaseApi.delete).mockResolvedValue(undefined as never)

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    await store.deleteKnowledgeBase('kb-1')

    expect(store.currentKnowledgeBase).toBeNull()
    expect(store.documents).toEqual([])
  })

  it('deleteKnowledgeBase keeps current when deleting different kb', async () => {
    const kb2 = { ...baseKb, id: 'kb-2' }
    let listCallCount = 0
    vi.mocked(knowledgeBaseApi.list).mockImplementation(async () => {
      listCallCount++
      // first call after fetch returns both; subsequent (after delete) returns only kb-1
      if (listCallCount <= 1) {
        return { total: 2, skip: 0, limit: 20, items: [{ ...baseKb }, kb2] }
      }
      return { total: 1, skip: 0, limit: 20, items: [{ ...baseKb }] }
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({ total: 0, items: [] })
    vi.mocked(knowledgeBaseApi.delete).mockResolvedValue(undefined as never)

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    await store.deleteKnowledgeBase('kb-2')

    // Current still kb-1
    expect(store.currentKnowledgeBase?.id).toBe('kb-1')
  })

  it('createDocument returns null when no current knowledge base', async () => {
    const store = useKnowledgeBaseStore()
    const result = await store.createDocument({
      title: 't', content: 'c', content_type: 'markdown', is_folder: false, parent_id: null,
    })
    expect(result).toBeNull()
  })

  it('updateDocument returns null when no current knowledge base', async () => {
    const store = useKnowledgeBaseStore()
    const result = await store.updateDocument('doc-x', { title: 't' })
    expect(result).toBeNull()
  })

  it('updateDocument calls API and refreshes the documents list', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1, skip: 0, limit: 20, items: [{ ...baseKb }],
    })
    vi.mocked(knowledgeBaseApi.listDocuments).mockResolvedValue({
      total: 1,
      items: [{ ...baseDocSummary, title: '已更新' }],
    })
    vi.mocked(knowledgeBaseApi.updateDocument).mockResolvedValue({
      ...baseDoc,
      title: '已更新',
    })

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    const result = await store.updateDocument('doc-1', { title: '已更新' })

    expect(result?.title).toBe('已更新')
    expect(knowledgeBaseApi.updateDocument).toHaveBeenCalledWith('kb-1', 'doc-1', { title: '已更新' })
  })

  it('deleteDocument returns false when no current knowledge base', async () => {
    const store = useKnowledgeBaseStore()
    const result = await store.deleteDocument('doc-x')
    expect(result).toBe(false)
  })

  it('deleteDocument deletes via API and refreshes both lists', async () => {
    vi.mocked(knowledgeBaseApi.list).mockResolvedValue({
      total: 1, skip: 0, limit: 20, items: [{ ...baseKb }],
    })
    vi.mocked(knowledgeBaseApi.listDocuments)
      .mockResolvedValueOnce({ total: 1, items: [{ ...baseDocSummary }] })
      .mockResolvedValueOnce({ total: 0, items: [] })
    vi.mocked(knowledgeBaseApi.getDocument).mockResolvedValue({ ...baseDoc })
    vi.mocked(knowledgeBaseApi.deleteDocument).mockResolvedValue(undefined as never)

    const store = useKnowledgeBaseStore()
    await store.fetchKnowledgeBases()
    await store.selectKnowledgeBase('kb-1')
    await store.fetchDocumentDetail('doc-1')
    expect(store.currentDocument?.id).toBe('doc-1')

    const result = await store.deleteDocument('doc-1')

    expect(result).toBe(true)
    expect(knowledgeBaseApi.deleteDocument).toHaveBeenCalledWith('kb-1', 'doc-1')
    expect(store.currentDocument).toBeNull()
    expect(store.documents).toHaveLength(0)
  })
})
