<template>
  <el-dialog
    v-model="visible"
    title="交易日统计选项"
    width="980px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            交易日数量
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ summaries.length }}
          </div>
          <div class="text-xs text-slate-400">
            当前筛选范围
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            累计盈亏
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="numberClass(totalCumulativePnl)"
          >
            {{ formatSigned(totalCumulativePnl, 2) }}
          </div>
          <div class="text-xs text-slate-400">
            最后一个交易日口径
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            总成交笔数
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ totalTradeCount }}
          </div>
          <div class="text-xs text-slate-400">
            统计期间合计
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            最佳单日盈亏
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="numberClass(bestDailyPnl)"
          >
            {{ formatSigned(bestDailyPnl, 2) }}
          </div>
          <div class="text-xs text-slate-400">
            基于当日盈亏
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <el-select
            v-model="selectedUnitId"
            clearable
            placeholder="全部单元"
            size="small"
          >
            <el-option
              label="全部单元"
              value=""
            />
            <el-option
              v-for="unit in store.units"
              :key="unit.id"
              :label="unit.strategy_name || unit.strategy_id"
              :value="unit.id"
            />
          </el-select>
          <el-date-picker
            v-model="startDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="开始日期"
            size="small"
          />
          <el-date-picker
            v-model="endDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="结束日期"
            size="small"
          />
          <div class="flex gap-2">
            <el-button
              size="small"
              :loading="loading"
              type="primary"
              @click="loadSummary"
            >
              查询
            </el-button>
            <el-button
              size="small"
              @click="resetFilters"
            >
              重置
            </el-button>
          </div>
        </div>
      </div>

      <el-table
        :data="summaries"
        stripe
        border
        size="small"
        class="dialog-table"
        empty-text="暂无交易日统计数据"
      >
        <el-table-column
          prop="trading_date"
          label="交易日"
          width="120"
        />
        <el-table-column
          label="当日盈亏"
          width="120"
          align="right"
        >
          <template #default="{ row }">
            <span :class="numberClass(row.daily_pnl)">
              {{ formatSigned(row.daily_pnl, 2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="trade_count"
          label="成交笔数"
          width="100"
          align="right"
        />
        <el-table-column
          label="累计盈亏"
          width="120"
          align="right"
        >
          <template #default="{ row }">
            <span :class="numberClass(row.cumulative_pnl)">
              {{ formatSigned(row.cumulative_pnl, 2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          label="最大回撤"
          width="110"
          align="right"
        >
          <template #default="{ row }">
            {{ formatSigned(row.max_drawdown, 2, '%') }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import { useWorkspaceStore } from '@/stores/workspace'
import type { TradingDailySummaryItem } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const store = useWorkspaceStore()
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const loading = ref(false)
const selectedUnitId = ref('')
const startDate = ref('')
const endDate = ref('')
const summaries = ref<TradingDailySummaryItem[]>([])
const totalTradeCount = computed(() =>
  summaries.value.reduce((total, item) => total + Number(item.trade_count || 0), 0)
)
const totalCumulativePnl = computed(() =>
  summaries.value.length ? Number(summaries.value[summaries.value.length - 1]?.cumulative_pnl || 0) : 0
)
const bestDailyPnl = computed(() =>
  summaries.value.length
    ? summaries.value.reduce((best, item) => Math.max(best, Number(item.daily_pnl || 0)), Number.NEGATIVE_INFINITY)
    : 0
)

async function loadSummary() {
  loading.value = true
  try {
    const response = await workspaceApi.getTradingDailySummary(props.workspaceId, {
      unit_id: selectedUnitId.value || undefined,
      start_date: startDate.value || undefined,
      end_date: endDate.value || undefined,
    })
    summaries.value = response.summaries
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '加载交易日统计失败'))
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  selectedUnitId.value = ''
  startDate.value = ''
  endDate.value = ''
  void loadSummary()
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      void loadSummary()
    }
  },
)

function formatSigned(value: number | null | undefined, digits = 2, suffix = '') {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  return `${number >= 0 ? '+' : ''}${number.toFixed(digits)}${suffix}`
}

function numberClass(value: number | null | undefined) {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-slate-600'
  return value > 0 ? 'text-red-600' : 'text-green-600'
}
</script>

<style scoped>
.dialog-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
</style>
