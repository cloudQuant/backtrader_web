<template>
  <el-card>
    <template #header>
      <span class="font-bold">{{ t('backtestComp.bmTitle') }}</span>
    </template>

    <!-- Metric panel -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div
        v-for="m in metrics"
        :key="m.label"
        class="p-4 bg-gray-50 rounded-lg"
      >
        <div class="text-gray-500 text-sm">
          {{ m.label }}
        </div>
        <div
          class="text-2xl font-bold"
          :class="m.colorClass"
        >
          {{ m.display }}
        </div>
      </div>
    </div>

    <!-- Equity curve -->
    <div class="h-80">
      <EquityCurve
        v-if="result.equity_curve.length"
        :equity="result.equity_curve"
        :dates="result.equity_dates"
        :drawdown="result.drawdown_curve"
      />
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
      display: `${(r.total_return ?? 0).toFixed(2)}%`,
      colorClass: (r.total_return ?? 0) >= 0 ? 'text-green-500' : 'text-red-500',
    },
    {
      label: t('backtestComp.bmAnnualReturn'),
      display: `${(r.annual_return ?? 0).toFixed(2)}%`,
      colorClass: (r.annual_return ?? 0) >= 0 ? 'text-green-500' : 'text-red-500',
    },
    {
      label: t('backtestComp.bmSharpeRatio'),
      display: (r.sharpe_ratio ?? 0).toFixed(2),
      colorClass: 'text-gray-800',
    },
    {
      label: t('backtestComp.bmMaxDrawdown'),
      display: `${(r.max_drawdown ?? 0).toFixed(2)}%`,
      colorClass: 'text-red-500',
    },
    {
      label: t('backtestComp.bmWinRate'),
      display: `${(r.win_rate ?? 0).toFixed(1)}%`,
      colorClass: 'text-gray-800',
    },
    {
      label: t('backtestComp.bmTotalTrades'),
      display: String(r.total_trades),
      colorClass: 'text-gray-800',
    },
    {
      label: t('backtestComp.bmProfitable'),
      display: String(r.profitable_trades),
      colorClass: 'text-green-500',
    },
    {
      label: t('backtestComp.bmLosing'),
      display: String(r.losing_trades),
      colorClass: 'text-red-500',
    },
  ]
})
</script>
