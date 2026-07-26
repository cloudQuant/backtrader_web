<template>
  <section
    class="kb-hero"
    data-test="kb-hero"
  >
    <div class="kb-hero-copy">
      <div class="kb-kicker">
        {{ t('kb.heroKicker') }}
      </div>
      <h1>{{ t('kb.pageTitle') }}</h1>
      <p>{{ t('kb.pageSubtitle') }}</p>
      <div
        class="kb-hero-metrics"
        data-test="kb-hero-metrics"
      >
        <article class="kb-metric-card">
          <el-icon aria-hidden="true">
            <Collection />
          </el-icon>
          <span>{{ t('kb.kbList') }}</span>
          <strong>{{ store.knowledgeBases.length }}</strong>
        </article>
        <article class="kb-metric-card">
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <span>{{ t('kb.statTotal') }}</span>
          <strong>{{ store.documents.length }}</strong>
        </article>
        <article class="kb-metric-card">
          <el-icon aria-hidden="true">
            <Finished />
          </el-icon>
          <span>{{ t('kb.statIndexed') }}</span>
          <strong>{{ indexedDocumentCount }}</strong>
        </article>
        <article class="kb-metric-card">
          <el-icon aria-hidden="true">
            <Folder />
          </el-icon>
          <span>{{ t('kb.statFolders') }}</span>
          <strong>{{ folderCount }}</strong>
        </article>
      </div>
    </div>

    <div class="kb-hero-command">
      <div>
        <div class="kb-command-title">
          {{ store.currentKnowledgeBase?.name || t('kb.noKnowledgeBaseSelected') }}
        </div>
        <div class="kb-command-subtitle">
          {{ store.currentKnowledgeBase?.description || t('kb.noDescription') }}
        </div>
      </div>
      <div class="kb-command-tags">
        <span>{{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</span>
        <span>{{ currentKnowledgeBaseSettings.search_mode }}</span>
        <span>top_k {{ currentKnowledgeBaseSettings.default_top_k }}</span>
      </div>
      <div class="kb-command-actions">
        <button
          type="button"
          class="kb-button kb-button-primary"
          @click="openCreateDialog(false)"
        >
          <el-icon aria-hidden="true">
            <Plus />
          </el-icon>
          {{ t('kb.createDoc') }}
        </button>
        <button
          type="button"
          class="kb-button"
          @click="openImportDialog"
        >
          <el-icon aria-hidden="true">
            <Upload />
          </el-icon>
          {{ t('kb.importDocs') }}
        </button>
        <button
          type="button"
          class="kb-button"
          :disabled="!store.currentKnowledgeBase"
          @click="openKnowledgeBaseSettingsDialog"
        >
          <el-icon aria-hidden="true">
            <Setting />
          </el-icon>
          {{ t('kb.retrievalConfig') }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Collection, Document, Finished, Folder, Plus, Setting, Upload } from '@element-plus/icons-vue'
import type { KBDocumentItem, KnowledgeBaseItem, KnowledgeBaseSettings } from '@/api/knowledgeBase'

interface KnowledgeBaseStoreSummary {
  knowledgeBases: KnowledgeBaseItem[]
  documents: KBDocumentItem[]
  currentKnowledgeBase: KnowledgeBaseItem | null
}

defineProps<{
  store: KnowledgeBaseStoreSummary
  indexedDocumentCount: number
  folderCount: number
  currentKnowledgeBaseSettings: KnowledgeBaseSettings
  retrievalProfileLabel: (profile?: string) => string
  openCreateDialog: (isFolder: boolean) => void
  openImportDialog: () => void
  openKnowledgeBaseSettingsDialog: () => void
}>()

const { t } = useI18n()
</script>

<style scoped>
.kb-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 430px);
  gap: 20px;
  align-items: stretch;
  padding: 22px;
  border: 1px solid color-mix(in srgb, var(--kb-border) 72%, var(--primary-color) 28%);
  border-radius: 8px;
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--kb-surface) 88%, var(--primary-color) 12%),
      color-mix(in srgb, var(--kb-surface-soft) 90%, var(--primary-color) 10%)
    );
}

.kb-hero-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: space-between;
  gap: 18px;
}

.kb-kicker {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.kb-hero h1 {
  margin: 6px 0 0;
  color: var(--text-color-primary);
  font-size: 36px;
  font-weight: 760;
  line-height: 1.14;
  letter-spacing: 0;
}

.kb-hero p {
  max-width: 820px;
  margin: 10px 0 0;
  color: var(--text-color-secondary);
  font-size: 15px;
  line-height: 1.7;
}

.kb-hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.kb-metric-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 9px;
  align-items: center;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--kb-surface) 90%, var(--kb-surface-muted) 10%);
}

.kb-metric-card .el-icon {
  grid-row: span 2;
  color: var(--primary-color);
  font-size: 18px;
}

.kb-metric-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.kb-metric-card strong {
  color: var(--text-color-primary);
  font-size: 22px;
  font-weight: 760;
  line-height: 1;
}

.kb-hero-command {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--kb-surface) 90%, var(--primary-color) 10%);
}

.kb-command-title {
  color: var(--text-color-primary);
  font-size: 16px;
  font-weight: 760;
}

.kb-command-subtitle {
  margin-top: 6px;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.kb-command-tags,
.kb-settings-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.kb-command-tags span,
.kb-settings-tags span {
  border: 1px solid color-mix(in srgb, var(--primary-color) 22%, var(--kb-border) 78%);
  border-radius: 9999px;
  background: var(--kb-primary-soft);
  padding: 3px 8px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 650;
}

.kb-command-actions {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.kb-button,
.kb-page button {
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.kb-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  background: var(--kb-surface);
  padding: 8px 12px;
  color: var(--text-color-regular);
  font-size: 14px;
  font-weight: 650;
}

.kb-button:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--primary-color) 38%, var(--kb-border) 62%);
  background: var(--kb-primary-soft);
  color: var(--primary-color);
}

.kb-button-primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
}

.kb-button-primary:hover:not(:disabled) {
  background: var(--primary-color-dark);
  color: var(--el-color-white);
}

</style>
