/**
 * Smoke tests for src/api/knowledgeBase.ts.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
  },
}))

vi.mock('@/utils/session', () => ({
  getAccessToken: vi.fn(() => 'mock-token'),
}))

describe('knowledgeBaseApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('list GETs /knowledge-base/ with optional params', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)

    await knowledgeBaseApi.list()
    expect(get).toHaveBeenCalledWith('/knowledge-base/', { params: undefined })

    await knowledgeBaseApi.list({ skip: 0, limit: 20, search: 'q' })
    expect(get).toHaveBeenCalledWith('/knowledge-base/', { params: { skip: 0, limit: 20, search: 'q' } })
  })

  it('update PUTs to /knowledge-base/:id', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const put = vi.mocked(apiModule.put).mockResolvedValue({} as never)

    await knowledgeBaseApi.update('kb-1', { name: 'updated' })
    expect(put).toHaveBeenCalledWith('/knowledge-base/kb-1', { name: 'updated' })
  })

  it('delete DELETEs /knowledge-base/:id', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const del = vi.mocked(apiModule.delete).mockResolvedValue({} as never)

    await knowledgeBaseApi.delete('kb-1')
    expect(del).toHaveBeenCalledWith('/knowledge-base/kb-1')
  })

  it('listDocuments GETs /knowledge-base/:id/documents/', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)

    await knowledgeBaseApi.listDocuments('kb-1')
    expect(get).toHaveBeenCalledWith('/knowledge-base/kb-1/documents/')
  })

  it('getDocument GETs /knowledge-base/:kbId/documents/:docId', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)

    await knowledgeBaseApi.getDocument('kb-1', 'doc-1')
    expect(get).toHaveBeenCalledWith('/knowledge-base/kb-1/documents/doc-1')
  })

  it('createDocument POSTs to /knowledge-base/:id/documents/', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)

    const payload = { title: 'doc', content_type: 'markdown', is_folder: false }
    await knowledgeBaseApi.createDocument('kb-1', payload)
    expect(post).toHaveBeenCalledWith('/knowledge-base/kb-1/documents/', payload)
  })

  it('updateDocument PUTs the document path', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const put = vi.mocked(apiModule.put).mockResolvedValue({} as never)

    await knowledgeBaseApi.updateDocument('kb-1', 'doc-1', { title: 'new' })
    expect(put).toHaveBeenCalledWith('/knowledge-base/kb-1/documents/doc-1', { title: 'new' })
  })

  it('deleteDocument DELETEs the document path', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const apiModule = (await import('@/api/index')).default
    const del = vi.mocked(apiModule.delete).mockResolvedValue({} as never)

    await knowledgeBaseApi.deleteDocument('kb-1', 'doc-1')
    expect(del).toHaveBeenCalledWith('/knowledge-base/kb-1/documents/doc-1')
  })

  it('getDocumentSourceFile GETs the blob and adds Authorization header', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const axiosModule = (await import('axios')).default
    const get = vi.mocked(axiosModule.get).mockResolvedValue({ data: new Blob(['hello']) } as never)

    const result = await knowledgeBaseApi.getDocumentSourceFile('kb-1', 'doc-1')
    expect(get).toHaveBeenCalledWith(
      '/api/v1/knowledge-base/kb-1/documents/doc-1/source-file',
      { responseType: 'blob', headers: { Authorization: 'Bearer mock-token' } },
    )
    expect(result).toBeInstanceOf(Blob)
  })

  it('getDocumentSourceFile uses empty bearer when token is missing', async () => {
    const { knowledgeBaseApi } = await import('@/api/knowledgeBase')
    const axiosModule = (await import('axios')).default
    const sessionUtils = await import('@/utils/session')
    vi.mocked(sessionUtils.getAccessToken).mockReturnValueOnce(null)
    const get = vi.mocked(axiosModule.get).mockResolvedValue({ data: new Blob() } as never)

    await knowledgeBaseApi.getDocumentSourceFile('kb-1', 'doc-1')
    expect(get).toHaveBeenCalledWith(
      '/api/v1/knowledge-base/kb-1/documents/doc-1/source-file',
      { responseType: 'blob', headers: { Authorization: 'Bearer ' } },
    )
  })
})
