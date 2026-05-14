<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-sm text-slate-500">知识库文档</div>
        <h2 class="text-2xl font-semibold text-slate-900">{{ docData?.title || '文档详情' }}</h2>
      </div>
      <button
        type="button"
        class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
        @click="goBack"
      >
        返回知识库
      </button>
    </div>

    <div v-if="loading" class="rounded border border-slate-200 bg-white px-4 py-8 text-sm text-slate-500">
      正在加载文档...
    </div>

    <div v-else-if="errorMessage" class="rounded border border-rose-200 bg-rose-50 px-4 py-8 text-sm text-rose-700">
      {{ errorMessage }}
    </div>

    <template v-else-if="docData">
      <!-- 文档类型 / 状态标签行 -->
      <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="rounded px-2 py-0.5" :class="statusClass(doc.status)">{{ doc.status }}</span>
            <span class="rounded px-2 py-0.5" :class="indexClass(doc.index_status)">{{ doc.index_status }}</span>
        <span v-if="sourceFileName" class="rounded bg-slate-100 px-2 py-0.5 text-slate-600">{{ sourceFileName }}</span>
      </div>

      <!-- 三栏: 文档预览 / 摘要 / 信息 -->
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <!-- 主内容卡片 -->
        <el-card class="min-w-0">
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium text-slate-900">文档内容</div>
              <div class="flex items-center gap-2 text-xs">
                <!-- 视图切换 Tab -->
                <el-tabs v-model="activeTab" class="kb-doc-tabs" @tab-change="onTabChange">
                  <el-tab-pane label="源文件" name="source" />
                  <el-tab-pane label="Markdown" name="markdown" />
                  <el-tab-pane label="元信息" name="metadata" />
                </el-tabs>
                <!-- 缩放控制（仅 PDF 源文件模式） -->
                <template v-if="activeTab === 'source' && sourceMimeType === 'application/pdf'">
                  <span class="text-slate-400">|</span>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    title="缩小"
                    @click="adjustZoom(-0.1)"
                  >
                    −
                  </button>
                  <span class="text-xs text-slate-600">{{ Math.round(pdfZoom * 100) }}%</span>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    title="放大"
                    @click="adjustZoom(0.1)"
                  >
                    +
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    title="重置"
                    @click="pdfZoom = 1"
                  >
                    ⟲
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    :title="pdfFullscreen ? '退出全屏' : '全屏'"
                    @click="toggleFullscreen"
                  >
                    {{ pdfFullscreen ? '⊠' : '⛶' }}
                  </button>
                  <a
                    v-if="sourcePreviewUrl"
                    :href="sourcePreviewUrl"
                    :download="sourceFileName || 'document'"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
                    title="下载"
                    target="_blank"
                  >
                    ↓
                  </a>
                </template>
              </div>
            </div>
          </template>

          <!-- ========== 源文件视图 ========== -->
          <div v-show="activeTab === 'source'" class="min-h-[60vh]">
            <!-- PDF 预览 -->
            <div
              v-if="sourceMimeType === 'application/pdf' && sourcePreviewUrl"
              :class="['overflow-hidden rounded border border-slate-200 bg-slate-50', pdfFullscreen ? 'fixed inset-0 z-[9999] h-screen w-screen' : '']"
            >
              <iframe
                :src="pdfEmbedUrl"
                class="w-full bg-slate-100"
                :class="pdfFullscreen ? 'h-screen' : 'h-[72vh]'"
                title="PDF预览"
              />
            </div>

            <!-- Office 文件 (docx/xlsx/pptx) 使用 Office Online Viewer -->
            <div
              v-else-if="isOfficeFile && sourcePreviewUrl"
              class="overflow-hidden rounded border border-slate-200"
            >
              <iframe
                :src="officeViewerUrl"
                class="h-[72vh] w-full bg-slate-100"
                title="Office文档预览"
              />
            </div>

            <!-- 其他不支持预览的文件 -->
            <div
              v-else-if="sourceFileName"
              class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
            >
              <div class="mb-4 text-4xl">📄</div>
              <div class="font-medium text-slate-700">{{ sourceFileName }}</div>
              <div class="mt-2 text-xs text-slate-400">此文件类型暂不支持浏览器内联预览</div>
              <div class="mt-4 flex gap-2">
                <button
                  type="button"
                  class="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                  @click="downloadSourceFile"
                >
                  下载原文件
                </button>
                <button
                  v-if="doc.content"
                  type="button"
                  class="rounded border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  @click="activeTab = 'markdown'"
                >
                  阅读 Markdown 正文
                </button>
              </div>
            </div>

            <!-- 无源文件 -->
            <div
              v-else
              class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
            >
              <div class="text-4xl">📭</div>
              <div class="mt-2">暂无源文件</div>
            </div>
          </div>

          <!-- ========== Markdown 视图 ========== -->
          <div v-show="activeTab === 'markdown'" class="min-h-[60vh]">
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
              <div class="text-4xl">📝</div>
              <div class="mt-2">暂无 Markdown 正文内容</div>
            </div>
          </div>

          <!-- ========== 元信息视图 ========== -->
          <div v-show="activeTab === 'metadata'" class="min-h-[60vh] space-y-4 py-2">
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">文档 ID</div>
                <div class="mt-1 break-all text-slate-700">{{ doc.id }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">知识库 ID</div>
                <div class="mt-1 break-all text-slate-700">{{ doc.knowledge_base_id }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">类型</div>
                <div class="mt-1 text-slate-700">{{ doc.is_folder ? '文件夹' : doc.content_type }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">状态</div>
                <div class="mt-1 text-slate-700">{{ doc.status }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">索引状态</div>
                <div class="mt-1 text-slate-700">{{ doc.index_status }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">创建时间</div>
                <div class="mt-1 text-slate-700">{{ formatDate(doc.created_at) }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">更新时间</div>
                <div class="mt-1 text-slate-700">{{ formatDate(doc.updated_at) }}</div>
              </div>
              <div class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">内容长度</div>
                <div class="mt-1 text-slate-700">{{ doc.content?.length ?? 0 }} 字符</div>
              </div>
              <div v-if="sourceFileName" class="rounded border border-slate-100 bg-slate-50 p-3 col-span-2">
                <div class="text-xs text-slate-400">原始文件名</div>
                <div class="mt-1 text-slate-700">{{ sourceFileName }}</div>
              </div>
              <div v-if="sourceMimeType" class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">MIME 类型</div>
                <div class="mt-1 text-slate-700">{{ sourceMimeType }}</div>
              </div>
              <div v-if="sourceFileSize" class="rounded border border-slate-100 bg-slate-50 p-3">
                <div class="text-xs text-slate-400">文件大小</div>
                <div class="mt-1 text-slate-700">{{ formatBytes(sourceFileSize) }}</div>
              </div>
              <div v-if="doc.file_path" class="rounded border border-slate-100 bg-slate-50 p-3 col-span-2">
                <div class="text-xs text-slate-400">文件路径</div>
                <div class="mt-1 break-all text-slate-700">{{ doc.file_path }}</div>
              </div>
            </div>

            <div v-if="doc.metadata" class="rounded border border-slate-200 p-4">
              <div class="mb-2 text-sm font-medium text-slate-700">完整元数据</div>
              <pre class="overflow-auto whitespace-pre-wrap break-all text-xs text-slate-600">{{ JSON.stringify(doc.metadata, null, 2) }}</pre>
            </div>
          </div>
        </el-card>

        <!-- 右侧摘要/操作面板 -->
        <div class="space-y-4">
          <!-- 文档摘要卡片 -->
          <el-card>
            <template #header>
              <div class="font-medium">文档摘要</div>
            </template>
            <div class="space-y-3 text-sm">
              <div class="leading-6 text-slate-700">{{ documentSummary }}</div>
              <div v-if="sourceFileName" class="flex flex-wrap gap-2">
                <button
                  v-if="sourceMimeType === 'application/pdf' || isOfficeFile"
                  type="button"
                  class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                  @click="activeTab = 'source'"
                >
                  预览源文件
                </button>
                <button
                  v-if="doc.content"
                  type="button"
                  class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                  @click="activeTab = 'markdown'"
                >
                  阅读 Markdown
                </button>
                <button
                  v-if="sourcePreviewUrl"
                  type="button"
                  class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                  @click="downloadSourceFile"
                >
                  下载原文件
                </button>
              </div>
            </div>
          </el-card>

          <!-- 阅读建议 -->
          <el-card>
            <template #header>
              <div class="font-medium">阅读建议</div>
            </template>
            <ul class="space-y-2 text-sm text-slate-600">
              <li v-if="sourceMimeType === 'application/pdf' || isOfficeFile">优先查看"源文件"标签页获取原始文档内容。</li>
              <li v-if="doc.content">使用"Markdown"标签页可全文检索/复制。</li>
              <li v-if="doc.index_status !== 'indexed'">⚠️ 当前文档尚未完成索引，AI 检索结果可能不完整。</li>
              <li v-else>✅ 当前文档已索引，可在 AI 问答页结合上下文进行追问。</li>
            </ul>
          </el-card>

          <!-- AI 快捷问答入口 -->
          <el-card>
            <template #header>
              <div class="font-medium">快捷 AI 问答</div>
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
import { useRoute, useRouter } from 'vue-router'

import type { KBDocumentItem } from '@/api/knowledgeBase'
import { knowledgeBaseApi } from '@/api/knowledgeBase'
import { getErrorMessage } from '@/api'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const errorMessage = ref('')
const docData = ref<KBDocumentItem | null>(null)
const sourcePreviewUrl = ref('')

// Tab 状态
const activeTab = ref<'source' | 'markdown' | 'metadata'>('source')

// PDF 缩放/全屏
const pdfZoom = ref(1)
const pdfFullscreen = ref(false)

// Office 文件支持列表
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

// PDF embed URL (Google Docs viewer，支持缩放参数)
const pdfEmbedUrl = computed(() => {
  if (!sourcePreviewUrl.value) return ''
  // Google Docs PDF viewer 支持 zoom 参数
  return `${sourcePreviewUrl.value}#toolbar=1&navpanes=1&zoom=${Math.round(pdfZoom.value * 100)}`
})

// Office Online Viewer URL（免费，无需 API key）
const officeViewerUrl = computed(() => {
  if (!sourcePreviewUrl.value) return ''
  // 必须是经过 encode 的 URL
  const encodedSrc = encodeURIComponent(sourcePreviewUrl.value)
  return `https://view.officeapps.live.com/op/embed.aspx?src=${encodedSrc}&wdPrint=0&wdDownload=1`
})

const quickPrompts = [
  '总结这篇文档的核心内容',
  '提取文档中的关键要点',
  '这篇文章的主要结论是什么？',
]

const documentSummary = computed(() => {
  const content = docData.value?.content?.trim() ?? ''
  if (!content) return '该文档暂无正文内容。'
  if (content.length <= 200) return content
  return `${content.slice(0, 200)}...`
})

// 模板专用的非 null 文档对象（避免每个属性都要可选链）
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
  if (!value) return '未知时间'
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

function onTabChange(tab: string) {
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
    // 源文件加载失败，静默
  }
}

async function fetchDocument() {
  const kbId = String(route.params.kbId || '')
  const docId = String(route.params.docId || '')
  if (!kbId || !docId) {
    errorMessage.value = '缺少文档参数'
    return
  }

  loading.value = true
  errorMessage.value = ''
  revokeSourcePreviewUrl()
  try {
    docData.value = await knowledgeBaseApi.getDocument(kbId, docId)
    if (sourceFileName.value) {
      await loadSourceFile()
      // 自动选择源文件预览（如果支持）
      if (sourceMimeType.value === 'application/pdf' || isOfficeFile.value) {
        activeTab.value = 'source'
      } else if (docData.value?.content) {
        activeTab.value = 'markdown'
      }
    } else if (docData.value?.content) {
      activeTab.value = 'markdown'
    }
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '加载文档失败')
  } finally {
    loading.value = false
  }
}

// 监听来自 AI 问答页的快捷 prompt
watch(
  () => route.query?.prompt,
  (prompt) => {
    if (prompt && typeof prompt === 'string') {
      // 将 prompt 传递到 AI 问答页（通过 sessionStorage 桥接）
      sessionStorage.setItem('kb_quick_prompt', prompt)
      router.replace({ path: '/ai-chat', query: { kbId: route.params.kbId, prompt } })
    }
  },
  { immediate: true }
)

onMounted(fetchDocument)
onBeforeUnmount(revokeSourcePreviewUrl)

// 监听全屏退出事件（浏览器 ESC 等）
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

/* Tab 样式覆盖 */
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
