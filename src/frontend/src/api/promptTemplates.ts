import request from '@/api/index'

export type PromptTemplateStatus = 'draft' | 'active' | 'archived'

export interface PromptTemplate {
  id: string
  name: string
  version: string
  content: string
  status: PromptTemplateStatus
  variables: string[]
  rollout_percentage: number
  created_at: string
  created_by?: string | null
}

export interface PromptTemplateCreatePayload {
  name: string
  version: string
  content: string
  variables: string[]
  rollout_percentage?: number
  status?: PromptTemplateStatus
}

export interface PromptTemplateTestResponse {
  template_id: string
  name: string
  version: string
  rendered_prompt: string
  missing_variables: string[]
}

export const promptTemplatesApi = {
  list() {
    return request.get<{ items: PromptTemplate[] }>('/admin/prompt-templates')
  },
  create(payload: PromptTemplateCreatePayload) {
    return request.post<PromptTemplate>('/admin/prompt-templates', payload)
  },
  activate(id: string) {
    return request.patch<PromptTemplate>(`/admin/prompt-templates/${id}/activate`)
  },
  test(id: string, variables: Record<string, string>) {
    return request.post<PromptTemplateTestResponse>(`/admin/prompt-templates/${id}/test`, {
      variables,
    })
  },
}
