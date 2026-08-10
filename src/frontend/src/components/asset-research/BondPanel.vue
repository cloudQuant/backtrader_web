<template>
  <section class="asset-detail-panel" aria-labelledby="bond-panel-title">
    <div class="panel-head">
      <span class="panel-kicker">债券估值</span>
      <h3 id="bond-panel-title">收益率与风险</h3>
    </div>
    <dl class="detail-grid">
      <div>
        <dt>到期收益率</dt>
        <dd>{{ details?.yield_to_maturity ?? '未提供' }}</dd>
      </div>
      <div>
        <dt>修正久期</dt>
        <dd>{{ details?.modified_duration ?? '未提供' }}</dd>
      </div>
      <div>
        <dt>凸性</dt>
        <dd>{{ details?.convexity ?? '未提供' }}</dd>
      </div>
      <div>
        <dt>DV01</dt>
        <dd>{{ details?.dv01 ?? '未提供' }}</dd>
      </div>
      <div>
        <dt>信用利差</dt>
        <dd>{{ details?.credit_spread_bps ?? '未提供' }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  details?: Record<string, unknown> | null
}>()
</script>

<style scoped>
.asset-detail-panel { padding: 20px; border: 1px solid var(--el-border-color-light); border-radius: 8px; }
.panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.panel-kicker { color: var(--el-color-primary); font-size: 12px; }
h3 { margin: 4px 0 0; font-size: 18px; }
.detail-grid { display: grid; gap: 10px; margin: 16px 0 0; }
.detail-grid div { display: grid; gap: 4px; }
dt { color: var(--el-text-color-secondary); font-size: 12px; }
dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
</style>

