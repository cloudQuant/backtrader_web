import api from './index'

export type KnowledgeBaseRetrievalProfile = 'quant_research' | 'precision' | 'exploration'
export type KnowledgeBaseSearchMode = 'hybrid' | 'keyword'
export type KnowledgeBaseQuantFocus =
  | 'general'
  | 'strategy_research'
  | 'strategy_review'
  | 'implementation'

export interface KnowledgeBaseSettings {
  retrieval_profile: KnowledgeBaseRetrievalProfile
  search_mode: KnowledgeBaseSearchMode
  default_top_k: number
  min_similarity: number
  title_weight: number
  keyword_weight: number
  phrase_weight: number
  recency_weight: number
  max_context_chunks: number
  use_conversation_memory: boolean
  conversation_lookback_messages: number
  prioritize_title_matches: boolean
  prefer_recent_documents: boolean
  quant_focus: KnowledgeBaseQuantFocus
  system_prompt_suffix?: string | null
}

export interface KnowledgeBaseItem {
  id: string
  owner_id: string
  name: string
  description?: string | null
  document_count: number
  is_public: boolean
  settings?: KnowledgeBaseSettings | null
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseListResponse {
  total: number
  items: KnowledgeBaseItem[]
  skip: number
  limit: number
}

export interface KnowledgeBaseUpdateRequest {
  name?: string
  description?: string | null
  is_public?: boolean
  settings?: Partial<KnowledgeBaseSettings>
}

export interface KBDocumentSummaryItem {
  id: string
  knowledge_base_id: string
  title: string
  content_type: string
  file_path?: string | null
  is_folder: boolean
  parent_id?: string | null
  sort_order: number
  status: string
  index_status: string
  indexed_at?: string | null
  metadata?: Record<string, unknown> | null
  has_content?: boolean
  content_length?: number
  created_at: string
  updated_at: string
}

export interface KBDocumentItem extends KBDocumentSummaryItem {
  content?: string | null
}

export interface KBDocumentListResponse {
  total: number
  items: KBDocumentSummaryItem[]
}

export interface KBDocumentCreateRequest {
  title: string
  content?: string | null
  content_type: string
  is_folder: boolean
  parent_id?: string | null
}

export interface KBDocumentUpdateRequest {
  title?: string
  content?: string | null
  content_type?: string
  status?: string
  parent_id?: string | null
  sort_order?: number
  index_status?: string
}

export const knowledgeBaseApi = {
  list(params?: { skip?: number; limit?: number; search?: string }) {
    return api.get<KnowledgeBaseListResponse>('/knowledge-base/', { params })
  },
  update(knowledgeBaseId: string, data: KnowledgeBaseUpdateRequest) {
    return api.put<KnowledgeBaseItem>(`/knowledge-base/${knowledgeBaseId}`, data)
  },
  delete(knowledgeBaseId: string) {
    return api.delete<{ message: string }>(`/knowledge-base/${knowledgeBaseId}`)
  },
  listDocuments(knowledgeBaseId: string) {
    return api.get<KBDocumentListResponse>(`/knowledge-base/${knowledgeBaseId}/documents/`)
  },
  getDocument(knowledgeBaseId: string, documentId: string) {
    return api.get<KBDocumentItem>(`/knowledge-base/${knowledgeBaseId}/documents/${documentId}`)
  },
  getDocumentSourceFile(knowledgeBaseId: string, documentId: string) {
    return api.get<Blob>(`/knowledge-base/${knowledgeBaseId}/documents/${documentId}/source-file`, {
      responseType: 'blob',
    })
  },
  createDocument(knowledgeBaseId: string, data: KBDocumentCreateRequest) {
    return api.post<KBDocumentItem>(`/knowledge-base/${knowledgeBaseId}/documents/`, data)
  },
  updateDocument(knowledgeBaseId: string, documentId: string, data: KBDocumentUpdateRequest) {
    return api.put<KBDocumentItem>(`/knowledge-base/${knowledgeBaseId}/documents/${documentId}`, data)
  },
  deleteDocument(knowledgeBaseId: string, documentId: string) {
    return api.delete<{ message: string }>(`/knowledge-base/${knowledgeBaseId}/documents/${documentId}`)
  },
}
