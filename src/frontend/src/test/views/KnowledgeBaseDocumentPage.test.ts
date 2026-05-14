import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import KnowledgeBaseDocumentPage from '@/views/KnowledgeBaseDocumentPage.vue'
import { elStubs } from '@/test/stubs'

const routeMocks = vi.hoisted(() => ({
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routeMocks.push }),
  useRoute: () => ({ params: { kbId: 'kb-1', docId: 'doc-1' }, query: {} }),
}))

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api')
  return actual
})

vi.mock('@/api/knowledgeBase', () => ({
  knowledgeBaseApi: {
    getDocument: vi.fn().mockResolvedValue({
      id: 'doc-1',
      knowledge_base_id: 'kb-1',
      title: '文档1',
      content: '这是正文内容',
      content_type: 'markdown',
      file_path: null,
      is_folder: false,
      parent_id: null,
      sort_order: 0,
      status: 'draft',
      index_status: 'not_indexed',
      indexed_at: null,
      metadata: {
        reqdocs_source_filename: '文档1.pdf',
        reqdocs_source_mime_type: 'application/pdf',
      },
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z',
    }),
    getDocumentSourceFile: vi.fn().mockResolvedValue(new Blob(['pdf-bytes'], { type: 'application/pdf' })),
  },
}))

describe('KnowledgeBaseDocumentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads document and shows tabs with source file available', async () => {
    const wrapper = mount(KnowledgeBaseDocumentPage, { global: { stubs: { ...elStubs } } })
    await flushPromises()

    expect(wrapper.text()).toContain('文档1')
    expect(wrapper.text()).toContain('源文件')
    expect(wrapper.text()).toContain('Markdown')
    expect(wrapper.text()).toContain('文档摘要')
    expect(wrapper.text()).toContain('阅读建议')
    expect(wrapper.text()).toContain('文档1.pdf')
    expect(wrapper.text()).toContain('快捷 AI 问答')
  })

})
