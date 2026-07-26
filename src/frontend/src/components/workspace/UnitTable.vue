<template>
  <ResponsiveDataGrid :mobile-label="t('workspaceDialogs.unitName')">
    <template #desktop>
      <el-table
        ref="tableRef"
        :data="units"
        row-key="id"
        stripe
        border
        size="small"
        class="trading-units-table"
        :empty-text="t('workspaceDialogs.emptyUnits') + ', ' + t('workspaceDialogs.clickPrefix') + ' \u300c' + t('workspaceDialogs.newUnit') + '\u300d ' + t('workspaceDialogs.rangeStart')"
        @selection-change="handleSelectionChange"
        @row-dblclick="handleRowDoubleClick"
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
            {{ formatQuantity(row.trading_snapshot?.long_position) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('workspaceDialogs.flat')"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            {{ formatQuantity(row.trading_snapshot?.short_position) }}
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

    <template #mobile>
      <ol class="trading-units-mobile-list">
        <li
          v-for="row in units"
          :key="row.id"
        >
          <article
            class="trading-unit-card"
            :aria-label="`${row.strategy_name || row.strategy_id || '-'} ${row.symbol || ''}`"
          >
            <div class="trading-unit-card__header">
              <button
                type="button"
                class="trading-unit-card__identity"
                :aria-label="t('workspaceDialogs.detailCol')"
                @click="emit('open-detail', row)"
              >
                <span>{{ row.strategy_name || row.strategy_id || '-' }}</span>
                <small>{{ row.symbol_name || row.symbol || '-' }}</small>
              </button>
              <UnitRunStatusBadge :unit="row" />
            </div>

            <dl class="trading-unit-card__metrics">
              <div>
                <dt>{{ t('workspaceDialogs.symbolCodeShort') }}</dt>
                <dd>{{ row.symbol || '-' }}</dd>
              </div>
              <div>
                <dt>{{ t('workspaceDialogs.timeframeCol') }}</dt>
                <dd>{{ row.timeframe || '-' }}</dd>
              </div>
              <div>
                <dt>{{ t('workspaceDialogs.latestPrice') }}</dt>
                <dd>{{ formatPrice(row.trading_snapshot?.latest_price) }}</dd>
              </div>
              <div>
                <dt>{{ t('workspaceDialogs.todayPnL') }}</dt>
                <dd :class="numberClass(row.trading_snapshot?.today_pnl)">
                  {{ formatSignedNumber(row.trading_snapshot?.today_pnl, 2, false) }}
                </dd>
              </div>
            </dl>

            <div class="trading-unit-card__actions">
              <el-button
                type="primary"
                size="small"
                :aria-label="t('workspaceDialogs.detailCol')"
                @click="emit('open-detail', row)"
              >
                {{ t('workspaceDialogs.detailCol') }}
              </el-button>
            </div>
          </article>
        </li>
      </ol>
    </template>
  </ResponsiveDataGrid>
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
  formatQuantity,
  formatSignedNumber,
  formatTime,
  numberClass,
} from '@/composables/useUnitTableRendering'
import ResponsiveDataGrid from '@/components/common/ResponsiveDataGrid.vue'
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

function handleSelectionChange(rows: StrategyUnit[]) {
  emit('selection-change', rows)
}

function handleRowDoubleClick(row: StrategyUnit, column: { type?: string }, event: Event) {
  emit('row-dblclick', row, column, event)
}

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

.trading-units-mobile-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.trading-unit-card {
  display: grid;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.trading-unit-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.trading-unit-card__identity {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-color-primary);
  cursor: pointer;
  text-align: left;
}

.trading-unit-card__identity:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 3px;
}

.trading-unit-card__identity > span,
.trading-unit-card__identity > small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trading-unit-card__identity > span {
  font-size: 14px;
  font-weight: 720;
}

.trading-unit-card__identity > small {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.trading-unit-card__header :deep(.status-cell) {
  min-width: 116px;
}

.trading-unit-card__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.trading-unit-card__metrics > div {
  min-width: 0;
}

.trading-unit-card__metrics dt {
  margin-bottom: 3px;
  color: var(--text-color-secondary);
  font-size: 11px;
}

.trading-unit-card__metrics dd {
  margin: 0;
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trading-unit-card__actions :deep(.el-button) {
  width: 100%;
}
</style>
