import api from './index'
import axios from 'axios'

import { getAccessToken } from '@/utils/session'

export interface KnowledgeBaseItem {
  id: string
  owner_id: string
  name: string
  description?: string | null
  document_count: number
  is_public: boolean
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
}

export interface KBDocumentItem {
  id: string
  knowledge_base_id: string
  title: string
  content?: string | null
  content_type: string
  file_path?: string | null
  is_folder: boolean
  parent_id?: string | null
  sort_order: number
  status: string
  index_status: string
  indexed_at?: string | null
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface KBDocumentListResponse {
  total: number
  items: KBDocumentItem[]
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
    return axios.get(`/api/v1/knowledge-base/${knowledgeBaseId}/documents/${documentId}/source-file`, {
      responseType: 'blob',
      headers: {
        Authorization: `Bearer ${getAccessToken() || ''}`,
      },
    }).then(response => response.data as Blob)
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
