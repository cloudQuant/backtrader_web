<template>
  <div class="trade-records-table">
    <div class="flex justify-between items-center mb-4">
      <h4 class="text-md font-medium">交易记录</h4>
      <div class="flex gap-2">
        <el-select v-model="directionFilter" placeholder="交易方向" size="small" clearable style="width: 120px">
          <el-option label="全部" value="" />
          <el-option label="买入" value="buy" />
          <el-option label="卖出" value="sell" />
        </el-select>
        <el-select v-model="pnlFilter" placeholder="盈亏状态" size="small" clearable style="width: 120px">
          <el-option label="全部" value="" />
          <el-option label="盈利" value="profit" />
          <el-option label="亏损" value="loss" />
        </el-select>
        <el-button size="small" @click="handleExport">
          <el-icon><Download /></el-icon>导出
        </el-button>
      </div>
    </div>
    
    <!-- 汇总统计 -->
    <div class="grid grid-cols-4 gap-4 mb-4 p-3 bg-gray-50 rounded">
      <div class="text-center">
        <div class="text-gray-500 text-xs">总交易</div>
        <div class="font-semibold">{{ trades.length }}</div>
      </div>
      <div class="text-center">
        <div class="text-gray-500 text-xs">盈利次数</div>
        <div class="font-semibold text-green-600">{{ profitCount }}</div>
      </div>
      <div class="text-center">
        <div class="text-gray-500 text-xs">亏损次数</div>
        <div class="font-semibold text-red-600">{{ lossCount }}</div>
      </div>
      <div class="text-center">
        <div class="text-gray-500 text-xs">总手续费</div>
        <div class="font-semibold">¥{{ totalCommission.toFixed(2) }}</div>
      </div>
    </div>
    
    <!-- 交易表格 -->
    <el-table
      :data="filteredTrades"
      stripe
      border
      size="small"
      :default-sort="{ prop: 'id', order: 'descending' }"
      max-height="400"
    >
      <el-table-column prop="id" label="序号" width="60" sortable />
      <el-table-column prop="datetime" label="时间" width="160" sortable />
      <el-table-column prop="direction" label="方向" width="70">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'buy' ? 'danger' : 'success'" size="small">
            {{ row.direction === 'buy' ? '买入' : '卖出' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="price" label="价格" width="90" sortable>
        <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="size" label="数量" width="80" sortable />
      <el-table-column prop="value" label="金额" width="100" sortable>
        <template #default="{ row }">¥{{ row.value.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="commission" label="手续费" width="80">
        <template #default="{ row }">¥{{ row.commission.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="pnl" label="盈亏" width="100" sortable>
        <template #default="{ row }">
          <span v-if="row.pnl !== null" :class="row.pnl >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ row.pnl >= 0 ? '+' : '' }}¥{{ row.pnl.toFixed(2) }}
          </span>
          <span v-else class="text-gray-400">--</span>
        </template>
      </el-table-column>
      <el-table-column prop="return_pct" label="收益率" width="90" sortable>
        <template #default="{ row }">
          <span v-if="row.return_pct !== null" :class="row.return_pct >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ row.return_pct >= 0 ? '+' : '' }}{{ (row.return_pct * 100).toFixed(2) }}%
          </span>
          <span v-else class="text-gray-400">--</span>
        </template>
      </el-table-column>
      <el-table-column prop="holding_days" label="持仓天数" width="90">
        <template #default="{ row }">
          {{ row.holding_days !== null ? row.holding_days + '天' : '--' }}
        </template>
      </el-table-column>
      <el-table-column prop="cumulative_pnl" label="累计盈亏" width="110" sortable>
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
import { Download } from '@element-plus/icons-vue'
import type { TradeRecord } from '@/types/analytics'

const props = withDefaults(defineProps<{
  trades: TradeRecord[]
}>(), {
  trades: () => [],
})

const directionFilter = ref('')
const pnlFilter = ref('')

const filteredTrades = computed(() => {
  return props.trades.filter(t => {
    if (directionFilter.value && t.direction !== directionFilter.value) return false
    if (pnlFilter.value === 'profit' && (t.pnl === null || t.pnl <= 0)) return false
    if (pnlFilter.value === 'loss' && (t.pnl === null || t.pnl >= 0)) return false
    return true
  })
})

const profitCount = computed(() => props.trades.filter(t => t.pnl !== null && t.pnl > 0).length)
const lossCount = computed(() => props.trades.filter(t => t.pnl !== null && t.pnl < 0).length)
const totalCommission = computed(() => props.trades.reduce((sum, t) => sum + t.commission, 0))

function handleExport() {
  const headers = ['序号', '时间', '方向', '价格', '数量', '金额', '手续费', '盈亏', '收益率', '持仓天数', '累计盈亏']
  const rows = filteredTrades.value.map(t => [
    t.id,
    t.datetime,
    t.direction === 'buy' ? '买入' : '卖出',
    t.price,
    t.size,
    t.value,
    t.commission,
    t.pnl ?? '',
    t.return_pct !== null ? (t.return_pct * 100).toFixed(2) + '%' : '',
    t.holding_days ?? '',
    t.cumulative_pnl,
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
