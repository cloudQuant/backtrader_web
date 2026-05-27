<template>
  <section class="citation-box">
    <div class="citation-head">
      <span>参考文档</span>
      <span>{{ citations.length }} 条引用</span>
    </div>
    <button
      v-for="(citation, index) in citations"
      :key="getCitationKey(citation, index)"
      type="button"
      class="citation-item"
      :disabled="!citation.document_id"
      @click="emit('jump', citation.document_id)"
    >
      <span class="citation-index">{{ index + 1 }}</span>
      <span class="citation-content">
        <strong>{{ getCitationTitle(citation) }}</strong>
        <small>
          chunk #{{ getCitationChunkIndex(citation) }}
          / {{ getCitationSimilarity(citation) }}%
        </small>
        <span v-if="citation.content">{{ citation.content }}</span>
      </span>
      <el-icon><Link /></el-icon>
    </button>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@element-plus/icons-vue'

import type { KBCitation } from '@/api/kbChat'
import {
  getCitationChunkIndex,
  getCitationKey,
  getCitationSimilarity,
  getCitationTitle,
} from '@/composables/useAIChatRendering'

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
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
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
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-hover);
  padding: 10px;
  text-align: left;
  cursor: pointer;
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
  background: var(--info-surface);
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
