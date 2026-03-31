<template>
  <el-card>
    <template #header>
      <span class="font-bold">回测历史</span>
    </template>

    <el-table
      v-loading="loading"
      :data="results"
      stripe
    >
      <el-table-column
        label="策略"
        width="180"
      >
        <template #default="{ row }">
          {{ getStrategyName(row.strategy_id) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="symbol"
        label="标的"
        width="120"
      />
      <el-table-column
        label="收益率"
        width="100"
      >
        <template #default="{ row }">
          <span :class="row.total_return >= 0 ? 'text-green-500' : 'text-red-500'">
            {{ (row.total_return ?? 0).toFixed(2) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="夏普"
        width="80"
      >
        <template #default="{ row }">
          {{ (row.sharpe_ratio ?? 0).toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column
        label="回撤"
        width="80"
      >
        <template #default="{ row }">
          <span class="text-red-500">{{ (row.max_drawdown ?? 0).toFixed(2) }}%</span>
        </template>
      </el-table-column>
      <el-table-column
        label="状态"
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
        label="创建时间"
        width="180"
      />
      <el-table-column
        label="操作"
        width="120"
      >
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="$emit('view', row)"
          >
            查看
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            @click="$emit('delete', row.task_id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { getStatusType, getStatusText } from '@/constants/strategy'
import type { BacktestResult, StrategyTemplate, Strategy } from '@/types'

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
  const t = props.templates.find(t => t.id === id)
  if (t) return t.name
  const s = props.strategies.find(s => s.id === id)
  if (s) return s.name
  return id
}
</script>
