<template>
  <el-card class="backtest-history-card">
    <template #header>
      <div class="backtest-history-head">
        <div>
          <span>{{ t('backtestComp.bhTitle') }}</span>
          <p>{{ results.length }}</p>
        </div>
      </div>
    </template>

    <el-table
      v-loading="loading"
      :data="results"
      :empty-text="t('common.noData')"
      stripe
      class="backtest-history-table"
    >
      <el-table-column
        :label="t('backtestComp.bhStrategy')"
        width="180"
      >
        <template #default="{ row }">
          {{ getStrategyName(row.strategy_id) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="symbol"
        :label="t('backtestComp.bhSymbol')"
        width="120"
      />
      <el-table-column
        :label="t('backtestComp.bhReturn')"
        width="100"
      >
        <template #default="{ row }">
          <span :class="resultToneClass(row.total_return)">
            {{ (row.total_return ?? 0).toFixed(2) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column
        :label="t('backtestComp.bhSharpe')"
        width="80"
      >
        <template #default="{ row }">
          {{ (row.sharpe_ratio ?? 0).toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('backtestComp.bhDrawdown')"
        width="80"
      >
        <template #default="{ row }">
          <span class="is-negative">{{ (row.max_drawdown ?? 0).toFixed(2) }}%</span>
        </template>
      </el-table-column>
      <el-table-column
        :label="t('backtestComp.bhStatus')"
        width="100"
      >
        <template #default="{ row }">
          <el-tag
            :type="getStatusType(row.status)"
            size="small"
          >
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        :label="t('backtestComp.bhCreatedAt')"
        width="180"
      >
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column
        :label="t('backtestComp.bhActions')"
        width="150"
      >
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="$emit('view', row)"
          >
            <el-icon aria-hidden="true">
              <View />
            </el-icon>
            {{ t('backtestComp.bhView') }}
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            @click="$emit('delete', row.task_id)"
          >
            <el-icon aria-hidden="true">
              <Delete />
            </el-icon>
            {{ t('backtestComp.bhDelete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Delete, View } from '@element-plus/icons-vue'
import { getStatusType } from '@/constants/strategy'
import type { BacktestResult, StrategyTemplate, Strategy } from '@/types'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  results: BacktestResult[]
  templates: StrategyTemplate[]
  strategies: Strategy[]
  loading?: boolean
}>(), {
  loading: false,
})

defineEmits<{
  view: [result: BacktestResult]
  delete: [taskId: string]
}>()

function getStrategyName(id: string): string {
  const tpl = props.templates.find(item => item.id === id)
  if (tpl) return tpl.name
  const s = props.strategies.find(item => item.id === id)
  if (s) return s.name
  return id
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: t('backtest.pending'),
    running: t('backtest.running'),
    completed: t('backtest.completed'),
    failed: t('backtest.failed'),
    cancelled: t('dashboard.cancelled'),
  }
  return map[status] || status
}

function formatDate(value: string): string {
  return value ? new Date(value).toLocaleString() : '--'
}

function resultToneClass(value: number | null | undefined): string {
  return (value ?? 0) >= 0 ? 'is-positive' : 'is-negative'
}
</script>

<style scoped>
.backtest-history-card {
  border-color: var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.backtest-history-card :deep(.el-card__header) {
  border-bottom-color: var(--border-color-light);
}

.backtest-history-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.backtest-history-head span {
  display: block;
  color: var(--text-color-primary);
  font-size: 16px;
  font-weight: 740;
  line-height: 1.3;
}

.backtest-history-head p {
  margin: 5px 0 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.backtest-history-table {
  --el-table-header-bg-color: var(--fill-color-lighter);
  --el-table-tr-bg-color: var(--bg-color);
  --el-table-row-hover-bg-color: var(--fill-color-light);
  --el-table-border-color: var(--border-color-light);
  --el-table-text-color: var(--text-color-regular);
  --el-table-header-text-color: var(--text-color-secondary);
}

.backtest-history-table :deep(.el-button) {
  gap: 4px;
}

.is-positive {
  color: var(--success-color);
  font-weight: 700;
}

.is-negative {
  color: var(--danger-color);
  font-weight: 700;
}

@media (max-width: 760px) {
  .backtest-history-card :deep(.el-card__body) {
    padding: 12px;
  }

  .backtest-history-table {
    overflow-x: auto;
  }
}
</style>
