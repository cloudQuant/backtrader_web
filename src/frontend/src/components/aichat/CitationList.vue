<template>
  <section
    class="citation-box"
    :aria-label="t('aiChat.referenceDocs')"
  >
    <div class="citation-head">
      <span>{{ t('aiChat.referenceDocs') }}</span>
      <span>{{ t('aiChat.citationsCount', { n: citations.length }) }}</span>
    </div>
    <button
      v-for="(citation, index) in citations"
      :key="getCitationKey(citation, index)"
      type="button"
      class="citation-item"
      data-test="citation-chip"
      :href="citation.document_id ? `#document-${citation.document_id}` : undefined"
      :disabled="!citation.document_id"
      :aria-label="t('aiChat.citationLabel', { index: index + 1, title: getCitationTitle(citation) })"
      @click="emit('jump', citation.document_id)"
    >
      <span
        class="citation-index"
        aria-hidden="true"
      >{{ index + 1 }}</span>
      <span class="citation-content">
        <strong>{{ getCitationTitle(citation) }}</strong>
        <small>
          chunk #{{ getCitationChunkIndex(citation) }}
          / {{ getCitationSimilarity(citation) }}%
        </small>
        <span v-if="citation.content">{{ citation.content }}</span>
      </span>
      <el-icon aria-hidden="true">
        <Link />
      </el-icon>
    </button>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import type { KBCitation } from '@/api/kbChat'
import {
  getCitationChunkIndex,
  getCitationKey,
  getCitationSimilarity,
  getCitationTitle,
} from '@/composables/useAIChatRendering'

const { t } = useI18n()

defineProps<{
  citations: KBCitation[]
}>()

const emit = defineEmits<{
  jump: [documentId?: string | null]
}>()
</script>

<style scoped lang="scss">
.citation-box {
  margin-top: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 12px;
}

.citation-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--text-color-regular);
  font-size: 12px;
  font-weight: 700;
}

.citation-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 20px;
  gap: 10px;
  width: 100%;
  align-items: start;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 88%, var(--fill-color-light) 12%);
  padding: 10px;
  text-align: left;
  cursor: pointer;
}

.citation-item:hover {
  border-color: color-mix(in srgb, var(--primary-color) 34%, var(--border-color) 66%);
  background: color-mix(in srgb, var(--bg-color) 84%, var(--primary-color) 16%);
}

.citation-item + .citation-item {
  margin-top: 8px;
}

.citation-index {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  background: color-mix(in srgb, var(--bg-color) 76%, var(--primary-color) 24%);
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
}

.citation-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.citation-content strong {
  color: var(--text-color-primary);
  font-size: 13px;
}

.citation-content small,
.citation-content span {
  color: var(--text-color-secondary);
  font-size: 12px;
}
</style>
