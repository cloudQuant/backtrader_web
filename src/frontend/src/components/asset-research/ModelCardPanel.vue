<template>
  <section class="model-card-panel" aria-labelledby="model-card-title">
    <div class="panel-head">
      <span class="panel-kicker">模型卡</span>
      <h3 id="model-card-title">模型治理</h3>
    </div>
    <dl v-if="modelCard" class="detail-grid">
      <div>
        <dt>模型名称</dt>
        <dd>{{ modelCard.model_name }}</dd>
      </div>
      <div>
        <dt>负责人</dt>
        <dd>{{ modelCard.owner }}</dd>
      </div>
      <div>
        <dt>评估清单</dt>
        <dd>{{ modelCard.evaluation_manifest_hash }}</dd>
      </div>
      <div>
        <dt>限制</dt>
        <dd>{{ modelCard.limitations.join('；') }}</dd>
      </div>
    </dl>
    <p v-else class="empty-copy">
      未提供已晋级模型卡；当前公开结论保持研究观察。
    </p>
  </section>
</template>

<script setup lang="ts">
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

