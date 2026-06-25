<template>
    <el-dialog
      :model-value="visible"
      @update:model-value="(v: boolean) => emit('update:visible', v)"
      :title="t('tradingUnits.unitDetail')"
      width="980px"
    >
      <div
        v-if="detailUnit"
        class="space-y-4 text-sm"
      >
        <div class="flex flex-wrap items-center justify-end gap-2">
          <el-button
            size="small"
            @click="emit('openRuntimeDialog', detailUnit)"
          >
            {{ t('tradingUnits.viewRunFile') }}
          </el-button>
          <el-button
            type="primary"
            size="small"
            @click="emit('openRuntimeDirectory', detailUnit)"
          >
            {{ t('tradingUnits.openUnit') }}
          </el-button>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.unit') }}
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.strategy_name || detailUnit.strategy_id }}
            </div>
            <div class="text-xs text-slate-400">
              {{ detailUnit.symbol }} / {{ detailUnit.timeframe }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.tradingMode') }}
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_mode === 'live' ? t('tradingUnits.liveTrading') : t('tradingUnits.paperTrading') }}
            </div>
            <div class="text-xs text-slate-400">
              {{ statusLabel(detailUnit) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.gateway') }}
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_snapshot?.gateway_summary || '-' }}
            </div>
            <div class="text-xs text-slate-400">
              {{ t('tradingUnits.instance') }} {{ detailUnit.trading_instance_id || '-' }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.lastUpdate') }}
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_snapshot?.updated_at || formatTime(detailUnit.updated_at) }}
            </div>
            <div class="text-xs text-slate-400">
              {{ t('tradingUnits.tradingDay') }} {{ detailUnit.trading_snapshot?.trading_day || '-' }}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.longPosition') }} / {{ t('tradingUnits.flat') }}
            </div>
            <div class="mt-1 text-lg font-semibold text-slate-700">
              {{ formatNumber(detailUnit.trading_snapshot?.long_position, 0, false) }}
              /
              {{ formatNumber(detailUnit.trading_snapshot?.short_position, 0, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.todayPnL') }}
            </div>
            <div
              class="mt-1 text-lg font-semibold"
              :class="numberClass(detailUnit.trading_snapshot?.today_pnl)"
            >
              {{ formatSignedNumber(detailUnit.trading_snapshot?.today_pnl, 2, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.cumulativePnL') }}
            </div>
            <div
              class="mt-1 text-lg font-semibold"
              :class="numberClass(detailUnit.trading_snapshot?.cumulative_pnl)"
            >
              {{ formatSignedNumber(detailUnit.trading_snapshot?.cumulative_pnl, 2, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              {{ t('tradingUnits.leverage') }} / {{ t('tradingUnits.latestPrice') }}
            </div>
            <div class="mt-1 text-lg font-semibold text-slate-700">
              {{ formatNumber(detailUnit.trading_snapshot?.leverage, 2, false) }}
              /
              {{ formatPrice(detailUnit.trading_snapshot?.latest_price) }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-3 text-sm font-medium text-slate-700">
            {{ t('tradingUnits.runInfo') }}
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div><span class="text-gray-500">{{ t('tradingUnits.runStarted') }}：</span>{{ detailUnit.trading_snapshot?.started_at || '-' }}</div>
            <div><span class="text-gray-500">{{ t('tradingUnits.runStopped') }}：</span>{{ detailUnit.trading_snapshot?.stopped_at || '-' }}</div>
            <div class="md:col-span-2">
              <span class="text-gray-500">{{ t('tradingUnits.errorInfo') }}：</span>{{ detailUnit.trading_snapshot?.error || '-' }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-3 text-sm font-medium text-slate-700">
            {{ t('tradingUnits.tradeDetail') }}
          </div>
          <el-table
            :data="detailUnit.trading_snapshot?.trades || []"
            size="small"
            border
            class="detail-trades-table"
            :empty-text="t('tradingUnits.noTradeDetail')"
          >
            <el-table-column
              prop="id"
              :label="t('tradingUnits.tradeId')"
              width="90"
              align="center"
              show-overflow-tooltip
            />
            <el-table-column
              prop="data_name"
              :label="t('tradingUnits.contract')"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('tradingUnits.direction')"
              width="90"
              align="center"
            >
              <template #default="{ row }">
                {{ directionLabel(row.direction) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="size"
              :label="t('tradingUnits.quantity')"
              width="90"
              align="right"
            />
            <el-table-column
              :label="t('tradingUnits.tradePrice')"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                {{ formatPrice(row.price) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('tradingUnits.netPnL')"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                <span :class="numberClass(tradePnl(row))">
                  {{ formatSignedNumber(tradePnl(row), 2, false) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('tradingUnits.commission')"
              width="100"
              align="right"
            >
              <template #default="{ row }">
                {{ formatNumber(row.commission, 2, false) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('tradingUnits.openTime')"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ formatTradeTime(row.dtopen) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('tradingUnits.closeTime')"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ formatTradeTime(row.dtclose) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('tradingUnits.holdingBars')"
              width="100"
              align="right"
            >
              <template #default="{ row }">
                {{ formatNumber(row.barlen, 0, false) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-dialog>
</template>

<script setup lang="ts">
import {
  directionLabel,
  formatNumber,
  formatPrice,
  formatSignedNumber,
  formatTime,
  numberClass,
  statusLabel,
} from '@/composables/useUnitTableRendering'
import { useI18n } from 'vue-i18n'
import type { StrategyUnit, TradingTrade } from '@/types/workspace'

const { t } = useI18n()

defineProps<{
  visible: boolean
  detailUnit: StrategyUnit | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'openRuntimeDialog', unit: StrategyUnit): void
  (e: 'openRuntimeDirectory', unit: StrategyUnit): void
}>()

function formatTradeTime(value: string | null | undefined): string {
  const text = String(value ?? '').trim()
  if (!text) return '-'
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text
  const date = new Date(text.replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('zh-CN')
}

function tradePnl(row: TradingTrade): number | null {
  return row.pnlcomm ?? row.pnl ?? null
}
</script>
