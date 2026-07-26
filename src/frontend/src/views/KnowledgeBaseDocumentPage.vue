<template>
  <div
    class="kb-doc-page"
    data-test="kb-doc-page"
  >
    <section
      class="kb-doc-hero"
      data-test="kb-doc-hero"
    >
      <div class="kb-doc-hero-main">
        <div class="kb-doc-kicker">
          {{ t('kbDoc.heroKicker') }}
        </div>
        <h1>{{ docData?.title || t('kbDoc.fallbackTitle') }}</h1>
        <p>{{ t('kbDoc.heroSubtitle') }}</p>
        <div
          v-if="docData"
          class="kb-doc-tags"
        >
          <span :class="statusClass(doc.status)">{{ doc.status }}</span>
          <span :class="indexClass(doc.index_status)">{{ doc.index_status }}</span>
          <span v-if="sourceFileName">{{ sourceFileName }}</span>
        </div>
      </div>

      <div class="kb-doc-hero-actions">
        <button
          type="button"
          class="kb-doc-button"
          @click="goBack"
        >
          <el-icon aria-hidden="true">
            <ArrowLeft />
          </el-icon>
          {{ t('kbDoc.btnBack') }}
        </button>
        <button
          v-if="docData"
          type="button"
          class="kb-doc-button kb-doc-button-primary"
          @click="openQuickChat(t('kbDoc.prompt1'))"
        >
          <el-icon aria-hidden="true">
            <MagicStick />
          </el-icon>
          {{ t('kbDoc.quickAiTitle') }}
        </button>
      </div>

      <div
        v-if="docData"
        class="kb-doc-metrics"
        data-test="kb-doc-metrics"
      >
        <article class="kb-doc-metric">
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <span>{{ t('kbDoc.statStatus') }}</span>
          <strong>{{ doc.status }}</strong>
        </article>
        <article class="kb-doc-metric">
          <el-icon aria-hidden="true">
            <DataAnalysis />
          </el-icon>
          <span>{{ t('kbDoc.statIndex') }}</span>
          <strong>{{ doc.index_status }}</strong>
        </article>
        <article class="kb-doc-metric">
          <el-icon aria-hidden="true">
            <Files />
          </el-icon>
          <span>{{ t('kbDoc.statSource') }}</span>
          <strong>{{ sourceFileName ? t('kbDoc.sourceAvailable') : t('kbDoc.sourceMissing') }}</strong>
        </article>
        <article class="kb-doc-metric">
          <el-icon aria-hidden="true">
            <Reading />
          </el-icon>
          <span>{{ t('kbDoc.statContent') }}</span>
          <strong>{{ doc.content?.length ?? 0 }} {{ t('kbDoc.metaContentLengthSuffix') }}</strong>
        </article>
      </div>
    </section>

    <div
      v-if="loading"
      class="kb-doc-state"
      data-test="kb-doc-loading"
    >
      {{ t('kbDoc.loading') }}
    </div>

    <div
      v-else-if="errorMessage"
      class="kb-doc-state kb-doc-state-error"
      data-test="kb-doc-error"
    >
      {{ errorMessage }}
    </div>

    <template v-else-if="docData">
      <div class="kb-doc-workbench">
        <el-card
          class="kb-doc-panel kb-doc-reader-panel"
          data-test="kb-doc-reader-panel"
        >
          <template #header>
            <div class="kb-doc-panel-header">
              <div>
                <div class="kb-doc-panel-kicker">
                  {{ t('kbDoc.readerPanelKicker') }}
                </div>
                <div class="kb-doc-panel-title">
                  {{ t('kbDoc.cardTitle') }}
                </div>
              </div>
              <div class="kb-doc-reader-controls">
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
                    :label="t('kbDoc.tabMarkdown')"
                    name="markdown"
                  />
                  <el-tab-pane
                    :label="t('kbDoc.tabMeta')"
                    name="metadata"
                  />
                </el-tabs>
                <div
                  v-if="activeTab === 'source' && sourceMimeType === 'application/pdf'"
                  class="kb-doc-zoom-controls"
                >
                  <button
                    type="button"
                    class="kb-doc-icon-button"
                    :title="t('kbDoc.btnZoomOut')"
                    @click="adjustZoom(-0.1)"
                  >
                    <el-icon aria-hidden="true">
                      <ZoomOut />
                    </el-icon>
                  </button>
                  <span>{{ Math.round(pdfZoom * 100) }}%</span>
                  <button
                    type="button"
                    class="kb-doc-icon-button"
                    :title="t('kbDoc.btnZoomIn')"
                    @click="adjustZoom(0.1)"
                  >
                    <el-icon aria-hidden="true">
                      <ZoomIn />
                    </el-icon>
                  </button>
                  <button
                    type="button"
                    class="kb-doc-icon-button"
                    :title="t('kbDoc.btnReset')"
                    @click="pdfZoom = 1"
                  >
                    <el-icon aria-hidden="true">
                      <RefreshLeft />
                    </el-icon>
                  </button>
                  <button
                    type="button"
                    class="kb-doc-icon-button"
                    :title="pdfFullscreen ? t('kbDoc.btnExitFullscreen') : t('kbDoc.btnFullscreen')"
                    @click="toggleFullscreen"
                  >
                    <el-icon aria-hidden="true">
                      <FullScreen />
                    </el-icon>
                  </button>
                  <a
                    v-if="sourcePreviewUrl"
                    :href="sourcePreviewUrl"
                    :download="sourceFileName || 'document'"
                    class="kb-doc-icon-button"
                    :title="t('kbDoc.btnDownload')"
                    target="_blank"
                  >
                    <el-icon aria-hidden="true">
                      <Download />
                    </el-icon>
                  </a>
                </div>
                <button
                  type="button"
                  class="kb-doc-mobile-side-trigger"
                  data-test="kb-doc-open-side-panel"
                  :aria-expanded="mobileSidePanelOpen"
                  aria-haspopup="dialog"
                  @click="openMobileSidePanel($event)"
                >
                  <el-icon aria-hidden="true">
                    <Reading />
                  </el-icon>
                  {{ t('kbDoc.openSidePanel') }}
                </button>
              </div>
            </div>
          </template>

          <KnowledgeBaseDocSourceView
            v-show="activeTab === 'source'"
            :source-mime-type="sourceMimeType"
            :source-preview-url="sourcePreviewUrl"
            :pdf-fullscreen="pdfFullscreen"
            :pdf-embed-url="pdfEmbedUrl"
            :is-office-file="isOfficeFile"
            :office-viewer-url="officeViewerUrl"
            :source-file-name="sourceFileName"
            :has-content="!!doc.content"
            @download="downloadSourceFile"
            @read-markdown="activeTab = 'markdown'"
          />

          <div
            v-show="activeTab === 'markdown'"
            class="kb-doc-markdown-pane"
          >
            <article
              v-if="doc.content"
              class="document-reader"
            >
              {{ doc.content }}
            </article>
            <div
              v-else
              class="kb-doc-empty"
            >
              <el-icon aria-hidden="true">
                <Document />
              </el-icon>
              <div>{{ t('kbDoc.noMarkdownContent') }}</div>
            </div>
          </div>

          <KnowledgeBaseDocMetadata
            :visible="activeTab === 'metadata'"
            :doc="doc"
            :source-file-name="sourceFileName"
            :source-mime-type="sourceMimeType"
            :source-file-size="sourceFileSize"
            :format-date="formatDate"
            :format-bytes="formatBytes"
          />
        </el-card>

        <aside
          ref="sidePanel"
          class="kb-doc-side"
          :class="{ 'kb-doc-side--mobile-open': mobileSidePanelOpen }"
          :role="mobileSidePanelOpen ? 'dialog' : undefined"
          :aria-modal="mobileSidePanelOpen ? 'true' : undefined"
          :aria-label="mobileSidePanelOpen ? t('kbDoc.sidePanelTitle') : undefined"
          data-test="kb-doc-side-panel"
          @keydown="handleMobileSidePanelKeydown"
        >
          <button
            v-if="mobileSidePanelOpen"
            ref="sidePanelClose"
            type="button"
            class="kb-doc-mobile-side-close"
            :aria-label="t('kbDoc.closeSidePanel')"
            @click="closeMobileSidePanel"
          >
            <el-icon aria-hidden="true">
              <Close />
            </el-icon>
          </button>
          <KnowledgeBaseDocSidePanel
            :document-summary="documentSummary"
            :source-file-name="sourceFileName"
            :source-mime-type="sourceMimeType"
            :source-preview-url="sourcePreviewUrl"
            :is-office-file="isOfficeFile"
            :has-content="!!doc.content"
            :is-indexed="doc.index_status === 'indexed'"
            :quick-prompts="quickPrompts"
            @navigate="(tab) => (activeTab = tab)"
            @download="downloadSourceFile"
            @quick-chat="openQuickChat"
          />
        </aside>
      </div>
      <button
        v-if="mobileSidePanelOpen"
        type="button"
        class="kb-doc-mobile-side-backdrop"
        tabindex="-1"
        :aria-label="t('kbDoc.closeSidePanel')"
        @click="closeMobileSidePanel"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { KBDocumentItem } from '@/api/knowledgeBase'
import { knowledgeBaseApi } from '@/api/knowledgeBase'
import { getErrorMessage } from '@/api'
import KnowledgeBaseDocSidePanel from './knowledge-base-components/KnowledgeBaseDocSidePanel.vue'
import KnowledgeBaseDocMetadata from './knowledge-base-components/KnowledgeBaseDocMetadata.vue'
import KnowledgeBaseDocSourceView from './knowledge-base-components/KnowledgeBaseDocSourceView.vue'
import {
  ArrowLeft,
  Close,
  DataAnalysis,
  Document,
  Download,
  Files,
  FullScreen,
  MagicStick,
  Reading,
  RefreshLeft,
  ZoomIn,
  ZoomOut,
} from '@element-plus/icons-vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const errorMessage = ref('')
const docData = ref<KBDocumentItem | null>(null)
const sourcePreviewUrl = ref('')
const mobileSidePanelOpen = ref(false)
const sidePanel = ref<HTMLElement | null>(null)
const sidePanelClose = ref<HTMLButtonElement | null>(null)
let sidePanelTrigger: HTMLElement | null = null

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
  router.push({ path: '/ai/knowledge-base', query: { kbId: String(route.params.kbId || '') } })
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
  router.push({ path: '/ai/chat', query: { kbId, prompt } })
}

async function openMobileSidePanel(event: MouseEvent) {
  sidePanelTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  mobileSidePanelOpen.value = true
  await nextTick()
  sidePanelClose.value?.focus()
}

function closeMobileSidePanel() {
  mobileSidePanelOpen.value = false
  void nextTick(() => sidePanelTrigger?.focus())
}

function handleMobileSidePanelKeydown(event: KeyboardEvent) {
  if (!mobileSidePanelOpen.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMobileSidePanel()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = sidePanel.value
    ? Array.from(sidePanel.value.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ))
    : []
  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
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
      router.replace({ path: '/ai/chat', query: { kbId: route.params.kbId, prompt } })
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
.kb-doc-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  --kb-doc-surface: var(--bg-color);
  --kb-doc-surface-soft: var(--fill-color-lighter);
  --kb-doc-surface-muted: var(--fill-color-light);
  --kb-doc-border: var(--border-color);
  --kb-doc-primary-soft: color-mix(in srgb, var(--bg-color) 82%, var(--primary-color) 18%);
  --kb-doc-success-soft: color-mix(in srgb, var(--bg-color) 84%, var(--success-color) 16%);
  --kb-doc-warning-soft: color-mix(in srgb, var(--bg-color) 84%, var(--warning-color) 16%);
  --kb-doc-danger-soft: color-mix(in srgb, var(--bg-color) 84%, var(--danger-color) 16%);
  color: var(--text-color-primary);
}

.kb-doc-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: start;
  padding: 22px;
  border: 1px solid color-mix(in srgb, var(--kb-doc-border) 72%, var(--primary-color) 28%);
  border-radius: 8px;
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--kb-doc-surface) 88%, var(--primary-color) 12%),
      color-mix(in srgb, var(--kb-doc-surface-soft) 90%, var(--primary-color) 10%)
    );
}

.kb-doc-hero-main {
  min-width: 0;
}

.kb-doc-kicker,
.kb-doc-panel-kicker {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  text-transform: uppercase;
}

.kb-doc-hero h1 {
  margin: 8px 0 0;
  color: var(--text-color-primary);
  font-size: 34px;
  font-weight: 760;
  line-height: 1.15;
  letter-spacing: 0;
  hyphens: auto;
  overflow-wrap: break-word;
  word-break: normal;
}

.kb-doc-hero p {
  max-width: 820px;
  margin: 10px 0 0;
  color: var(--text-color-secondary);
  font-size: 15px;
  line-height: 1.7;
}

.kb-doc-hero-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.kb-doc-button,
.kb-doc-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--kb-doc-border);
  border-radius: 8px;
  background: var(--kb-doc-surface);
  color: var(--text-color-regular);
  font: inherit;
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.kb-doc-button {
  gap: 7px;
  min-height: 38px;
  padding: 8px 12px;
  font-size: 14px;
  font-weight: 650;
}

.kb-doc-button:hover,
.kb-doc-icon-button:hover {
  border-color: color-mix(in srgb, var(--primary-color) 42%, var(--kb-doc-border) 58%);
  background: var(--kb-doc-primary-soft);
  color: var(--primary-color);
}

.kb-doc-button-primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
}

.kb-doc-button-primary:hover {
  background: var(--primary-color-dark);
  color: var(--el-color-white);
}

.kb-doc-tags,
.kb-doc-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kb-doc-tags {
  margin-top: 16px;
}

.kb-doc-tags span {
  border: 1px solid var(--kb-doc-border);
  border-radius: 9999px;
  background: var(--kb-doc-surface);
  padding: 4px 9px;
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.kb-doc-metrics {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.kb-doc-metric {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 10px;
  align-items: center;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--kb-doc-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--kb-doc-surface) 90%, var(--kb-doc-surface-muted) 10%);
}

.kb-doc-metric .el-icon {
  grid-row: span 2;
  color: var(--primary-color);
  font-size: 18px;
}

.kb-doc-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.kb-doc-metric strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 17px;
  font-weight: 760;
  line-height: 1.25;
  hyphens: auto;
  overflow-wrap: break-word;
  word-break: normal;
}

.kb-doc-state {
  border: 1px solid var(--kb-doc-border);
  border-radius: 8px;
  background: var(--kb-doc-surface);
  padding: 28px;
  color: var(--text-color-secondary);
  font-size: 14px;
}

.kb-doc-state-error {
  border-color: color-mix(in srgb, var(--danger-color) 44%, var(--kb-doc-border) 56%);
  background: var(--kb-doc-danger-soft);
  color: var(--danger-color);
}

.kb-doc-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  gap: 16px;
  align-items: start;
}

.kb-doc-panel {
  min-width: 0;
}

.kb-doc-page :deep(.el-card) {
  --el-card-bg-color: var(--kb-doc-surface);
  --el-card-border-color: var(--kb-doc-border);
  border-radius: 8px;
  color: var(--text-color-primary);
}

.kb-doc-page :deep(.el-card__header) {
  border-bottom-color: var(--kb-doc-border);
  background: color-mix(in srgb, var(--kb-doc-surface) 90%, var(--kb-doc-surface-muted) 10%);
}

.kb-doc-page :deep(.el-card__body) {
  background: var(--kb-doc-surface);
}

.kb-doc-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.kb-doc-mobile-side-trigger,
.kb-doc-mobile-side-close,
.kb-doc-mobile-side-backdrop {
  display: none;
}

.kb-doc-panel-title {
  margin-top: 3px;
  color: var(--text-color-primary);
  font-size: 16px;
  font-weight: 760;
}

.kb-doc-reader-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

.kb-doc-zoom-controls {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.kb-doc-icon-button {
  width: 30px;
  height: 30px;
  padding: 0;
  font-size: 14px;
  text-decoration: none;
}

.kb-doc-markdown-pane {
  min-height: 60vh;
}

.document-reader {
  font-feature-settings: 'liga' 1, 'calt' 1;
  max-height: 72vh;
  overflow: auto;
  border: 1px solid var(--kb-doc-border);
  border-radius: 8px;
  background: var(--kb-doc-surface-soft);
  padding: 22px;
  color: var(--text-color-primary);
  font-size: 15px;
  line-height: 1.85;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.kb-doc-empty {
  display: grid;
  place-items: center;
  gap: 10px;
  min-height: 320px;
  border: 1px dashed var(--kb-doc-border);
  border-radius: 8px;
  background: var(--kb-doc-surface-soft);
  color: var(--text-color-secondary);
  font-size: 14px;
  text-align: center;
}

.kb-doc-empty .el-icon {
  color: var(--primary-color);
  font-size: 34px;
}

.kb-doc-page :deep(.text-slate-900),
.kb-doc-page :deep(.text-slate-800),
.kb-doc-page :deep(.text-slate-700) {
  color: var(--text-color-primary) !important;
}

.kb-doc-page :deep(.text-slate-600),
.kb-doc-page :deep(.text-slate-500) {
  color: var(--text-color-secondary) !important;
}

.kb-doc-page :deep(.text-slate-400),
.kb-doc-page :deep(.text-slate-300) {
  color: var(--text-color-placeholder) !important;
}

.kb-doc-page :deep(.bg-white),
.kb-doc-page :deep(.bg-slate-50),
.kb-doc-page :deep(.bg-slate-100),
.kb-doc-page :deep(.bg-blue-50) {
  background: var(--kb-doc-surface-soft) !important;
}

.kb-doc-page :deep(.bg-emerald-100) {
  background: var(--kb-doc-success-soft) !important;
}

.kb-doc-page :deep(.bg-amber-100) {
  background: var(--kb-doc-warning-soft) !important;
}

.kb-doc-page :deep(.bg-rose-50) {
  background: var(--kb-doc-danger-soft) !important;
}

.kb-doc-page :deep(.bg-blue-600) {
  background: var(--primary-color) !important;
}

.kb-doc-page :deep(.text-emerald-700) {
  color: var(--success-color) !important;
}

.kb-doc-page :deep(.text-amber-700) {
  color: var(--warning-color) !important;
}

.kb-doc-page :deep(.text-blue-700) {
  color: var(--primary-color) !important;
}

.kb-doc-page :deep(.text-rose-700) {
  color: var(--danger-color) !important;
}

.kb-doc-page :deep(.border),
.kb-doc-page :deep(.border-slate-100),
.kb-doc-page :deep(.border-slate-200),
.kb-doc-page :deep(.border-slate-300),
.kb-doc-page :deep(.border-rose-200) {
  border-color: var(--kb-doc-border) !important;
}

.kb-doc-page :deep(input),
.kb-doc-page :deep(select),
.kb-doc-page :deep(textarea) {
  border-color: var(--kb-doc-border) !important;
  background: var(--kb-doc-surface) !important;
  color: var(--text-color-primary) !important;
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
  color: var(--text-color-secondary);
}
:deep(.kb-doc-tabs .el-tabs__item.is-active) {
  color: var(--primary-color);
}
:deep(.kb-doc-tabs .el-tabs__active-bar) {
  height: 2px;
  background: var(--primary-color);
}

@media (max-width: 1100px) {
  .kb-doc-hero {
    grid-template-columns: 1fr;
  }

  .kb-doc-hero-actions {
    justify-content: flex-start;
  }

  .kb-doc-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kb-doc-workbench {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .kb-doc-hero {
    padding: 16px;
  }

  .kb-doc-button {
    width: 100%;
  }

  .kb-doc-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kb-doc-panel-header,
  .kb-doc-reader-controls {
    align-items: stretch;
    flex-direction: column;
  }

  .kb-doc-reader-controls {
    width: 100%;
  }

  .kb-doc-mobile-side-trigger {
    display: inline-flex;
    width: 100%;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 36px;
    border: 1px solid var(--kb-doc-border);
    border-radius: 8px;
    background: var(--kb-doc-surface);
    color: var(--text-color-regular);
    cursor: pointer;
  }

  .kb-doc-side {
    display: none;
  }

  .kb-doc-side.kb-doc-side--mobile-open {
    position: fixed;
    z-index: 1001;
    top: max(12px, env(safe-area-inset-top));
    right: max(12px, env(safe-area-inset-right));
    bottom: max(12px, env(safe-area-inset-bottom));
    display: block;
    width: min(420px, calc(100vw - 24px));
    overflow-y: auto;
    border: 1px solid var(--kb-doc-border);
    border-radius: 8px;
    background: var(--kb-doc-surface);
    padding: 14px;
    box-shadow: var(--shadow-lg, var(--shadow-sm));
    overscroll-behavior: contain;
  }

  .kb-doc-mobile-side-close {
    display: inline-flex;
    width: 32px;
    height: 32px;
    align-items: center;
    justify-content: center;
    margin: 0 0 12px auto;
    border: 1px solid var(--kb-doc-border);
    border-radius: 8px;
    background: var(--kb-doc-surface);
    color: var(--text-color-regular);
    cursor: pointer;
  }

  .kb-doc-mobile-side-backdrop {
    position: fixed;
    z-index: 1000;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
    background: color-mix(in srgb, var(--text-color-primary) 34%, transparent);
    cursor: default;
  }
}

@media (max-width: 520px) {
  .kb-doc-hero h1 {
    font-size: 28px;
  }

  .kb-doc-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
