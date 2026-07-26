<template>
  <div class="kb-doc-side-panel">
    <!-- Document summary card -->
    <el-card class="kb-doc-side-card">
      <template #header>
        <div class="kb-doc-side-title">
          {{ t('kbDoc.summaryTitle') }}
        </div>
      </template>
      <div class="kb-doc-side-stack">
        <div class="kb-doc-summary-text">
          {{ documentSummary }}
        </div>
        <div
          v-if="sourceFileName"
          class="kb-doc-side-actions"
        >
          <button
            v-if="sourceMimeType === 'application/pdf' || isOfficeFile"
            type="button"
            class="kb-doc-side-action"
            @click="emit('navigate', 'source')"
          >
            {{ t('kbDoc.btnPreviewSource') }}
          </button>
          <button
            v-if="hasContent"
            type="button"
            class="kb-doc-side-action"
            @click="emit('navigate', 'markdown')"
          >
            {{ t('kbDoc.btnReadMd') }}
          </button>
          <button
            v-if="sourcePreviewUrl"
            type="button"
            class="kb-doc-side-action"
            @click="emit('download')"
          >
            {{ t('kbDoc.btnDownloadOriginal') }}
          </button>
        </div>
      </div>
    </el-card>

    <!-- Reading tips -->
    <el-card class="kb-doc-side-card">
      <template #header>
        <div class="kb-doc-side-title">
          {{ t('kbDoc.readingTipsTitle') }}
        </div>
      </template>
      <ul class="kb-doc-tip-list">
        <li v-if="sourceMimeType === 'application/pdf' || isOfficeFile">
          {{ t('kbDoc.tipPreferSource') }}
        </li>
        <li v-if="hasContent">
          {{ t('kbDoc.tipUseMarkdown') }}
        </li>
        <li v-if="!isIndexed">
          {{ t('kbDoc.tipNotIndexed') }}
        </li>
        <li v-else>
          {{ t('kbDoc.tipIndexed') }}
        </li>
      </ul>
    </el-card>

    <!-- Quick AI Q&A entry -->
    <el-card class="kb-doc-side-card">
      <template #header>
        <div class="kb-doc-side-title">
          {{ t('kbDoc.quickAiTitle') }}
        </div>
      </template>
      <div class="kb-doc-prompt-list">
        <button
          v-for="prompt in quickPrompts"
          :key="prompt"
          type="button"
          class="kb-doc-prompt-button"
          @click="emit('quickChat', prompt)"
        >
          {{ prompt }}
        </button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  documentSummary: string
  sourceFileName: string
  sourceMimeType: string
  sourcePreviewUrl: string
  isOfficeFile: boolean
  hasContent: boolean
  isIndexed: boolean
  quickPrompts: string[]
}>()

const emit = defineEmits<{
  (e: 'navigate', tab: 'source' | 'markdown'): void
  (e: 'download'): void
  (e: 'quickChat', prompt: string): void
}>()
</script>

<style scoped>
.kb-doc-side-panel {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.kb-doc-side-panel :deep(.el-card) {
  --el-card-bg-color: var(--bg-color);
  --el-card-border-color: var(--border-color);
  border-radius: 8px;
  color: var(--text-color-primary);
}

.kb-doc-side-panel :deep(.el-card__header) {
  border-bottom-color: var(--border-color);
  background: color-mix(in srgb, var(--bg-color) 90%, var(--fill-color-light) 10%);
}

.kb-doc-side-title {
  color: var(--text-color-primary);
  font-size: 14px;
  font-weight: 760;
}

.kb-doc-side-stack,
.kb-doc-prompt-list {
  display: grid;
  gap: 10px;
}

.kb-doc-summary-text {
  color: var(--text-color-secondary);
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.kb-doc-side-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kb-doc-side-action,
.kb-doc-prompt-button {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-regular);
  cursor: pointer;
  font: inherit;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.kb-doc-side-action {
  padding: 7px 10px;
  font-size: 12px;
  font-weight: 650;
}

.kb-doc-prompt-button {
  display: block;
  width: 100%;
  padding: 10px 11px;
  text-align: left;
  font-size: 13px;
  line-height: 1.5;
}

.kb-doc-side-action:hover,
.kb-doc-prompt-button:hover {
  border-color: color-mix(in srgb, var(--primary-color) 42%, var(--border-color) 58%);
  background: color-mix(in srgb, var(--bg-color) 82%, var(--primary-color) 18%);
  color: var(--primary-color);
}

.kb-doc-tip-list {
  display: grid;
  gap: 9px;
  margin: 0;
  padding-left: 18px;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
</style>
