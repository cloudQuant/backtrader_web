import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import type {
  KBDocumentItem,
  KnowledgeBaseItem,
  KnowledgeBaseSettings,
} from '@/api/knowledgeBase'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

type ViewMode = 'tree' | 'table'
type SortKey = 'sort_order' | 'title' | 'updated_at' | 'status'
type BulkMode = 'publish' | 'draft' | 'move_root' | 'mark_not_indexed' | 'delete'
export type TreeRow = KBDocumentItem & { depth: number }

export interface KnowledgeBaseCreateDialogState {
  open: boolean
  isFolder: boolean
  title: string
  content: string
  parentId: string | null
}

export interface KnowledgeBaseRenameDialogState {
  open: boolean
  target: KBDocumentItem | null
  title: string
}

export interface KnowledgeBaseImportDialogState {
  open: boolean
  title: string
  content: string
}

export interface KnowledgeBaseBulkDialogState {
  open: boolean
  mode: BulkMode
}

export interface KnowledgeBaseDeleteDialogState {
  open: boolean
  target: KBDocumentItem | null
}

export interface KnowledgeBaseRenameCollectionDialogState {
  open: boolean
  target: KnowledgeBaseItem | null
  name: string
}

export interface KnowledgeBaseDeleteCollectionDialogState {
  open: boolean
  target: KnowledgeBaseItem | null
}

export interface KnowledgeBaseSettingsDialogState {
  open: boolean
  form: KnowledgeBaseSettings
}

export function useKnowledgeBasePage() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const store = useKnowledgeBaseStore()

  const knowledgeBaseSearch = ref('')
  const documentSearch = ref('')
  const selectedDocumentId = ref<string | null>(null)
  const viewMode = ref<ViewMode>('tree')
  const sortKey = ref<SortKey>('sort_order')
  const currentPage = ref(1)
  const pageSize = ref(12)
  const expandedFolderIds = ref<Set<string>>(new Set())
  const selectedDocumentIds = ref<Set<string>>(new Set())

  const createDialog = reactive<KnowledgeBaseCreateDialogState>({
    open: false,
    isFolder: false,
    title: '',
    content: '',
    parentId: null as string | null,
  })

  const renameDialog = reactive<KnowledgeBaseRenameDialogState>({
    open: false,
    target: null as KBDocumentItem | null,
    title: '',
  })

  const importDialog = reactive<KnowledgeBaseImportDialogState>({
    open: false,
    title: '',
    content: '',
  })

  const bulkDialog = reactive<KnowledgeBaseBulkDialogState>({
    open: false,
    mode: 'publish' as BulkMode,
  })

  const deleteDialog = reactive<KnowledgeBaseDeleteDialogState>({
    open: false,
    target: null as KBDocumentItem | null,
  })

  const knowledgeBaseRenameDialog = reactive<KnowledgeBaseRenameCollectionDialogState>({
    open: false,
    target: null as KnowledgeBaseItem | null,
    name: '',
  })

  const knowledgeBaseDeleteDialog = reactive<KnowledgeBaseDeleteCollectionDialogState>({
    open: false,
    target: null as KnowledgeBaseItem | null,
  })

  function createDefaultKnowledgeBaseSettings(): KnowledgeBaseSettings {
    return {
      retrieval_profile: 'quant_research',
      search_mode: 'hybrid',
      default_top_k: 8,
      min_similarity: 0.08,
      title_weight: 0.35,
      keyword_weight: 0.35,
      phrase_weight: 0.2,
      recency_weight: 0.1,
      max_context_chunks: 6,
      use_conversation_memory: true,
      conversation_lookback_messages: 6,
      prioritize_title_matches: true,
      prefer_recent_documents: true,
      quant_focus: 'strategy_research',
      system_prompt_suffix: '',
    }
  }

  const knowledgeBaseSettingsDialog = reactive<KnowledgeBaseSettingsDialogState>({
    open: false,
    form: createDefaultKnowledgeBaseSettings(),
  })

  const draggedDocumentId = ref<string | null>(null)

  const filteredKnowledgeBases = computed(() => {
    const keyword = knowledgeBaseSearch.value.trim().toLowerCase()
    if (!keyword) return store.knowledgeBases
    return store.knowledgeBases.filter(kb => [kb.name, kb.description ?? ''].some(value => value.toLowerCase().includes(keyword)))
  })

  const sortedDocuments = computed(() => {
    const keyword = documentSearch.value.trim().toLowerCase()
    const filtered = !keyword
      ? store.documents
      : store.documents.filter(doc => [doc.title, doc.content ?? '', doc.file_path ?? ''].some(value => value.toLowerCase().includes(keyword)))

    return [...filtered].sort((a, b) => {
      if (sortKey.value === 'title') return a.title.localeCompare(b.title)
      if (sortKey.value === 'updated_at') return (b.updated_at ?? '').localeCompare(a.updated_at ?? '')
      if (sortKey.value === 'status') return a.status.localeCompare(b.status)
      return a.sort_order - b.sort_order
    })
  })

  const indexedDocumentCount = computed(() => store.documents.filter(doc => doc.index_status === 'indexed').length)
  const folderCount = computed(() => store.documents.filter(doc => doc.is_folder).length)
  const currentKnowledgeBaseSettings = computed<KnowledgeBaseSettings>(() => ({
    ...createDefaultKnowledgeBaseSettings(),
    ...(store.currentKnowledgeBase?.settings ?? {}),
  }))

  const displayRows = computed<TreeRow[]>(() => {
    const byParent = new Map<string | null, KBDocumentItem[]>()
    for (const doc of sortedDocuments.value) {
      const key = doc.parent_id ?? null
      const bucket = byParent.get(key) ?? []
      bucket.push(doc)
      byParent.set(key, bucket)
    }

    const rows: TreeRow[] = []
    const visited = new Set<string>()
    const walk = (parentId: string | null, depth: number) => {
      const children = byParent.get(parentId) ?? []
      for (const child of children) {
        if (visited.has(child.id)) continue
        visited.add(child.id)
        rows.push({ ...child, depth })
        if (!child.is_folder || expandedFolderIds.value.has(child.id)) {
          walk(child.id, depth + 1)
        }
      }
    }
    walk(null, 0)
    for (const doc of sortedDocuments.value) {
      if (!visited.has(doc.id)) rows.push({ ...doc, depth: 0 })
    }
    return rows
  })

  const totalPages = computed(() => Math.max(1, Math.ceil(displayRows.value.length / pageSize.value)))
  const visibleRows = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    return displayRows.value.slice(start, start + pageSize.value)
  })
  const selectedDocumentSummary = computed(() => displayRows.value.find(doc => doc.id === selectedDocumentId.value) ?? visibleRows.value[0] ?? null)
  const selectedDocument = computed(() => {
    const summary = selectedDocumentSummary.value
    if (!summary) return null
    if (store.currentDocument?.id === summary.id) {
      return { ...summary, ...store.currentDocument }
    }
    return summary
  })
  const formattedMetadata = computed(() => (selectedDocument.value?.metadata ? JSON.stringify(selectedDocument.value.metadata, null, 2) : ''))
  const selectedDocumentContent = computed(() => {
    const doc = selectedDocument.value
    if (!doc) return ''
    if (store.documentDetailLoading && store.currentDocument?.id !== doc.id) {
      return t('loading')
    }
    return doc.content || t('kb.emptyContent')
  })
  const allVisibleSelected = computed(() => visibleRows.value.length > 0 && visibleRows.value.every(doc => selectedDocumentIds.value.has(doc.id)))
  const bulkDialogMessage = computed(() => {
    const count = selectedDocumentIds.value.size
    if (bulkDialog.mode === 'publish') return t('kb.msgConfirmSetAs', { n: count }) + ' published'
    if (bulkDialog.mode === 'draft') return t('kb.msgConfirmSetAs', { n: count }) + ' draft'
    if (bulkDialog.mode === 'move_root') return t('kb.msgConfirmMoveToRoot', { n: count })
    if (bulkDialog.mode === 'mark_not_indexed') return t('kb.msgConfirmMarkAs', { n: count }) + ' not_indexed'
    return t('kb.msgConfirmDelete') + ` ${count}?`
  })

  function statusClass(status: string) {
    if (status === 'published') return 'bg-emerald-100 text-emerald-700'
    if (status === 'draft') return 'bg-amber-100 text-amber-700'
    return 'bg-slate-100 text-slate-600'
  }

  function indexClass(status: string) {
    if (status === 'indexed') return 'bg-blue-100 text-blue-700'
    if (status === 'not_indexed') return 'bg-slate-100 text-slate-600'
    return 'bg-amber-100 text-amber-700'
  }

  function formatDate(value?: string | null) {
    if (!value) return t('kb.msgUnknownTime')
    return value.replace('T', ' ').slice(0, 16)
  }

  function retrievalProfileLabel(profile?: string | null) {
    if (profile === 'precision') return t('kb.profilePrecision')
    if (profile === 'exploration') return t('kb.profileExploration')
    return t('kb.profileQuantBalance')
  }

  function documentInsight(doc: KBDocumentItem) {
    if (doc.is_folder) return t('kb.statFolders')
    const length = doc.content != null ? doc.content.length : (doc.content_length ?? 0)
    if (length > 4000) return t('kb.msgLongDoc')
    if (length > 0 || doc.has_content) return t('kb.msgBodyMigrated')
    return t('kb.msgPendingContent')
  }

  function insightChip(doc: KBDocumentItem) {
    if (doc.is_folder) return '📁 ' + t('kb.msgStructure')
    if (doc.index_status === 'indexed') return '✨ ' + t('kb.statIndexed')
    const length = doc.content != null ? doc.content.length : (doc.content_length ?? 0)
    if (length > 4000) return '📚 ' + t('kb.msgLongText')
    if (length > 0 || doc.has_content) return '📝 ' + t('kb.msgBody')
    return '⏳ ' + t('kb.msgPlaceholder')
  }

  function toggleFolder(folderId: string) {
    const next = new Set(expandedFolderIds.value)
    if (next.has(folderId)) next.delete(folderId)
    else next.add(folderId)
    expandedFolderIds.value = next
  }

  function toggleDocumentSelection(documentId: string) {
    const next = new Set(selectedDocumentIds.value)
    if (next.has(documentId)) next.delete(documentId)
    else next.add(documentId)
    selectedDocumentIds.value = next
  }

  function toggleSelectAllVisible(event: Event) {
    const checked = (event.target as HTMLInputElement).checked
    const next = new Set(selectedDocumentIds.value)
    if (checked) visibleRows.value.forEach(doc => next.add(doc.id))
    else visibleRows.value.forEach(doc => next.delete(doc.id))
    selectedDocumentIds.value = next
  }

  function clearSelection() {
    selectedDocumentIds.value = new Set()
  }

  function openDocument(document: KBDocumentItem) {
    router.push({
      name: 'KnowledgeBaseDocument',
      params: {
        kbId: document.knowledge_base_id,
        docId: document.id,
      },
    })
  }

  function handleDragStart(documentId: string) {
    draggedDocumentId.value = documentId
  }

  async function handleDrop(target: KBDocumentItem) {
    const sourceId = draggedDocumentId.value
    draggedDocumentId.value = null
    if (!sourceId || sourceId === target.id) return
    const source = store.documents.find(doc => doc.id === sourceId)
    if (!source) return
    const parentId = target.parent_id ?? null
    const siblings = store.documents
      .filter(doc => (doc.parent_id ?? null) === parentId)
      .sort((a, b) => a.sort_order - b.sort_order)
    const sourceIndex = siblings.findIndex(doc => doc.id === sourceId)
    const targetIndex = siblings.findIndex(doc => doc.id === target.id)
    if (sourceIndex === -1 || targetIndex === -1) return
    const reordered = [...siblings]
    const [moved] = reordered.splice(sourceIndex, 1)
    reordered.splice(targetIndex, 0, moved)
    for (const [index, doc] of reordered.entries()) {
      await store.updateDocument(doc.id, { sort_order: index, parent_id: parentId })
    }
    ElMessage.success(t('kb.msgTreeOrderUpdated'))
  }

  function openCreateDialog(isFolder: boolean, parentId: string | null = null) {
    createDialog.open = true
    createDialog.isFolder = isFolder
    createDialog.title = ''
    createDialog.content = ''
    createDialog.parentId = parentId
  }

  function closeCreateDialog() {
    createDialog.open = false
  }

  async function submitCreateDialog() {
    if (!store.currentKnowledgeBase) {
      ElMessage.warning(t('kb.msgSelectKbFirst'))
      return
    }
    if (!createDialog.title.trim()) {
      ElMessage.warning(t('kb.msgEnterName'))
      return
    }
    const created = await store.createDocument({
      title: createDialog.title.trim(),
      content: createDialog.isFolder ? '' : createDialog.content,
      content_type: 'markdown',
      is_folder: createDialog.isFolder,
      parent_id: createDialog.parentId,
    })
    if (created) {
      selectedDocumentId.value = created.id
      if (created.is_folder) expandedFolderIds.value = new Set([...expandedFolderIds.value, created.id])
      ElMessage.success(created.is_folder ? t('kb.msgFolderCreated') : t('kb.msgDocCreated'))
      closeCreateDialog()
    }
  }

  function openRenameDialog(target: KBDocumentItem) {
    renameDialog.open = true
    renameDialog.target = target
    renameDialog.title = target.title
  }

  function closeRenameDialog() {
    renameDialog.open = false
    renameDialog.target = null
    renameDialog.title = ''
  }

  async function submitRenameDialog() {
    if (!renameDialog.target || !renameDialog.title.trim()) {
      ElMessage.warning(t('kb.msgEnterNewName'))
      return
    }
    await store.updateDocument(renameDialog.target.id, { title: renameDialog.title.trim() })
    ElMessage.success(t('kb.msgNameUpdated'))
    closeRenameDialog()
  }

  function openImportDialog() {
    importDialog.open = true
    importDialog.title = ''
    importDialog.content = ''
  }

  function closeImportDialog() {
    importDialog.open = false
  }

  async function submitImportDialog() {
    if (!store.currentKnowledgeBase) {
      ElMessage.warning(t('kb.msgSelectKbFirst'))
      return
    }
    if (!importDialog.title.trim()) {
      ElMessage.warning(t('kb.msgEnterImportTitle'))
      return
    }
    const created = await store.createDocument({
      title: importDialog.title.trim(),
      content: importDialog.content,
      content_type: 'markdown',
      is_folder: false,
      parent_id: selectedDocument.value?.is_folder ? selectedDocument.value.id : null,
    })
    if (created) {
      selectedDocumentId.value = created.id
      ElMessage.success(t('kb.msgImported'))
      closeImportDialog()
    }
  }

  function openBulkActionDialog(mode: BulkMode) {
    if (!selectedDocumentIds.value.size) {
      ElMessage.warning(t('kb.msgSelectDocFirst'))
      return
    }
    bulkDialog.open = true
    bulkDialog.mode = mode
  }

  function closeBulkDialog() {
    bulkDialog.open = false
  }

  async function submitBulkDialog() {
    const ids = [...selectedDocumentIds.value]
    if (!ids.length) {
      ElMessage.warning(t('kb.msgSelectDocFirst'))
      return
    }
    if (bulkDialog.mode === 'publish') {
      for (const id of ids) {
        await store.updateDocument(id, { status: 'published' })
      }
      ElMessage.success(t('kb.msgPublishedN', { n: ids.length }))
    } else if (bulkDialog.mode === 'draft') {
      for (const id of ids) {
        await store.updateDocument(id, { status: 'draft' })
      }
      ElMessage.success(t('kb.msgSetDraftN', { n: ids.length }))
    } else if (bulkDialog.mode === 'move_root') {
      for (const id of ids) {
        await store.updateDocument(id, { parent_id: null })
      }
      ElMessage.success(t('kb.msgMovedNToRoot', { n: ids.length }))
    } else if (bulkDialog.mode === 'mark_not_indexed') {
      for (const id of ids) {
        await store.updateDocument(id, { index_status: 'not_indexed' })
      }
      ElMessage.success(t('kb.msgMarkedN', { n: ids.length }))
    } else {
      for (const id of ids) {
        await store.deleteDocument(id)
      }
      clearSelection()
      ElMessage.success(t('kb.msgDeletedN', { n: ids.length }))
    }
    closeBulkDialog()
  }

  function openDeleteDialog(target: KBDocumentItem) {
    deleteDialog.open = true
    deleteDialog.target = target
  }

  function closeDeleteDialog() {
    deleteDialog.open = false
    deleteDialog.target = null
  }

  async function submitDeleteDialog() {
    if (!deleteDialog.target) return
    await store.deleteDocument(deleteDialog.target.id)
    selectedDocumentIds.value.delete(deleteDialog.target.id)
    if (selectedDocumentId.value === deleteDialog.target.id) selectedDocumentId.value = null
    ElMessage.success(t('kb.msgDocDeleted'))
    closeDeleteDialog()
  }

  async function handleBatchCopyTitles() {
    if (!sortedDocuments.value.length) {
      ElMessage.warning(t('kb.msgNoTitlesToCopy'))
      return
    }
    try {
      await navigator.clipboard.writeText(sortedDocuments.value.map(doc => doc.title).join('\n'))
      ElMessage.success(t('kb.msgCopiedN', { n: sortedDocuments.value.length }))
    } catch {
      ElMessage.warning(t('kb.msgCopyFailed'))
    }
  }

  function openCreateChildDialog(row: KBDocumentItem) {
    openCreateDialog(false, row.is_folder ? row.id : row.parent_id ?? null)
  }

  async function handleCopyNodeTitle(row: KBDocumentItem) {
    try {
      await navigator.clipboard.writeText(row.title)
      ElMessage.success(t('kb.msgTitleCopied'))
    } catch {
      ElMessage.warning(t('kb.msgCopyFailed'))
    }
  }

  function openKnowledgeBaseRenameDialog(kb: KnowledgeBaseItem) {
    knowledgeBaseRenameDialog.open = true
    knowledgeBaseRenameDialog.target = kb
    knowledgeBaseRenameDialog.name = kb.name
  }

  function closeKnowledgeBaseRenameDialog() {
    knowledgeBaseRenameDialog.open = false
    knowledgeBaseRenameDialog.target = null
    knowledgeBaseRenameDialog.name = ''
  }

  async function submitKnowledgeBaseRenameDialog() {
    if (!knowledgeBaseRenameDialog.target || !knowledgeBaseRenameDialog.name.trim()) {
      ElMessage.warning(t('kb.msgEnterKbName'))
      return
    }
    await store.updateKnowledgeBase(knowledgeBaseRenameDialog.target.id, {
      name: knowledgeBaseRenameDialog.name.trim(),
    })
    ElMessage.success(t('kb.msgKbNameUpdated'))
    closeKnowledgeBaseRenameDialog()
  }

  function openKnowledgeBaseDeleteDialog(kb: KnowledgeBaseItem) {
    knowledgeBaseDeleteDialog.open = true
    knowledgeBaseDeleteDialog.target = kb
  }

  function openKnowledgeBaseSettingsDialog() {
    knowledgeBaseSettingsDialog.open = true
    knowledgeBaseSettingsDialog.form = {
      ...createDefaultKnowledgeBaseSettings(),
      ...(store.currentKnowledgeBase?.settings ?? {}),
      system_prompt_suffix: store.currentKnowledgeBase?.settings?.system_prompt_suffix ?? '',
    }
  }

  function closeKnowledgeBaseSettingsDialog() {
    knowledgeBaseSettingsDialog.open = false
  }

  async function submitKnowledgeBaseSettingsDialog() {
    if (!store.currentKnowledgeBase) {
      ElMessage.warning(t('kb.msgSelectKbFirst'))
      return
    }
    const settingsPayload = {
      ...knowledgeBaseSettingsDialog.form,
      default_top_k: Math.min(20, Math.max(1, Number(knowledgeBaseSettingsDialog.form.default_top_k) || 8)),
      min_similarity: Math.min(1, Math.max(0, Number(knowledgeBaseSettingsDialog.form.min_similarity) || 0)),
      max_context_chunks: Math.min(12, Math.max(1, Number(knowledgeBaseSettingsDialog.form.max_context_chunks) || 6)),
      conversation_lookback_messages: Math.min(
        20,
        Math.max(0, Number(knowledgeBaseSettingsDialog.form.conversation_lookback_messages) || 0),
      ),
      system_prompt_suffix: knowledgeBaseSettingsDialog.form.system_prompt_suffix?.trim() || null,
    }
    await store.updateKnowledgeBase(store.currentKnowledgeBase.id, {
      settings: settingsPayload,
    })
    ElMessage.success(t('kb.msgRetrievalUpdated'))
    closeKnowledgeBaseSettingsDialog()
  }

  function closeKnowledgeBaseDeleteDialog() {
    knowledgeBaseDeleteDialog.open = false
    knowledgeBaseDeleteDialog.target = null
  }

  async function submitKnowledgeBaseDeleteDialog() {
    if (!knowledgeBaseDeleteDialog.target) {
      return
    }
    const deletedId = knowledgeBaseDeleteDialog.target.id
    await store.deleteKnowledgeBase(deletedId)
    ElMessage.success(t('kb.msgKbDeleted'))
    if (selectedDocumentId.value && !store.currentKnowledgeBase) {
      selectedDocumentId.value = null
    }
    closeKnowledgeBaseDeleteDialog()
  }

  async function handleMoveToRoot(row: KBDocumentItem) {
    await store.updateDocument(row.id, { parent_id: null })
    ElMessage.success(t('kb.msgMovedToRoot'))
  }

  async function handleSelectKnowledgeBase(id: string) {
    documentSearch.value = ''
    selectedDocumentId.value = null
    clearSelection()
    currentPage.value = 1
    await store.selectKnowledgeBase(id)
    expandedFolderIds.value = new Set(store.documents.filter(doc => doc.is_folder && !doc.parent_id).map(doc => doc.id))
    if (route.query.kbId === id && typeof route.query.docId === 'string') {
      selectedDocumentId.value = route.query.docId
    }
  }

  watch([sortKey, pageSize], () => {
    currentPage.value = 1
  })

  watch(
    () => displayRows.value,
    (rows) => {
      if (!rows.length) {
        selectedDocumentId.value = null
        return
      }
      if (!rows.some(doc => doc.id === selectedDocumentId.value)) {
        selectedDocumentId.value = rows[0]?.id ?? null
      }
      if (currentPage.value > totalPages.value) currentPage.value = totalPages.value
    },
    { immediate: true },
  )

  let documentDetailRequestId = 0
  watch(
    () => [store.currentKnowledgeBase?.id, selectedDocumentId.value] as const,
    async ([kbId, docId]) => {
      const requestId = ++documentDetailRequestId
      if (!kbId || !docId) {
        store.clearCurrentDocument()
        return
      }
      try {
        await store.fetchDocumentDetail(docId)
      } catch {
        if (requestId === documentDetailRequestId) {
          store.clearCurrentDocument()
          ElMessage.error(t('kbDoc.msgLoadDocFailed'))
        }
      }
    },
  )

  onMounted(async () => {
    await store.fetchKnowledgeBases()
    const requestedKbId = typeof route.query.kbId === 'string' ? route.query.kbId : undefined
    const firstId = requestedKbId || store.knowledgeBases[0]?.id
    if (firstId) {
      await store.selectKnowledgeBase(firstId)
      expandedFolderIds.value = new Set(store.documents.filter(doc => doc.is_folder && !doc.parent_id).map(doc => doc.id))
      if (typeof route.query.docId === 'string') selectedDocumentId.value = route.query.docId
    }
  })

  return {
    // Store
    store,
    // Refs
    knowledgeBaseSearch,
    documentSearch,
    selectedDocumentId,
    viewMode,
    sortKey,
    currentPage,
    pageSize,
    expandedFolderIds,
    selectedDocumentIds,
    draggedDocumentId,
    // Dialogs
    createDialog,
    renameDialog,
    importDialog,
    bulkDialog,
    deleteDialog,
    knowledgeBaseRenameDialog,
    knowledgeBaseDeleteDialog,
    knowledgeBaseSettingsDialog,
    // Computed
    filteredKnowledgeBases,
    sortedDocuments,
    indexedDocumentCount,
    folderCount,
    currentKnowledgeBaseSettings,
    displayRows,
    totalPages,
    visibleRows,
    selectedDocument,
    formattedMetadata,
    selectedDocumentContent,
    allVisibleSelected,
    bulkDialogMessage,
    // Functions
    statusClass,
    indexClass,
    formatDate,
    retrievalProfileLabel,
    documentInsight,
    insightChip,
    toggleFolder,
    toggleDocumentSelection,
    toggleSelectAllVisible,
    clearSelection,
    openDocument,
    handleDragStart,
    handleDrop,
    openCreateDialog,
    closeCreateDialog,
    submitCreateDialog,
    openRenameDialog,
    closeRenameDialog,
    submitRenameDialog,
    openImportDialog,
    closeImportDialog,
    submitImportDialog,
    openBulkActionDialog,
    closeBulkDialog,
    submitBulkDialog,
    openDeleteDialog,
    closeDeleteDialog,
    submitDeleteDialog,
    handleBatchCopyTitles,
    openCreateChildDialog,
    handleCopyNodeTitle,
    openKnowledgeBaseRenameDialog,
    closeKnowledgeBaseRenameDialog,
    submitKnowledgeBaseRenameDialog,
    openKnowledgeBaseDeleteDialog,
    openKnowledgeBaseSettingsDialog,
    closeKnowledgeBaseSettingsDialog,
    submitKnowledgeBaseSettingsDialog,
    closeKnowledgeBaseDeleteDialog,
    submitKnowledgeBaseDeleteDialog,
    handleMoveToRoot,
    handleSelectKnowledgeBase,
  }
}
