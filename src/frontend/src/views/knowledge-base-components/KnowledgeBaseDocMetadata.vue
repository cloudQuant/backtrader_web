<template>
  <div
    v-show="visible"
    class="kb-doc-metadata"
  >
    <div class="kb-doc-metadata-grid">
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaDocId') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.id }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaKbId') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.knowledge_base_id }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaType') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.is_folder ? t('kbDoc.metaTypeFolder') : doc.content_type }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaStatus') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.status }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaIndexStatus') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.index_status }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaCreatedAt') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ formatDate(doc.created_at) }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaUpdatedAt') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ formatDate(doc.updated_at) }}
        </div>
      </div>
      <div class="kb-doc-meta-card">
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaContentLength') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.content?.length ?? 0 }} {{ t('kbDoc.metaContentLengthSuffix') }}
        </div>
      </div>
      <div
        v-if="sourceFileName"
        class="kb-doc-meta-card kb-doc-meta-card-wide"
      >
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaOriginalName') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ sourceFileName }}
        </div>
      </div>
      <div
        v-if="sourceMimeType"
        class="kb-doc-meta-card"
      >
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaMimeType') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ sourceMimeType }}
        </div>
      </div>
      <div
        v-if="sourceFileSize"
        class="kb-doc-meta-card"
      >
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaFileSize') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ formatBytes(sourceFileSize) }}
        </div>
      </div>
      <div
        v-if="doc.file_path"
        class="kb-doc-meta-card kb-doc-meta-card-wide"
      >
        <div class="kb-doc-meta-label">
          {{ t('kbDoc.metaFilePath') }}
        </div>
        <div class="kb-doc-meta-value">
          {{ doc.file_path }}
        </div>
      </div>
    </div>

    <div
      v-if="doc.metadata"
      class="kb-doc-metadata-json"
    >
      <div class="kb-doc-metadata-json-title">
        {{ t('kbDoc.metaFullMetadata') }}
      </div>
      <pre>{{ JSON.stringify(doc.metadata, null, 2) }}</pre>
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

<style scoped>
.kb-doc-metadata {
  display: grid;
  gap: 14px;
  min-height: 60vh;
  padding: 2px 0;
}

.kb-doc-metadata-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.kb-doc-meta-card,
.kb-doc-metadata-json {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.kb-doc-meta-card {
  min-width: 0;
  padding: 12px;
}

.kb-doc-meta-card-wide {
  grid-column: 1 / -1;
}

.kb-doc-meta-label {
  color: var(--text-color-placeholder);
  font-size: 12px;
  line-height: 1.3;
}

.kb-doc-meta-value {
  margin-top: 6px;
  color: var(--text-color-primary);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.kb-doc-metadata-json {
  min-width: 0;
  padding: 14px;
}

.kb-doc-metadata-json-title {
  margin-bottom: 10px;
  color: var(--text-color-primary);
  font-size: 14px;
  font-weight: 700;
}

.kb-doc-metadata-json pre {
  max-height: 360px;
  overflow: auto;
  margin: 0;
  border-radius: 8px;
  background: var(--bg-color);
  padding: 12px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .kb-doc-metadata-grid {
    grid-template-columns: 1fr;
  }
}
</style>
