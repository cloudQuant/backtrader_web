<template>
  <div class="performance-panel">
    <h3 class="text-lg font-semibold mb-4">
      {{ t('charts.perfTitle') }}
    </h3>
    
    <!-- 主要指标 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <MetricCard
        :title="t('charts.perfInitialCapital')"
        :value="metrics?.initial_capital"
        format="currency"
        :tooltip="t('charts.perfInitialCapitalTip')"
      />
      <MetricCard
        :title="t('charts.perfFinalAssets')"
        :value="metrics?.final_assets"
        :change="metrics?.total_return"
        format="currency"
        :tooltip="t('charts.perfFinalAssetsTip')"
      />
      <MetricCard
        :title="t('charts.perfTotalReturn')"
        :value="metrics?.total_return"
        format="percent"
        :tooltip="t('charts.perfTotalReturnTip')"
      />
      <MetricCard
        :title="t('charts.perfAnnualizedReturn')"
        :value="metrics?.annualized_return"
        format="percent"
        :tooltip="t('charts.perfAnnualizedReturnTip')"
      />
    </div>
    
    <!-- 风险指标 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <MetricCard
        :title="t('charts.perfMaxDrawdown')"
        :value="metrics?.max_drawdown"
        format="percent"
        color="danger"
        :tooltip="t('charts.perfMaxDrawdownTip')"
      />
      <MetricCard
        :title="t('charts.perfSharpeRatio')"
        :value="metrics?.sharpe_ratio"
        format="number"
        :precision="2"
        :tooltip="t('charts.perfSharpeRatioTip')"
      />
      <MetricCard
        :title="t('charts.perfWinRate')"
        :value="metrics?.win_rate"
        format="percent"
        :tooltip="t('charts.perfWinRateTip')"
      />
      <MetricCard
        :title="t('charts.perfProfitFactor')"
        :value="metrics?.profit_factor"
        format="number"
        :precision="2"
        :tooltip="t('charts.perfProfitFactorTip')"
      />
    </div>
    
    <!-- 交易统计 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <MetricCard
        :title="t('charts.perfTradeCount')"
        :value="metrics?.trade_count"
        format="number"
        :precision="0"
        :tooltip="t('charts.perfTradeCountTip')"
      />
      <MetricCard
        :title="t('charts.perfAvgHoldingDays')"
        :value="metrics?.avg_holding_days"
        format="days"
        :tooltip="t('charts.perfAvgHoldingDaysTip')"
      />
      <MetricCard
        :title="t('charts.perfMaxConsecutiveWins')"
        :value="metrics?.max_consecutive_wins"
        format="number"
        :precision="0"
        color="success"
        :tooltip="t('charts.perfMaxConsecutiveWinsTip')"
      />
      <MetricCard
        :title="t('charts.perfMaxConsecutiveLosses')"
        :value="metrics?.max_consecutive_losses"
        format="number"
        :precision="0"
        color="danger"
        :tooltip="t('charts.perfMaxConsecutiveLossesTip')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MetricCard from './MetricCard.vue'
import type { PerformanceMetrics } from '@/types/analytics'

const { t } = useI18n()

defineProps<{
  metrics?: Partial<PerformanceMetrics>
}>()
</script>
