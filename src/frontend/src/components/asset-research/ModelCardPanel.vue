<template>
  <section class="model-card-panel" aria-labelledby="model-card-title">
    <div class="panel-head">
      <span class="panel-kicker">{{ t('assetResearch.modelCardPanel.kicker') }}</span>
      <h3 id="model-card-title">{{ t('assetResearch.modelCardPanel.title') }}</h3>
    </div>
    <dl v-if="modelCard" class="detail-grid">
      <div>
        <dt>{{ t('assetResearch.modelCardPanel.modelName') }}</dt>
        <dd>{{ modelCard.model_name }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.modelCardPanel.owner') }}</dt>
        <dd>{{ modelCard.owner }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.modelCardPanel.evaluationManifest') }}</dt>
        <dd>{{ modelCard.evaluation_manifest_hash }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.modelCardPanel.limitations') }}</dt>
        <dd>{{ modelCard.limitations.join('；') }}</dd>
      </div>
    </dl>
    <p v-else class="empty-copy">
      {{ t('assetResearch.modelCardPanel.noPromotedCard') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

export interface ModelCardView {
  model_name: string
  owner: string
  evaluation_manifest_hash: string
  limitations: string[]
}

defineProps<{
  modelCard?: ModelCardView | null
}>()
</script>

<style scoped>
.model-card-panel { padding: 20px; border: 1px solid var(--el-border-color-light); border-radius: 8px; }
.panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.panel-kicker { color: var(--el-color-primary); font-size: 12px; }
h3 { margin: 4px 0 0; font-size: 18px; }
.detail-grid { display: grid; gap: 10px; margin: 16px 0 0; }
.detail-grid div { display: grid; gap: 4px; }
dt { color: var(--el-text-color-secondary); font-size: 12px; }
dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
.empty-copy { margin: 16px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
</style>

