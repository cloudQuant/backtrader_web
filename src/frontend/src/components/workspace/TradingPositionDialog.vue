<template>
  <el-dialog
    :model-value="modelValue"
    title="头寸管理器"
    width="820px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="mb-4 text-sm text-gray-500">
      {{ unit?.strategy_name || unit?.strategy_id || '未选择策略单元' }}
    </div>

    <el-empty
      v-if="positions.length === 0"
      description="当前单元暂无持仓数据"
    />

    <el-table
      v-else
      :data="positions"
      border
      size="small"
      max-height="420"
    >
      <el-table-column
        prop="data_name"
        label="标的"
        min-width="140"
      />
      <el-table-column
        prop="direction"
        label="方向"
        width="90"
        align="center"
      />
      <el-table-column
        prop="size"
        label="数量"
        width="90"
        align="right"
      />
      <el-table-column
        label="开仓价"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.price, 4) }}
        </template>
      </el-table-column>
      <el-table-column
        label="当前价"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.current_price, 4) }}
        </template>
      </el-table-column>
      <el-table-column
        label="市值"
        width="120"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.market_value, 2) }}
        </template>
      </el-table-column>
      <el-table-column
        label="持仓盈亏"
        width="120"
        align="right"
      >
        <template #default="{ row }">
          <span :class="numberClass(row.pnl)">
            {{ formatSignedNumber(row.pnl, 2) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StrategyUnit } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  unit: StrategyUnit | null
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const positions = computed(() => props.unit?.trading_snapshot?.positions ?? [])

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  return Number(value).toFixed(digits)
}

function formatSignedNumber(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  return `${number >= 0 ? '+' : ''}${number.toFixed(digits)}`
}

function numberClass(value: number | null | undefined) {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-gray-500'
  return value > 0 ? 'text-red-500' : 'text-green-600'
}
</script>
