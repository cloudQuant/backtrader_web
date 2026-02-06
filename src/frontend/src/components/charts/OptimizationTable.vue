<template>
  <div class="optimization-table">
    <div class="flex justify-between items-center mb-4">
      <h4 class="text-md font-medium">参数优化结果</h4>
      <el-select v-model="sortBy" size="small" style="width: 140px" @change="handleSortChange">
        <el-option label="按夏普比率" value="sharpe_ratio" />
        <el-option label="按收益率" value="total_return" />
        <el-option label="按最大回撤" value="max_drawdown" />
      </el-select>
    </div>
    
    <!-- 最优参数卡片 -->
    <div v-if="best" class="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
      <div class="flex items-center gap-2 mb-2">
        <el-icon class="text-blue-500"><Trophy /></el-icon>
        <span class="font-semibold text-blue-700">最优参数组合</span>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div v-for="(value, key) in best.params" :key="key">
          <span class="text-gray-500">{{ key }}:</span>
          <span class="font-medium ml-1">{{ value }}</span>
        </div>
        <div>
          <span class="text-gray-500">收益率:</span>
          <span class="font-medium ml-1 text-green-600">{{ (best.total_return * 100).toFixed(2) }}%</span>
        </div>
        <div>
          <span class="text-gray-500">夏普比率:</span>
          <span class="font-medium ml-1">{{ best.sharpe_ratio?.toFixed(2) ?? '--' }}</span>
        </div>
      </div>
    </div>
    
    <!-- 结果表格 -->
    <el-table
      :data="results"
      stripe
      border
      size="small"
      max-height="400"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="rank" label="排名" width="60" />
      <el-table-column label="参数" min-width="200">
        <template #default="{ row }">
          <span v-for="(value, key, index) in row.params" :key="key">
            {{ key }}={{ value }}{{ index < Object.keys(row.params).length - 1 ? ', ' : '' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="total_return" label="收益率" width="100" sortable>
        <template #default="{ row }">
          <span :class="row.total_return >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ (row.total_return * 100).toFixed(2) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="max_drawdown" label="最大回撤" width="100" sortable>
        <template #default="{ row }">
          <span class="text-red-600">{{ (row.max_drawdown * 100).toFixed(2) }}%</span>
        </template>
      </el-table-column>
      <el-table-column prop="sharpe_ratio" label="夏普比率" width="100" sortable>
        <template #default="{ row }">{{ row.sharpe_ratio?.toFixed(2) ?? '--' }}</template>
      </el-table-column>
      <el-table-column prop="trade_count" label="交易次数" width="90" sortable />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Trophy } from '@element-plus/icons-vue'
import type { OptimizationResultItem } from '@/types/analytics'

const props = defineProps<{
  results: OptimizationResultItem[]
  best: OptimizationResultItem | null
}>()

const emit = defineEmits<{
  (e: 'sort-change', sortBy: string): void
}>()

const sortBy = ref('sharpe_ratio')

function handleSortChange(value: string) {
  emit('sort-change', value)
}

function rowClassName({ row }: { row: OptimizationResultItem }) {
  return row.is_best ? 'best-row' : ''
}
</script>

<style scoped>
:deep(.best-row) {
  background-color: #eff6ff !important;
}
</style>
