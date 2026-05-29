<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-sm text-slate-500">
          {{ t('kbDoc.pageTitle') }}
        </div>
        <h2 class="text-2xl font-semibold text-slate-900">
          {{ docData?.title || t('kbDoc.fallbackTitle') }}
        </h2>
      </div>
      <button
        type="button"
        class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
        @click="goBack"
      >
        {{ t('kbDoc.btnBack') }}
      </button>
    </div>

    <div
      v-if="loading"
      class="rounded border border-slate-200 bg-white px-4 py-8 text-sm text-slate-500"
    >
      {{ t('kbDoc.loading') }}
    </div>

    <div
      v-else-if="errorMessage"
      class="rounded border border-rose-200 bg-rose-50 px-4 py-8 text-sm text-rose-700"
    >
      {{ errorMessage }}
    </div>

    <template v-else-if="docData">
      <!-- Document type / status tag row -->
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span
          class="rounded px-2 py-0.5"
          :class="statusClass(doc.status)"
        >{{ doc.status }}</span>
        <span
          class="rounded px-2 py-0.5"
          :class="indexClass(doc.index_status)"
        >{{ doc.index_status }}</span>
        <span
          v-if="sourceFileName"
          class="rounded bg-slate-100 px-2 py-0.5 text-slate-600"
        >{{ sourceFileName }}</span>
      </div>

      <!-- Three columns: doc preview / summary / info -->
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <!-- Main content card -->
        <el-card class="min-w-0">
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium text-slate-900">
                {{ t('kbDoc.cardTitle') }}
              </div>
              <div class="flex items-center gap-2 text-xs">
                <!-- View switcher tab -->
                <el-tabs
                  v-model="activeTab"
                  class="kb-doc-tabs"
                  @tab-change="onTabChange"
                >
                  <el-tab-pane
                    :label="t('kbDoc.tabSource')"
                    name="source"
                  />
                  <el-tab-pane
                    label="Markdown"
                    name="markdown"
                  />
                  <el-tab-pane
                    :label="t('kbDoc.tabMeta')"
                    name="metadata"
                  />
                </el-tabs>
                <!-- Zoom controls (PDF only) -->
                <template v-if="activeTab === 'source' && sourceMimeType === 'application/pdf'">
                  <span class="text-slate-400">|</span>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    :title="t('kbDoc.btnZoomOut')"
                    @click="adjustZoom(-0.1)"
                  >
                    −
                  </button>
                  <span class="text-xs text-slate-600">{{ Math.round(pdfZoom * 100) }}%</span>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    :title="t('kbDoc.btnZoomIn')"
                    @click="adjustZoom(0.1)"
                  >
                    +
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    :title="t('kbDoc.btnReset')"
                    @click="pdfZoom = 1"
                  >
                    ⟲
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    :title="pdfFullscreen ? t('kbDoc.btnExitFullscreen') : t('kbDoc.btnFullscreen')"
                    @click="toggleFullscreen"
                  >
                    {{ pdfFullscreen ? '⊠' : '⛶' }}
                  </button>
                  <a
                    v-if="sourcePreviewUrl"
                    :href="sourcePreviewUrl"
                    :download="sourceFileName || 'document'"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    :title="t('kbDoc.btnDownload')"
                    target="_blank"
                  >
                    ↓
                  </a>
                </template>
              </div>
            </div>
          </template>

          <!-- ========== Source file view ========== -->
          <div
            v-show="activeTab === 'source'"
            class="min-h-[60vh]"
          >
            <!-- PDF preview -->
            <div
              v-if="sourceMimeType === 'application/pdf' && sourcePreviewUrl"
              :class="['overflow-hidden rounded border border-slate-200 bg-slate-50', pdfFullscreen ? 'fixed inset-0 z-[9999] h-screen w-screen' : '']"
            >
              <iframe
                :src="pdfEmbedUrl"
                class="w-full bg-slate-100"
                :class="pdfFullscreen ? 'h-screen' : 'h-[72vh]'"
                :title="t('kbDoc.pdfTitle')"
              />
            </div>

            <!-- Office files (docx/xlsx/pptx) via Office Online Viewer -->
            <div
              v-else-if="isOfficeFile && sourcePreviewUrl"
              class="overflow-hidden rounded border border-slate-200"
            >
              <iframe
                :src="officeViewerUrl"
                class="h-[72vh] w-full bg-slate-100"
                :title="t('kbDoc.officeTitle')"
              />
            </div>

            <!-- Other unsupported files -->
            <div
              v-else-if="sourceFileName"
              class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
            >
              <div class="mb-4 text-4xl">
                📄
              </div>
              <div class="font-medium text-slate-700">
                {{ sourceFileName }}
              </div>
              <div class="mt-2 text-xs text-slate-400">
                {{ t('kbDoc.notInlinePreview') }}
              </div>
              <div class="mt-4 flex gap-2">
                <button
                  type="button"
                  class="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                  @click="downloadSourceFile"
                >
                  {{ t('kbDoc.btnDownloadOriginal') }}
                </button>
                <button
                  v-if="doc.content"
                  type="button"
                  class="rounded border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  @click="activeTab = 'markdown'"
                >
                  {{ t('kbDoc.btnReadMarkdown') }}
                </button>
              </div>
            </div>

            <!-- No source file -->
            <div
              v-else
              class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
            >
              <div class="text-4xl">
                📭
              </div>
              <div class="mt-2">
                {{ t('kbDoc.noSourceFile') }}
              </div>
            </div>
          </div>

          <!-- ========== Markdown view ========== -->
          <div
            v-show="activeTab === 'markdown'"
            class="min-h-[60vh]"
          >
            <article
              v-if="doc.content"
              class="document-reader max-h-[72vh] overflow-auto whitespace-pre-wrap break-words text-[15px] leading-8 text-slate-800"
            >
              {{ doc.content }}
            </article>
            <div
              v-else
              class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
            >
              <div class="text-4xl">
                📝
              </div>
              <div class="mt-2">
                {{ t('kbDoc.noMarkdownContent') }}
              </div>
            </div>
          </div>

          <!-- ========== Metadata view ========== -->
          <div
            v-show="activeTab === 'metadata'"
            class="min-h-[60vh] space-y-4 py-2"
          >
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaDocId') }}
                </div>
                <div class="mt-1 break-all text-slate-700">
                  {{ doc.id }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaKbId') }}
                </div>
                <div class="mt-1 break-all text-slate-700">
                  {{ doc.knowledge_base_id }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaType') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ doc.is_folder ? t('kbDoc.metaTypeFolder') : doc.content_type }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaStatus') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ doc.status }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaIndexStatus') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ doc.index_status }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaCreatedAt') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ formatDate(doc.created_at) }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaUpdatedAt') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ formatDate(doc.updated_at) }}
                </div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaContentLength') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ doc.content?.length ?? 0 }} {{ t('kbDoc.metaContentLengthSuffix') }}
                </div>
              </div>
              <div
                v-if="sourceFileName"
                class="rounded border border-slate-100 bg-slate-50 p-3 col-span-2"
              >
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaOriginalName') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ sourceFileName }}
                </div>
              </div>
              <div
                v-if="sourceMimeType"
                class="rounded border border-slate-100 bg-slate-50 p-3"
              >
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaMimeType') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ sourceMimeType }}
                </div>
              </div>
              <div
                v-if="sourceFileSize"
                class="rounded border border-slate-100 bg-slate-50 p-3"
              >
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaFileSize') }}
                </div>
                <div class="mt-1 text-slate-700">
                  {{ formatBytes(sourceFileSize) }}
                </div>
              </div>
              <div
                v-if="doc.file_path"
                class="rounded border border-slate-100 bg-slate-50 p-3 col-span-2"
              >
                <div class="text-xs text-slate-400">
                  {{ t('kbDoc.metaFilePath') }}
                </div>
                <div class="mt-1 break-all text-slate-700">
                  {{ doc.file_path }}
                </div>
              </div>
            </div>

            <div
              v-if="doc.metadata"
              class="rounded border border-slate-200 p-4"
            >
              <div class="mb-2 text-sm font-medium text-slate-700">
                {{ t('kbDoc.metaFullMetadata') }}
              </div>
              <pre class="overflow-auto whitespace-pre-wrap break-all text-xs text-slate-600">{{ JSON.stringify(doc.metadata, null, 2) }}</pre>
            </div>
          </div>
        </el-card>


        <!-- Right summary/action panel -->
        <div class="space-y-4">
          <!-- Document summary card -->
          <el-card>
            <template #header>
              <div class="font-medium">
                {{ t('kbDoc.summaryTitle') }}
              </div>
            </template>
            <div class="space-y-3 text-sm">
              <div class="leading-6 text-slate-700">
                {{ documentSummary }}
              </div>
              <div
                v-if="sourceFileName"
                class="flex flex-wrap gap-2"
              >
                <button
                  v-if="sourceMimeType === 'application/pdf' || isOfficeFile"
                  type="button"
                  class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                  @click="activeTab = 'source'"
                >
                  {{ t('kbDoc.btnPreviewSource') }}
                </button>
                <button
                  v-if="doc.content"
                  type="button"
                  class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                  @click="activeTab = 'markdown'"
                >
                  {{ t('kbDoc.btnReadMd') }}
                </button>
                <button
                  v-if="sourcePreviewUrl"
                  type="button"
                  class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                  @click="downloadSourceFile"
                >
                  {{ t('kbDoc.btnDownloadOriginal') }}
                </button>
              </div>
            </div>
          </el-card>

          <!-- Reading tips -->
          <el-card>
            <template #header>
              <div class="font-medium">
                {{ t('kbDoc.readingTipsTitle') }}
              </div>
            </template>
            <ul class="space-y-2 text-sm text-slate-600">
              <li v-if="sourceMimeType === 'application/pdf' || isOfficeFile">
                {{ t('kbDoc.tipPreferSource') }}
              </li>
              <li v-if="doc.content">
                {{ t('kbDoc.tipUseMarkdown') }}
              </li>
              <li v-if="doc.index_status !== 'indexed'">
                {{ t('kbDoc.tipNotIndexed') }}
              </li>
              <li v-else>
                {{ t('kbDoc.tipIndexed') }}
              </li>
            </ul>
          </el-card>

          <!-- Quick AI Q&A entry -->
          <el-card>
            <template #header>
              <div class="font-medium">
                {{ t('kbDoc.quickAiTitle') }}
              </div>
            </template>
            <div class="space-y-2 text-sm">
              <button
                v-for="prompt in quickPrompts"
                :key="prompt"
                type="button"
                class="block w-full rounded border border-slate-200 px-3 py-2 text-left text-slate-600 hover:bg-slate-50"
                @click="openQuickChat(prompt)"
              >
                {{ prompt }}
              </button>
            </div>
          </el-card>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { KBDocumentItem } from '@/api/knowledgeBase'
import { knowledgeBaseApi } from '@/api/knowledgeBase'
import { getErrorMessage } from '@/api'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const errorMessage = ref('')
const docData = ref<KBDocumentItem | null>(null)
const sourcePreviewUrl = ref('')

// Tab state
const activeTab = ref<'source' | 'markdown' | 'metadata'>('source')

// PDF zoom/fullscreen
const pdfZoom = ref(1)
const pdfFullscreen = ref(false)

// Office file support list
const OFFICE_TYPES = new Set([
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',       // .xlsx
  'application/vnd.openxmlformats-officedocument.presentationml.presentation', // .pptx
  'application/msword',  // .doc
  'application/vnd.ms-excel', // .xls
])

const isOfficeFile = computed(() => {
  return OFFICE_TYPES.has(sourceMimeType.value)
})

// PDF embed URL (Google Docs viewer with zoom param)
const pdfEmbedUrl = computed(() => {
  if (!sourcePreviewUrl.value) return ''
  return `${sourcePreviewUrl.value}#toolbar=1&navpanes=1&zoom=${Math.round(pdfZoom.value * 100)}`
})

// Office Online Viewer URL (free, no API key)
const officeViewerUrl = computed(() => {
  if (!sourcePreviewUrl.value) return ''
  const encodedSrc = encodeURIComponent(sourcePreviewUrl.value)
  return `https://view.officeapps.live.com/op/embed.aspx?src=${encodedSrc}&wdPrint=0&wdDownload=1`
})

const quickPrompts = computed(() => [
  t('kbDoc.prompt1'),
  t('kbDoc.prompt2'),
  t('kbDoc.prompt3'),
])

const documentSummary = computed(() => {
  const content = docData.value?.content?.trim() ?? ''
  if (!content) return t('kbDoc.summaryEmpty')
  if (content.length <= 200) return content
  return `${content.slice(0, 200)}...`
})

// Template-friendly non-null doc object (avoids optional chaining everywhere)
const doc = computed<KBDocumentItem>(() => docData.value ?? ({
  id: '',
  knowledge_base_id: '',
  title: '',
  content: null,
  content_type: '',
  file_path: null,
  is_folder: false,
  parent_id: null,
  status: '',
  index_status: '',
  sort_order: 0,
  created_at: '',
  updated_at: '',
  metadata: null,
}))

const sourceFileName = computed(() => {
  const metadata = docData.value?.metadata
  if (!metadata || typeof metadata !== 'object') return ''
  const value = (metadata as Record<string, unknown>).reqdocs_source_filename
  return typeof value === 'string' ? value : ''
})

const sourceMimeType = computed(() => {
  const metadata = docData.value?.metadata
  if (!metadata || typeof metadata !== 'object') return ''
  const value = (metadata as Record<string, unknown>).reqdocs_source_mime_type
  return typeof value === 'string' ? value : ''
})

const sourceFileSize = computed(() => {
  const metadata = docData.value?.metadata
  if (!metadata || typeof metadata !== 'object') return null
  const value = (metadata as Record<string, unknown>).reqdocs_source_file_size
  return typeof value === 'number' ? value : null
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
  if (!value) return t('kbDoc.msgUnknownTime')
  return value.replace('T', ' ').slice(0, 16)
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function adjustZoom(delta: number) {
  const next = Math.max(0.25, Math.min(3, pdfZoom.value + delta))
  pdfZoom.value = parseFloat(next.toFixed(2))
}

function toggleFullscreen() {
  if (!pdfFullscreen.value) {
    window.document.documentElement.requestFullscreen?.()
    pdfFullscreen.value = true
  } else {
    window.document.exitFullscreen?.()
    pdfFullscreen.value = false
  }
}

function revokeSourcePreviewUrl() {
  if (sourcePreviewUrl.value) {
    URL.revokeObjectURL(sourcePreviewUrl.value)
    sourcePreviewUrl.value = ''
  }
}

function goBack() {
  router.push({ path: '/knowledge-base', query: { kbId: String(route.params.kbId || '') } })
}

function downloadSourceFile() {
  if (!sourcePreviewUrl.value || !sourceFileName.value) return
  const link = window.document.createElement('a')
  link.href = sourcePreviewUrl.value
  link.download = sourceFileName.value
  link.click()
}

function openQuickChat(prompt: string) {
  const kbId = String(route.params.kbId || '')
  router.push({ path: '/ai-chat', query: { kbId, prompt } })
}

function onTabChange(tab: string | number) {
  if (tab === 'source' && !sourcePreviewUrl.value && sourceFileName.value) {
    loadSourceFile()
  }
}

async function loadSourceFile() {
  if (!docData.value) return
  const kbId = String(route.params.kbId || '')
  const docId = String(route.params.docId || '')
  try {
    const blob = await knowledgeBaseApi.getDocumentSourceFile(kbId, docId)
    sourcePreviewUrl.value = URL.createObjectURL(blob)
  } catch {
    // Source file load failed; silent
  }
}

async function fetchDocument() {
  const kbId = String(route.params.kbId || '')
  const docId = String(route.params.docId || '')
  if (!kbId || !docId) {
    errorMessage.value = t('kbDoc.msgMissingDocParams')
    return
  }

  loading.value = true
  errorMessage.value = ''
  revokeSourcePreviewUrl()
  try {
    docData.value = await knowledgeBaseApi.getDocument(kbId, docId)
    if (sourceFileName.value) {
      await loadSourceFile()
      // Auto-select source preview if supported
      if (sourceMimeType.value === 'application/pdf' || isOfficeFile.value) {
        activeTab.value = 'source'
      } else if (docData.value?.content) {
        activeTab.value = 'markdown'
      }
    } else if (docData.value?.content) {
      activeTab.value = 'markdown'
    }
  } catch (error) {
    errorMessage.value = getErrorMessage(error, t('kbDoc.msgLoadDocFailed'))
  } finally {
    loading.value = false
  }
}

// Watch for quick prompt from AI chat page
watch(
  () => route.query?.prompt,
  (prompt) => {
    if (prompt && typeof prompt === 'string') {
      // Bridge prompt to AI chat page via sessionStorage
      sessionStorage.setItem('kb_quick_prompt', prompt)
      router.replace({ path: '/ai-chat', query: { kbId: route.params.kbId, prompt } })
    }
  },
  { immediate: true }
)

onMounted(fetchDocument)
onBeforeUnmount(revokeSourcePreviewUrl)

// Listen for fullscreen exit (browser ESC etc.)
if (typeof window !== 'undefined') {
  window.document.addEventListener('fullscreenchange', () => {
    if (!window.document.fullscreenElement) {
      pdfFullscreen.value = false
    }
  })
}
</script>

<style scoped>
.document-reader {
  font-feature-settings: 'liga' 1, 'calt' 1;
}

/* Tab style overrides */
:deep(.kb-doc-tabs .el-tabs__header) {
  margin-bottom: 0;
}
:deep(.kb-doc-tabs .el-tabs__nav-wrap::after) {
  display: none;
}
:deep(.kb-doc-tabs .el-tabs__item) {
  font-size: 13px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
}
:deep(.kb-doc-tabs .el-tabs__active-bar) {
  height: 2px;
}
</style>
