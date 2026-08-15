<template>
  <section class="asset-detail-panel" aria-labelledby="futures-panel-title">
    <div class="panel-head">
      <span class="panel-kicker">{{ t('assetResearch.futuresPanel.kicker') }}</span>
      <h3 id="futures-panel-title">{{ t('assetResearch.futuresPanel.title') }}</h3>
    </div>
    <dl class="detail-grid">
      <div>
        <dt>{{ t('assetResearch.futuresPanel.expiry') }}</dt>
        <dd>{{ identity?.details.expiry_at || t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.futuresPanel.contractMultiplier') }}</dt>
        <dd>{{ identity?.details.contract_multiplier || t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.futuresPanel.tradingCalendar') }}</dt>
        <dd>{{ identity?.details.trading_calendar_id || t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.futuresPanel.venue') }}</dt>
        <dd>{{ identity?.venue || t('assetResearch.notProvided') }}</dd>
      </div>
      <div>
        <dt>{{ t('assetResearch.futuresPanel.basisRoll') }}</dt>
        <dd>{{ details?.basis ?? t('assetResearch.notProvided') }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { InstrumentIdentity } from '@/api/assetResearch'

const { t } = useI18n()

defineProps<{
  identity?: InstrumentIdentity | null
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

