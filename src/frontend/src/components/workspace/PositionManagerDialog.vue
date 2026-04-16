<template>
  <el-dialog
    v-model="visible"
    title="头寸管理器"
    width="1180px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            展示头寸
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ positions.length }}
          </div>
          <div class="text-xs text-slate-400">
            按策略单元聚合
          </div>
        </div>
        <div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <div class="text-xs text-red-500">
            多头市值
          </div>
          <div class="mt-1 text-lg font-semibold text-red-600">
            {{ formatAmountCompact(summary.total_long_value) }}
          </div>
          <div class="text-xs text-red-300">
            Long Exposure
          </div>
        </div>
        <div class="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <div class="text-xs text-green-500">
            空头市值
          </div>
          <div class="mt-1 text-lg font-semibold text-green-600">
            {{ formatAmountCompact(summary.total_short_value) }}
          </div>
          <div class="text-xs text-green-300">
            Short Exposure
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <div class="text-xs text-slate-500">
            总盈亏
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="numberClass(summary.total_pnl)"
          >
            {{ formatSigned(summary.total_pnl, 2) }}
          </div>
          <div class="text-xs text-slate-400">
            Unrealized PnL
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3">
        <div class="text-sm text-slate-500">
          当前展示 {{ positions.length }} 个策略单元的聚合头寸
        </div>
        <el-button
          size="small"
          :loading="loading"
          @click="loadPositions"
        >
          刷新
        </el-button>
      </div>

      <el-table
        :data="positions"
        stripe
        size="small"
        border
        class="position-table"
        empty-text="暂无可展示的头寸数据"
      >
        <el-table-column
          prop="unit_name"
          label="策略单元"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="symbol"
          label="品种"
          width="110"
        />
        <el-table-column
          prop="symbol_name"
          label="简称"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column
          label="模式"
          width="90"
          align="center"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.trading_mode === 'live' ? 'danger' : 'info'"
              size="small"
            >
              {{ row.trading_mode === 'live' ? '实盘' : '模拟' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="long_position"
          label="多仓"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.long_position, 2) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="short_position"
          label="空仓"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.short_position, 2) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="avg_price"
          label="均价"
          width="100"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.avg_price, 4) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="latest_price"
          label="最新价"
          width="100"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.latest_price, 4) }}
          </template>
        </el-table-column>
        <el-table-column
          label="持仓盈亏"
          width="110"
          align="right"
        >
          <template #default="{ row }">
            <span :class="numberClass(row.position_pnl)">
              {{ formatSigned(row.position_pnl, 2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          label="市值"
          width="120"
          align="right"
        >
          <template #default="{ row }">
            {{ formatAmountCompact(row.market_value) }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { TradingPositionManagerItem } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unitIds?: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const loading = ref(false)
const positions = ref<TradingPositionManagerItem[]>([])
const summary = reactive({
  total_long_value: 0,
  total_short_value: 0,
  total_pnl: 0,
})

async function loadPositions() {
  loading.value = true
  try {
    const response = await workspaceApi.getTradingPositions(props.workspaceId, props.unitIds)
    positions.value = response.positions
    summary.total_long_value = response.total_long_value
    summary.total_short_value = response.total_short_value
    summary.total_pnl = response.total_pnl
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '加载头寸数据失败'))
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      void loadPositions()
    }
  },
)

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  return Number(value).toFixed(digits)
}

function formatAmountCompact(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  const abs = Math.abs(number)
  if (abs >= 100000000) {
    return `${(number / 100000000).toFixed(digits)}亿`
  }
  if (abs >= 10000) {
    return `${(number / 10000).toFixed(digits)}万`
  }
  return number.toFixed(digits)
}

function formatSigned(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  return `${number >= 0 ? '+' : ''}${number.toFixed(digits)}`
}

function numberClass(value: number | null | undefined) {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-slate-600'
  return value > 0 ? 'text-red-600' : 'text-green-600'
}
</script>

<style scoped>
.position-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
</style>
