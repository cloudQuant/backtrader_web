import { beforeEach, describe, expect, it, vi } from 'vitest'

import request from '@/api/index'
import { promptTemplatesApi } from '@/api/promptTemplates'

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

describe('promptTemplatesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads admin prompt templates', async () => {
    vi.mocked(request.get).mockResolvedValue({ items: [] })

    await promptTemplatesApi.list()

    expect(request.get).toHaveBeenCalledWith('/admin/prompt-templates')
  })

  it('creates prompt template with rollout percentage', async () => {
    vi.mocked(request.post).mockResolvedValue({ id: 'tpl-1' })

    await promptTemplatesApi.create({
      name: 'knowledge_qa',
      version: 'canary',
      content: '灰度模板 {{question}}',
      variables: ['question'],
      rollout_percentage: 25,
    })

    expect(request.post).toHaveBeenCalledWith('/admin/prompt-templates', {
      name: 'knowledge_qa',
      version: 'canary',
      content: '灰度模板 {{question}}',
      variables: ['question'],
      rollout_percentage: 25,
    })
  })

  it('activates prompt template version', async () => {
    vi.mocked(request.patch).mockResolvedValue({ id: 'tpl-1', status: 'active' })

    await promptTemplatesApi.activate('tpl-1')

    expect(request.patch).toHaveBeenCalledWith('/admin/prompt-templates/tpl-1/activate')
  })

  it('tests prompt template rendering', async () => {
    vi.mocked(request.post).mockResolvedValue({ rendered_prompt: 'rendered' })

    await promptTemplatesApi.test('tpl-1', { question: 'hello' })

    expect(request.post).toHaveBeenCalledWith('/admin/prompt-templates/tpl-1/test', {
      variables: { question: 'hello' },
    })
  })
})
