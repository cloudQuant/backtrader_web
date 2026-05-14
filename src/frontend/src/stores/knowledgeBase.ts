import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  knowledgeBaseApi,
  type KnowledgeBaseUpdateRequest,
  type KBDocumentCreateRequest,
  type KBDocumentUpdateRequest,
  type KBDocumentItem,
  type KnowledgeBaseItem,
} from '@/api/knowledgeBase'

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  const knowledgeBases = ref<KnowledgeBaseItem[]>([])
  const currentKnowledgeBase = ref<KnowledgeBaseItem | null>(null)
  const documents = ref<KBDocumentItem[]>([])
  const loading = ref(false)

  async function fetchKnowledgeBases() {
    loading.value = true
    try {
      const response = await knowledgeBaseApi.list()
      knowledgeBases.value = response.items
      return response
    } finally {
      loading.value = false
    }
  }

  async function selectKnowledgeBase(id: string) {
    currentKnowledgeBase.value = knowledgeBases.value.find(item => item.id === id) ?? null
    const response = await knowledgeBaseApi.listDocuments(id)
    documents.value = response.items
    return response
  }

  async function updateKnowledgeBase(id: string, data: KnowledgeBaseUpdateRequest) {
    loading.value = true
    try {
      const entity = await knowledgeBaseApi.update(id, data)
      await fetchKnowledgeBases()
      if (currentKnowledgeBase.value?.id === id) {
        currentKnowledgeBase.value = knowledgeBases.value.find(item => item.id === id) ?? null
      }
      return entity
    } finally {
      loading.value = false
    }
  }

  async function deleteKnowledgeBase(id: string) {
    loading.value = true
    try {
      await knowledgeBaseApi.delete(id)
      const wasCurrent = currentKnowledgeBase.value?.id === id
      await fetchKnowledgeBases()
      if (wasCurrent) {
        currentKnowledgeBase.value = knowledgeBases.value[0] ?? null
        if (currentKnowledgeBase.value) {
          await selectKnowledgeBase(currentKnowledgeBase.value.id)
        } else {
          documents.value = []
        }
      }
      return true
    } finally {
      loading.value = false
    }
  }

  async function createDocument(data: KBDocumentCreateRequest) {
    if (!currentKnowledgeBase.value) {
      return null
    }
    loading.value = true
    try {
      const entity = await knowledgeBaseApi.createDocument(currentKnowledgeBase.value.id, data)
      await selectKnowledgeBase(currentKnowledgeBase.value.id)
      await fetchKnowledgeBases()
      return entity
    } finally {
      loading.value = false
    }
  }

  async function updateDocument(documentId: string, data: KBDocumentUpdateRequest) {
    if (!currentKnowledgeBase.value) {
      return null
    }
    loading.value = true
    try {
      const entity = await knowledgeBaseApi.updateDocument(currentKnowledgeBase.value.id, documentId, data)
      await selectKnowledgeBase(currentKnowledgeBase.value.id)
      return entity
    } finally {
      loading.value = false
    }
  }

  async function deleteDocument(documentId: string) {
    if (!currentKnowledgeBase.value) {
      return false
    }
    loading.value = true
    try {
      await knowledgeBaseApi.deleteDocument(currentKnowledgeBase.value.id, documentId)
      await selectKnowledgeBase(currentKnowledgeBase.value.id)
      await fetchKnowledgeBases()
      return true
    } finally {
      loading.value = false
    }
  }

  return {
    knowledgeBases,
    currentKnowledgeBase,
    documents,
    loading,
    fetchKnowledgeBases,
    selectKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    createDocument,
    updateDocument,
    deleteDocument,
  }
})
