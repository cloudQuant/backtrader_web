<template>
  <el-table
    ref="tableRef"
    :data="units"
    row-key="id"
    stripe
    border
    size="small"
    class="trading-units-table"
    empty-text="暂无策略单元，点击「新建策略单元」开始"
    @selection-change="rows => emit('selection-change', rows)"
    @row-dblclick="(row, column, event) => emit('row-dblclick', row, column, event)"
  >
    <el-table-column
      type="selection"
      width="42"
    />
    <el-table-column
      label="序号"
      width="60"
      align="center"
    >
      <template #default="{ row }">
        {{ row.sort_order + 1 }}
      </template>
    </el-table-column>
    <el-table-column
      label="状态"
      width="156"
      fixed="left"
    >
      <template #default="{ row }">
        <UnitRunStatusBadge :unit="row" />
      </template>
    </el-table-column>
    <el-table-column
      prop="group_name"
      label="组名"
      min-width="120"
      show-overflow-tooltip
    />
    <el-table-column
      prop="strategy_name"
      label="单元名"
      min-width="150"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span class="font-medium text-slate-700">{{ row.strategy_name || row.strategy_id }}</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="strategy_id"
      label="公式"
      min-width="160"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span class="font-mono text-xs text-slate-600">{{ row.strategy_id || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="symbol"
      label="商品代码"
      width="110"
    />
    <el-table-column
      prop="symbol_name"
      label="商品简称"
      width="120"
      show-overflow-tooltip
    />
    <el-table-column
      prop="timeframe"
      label="周期"
      width="90"
      align="center"
    />
    <el-table-column
      prop="category"
      label="分类"
      width="90"
    />
    <el-table-column
      label="起始日期"
      width="120"
    >
      <template #default="{ row }">
        {{ formatDate(row.data_config?.start_date) }}
      </template>
    </el-table-column>
    <el-table-column
      label="结束日期"
      width="120"
    >
      <template #default="{ row }">
        {{ row.data_config?.use_end_date ? formatDate(row.data_config?.end_date) : '-' }}
      </template>
    </el-table-column>
    <el-table-column
      label="更新时间"
      width="160"
    >
      <template #default="{ row }">
        {{ row.trading_snapshot?.updated_at || formatTime(row.updated_at) }}
      </template>
    </el-table-column>
    <el-table-column
      label="bar数"
      width="80"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.bar_count, 0, false) }}
      </template>
    </el-table-column>
    <el-table-column
      label="多仓"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.trading_snapshot?.long_position, 0, false) }}
      </template>
    </el-table-column>
    <el-table-column
      label="空仓"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.trading_snapshot?.short_position, 0, false) }}
      </template>
    </el-table-column>
    <el-table-column
      label="当日盈亏"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        <span :class="numberClass(row.trading_snapshot?.today_pnl)">
          {{ formatSignedNumber(row.trading_snapshot?.today_pnl, 2, false) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column
      label="持仓盈亏"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        <span :class="numberClass(row.trading_snapshot?.position_pnl)">
          {{ formatSignedNumber(row.trading_snapshot?.position_pnl, 2, false) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column
      label="最新价"
      width="100"
      align="right"
    >
      <template #default="{ row }">
        {{ formatPrice(row.trading_snapshot?.latest_price) }}
      </template>
    </el-table-column>
    <el-table-column
      label="涨幅(%)"
      width="100"
      align="right"
    >
      <template #default="{ row }">
        <span :class="numberClass(row.trading_snapshot?.change_pct)">
          {{ formatSignedNumber(row.trading_snapshot?.change_pct, 2, false, '%') }}
        </span>
      </template>
    </el-table-column>
    <el-table-column
      label="多头市值"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        {{ formatAmountCompact(row.trading_snapshot?.long_market_value) }}
      </template>
    </el-table-column>
    <el-table-column
      label="空头市值"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        {{ formatAmountCompact(row.trading_snapshot?.short_market_value) }}
      </template>
    </el-table-column>
    <el-table-column
      label="杠杆"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.trading_snapshot?.leverage, 2, false) }}
      </template>
    </el-table-column>
    <el-table-column
      label="累计盈亏"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        <span :class="numberClass(row.trading_snapshot?.cumulative_pnl)">
          {{ formatSignedNumber(row.trading_snapshot?.cumulative_pnl, 2, false) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column
      label="最大回撤率"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        {{ formatSignedNumber(row.trading_snapshot?.max_drawdown_rate, 2, false, '%') }}
      </template>
    </el-table-column>
    <el-table-column
      label="详情"
      width="90"
      fixed="right"
    >
      <template #default="{ row }">
        <el-button
          link
          type="primary"
          size="small"
          @click="emit('open-detail', row)"
        >
          详情
        </el-button>
      </template>
    </el-table-column>
    <el-table-column
      label="交易日"
      width="110"
      fixed="right"
    >
      <template #default="{ row }">
        {{ row.trading_snapshot?.trading_day || '-' }}
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import type { StrategyUnit } from '@/types/workspace'
import {
  formatAmountCompact,
  formatDate,
  formatNumber,
  formatPrice,
  formatSignedNumber,
  formatTime,
  numberClass,
} from '@/composables/useUnitTableRendering'
import UnitRunStatusBadge from './UnitRunStatusBadge.vue'

defineProps<{
  units: StrategyUnit[]
}>()

const emit = defineEmits<{
  'selection-change': [rows: StrategyUnit[]]
  'row-dblclick': [row: StrategyUnit, column?: { type?: string }, event?: Event]
  'open-detail': [unit: StrategyUnit]
}>()

const tableRef = ref<{
  clearSelection: () => void
  toggleRowSelection: (row: StrategyUnit, selected?: boolean) => void
} | null>(null)

function clearSelection() {
  tableRef.value?.clearSelection()
}

function toggleRowSelection(row: StrategyUnit, selected?: boolean) {
  tableRef.value?.toggleRowSelection(row, selected)
}

defineExpose({
  clearSelection,
  toggleRowSelection,
})
</script>

<style scoped>
.trading-units-table :deep(.el-table__header th) {
  background: var(--bg-color-page);
  color: var(--text-color-regular);
  font-weight: 600;
}

.trading-units-table :deep(.el-table__row:hover > td) {
  background: var(--info-surface) !important;
}
</style>
