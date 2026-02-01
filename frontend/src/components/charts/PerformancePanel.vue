<template>
  <div class="performance-panel">
    <h3 class="text-lg font-semibold mb-4">绩效概览</h3>
    
    <!-- 主要指标 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <MetricCard
        title="初始资金"
        :value="metrics?.initial_capital"
        format="currency"
        tooltip="回测开始时的初始资金"
      />
      <MetricCard
        title="最终资产"
        :value="metrics?.final_assets"
        :change="metrics?.total_return"
        format="currency"
        tooltip="回测结束时的总资产"
      />
      <MetricCard
        title="总收益率"
        :value="metrics?.total_return"
        format="percent"
        tooltip="(最终资产-初始资金)/初始资金"
      />
      <MetricCard
        title="年化收益"
        :value="metrics?.annualized_return"
        format="percent"
        tooltip="按252个交易日年化的收益率"
      />
    </div>
    
    <!-- 风险指标 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <MetricCard
        title="最大回撤"
        :value="metrics?.max_drawdown"
        format="percent"
        color="danger"
        tooltip="从最高点到最低点的最大跌幅"
      />
      <MetricCard
        title="夏普比率"
        :value="metrics?.sharpe_ratio"
        format="number"
        :precision="2"
        tooltip="(策略收益-无风险收益)/策略波动率"
      />
      <MetricCard
        title="胜率"
        :value="metrics?.win_rate"
        format="percent"
        tooltip="盈利交易次数/总交易次数"
      />
      <MetricCard
        title="盈亏比"
        :value="metrics?.profit_factor"
        format="number"
        :precision="2"
        tooltip="平均盈利/平均亏损"
      />
    </div>
    
    <!-- 交易统计 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <MetricCard
        title="交易次数"
        :value="metrics?.trade_count"
        format="number"
        :precision="0"
        tooltip="总交易次数"
      />
      <MetricCard
        title="平均持仓"
        :value="metrics?.avg_holding_days"
        format="days"
        tooltip="平均每笔交易持仓天数"
      />
      <MetricCard
        title="最大连赢"
        :value="metrics?.max_consecutive_wins"
        format="number"
        :precision="0"
        color="success"
        tooltip="最大连续盈利交易次数"
      />
      <MetricCard
        title="最大连亏"
        :value="metrics?.max_consecutive_losses"
        format="number"
        :precision="0"
        color="danger"
        tooltip="最大连续亏损交易次数"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import MetricCard from './MetricCard.vue'
import type { PerformanceMetrics } from '@/types/analytics'

defineProps<{
  metrics?: PerformanceMetrics
}>()
</script>
