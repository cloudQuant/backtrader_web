<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('workspaceDialogs.tpdTitle')"
    width="820px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="mb-4 text-sm text-gray-500">
      {{ unit?.strategy_name || unit?.strategy_id || t('workspaceDialogs.tpdNoUnit') }}
    </div>

    <el-empty
      v-if="positions.length === 0"
      :description="t('workspaceDialogs.tpdEmpty')"
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
        :label="t('workspaceDialogs.tpdColInstrument')"
        min-width="140"
      />
      <el-table-column
        prop="direction"
        :label="t('workspaceDialogs.tpdColDirection')"
        width="90"
        align="center"
      />
      <el-table-column
        :label="t('workspaceDialogs.tpdColSize')"
        width="90"
        align="right"
      >
        <template #default="{ row }">
          {{ formatQuantity(row.size) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('workspaceDialogs.tpdColOpenPrice')"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.price, 4) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('workspaceDialogs.tpdColCurrentPrice')"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.current_price, 4) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('workspaceDialogs.tpdColMarketValue')"
        width="120"
        align="right"
      >
        <template #default="{ row }">
          {{ formatAmount(row.market_value) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('workspaceDialogs.tpdColPositionPnl')"
        width="120"
        align="right"
      >
        <template #default="{ row }">
          <span :class="numberClass(positionPnl(row))">
            {{ formatSignedAmount(positionPnl(row)) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { StrategyUnit } from '@/types/workspace'
import { formatQuantity } from '@/composables/useUnitTableRendering'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  unit: StrategyUnit | null
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const POSITION_EPSILON = 1e-12

const positions = computed(() => (
  (props.unit?.trading_snapshot?.positions ?? []).filter(position => (
    Math.abs(Number(position.size || 0)) > POSITION_EPSILON
  ))
))

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  return Number(value).toFixed(digits)
}

function formatAmount(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  if (number !== 0 && Math.abs(number) < 1) return number.toFixed(6).replace(/\.?0+$/, '')
  return number.toFixed(2)
}

function formatSignedAmount(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return `${number >= 0 ? '+' : ''}${formatAmount(number)}`
}

function positionPnl(row: Record<string, unknown>) {
  for (const key of ['pnlcomm', 'position_pnl', 'net_pnl', 'pnl', 'gross_pnl']) {
    const value = row[key]
    if (value == null || value === '') continue
    const number = Number(value)
    if (Number.isFinite(number)) return number
  }
  return null
}

function numberClass(value: number | null | undefined) {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-gray-500'
  return value > 0 ? 'text-red-500' : 'text-green-600'
}
</script>
