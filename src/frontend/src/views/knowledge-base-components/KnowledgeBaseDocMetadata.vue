<template>
  <div
    v-show="visible"
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
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { KBDocumentItem } from '@/api/knowledgeBase'

const { t } = useI18n()

defineProps<{
  visible: boolean
  doc: KBDocumentItem
  sourceFileName: string
  sourceMimeType: string
  sourceFileSize: number | null
  formatDate: (value?: string | null) => string
  formatBytes: (bytes: number) => string
}>()
</script>
