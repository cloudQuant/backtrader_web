<template>
  <section class="asset-detail-panel" aria-labelledby="bond-panel-title">
    <div class="panel-head">
      <span class="panel-kicker">{{ t('assetResearch.bondPanel.kicker') }}</span>
      <h3 id="bond-panel-title">{{ t('assetResearch.bondPanel.title') }}</h3>
    </div>
    <dl class="detail-grid">
      <div>
        <dt>{{ t('assetResearch.bondPanel.yieldToMaturity') }}</dt>
        <dd>{{ details?.yield_to_maturity ?? t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.bondPanel.modifiedDuration') }}</dt>
        <dd>{{ details?.modified_duration ?? t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.bondPanel.convexity') }}</dt>
        <dd>{{ details?.convexity ?? t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>DV01</dt>
        <dd>{{ details?.dv01 ?? t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.bondPanel.creditSpread') }}</dt>
        <dd>{{ details?.credit_spread_bps ?? t('assetResearch.notProvided') }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

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

