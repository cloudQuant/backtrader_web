<template>
  <el-card>
    <template #header>
      <span class="font-bold">{{ t('backtestComp.bhTitle') }}</span>
    </template>

    <el-table
      v-loading="loading"
      :data="results"
      stripe
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
          <span :class="row.total_return >= 0 ? 'text-green-500' : 'text-red-500'">
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
          <span class="text-red-500">{{ (row.max_drawdown ?? 0).toFixed(2) }}%</span>
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
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="created_at"
        :label="t('backtestComp.bhCreatedAt')"
        width="180"
      />
      <el-table-column
        :label="t('backtestComp.bhActions')"
        width="120"
      >
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="$emit('view', row)"
          >
            {{ t('backtestComp.bhView') }}
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            @click="$emit('delete', row.task_id)"
          >
            {{ t('backtestComp.bhDelete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { getStatusType, getStatusText } from '@/constants/strategy'
import type { BacktestResult, StrategyTemplate, Strategy } from '@/types'

const { t } = useI18n()

const props = defineProps<{
  results: BacktestResult[]
  templates: StrategyTemplate[]
  strategies: Strategy[]
  loading: boolean
}>()

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
</script>
