<template>
  <el-dialog
    v-model="visible"
    :title="t('workspaceDialogs.tdsTitle')"
    width="980px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.tdsTradingDays') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ summaries.length }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.tdsCurrentRange') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.tdsCumulativePnl') }}
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="numberClass(totalCumulativePnl)"
          >
            {{ formatSigned(totalCumulativePnl, 2) }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.tdsLastDayBasis') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.tdsTotalTrades') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ totalTradeCount }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.tdsPeriodSum') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.tdsBestDailyPnl') }}
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="numberClass(bestDailyPnl)"
          >
            {{ formatSigned(bestDailyPnl, 2) }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.tdsBasedDailyPnl') }}
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <el-select
            v-model="selectedUnitId"
            clearable
            :placeholder="t('workspaceDialogs.tdsAllUnits')"
            size="small"
          >
            <el-option
              :label="t('workspaceDialogs.tdsAllUnits')"
              value=""
            />
            <el-option
              v-for="unit in store.units"
              :key="unit.id"
              :label="unit.strategy_name || unit.strategy_id || unit.id"
              :value="unit.id"
            />
          </el-select>
          <el-date-picker
            v-model="startDate"
            type="date"
            value-format="YYYY-MM-DD"
            :placeholder="t('workspaceDialogs.tdsStartDate')"
            size="small"
          />
          <el-date-picker
            v-model="endDate"
            type="date"
            value-format="YYYY-MM-DD"
            :placeholder="t('workspaceDialogs.tdsEndDate')"
            size="small"
          />
          <div class="flex gap-2">
            <el-button
              size="small"
              :loading="loading"
              type="primary"
              @click="loadSummary"
            >
              {{ t('workspaceDialogs.tdsQuery') }}
            </el-button>
            <el-button
              size="small"
              @click="resetFilters"
            >
              {{ t('workspaceDialogs.tdsReset') }}
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
        :empty-text="t('workspaceDialogs.tdsEmpty')"
      >
        <el-table-column
          prop="trading_date"
          :label="t('workspaceDialogs.tdsColDate')"
          width="120"
        />
        <el-table-column
          :label="t('workspaceDialogs.tdsColDailyPnl')"
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
          :label="t('workspaceDialogs.tdsColTradeCount')"
          width="100"
          align="right"
        />
        <el-table-column
          :label="t('workspaceDialogs.tdsColCumulativePnl')"
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
          :label="t('workspaceDialogs.tdsColMaxDrawdown')"
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
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import { useWorkspaceStore } from '@/stores/workspace'
import type { TradingDailySummaryItem } from '@/types/workspace'

const { t } = useI18n()

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
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.tdsLoadFailed')))
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
  background: var(--bg-color-page);
  color: var(--text-color-regular);
  font-weight: 600;
}
</style>
