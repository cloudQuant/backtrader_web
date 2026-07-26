<template>
  <el-card class="backtest-metrics-card">
    <template #header>
      <div class="backtest-metrics-head">
        <div>
          <span>{{ t('backtestComp.bmTitle') }}</span>
          <p>{{ result.symbol }} · {{ result.start_date }} - {{ result.end_date }}</p>
        </div>
        <strong :class="resultToneClass(result.total_return)">
          {{ formatPercent(result.total_return) }}
        </strong>
      </div>
    </template>

    <div class="backtest-metrics-grid">
      <article
        v-for="m in metrics"
        :key="m.label"
        class="backtest-metric-tile"
        :class="m.tone"
      >
        <span>
          {{ m.label }}
        </span>
        <strong>
          {{ m.display }}
        </strong>
      </article>
    </div>

    <div class="backtest-equity-surface">
      <div class="backtest-equity-title">
        {{ t('backtest.equityCurve') }}
      </div>
      <EquityCurve
        v-if="result.equity_curve.length"
        :equity="result.equity_curve"
        :dates="result.equity_dates"
        :drawdown="result.drawdown_curve"
      />
      <div
        v-else
        class="backtest-equity-empty"
      >
        {{ t('common.noData') }}
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import type { BacktestResult } from '@/types'

const { t } = useI18n()

const props = defineProps<{
  result: BacktestResult
}>()

const metrics = computed(() => {
  const r = props.result
  return [
    {
      label: t('backtestComp.bmTotalReturn'),
      display: formatPercent(r.total_return),
      tone: resultToneClass(r.total_return),
    },
    {
      label: t('backtestComp.bmAnnualReturn'),
      display: formatPercent(r.annual_return),
      tone: resultToneClass(r.annual_return),
    },
    {
      label: t('backtestComp.bmSharpeRatio'),
      display: (r.sharpe_ratio ?? 0).toFixed(2),
      tone: 'is-neutral',
    },
    {
      label: t('backtestComp.bmMaxDrawdown'),
      display: formatPercent(r.max_drawdown, false),
      tone: 'is-negative',
    },
    {
      label: t('backtestComp.bmWinRate'),
      display: formatPercent(r.win_rate, false, 1),
      tone: 'is-neutral',
    },
    {
      label: t('backtestComp.bmTotalTrades'),
      display: String(r.total_trades),
      tone: 'is-neutral',
    },
    {
      label: t('backtestComp.bmProfitable'),
      display: String(r.profitable_trades),
      tone: 'is-positive',
    },
    {
      label: t('backtestComp.bmLosing'),
      display: String(r.losing_trades),
      tone: 'is-negative',
    },
  ]
})

function formatPercent(value: number | null | undefined, showSign = true, precision = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--'
  return `${showSign && value >= 0 ? '+' : ''}${value.toFixed(precision)}%`
}

function resultToneClass(value: number | null | undefined): string {
  return (value ?? 0) >= 0 ? 'is-positive' : 'is-negative'
}
</script>

<style scoped>
.backtest-metrics-card {
  border-color: var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.backtest-metrics-card :deep(.el-card__header) {
  border-bottom-color: var(--border-color-light);
}

.backtest-metrics-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.backtest-metrics-head span {
  display: block;
  color: var(--text-color-primary);
  font-size: 16px;
  font-weight: 740;
  line-height: 1.3;
}

.backtest-metrics-head p {
  margin: 5px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.backtest-metrics-head strong {
  flex: none;
  font-size: 24px;
  line-height: 1.15;
}

.backtest-metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.backtest-metric-tile {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.backtest-metric-tile span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.backtest-metric-tile strong {
  display: block;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.15;
}

.is-positive,
.backtest-metric-tile.is-positive strong {
  color: var(--success-color);
}

.is-negative,
.backtest-metric-tile.is-negative strong {
  color: var(--danger-color);
}

.backtest-equity-surface {
  min-height: 340px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.backtest-equity-title {
  margin-bottom: 10px;
  color: var(--text-color-primary);
  font-size: 14px;
  font-weight: 720;
}

.backtest-equity-empty {
  display: flex;
  min-height: 280px;
  align-items: center;
  justify-content: center;
  color: var(--text-color-secondary);
  font-size: 13px;
}

@media (max-width: 960px) {
  .backtest-metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .backtest-metrics-head {
    flex-direction: column;
  }

  .backtest-metrics-grid {
    grid-template-columns: 1fr;
  }

  .backtest-equity-surface {
    padding: 10px;
  }
}
</style>
