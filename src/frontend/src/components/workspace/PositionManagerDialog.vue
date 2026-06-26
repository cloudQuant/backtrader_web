<template>
  <el-dialog
    v-model="visible"
    :title="t('workspaceDialogs.positionMgrTitle')"
    width="1180px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.pmDisplayPositions') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ positions.length }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.pmAggByUnit') }}
          </div>
        </div>
        <div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <div class="text-xs text-red-500">
            {{ t('workspaceDialogs.pmLongValue') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-red-600">
            {{ formatAmountCompact(summary.total_long_value) }}
          </div>
          <div class="text-xs text-red-300">
            {{ t('workspaceDialogs.pmLongExposure') }}
          </div>
        </div>
        <div class="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <div class="text-xs text-green-500">
            {{ t('workspaceDialogs.pmShortValue') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-green-600">
            {{ formatAmountCompact(summary.total_short_value) }}
          </div>
          <div class="text-xs text-green-300">
            {{ t('workspaceDialogs.pmShortExposure') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.pmTotalPnl') }}
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="numberClass(summary.total_pnl)"
          >
            {{ formatSigned(summary.total_pnl, 2) }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.pmUnrealizedPnl') }}
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3">
        <div class="text-sm text-slate-500">
          {{ t('workspaceDialogs.pmCurrentDisplay') }} {{ positions.length }} {{ t('workspaceDialogs.pmAggUnitsSuffix') }}
        </div>
        <el-button
          size="small"
          :loading="loading"
          @click="loadPositions"
        >
          {{ t('workspaceDialogs.pmRefresh') }}
        </el-button>
      </div>

      <el-table
        :data="positions"
        stripe
        size="small"
        border
        class="position-table"
        :empty-text="t('workspaceDialogs.pmEmpty')"
      >
        <el-table-column
          prop="unit_name"
          :label="t('workspaceDialogs.pmColUnit')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="symbol"
          :label="t('workspaceDialogs.pmColSymbol')"
          width="110"
        />
        <el-table-column
          prop="symbol_name"
          :label="t('workspaceDialogs.pmColSymbolName')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column
          :label="t('workspaceDialogs.pmColMode')"
          width="90"
          align="center"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.trading_mode === 'live' ? 'danger' : 'info'"
              size="small"
            >
              {{ row.trading_mode === 'live' ? t('workspaceDialogs.pmModeLive') : t('workspaceDialogs.pmModeSim') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="long_position"
          :label="t('workspaceDialogs.pmColLong')"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            {{ formatQuantity(row.long_position) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="short_position"
          :label="t('workspaceDialogs.pmColShort')"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            {{ formatQuantity(row.short_position) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="avg_price"
          :label="t('workspaceDialogs.pmColAvgPrice')"
          width="100"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.avg_price, 4) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="latest_price"
          :label="t('workspaceDialogs.pmColLatestPrice')"
          width="100"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.latest_price, 4) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('workspaceDialogs.pmColPositionPnl')"
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
          :label="t('workspaceDialogs.pmColMarketValue')"
          width="120"
          align="right"
        >
          <template #default="{ row }">
            {{ formatAmountCompact(row.market_value) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('workspaceDialogs.pmColMarginValue')"
          width="110"
          align="right"
        >
          <template #default="{ row }">
            {{ formatAmountCompact(row.margin_value) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('workspaceDialogs.leverage')"
          width="80"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.leverage, 2) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('workspaceDialogs.pmColCommission')"
          width="95"
          align="right"
        >
          <template #default="{ row }">
            {{ formatNumber(row.commission, 2) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('workspaceDialogs.pmColValuationStatus')"
          width="125"
          align="center"
        >
          <template #default="{ row }">
            <el-tooltip
              :content="valuationTooltip(row)"
              placement="top"
            >
              <el-tag
                :type="valuationStatusTag(row)"
                size="small"
              >
                {{ valuationStatusLabel(row) }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { TradingPositionManagerItem } from '@/types/workspace'

const { t } = useI18n()

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
    positions.value = response.positions.filter(position => (
      Math.abs(Number(position.long_position || 0)) > 0
      || Math.abs(Number(position.short_position || 0)) > 0
    ))
    const nextSummary = buildVisiblePositionSummary(positions.value)
    summary.total_long_value = nextSummary.total_long_value
    summary.total_short_value = nextSummary.total_short_value
    summary.total_pnl = nextSummary.total_pnl
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.pmLoadFailed')))
  } finally {
    loading.value = false
  }
}

function buildVisiblePositionSummary(rows: TradingPositionManagerItem[]) {
  const totals = rows.reduce((sum, item) => {
    const longMarketValue = Number(item.long_market_value)
    const shortMarketValue = Number(item.short_market_value)
    if (Number.isFinite(longMarketValue) || Number.isFinite(shortMarketValue)) {
      sum.total_long_value += Number.isFinite(longMarketValue) ? Math.max(longMarketValue, 0) : 0
      sum.total_short_value += Number.isFinite(shortMarketValue) ? Math.max(shortMarketValue, 0) : 0
      sum.total_pnl += Number(item.position_pnl || 0)
      return sum
    }
    const longPosition = Math.max(Number(item.long_position || 0), 0)
    const shortPosition = Math.max(Number(item.short_position || 0), 0)
    const marketValue = Math.abs(Number(item.market_value || 0))
    const totalPosition = longPosition + shortPosition
    if (totalPosition > 0) {
      sum.total_long_value += marketValue * (longPosition / totalPosition)
      sum.total_short_value += marketValue * (shortPosition / totalPosition)
    }
    sum.total_pnl += Number(item.position_pnl || 0)
    return sum
  }, {
    total_long_value: 0,
    total_short_value: 0,
    total_pnl: 0,
  })
  return {
    total_long_value: roundAmount(totals.total_long_value),
    total_short_value: roundAmount(totals.total_short_value),
    total_pnl: roundAmount(totals.total_pnl),
  }
}

function roundAmount(value: number) {
  return Math.round((Number(value) || 0) * 100) / 100
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

function formatQuantity(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  if (!Number.isFinite(number) || number === 0) return '-'
  if (Math.abs(number) < 0.0001) return number.toFixed(8).replace(/\.?0+$/, '')
  return number.toFixed(4)
}

function formatAmountCompact(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  const abs = Math.abs(number)
  if (abs >= 100000000) {
    return `${(number / 100000000).toFixed(digits)}${t('workspaceDialogs.pmAmountYi')}`
  }
  if (abs >= 10000) {
    return `${(number / 10000).toFixed(digits)}${t('workspaceDialogs.pmAmountWan')}`
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

function valuationStatusTag(row: TradingPositionManagerItem) {
  const status = String(row.valuation_status || '').toLowerCase()
  if (row.position_source === 'gateway' && status === 'confirmed') return 'success'
  if (status === 'stale_fallback') return 'danger'
  if (status === 'estimated' || (row.valuation_warnings?.length ?? 0) > 0) return 'warning'
  return 'info'
}

function valuationStatusLabel(row: TradingPositionManagerItem) {
  const status = String(row.valuation_status || '').toLowerCase()
  if (row.position_source === 'gateway' && status === 'confirmed') return t('workspaceDialogs.pmValuationGatewayConfirmed')
  if (status === 'stale_fallback') return t('workspaceDialogs.pmValuationStale')
  if (status === 'estimated' || (row.valuation_warnings?.length ?? 0) > 0) return t('workspaceDialogs.pmValuationEstimated')
  return t('workspaceDialogs.pmValuationUnknown')
}

function positionSourceLabel(value: string | null | undefined) {
  const source = String(value || '').toLowerCase()
  if (source === 'gateway') return t('workspaceDialogs.pmSourceGateway')
  if (source === 'log') return t('workspaceDialogs.pmSourceLog')
  if (source === 'snapshot') return t('workspaceDialogs.pmSourceSnapshot')
  if (source === 'mixed') return t('workspaceDialogs.pmSourceMixed')
  return t('workspaceDialogs.pmSourceUnknown')
}

function valuationTooltip(row: TradingPositionManagerItem) {
  const warnings = row.valuation_warnings?.filter(Boolean) ?? []
  if (warnings.length > 0) return warnings.join('；')
  const assetSource = row.asset_spec_source || '-'
  return `${t('workspaceDialogs.pmPositionSource')}: ${positionSourceLabel(row.position_source)}；${t('workspaceDialogs.pmAssetSpecSource')}: ${assetSource}`
}
</script>

<style scoped>
.position-table :deep(.el-table__header th) {
  background: var(--bg-color-page);
  color: var(--text-color-regular);
  font-weight: 600;
}
</style>
