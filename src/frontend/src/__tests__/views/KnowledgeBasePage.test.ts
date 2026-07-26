import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import KnowledgeBasePage from '@/views/KnowledgeBasePage.vue'
import { elStubs } from '@/test/stubs'

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

const mocks = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn().mockResolvedValue(undefined),
  selectKnowledgeBase: vi.fn().mockResolvedValue(undefined),
  fetchDocumentDetail: vi.fn().mockResolvedValue(undefined),
  clearCurrentDocument: vi.fn(),
  updateKnowledgeBase: vi.fn().mockResolvedValue(undefined),
  deleteKnowledgeBase: vi.fn().mockResolvedValue(true),
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
      title: '文档1',
      content: '文档内容',
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
}))

vi.mock('@/stores/knowledgeBase', () => ({
  useKnowledgeBaseStore: () => ({
    knowledgeBases: mocks.knowledgeBases,
    currentKnowledgeBase: mocks.knowledgeBases[0],
    documents: mocks.documents,
    currentDocument: mocks.documents[0],
    loading: false,
    documentDetailLoading: false,
    fetchKnowledgeBases: mocks.fetchKnowledgeBases,
    selectKnowledgeBase: mocks.selectKnowledgeBase,
    fetchDocumentDetail: mocks.fetchDocumentDetail,
    clearCurrentDocument: mocks.clearCurrentDocument,
    updateKnowledgeBase: mocks.updateKnowledgeBase,
    deleteKnowledgeBase: mocks.deleteKnowledgeBase,
  }),
}))

describe('KnowledgeBasePage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mocks.fetchKnowledgeBases.mockResolvedValue(undefined)
    mocks.selectKnowledgeBase.mockResolvedValue(undefined)
    mocks.fetchDocumentDetail.mockResolvedValue(undefined)
    mocks.clearCurrentDocument.mockClear()
    mocks.updateKnowledgeBase.mockResolvedValue(undefined)
    mocks.deleteKnowledgeBase.mockResolvedValue(true)
  })

  it('loads knowledge bases on mount', () => {
    mount(KnowledgeBasePage, { global: { stubs: { ...elStubs } } })
    expect(mocks.fetchKnowledgeBases).toHaveBeenCalled()
  })

  it('renders knowledge base and document title', () => {
    const wrapper = mount(KnowledgeBasePage, { global: { stubs: { ...elStubs } } })
    expect(wrapper.text()).toContain('知识库1')
    expect(wrapper.text()).toContain('文档1')
    expect(wrapper.text()).toContain('树视图')
    expect(wrapper.text()).toContain('表格视图')
    expect(wrapper.text()).toContain('导入文档')
    expect(wrapper.text()).toContain('新建文件夹')
    expect(wrapper.text()).toContain('全选当前视图')
    expect(wrapper.text()).toContain('批量删除')
    expect(wrapper.text()).toContain('操作')
    expect(wrapper.text()).toContain('按排序')
    expect(wrapper.text()).toContain('⋯')
    expect(wrapper.text()).toContain('重命名')
    expect(wrapper.text()).toContain('删除')
  })

  it('renders document status metadata for ReqDocs-like detail view', () => {
    const wrapper = mount(KnowledgeBasePage, { global: { stubs: { ...elStubs } } })
    expect(wrapper.text()).toContain('not_indexed')
    expect(wrapper.text()).toContain('markdown')
  })
})
