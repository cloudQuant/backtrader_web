<template>
  <section class="quality-panel" aria-labelledby="signal-quality-title">
    <div class="panel-head">
      <div>
        <span class="panel-kicker">{{ t('stockAnalysis.signalQualityKicker') }}</span>
        <h3 id="signal-quality-title">{{ t('stockAnalysis.signalQualityTitle') }}</h3>
      </div>
      <span class="quality-note">{{ t('stockAnalysis.signalQualityNote') }}</span>
    </div>

    <p v-if="loading" class="quality-empty">{{ t('common.loading') }}</p>
    <p v-else-if="!summary" class="quality-empty">{{ t('stockAnalysis.signalQualityEmpty') }}</p>
    <template v-else>
      <div class="quality-metrics">
        <div><span>{{ t('stockAnalysis.signalActionedWinRate') }}</span><strong>{{ percent(summary.actioned_success_rate) }}</strong></div>
        <div><span>{{ t('stockAnalysis.signalScorableCount') }}</span><strong>{{ summary.actioned_scorable_count }}</strong></div>
        <div><span>{{ t('stockAnalysis.signalCoverage') }}</span><strong>{{ percent(summary.coverage_rate) }}</strong></div>
        <div><span>{{ t('stockAnalysis.signalMaturity') }}</span><strong>{{ percent(summary.maturity_rate) }}</strong></div>
      </div>
      <p class="denominator">
        {{ t('stockAnalysis.signalDenominator', { success: summary.actioned_success_count, total: summary.actioned_scorable_count }) }}
      </p>
      <div class="action-grid">
        <article v-for="item in summary.actions" :key="item.action">
          <strong>{{ actionLabel(item.action) }}</strong>
          <span>{{ t('stockAnalysis.signalActionSamples', { scored: item.scorable_count, generated: item.generated_count }) }}</span>
          <b v-if="item.action !== 'WATCH'">{{ percent(item.success_rate) }}</b>
          <b v-else>{{ t('stockAnalysis.signalWatchExcluded') }}</b>
        </article>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { StockSignalAction, StockSignalSummary } from '@/api/stockAnalysis'

defineProps<{
  summary: StockSignalSummary | null
  loading?: boolean
}>()

const { t } = useI18n()

function percent(value: number | null | undefined): string {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : t('stockAnalysis.signalInsufficient')
}

function actionLabel(action: StockSignalAction): string {
  return action === 'BUY'
    ? t('stockAnalysis.signalBuy')
    : action === 'SELL'
      ? t('stockAnalysis.signalSell')
      : t('stockAnalysis.signalWatch')
}
</script>

<style scoped>
.quality-panel { padding: 20px; border: 1px solid var(--border-color-light); border-radius: 16px; background: var(--bg-color-overlay); }
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.panel-kicker { display: block; color: var(--el-color-primary); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
h3 { margin: 4px 0 0; font-size: 18px; }
.quality-note, .quality-empty, .denominator, article span { color: var(--text-color-secondary); font-size: 12px; }
.quality-empty { margin: 18px 0 0; }
.quality-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }
.quality-metrics div, article { padding: 12px; border-radius: 10px; background: var(--fill-color-light); }
.quality-metrics span { display: block; color: var(--text-color-secondary); font-size: 12px; }
.quality-metrics strong { display: block; margin-top: 5px; font-size: 20px; }
.denominator { margin: 12px 0; }
.action-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
article strong, article span, article b { display: block; }
article b { margin-top: 5px; }
@media (max-width: 760px) { .quality-metrics, .action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
