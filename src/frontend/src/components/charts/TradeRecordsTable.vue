<template>
  <div class="trade-records-table">
    <div class="flex justify-between items-center mb-4">
      <h4 class="text-md font-medium">
        {{ t('charts.trTitle') }}
      </h4>
      <div class="flex gap-2">
        <el-select
          v-model="directionFilter"
          :placeholder="t('charts.trDirection')"
          size="small"
          clearable
          style="width: 120px"
        >
          <el-option
            :label="t('charts.trAll')"
            value=""
          />
          <el-option
            :label="t('charts.trBuy')"
            value="buy"
          />
          <el-option
            :label="t('charts.trSell')"
            value="sell"
          />
        </el-select>
        <el-select
          v-model="pnlFilter"
          :placeholder="t('charts.trPnlState')"
          size="small"
          clearable
          style="width: 120px"
        >
          <el-option
            :label="t('charts.trAll')"
            value=""
          />
          <el-option
            :label="t('charts.trProfit')"
            value="profit"
          />
          <el-option
            :label="t('charts.trLoss')"
            value="loss"
          />
        </el-select>
        <el-button
          size="small"
          @click="handleExport"
        >
          <el-icon aria-hidden="true"><Download /></el-icon>{{ t('charts.trExport') }}
        </el-button>
      </div>
    </div>
    
    <!-- Summary stats -->
    <div class="grid grid-cols-4 gap-4 mb-4 p-3 bg-gray-50 rounded">
      <div class="text-center">
        <div class="text-gray-500 text-xs">
          {{ t('charts.trTotalTrades') }}
        </div>
        <div class="font-semibold">
          {{ trades.length }}
        </div>
      </div>
      <div class="text-center">
        <div class="text-gray-500 text-xs">
          {{ t('charts.trProfitCount') }}
        </div>
        <div class="font-semibold text-green-600">
          {{ profitCount }}
        </div>
      </div>
      <div class="text-center">
        <div class="text-gray-500 text-xs">
          {{ t('charts.trLossCount') }}
        </div>
        <div class="font-semibold text-red-600">
          {{ lossCount }}
        </div>
      </div>
      <div class="text-center">
        <div class="text-gray-500 text-xs">
          {{ t('charts.trTotalCommission') }}
        </div>
        <div class="font-semibold">
          ¥{{ totalCommission.toFixed(2) }}
        </div>
      </div>
    </div>
    
    <!-- Trade table -->
    <el-table
      :data="filteredTrades"
      stripe
      border
      size="small"
      :default-sort="{ prop: 'id', order: 'descending' }"
      max-height="400"
    >
      <el-table-column
        prop="id"
        :label="t('charts.trColId')"
        width="60"
        sortable
      />
      <el-table-column
        prop="direction"
        :label="t('charts.trColDirection')"
        width="70"
      >
        <template #default="{ row }">
          <el-tag
            :type="row.direction === 'buy' ? 'danger' : 'success'"
            size="small"
          >
            {{ row.direction === 'buy' ? t('charts.trBuy') : t('charts.trSell') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="dtopen"
        :label="t('charts.trColOpenDate')"
        width="110"
        sortable
      />
      <el-table-column
        prop="price"
        :label="t('charts.trColOpenPrice')"
        width="90"
        sortable
      >
        <template #default="{ row }">
          {{ row.price.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="dtclose"
        :label="t('charts.trColCloseDate')"
        width="110"
        sortable
      />
      <el-table-column
        prop="close_price"
        :label="t('charts.trColClosePrice')"
        width="90"
        sortable
      >
        <template #default="{ row }">
          {{ row.close_price !== null ? row.close_price.toFixed(2) : '--' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="size"
        :label="t('charts.trColSize')"
        width="80"
        sortable
      />
      <el-table-column
        prop="value"
        :label="t('charts.trColValue')"
        width="100"
        sortable
      >
        <template #default="{ row }">
          ¥{{ row.value.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="commission"
        :label="t('charts.trColCommission')"
        width="80"
      >
        <template #default="{ row }">
          ¥{{ row.commission.toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="pnl"
        :label="t('charts.trColPnl')"
        width="100"
        sortable
      >
        <template #default="{ row }">
          <span
            v-if="row.pnl !== null"
            :class="row.pnl >= 0 ? 'text-green-600' : 'text-red-600'"
          >
            {{ row.pnl >= 0 ? '+' : '' }}¥{{ row.pnl.toFixed(2) }}
          </span>
          <span
            v-else
            class="text-gray-400"
          >--</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="return_pct"
        :label="t('charts.trColReturnPct')"
        width="90"
        sortable
      >
        <template #default="{ row }">
          <span
            v-if="row.return_pct !== null"
            :class="row.return_pct >= 0 ? 'text-green-600' : 'text-red-600'"
          >
            {{ row.return_pct >= 0 ? '+' : '' }}{{ (row.return_pct * 100).toFixed(2) }}%
          </span>
          <span
            v-else
            class="text-gray-400"
          >--</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="holding_days"
        :label="t('charts.trColHoldingDays')"
        width="90"
      >
        <template #default="{ row }">
          {{ row.holding_days !== null ? row.holding_days + t('charts.days') : '--' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="cumulative_pnl"
        :label="t('charts.trColCumulativePnl')"
        width="110"
        sortable
      >
        <template #default="{ row }">
          <span :class="row.cumulative_pnl >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ row.cumulative_pnl >= 0 ? '+' : '' }}¥{{ row.cumulative_pnl.toFixed(2) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download } from '@element-plus/icons-vue'
import type { TradeRecord } from '@/types/analytics'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  trades: TradeRecord[]
}>(), {
  trades: () => [],
})

const directionFilter = ref('')
const pnlFilter = ref('')

const filteredTrades = computed(() => {
  return props.trades.filter(tr => {
    if (directionFilter.value && tr.direction !== directionFilter.value) return false
    if (pnlFilter.value === 'profit' && (tr.pnl === null || tr.pnl <= 0)) return false
    if (pnlFilter.value === 'loss' && (tr.pnl === null || tr.pnl >= 0)) return false
    return true
  })
})

const profitCount = computed(() => props.trades.filter(tr => tr.pnl !== null && tr.pnl > 0).length)
const lossCount = computed(() => props.trades.filter(tr => tr.pnl !== null && tr.pnl < 0).length)
const totalCommission = computed(() => props.trades.reduce((sum, tr) => sum + tr.commission, 0))

function handleExport() {
  const headers = [
    t('charts.trColId'),
    t('charts.trColDirection'),
    t('charts.trColOpenDate'),
    t('charts.trColOpenPrice'),
    t('charts.trColCloseDate'),
    t('charts.trColClosePrice'),
    t('charts.trColSize'),
    t('charts.trColValue'),
    t('charts.trColCommission'),
    t('charts.trColPnl'),
    t('charts.trColReturnPct'),
    t('charts.trColHoldingDays'),
    t('charts.trColCumulativePnl'),
  ]
  const rows = filteredTrades.value.map(tr => [
    tr.id,
    tr.direction === 'buy' ? t('charts.trBuy') : t('charts.trSell'),
    tr.dtopen ?? '',
    tr.price,
    tr.dtclose ?? '',
    tr.close_price ?? '',
    tr.size,
    tr.value,
    tr.commission,
    tr.pnl ?? '',
    tr.return_pct !== null ? (tr.return_pct * 100).toFixed(2) + '%' : '',
    tr.holding_days ?? '',
    tr.cumulative_pnl,
  ])
  
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'trade_records.csv'
  link.click()
  URL.revokeObjectURL(url)
}
</script>
