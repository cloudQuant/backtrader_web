<template>
  <el-table
    ref="tableRef"
    :data="units"
    row-key="id"
    stripe
    border
    size="small"
    class="trading-units-table"
    :empty-text="t('workspaceDialogs.emptyUnits') + ', ' + t('workspaceDialogs.clickPrefix') + ' \u300c' + t('workspaceDialogs.newUnit') + '\u300d ' + t('workspaceDialogs.rangeStart')"
    @selection-change="rows => emit('selection-change', rows)"
    @row-dblclick="(row, column, event) => emit('row-dblclick', row, column, event)"
  >
    <el-table-column
      type="selection"
      width="42"
    />
    <el-table-column
      :label="t('workspaceDialogs.indexNo')"
      width="60"
      align="center"
    >
      <template #default="{ row }">
        {{ row.sort_order + 1 }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.statusCol')"
      width="156"
      fixed="left"
    >
      <template #default="{ row }">
        <UnitRunStatusBadge :unit="row" />
      </template>
    </el-table-column>
    <el-table-column
      prop="group_name"
      :label="t('workspaceDialogs.groupName')"
      min-width="120"
      show-overflow-tooltip
    />
    <el-table-column
      prop="strategy_name"
      :label="t('workspaceDialogs.unitName')"
      min-width="150"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span class="font-medium text-slate-700">{{ row.strategy_name || row.strategy_id }}</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="strategy_id"
      :label="t('workspaceDialogs.formula')"
      min-width="160"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span class="font-mono text-xs text-slate-600">{{ row.strategy_id || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="symbol"
      :label="t('workspaceDialogs.symbolCodeShort')"
      width="110"
    />
    <el-table-column
      prop="symbol_name"
      :label="t('workspaceDialogs.symbolName')"
      width="120"
      show-overflow-tooltip
    />
    <el-table-column
      prop="timeframe"
      :label="t('workspaceDialogs.timeframeCol')"
      width="90"
      align="center"
    />
    <el-table-column
      prop="category"
      :label="t('workspaceDialogs.categoryCol')"
      width="90"
    />
    <el-table-column
      :label="t('workspaceDialogs.rangeStartDate')"
      width="120"
    >
      <template #default="{ row }">
        {{ formatDate(row.data_config?.start_date) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.rangeEndDate')"
      width="120"
    >
      <template #default="{ row }">
        {{ row.data_config?.use_end_date ? formatDate(row.data_config?.end_date) : '-' }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.updatedAt')"
      width="160"
    >
      <template #default="{ row }">
        {{ row.trading_snapshot?.updated_at || formatTime(row.updated_at) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="'bar ' + t('workspaceDialogs.countSuffix')"
      width="80"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.bar_count, 0, false) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.longShare')"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.trading_snapshot?.long_position, 0, false) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.flat')"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.trading_snapshot?.short_position, 0, false) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.todayPnL')"
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
      :label="t('workspaceDialogs.holdingPnL')"
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
      :label="t('workspaceDialogs.latestPrice')"
      width="100"
      align="right"
    >
      <template #default="{ row }">
        {{ formatPrice(row.trading_snapshot?.latest_price) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.changePct')"
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
      :label="t('workspaceDialogs.longMarketValue')"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        {{ formatAmountCompact(row.trading_snapshot?.long_market_value) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.shortMarketValue')"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        {{ formatAmountCompact(row.trading_snapshot?.short_market_value) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.leverage')"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        {{ formatNumber(row.trading_snapshot?.leverage, 2, false) }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.cumulativePnL')"
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
      :label="t('workspaceDialogs.maxDrawdownPct')"
      width="110"
      align="right"
    >
      <template #default="{ row }">
        {{ formatSignedNumber(row.trading_snapshot?.max_drawdown_rate, 2, false, '%') }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.detailCol')"
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
          {{ t('workspaceDialogs.detailCol') }}
        </el-button>
      </template>
    </el-table-column>
    <el-table-column
      :label="t('workspaceDialogs.tradingDay')"
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
import { useI18n } from 'vue-i18n'

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

const { t } = useI18n()

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
