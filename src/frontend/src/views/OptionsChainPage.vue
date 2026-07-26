<template>
  <div class="options-page">
    <header class="options-header">
      <div>
        <div class="options-eyebrow">
          {{ t('optionsChain.headerEyebrow') }}
        </div>
        <h2>
          {{ t('optionsChain.headerTitle') }}
        </h2>
        <p>
          {{ t('optionsChain.headerDesc') }}
        </p>
      </div>

      <div
        v-if="summary"
        class="options-status-strip"
      >
        <span>{{ t('optionsChain.metaUnderlying') }} <strong>{{ summary.underlying }}</strong></span>
        <span>{{ t('optionsChain.metaSource') }} <strong>{{ summary.source }}</strong></span>
        <span>{{ t('optionsChain.metaUpdated') }} <strong>{{ formattedTimestamp }}</strong></span>
      </div>
    </header>

    <el-card class="options-workbench">
      <section class="options-query-bar">
        <label class="options-field">
          <span>{{ t('optionsChain.fieldSymbol') }}</span>
          <el-input
            v-model="symbol"
            :placeholder="t('optionsChain.formSymbolPlaceholder')"
          />
        </label>
        <label class="options-field">
          <span>{{ t('optionsChain.fieldExpiry') }}</span>
          <el-input
            v-model="expiry"
            :placeholder="t('optionsChain.formExpiryPlaceholder')"
          />
        </label>
        <label class="options-field">
          <span>{{ t('optionsChain.fieldProvider') }}</span>
          <el-select v-model="provider">
            <el-option
              label="Data Governance"
              value="data_governance"
            />
            <el-option
              label="Auto"
              value="auto"
            />
            <el-option
              label="Mock"
              value="mock"
            />
          </el-select>
        </label>
        <el-button
          class="options-query-button"
          type="primary"
          :loading="loading"
          @click="load"
        >
          {{ t('optionsChain.btnQuery') }}
        </el-button>
      </section>

      <div
        v-if="summary"
        class="options-metric-section"
      >
        <div class="options-section-header">
          <div>
            <h3>{{ t('optionsChain.metricsTitle') }}</h3>
            <p>{{ t('optionsChain.metricsDesc') }}</p>
          </div>
          <span class="options-expiry-pill">{{ expiry }}</span>
        </div>

        <div class="options-metric-grid">
          <div
            v-for="metric in metricCards"
            :key="metric.key"
            class="options-metric-card"
            :class="`is-${metric.tone}`"
          >
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <small>{{ metric.helper }}</small>
          </div>
        </div>
      </div>

      <section class="options-table-panel">
        <div class="options-section-header">
          <div>
            <h3>{{ t('optionsChain.tableTitle') }}</h3>
            <p>{{ t('optionsChain.tableDesc') }}</p>
          </div>
          <span class="options-row-count">{{ t('optionsChain.rowCount', { count: rows.length }) }}</span>
        </div>

        <el-table
          :data="rows"
          class="options-chain-table"
        >
          <el-table-column
            :label="t('optionsChain.callSide')"
            align="center"
          >
            <el-table-column label="OI">
              <template #default="scope">
                {{ scope.row.call?.oi }}
              </template>
            </el-table-column>
            <el-table-column label="Vol">
              <template #default="scope">
                {{ scope.row.call?.volume }}
              </template>
            </el-table-column>
            <el-table-column label="IV">
              <template #default="scope">
                {{ formatPercent(scope.row.call?.iv) }}
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column
            prop="strike"
            :label="t('optionsChain.colStrike')"
            align="center"
          >
            <template #default="scope">
              <span
                class="options-strike"
                :class="{ 'is-atm': Number(scope.row.strike) === getSummaryNumber('atm_strike') }"
              >
                {{ scope.row.strike }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('optionsChain.putSide')"
            align="center"
          >
            <el-table-column label="IV">
              <template #default="scope">
                {{ formatPercent(scope.row.put?.iv) }}
              </template>
            </el-table-column>
            <el-table-column label="Vol">
              <template #default="scope">
                {{ scope.row.put?.volume }}
              </template>
            </el-table-column>
            <el-table-column label="OI">
              <template #default="scope">
                {{ scope.row.put?.oi }}
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </section>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { marketIntelApi } from '@/api/marketIntel'

const { t } = useI18n()

const loading = ref(false)
const symbol = ref('RB2510')
const expiry = ref('2026-12-31')
const provider = ref('data_governance')
const summary = ref<Record<string, unknown> | null>(null)

type OptionLeg = Record<string, unknown>
type OptionChainRow = Record<string, unknown> & {
  call?: OptionLeg
  put?: OptionLeg
}

const rows = ref<OptionChainRow[]>([])

const formattedTimestamp = computed(() => formatTimestamp(summary.value?.timestamp))

const metricCards = computed(() => {
  if (!summary.value) return []
  return [
    {
      key: 'pcr',
      label: 'Put / Call Ratio',
      value: formatNumber(summary.value.pcr, 2),
      helper: t('optionsChain.metricPcrHelper'),
      tone: 'neutral',
    },
    {
      key: 'max_pain',
      label: 'Max Pain',
      value: formatNumber(summary.value.max_pain, 0),
      helper: t('optionsChain.metricMaxPainHelper'),
      tone: 'amber',
    },
    {
      key: 'atm_iv',
      label: 'ATM IV',
      value: formatPercent(summary.value.atm_iv),
      helper: t('optionsChain.metricAtmIvHelper'),
      tone: 'teal',
    },
    {
      key: 'spot',
      label: 'Spot',
      value: formatNumber(summary.value.spot, 0),
      helper: t('optionsChain.metricSpotHelper'),
      tone: 'blue',
    },
    {
      key: 'strike_count',
      label: t('optionsChain.statStrikeCount'),
      value: formatNumber(summary.value.strike_count, 0),
      helper: t('optionsChain.metricStrikeCountHelper'),
      tone: 'neutral',
    },
    {
      key: 'strike_step',
      label: t('optionsChain.statStrikeStep'),
      value: formatNumber(summary.value.strike_step, 0),
      helper: t('optionsChain.metricStrikeStepHelper'),
      tone: 'neutral',
    },
  ]
})

async function load() {
  loading.value = true
  try {
    const response = await marketIntelApi.getOptionsChain(symbol.value, expiry.value, provider.value)
    summary.value = response
    rows.value = Array.isArray(response.rows) ? response.rows as OptionChainRow[] : []
  } finally {
    loading.value = false
  }
}

function getSummaryNumber(key: string) {
  return toFiniteNumber(summary.value?.[key])
}

function toFiniteNumber(value: unknown) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : undefined
}

function formatNumber(value: unknown, digits = 2) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === undefined) return '-'
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(numericValue)
}

function formatPercent(value: unknown) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === undefined) return '-'
  return `${(numericValue * 100).toFixed(2)}%`
}

function formatTimestamp(value: unknown) {
  const rawValue = String(value || '').trim()
  if (!rawValue) return '-'
  const parsed = new Date(rawValue)
  if (Number.isNaN(parsed.getTime())) return rawValue
  return parsed.toLocaleString()
}

void load()
</script>

<style scoped>
.options-page {
  display: grid;
  gap: 16px;
}

.options-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
}

.options-eyebrow {
  margin-bottom: 4px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 600;
}

.options-header h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 24px;
  line-height: 1.25;
}

.options-header p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
  font-size: 14px;
}

.options-status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.options-status-strip span,
.options-expiry-pill,
.options-row-count {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 4px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 6px;
  background: var(--bg-color-card);
}

.options-status-strip strong {
  margin-left: 4px;
  color: var(--text-color-primary);
  font-weight: 600;
}

.options-workbench {
  border-radius: 8px;
}

.options-query-bar {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(180px, 1fr) minmax(180px, 1fr) auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color-light);
}

.options-field {
  display: grid;
  gap: 6px;
}

.options-field span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 600;
}

.options-query-button {
  min-width: 132px;
}

.options-metric-section {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.options-section-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.options-section-header h3 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 16px;
  line-height: 1.35;
}

.options-section-header p {
  margin: 4px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.options-metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.options-metric-card {
  display: grid;
  gap: 6px;
  min-height: 112px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-page);
}

.options-metric-card span,
.options-metric-card small {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.options-metric-card strong {
  color: var(--text-color-primary);
  font-size: 24px;
  line-height: 1.1;
}

.options-metric-card.is-teal {
  border-color: rgba(20, 184, 166, 0.35);
}

.options-metric-card.is-blue {
  border-color: rgba(59, 130, 246, 0.35);
}

.options-metric-card.is-amber {
  border-color: rgba(245, 158, 11, 0.38);
}

.options-table-panel {
  display: grid;
  gap: 12px;
}

.options-chain-table {
  width: 100%;
}

.options-strike {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 68px;
  min-height: 28px;
  padding: 4px 8px;
  border-radius: 6px;
  font-weight: 600;
}

.options-strike.is-atm {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

@media (max-width: 1080px) {
  .options-metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .options-header,
  .options-section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .options-query-bar,
  .options-metric-grid {
    grid-template-columns: 1fr;
  }

  .options-query-button {
    width: 100%;
  }
}
</style>
