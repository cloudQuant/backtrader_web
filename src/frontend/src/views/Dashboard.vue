<template>
  <div class="space-y-6">
    <!-- 统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <el-card shadow="hover" class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-gray-500 text-sm">回测次数</div>
            <div class="text-3xl font-bold text-gray-800 mt-2">{{ stats.backtestCount }}</div>
          </div>
          <div class="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
            <el-icon class="text-blue-500 text-2xl"><DataLine /></el-icon>
          </div>
        </div>
      </el-card>
      
      <el-card shadow="hover" class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-gray-500 text-sm">策略数量</div>
            <div class="text-3xl font-bold text-gray-800 mt-2">{{ stats.strategyCount }}</div>
          </div>
          <div class="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
            <el-icon class="text-green-500 text-2xl"><Document /></el-icon>
          </div>
        </div>
      </el-card>
      
      <el-card shadow="hover" class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-gray-500 text-sm">平均收益率</div>
            <div class="text-3xl font-bold mt-2" :class="stats.avgReturn >= 0 ? 'text-green-500' : 'text-red-500'">
              {{ stats.avgReturn.toFixed(2) }}%
            </div>
          </div>
          <div class="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
            <el-icon class="text-purple-500 text-2xl"><TrendCharts /></el-icon>
          </div>
        </div>
      </el-card>
      
      <el-card shadow="hover" class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-gray-500 text-sm">最佳夏普比率</div>
            <div class="text-3xl font-bold text-gray-800 mt-2">{{ stats.bestSharpe.toFixed(2) }}</div>
          </div>
          <div class="w-12 h-12 rounded-full bg-orange-100 flex items-center justify-center">
            <el-icon class="text-orange-500 text-2xl"><Trophy /></el-icon>
          </div>
        </div>
      </el-card>
    </div>
    
    <!-- 快速操作 -->
    <el-card>
      <template #header>
        <span class="font-bold">快速开始</span>
      </template>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div
          class="p-6 border rounded-lg hover:border-blue-500 hover:shadow-md transition-all cursor-pointer"
          @click="$router.push('/backtest')"
        >
          <el-icon class="text-4xl text-blue-500 mb-4"><DataLine /></el-icon>
          <h3 class="font-bold text-lg mb-2">运行回测</h3>
          <p class="text-gray-500 text-sm">选择策略和数据，运行回测分析</p>
        </div>
        
        <div
          class="p-6 border rounded-lg hover:border-green-500 hover:shadow-md transition-all cursor-pointer"
          @click="$router.push('/strategy')"
        >
          <el-icon class="text-4xl text-green-500 mb-4"><Document /></el-icon>
          <h3 class="font-bold text-lg mb-2">创建策略</h3>
          <p class="text-gray-500 text-sm">编写自定义交易策略</p>
        </div>
        
        <div
          class="p-6 border rounded-lg hover:border-purple-500 hover:shadow-md transition-all cursor-pointer"
          @click="$router.push('/data')"
        >
          <el-icon class="text-4xl text-purple-500 mb-4"><Grid /></el-icon>
          <h3 class="font-bold text-lg mb-2">查询数据</h3>
          <p class="text-gray-500 text-sm">查看和导入行情数据</p>
        </div>
      </div>
    </el-card>
    
    <!-- 最近回测 -->
    <el-card>
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold">最近回测</span>
          <el-button type="primary" link @click="$router.push('/backtest')">
            查看全部
          </el-button>
        </div>
      </template>
      
      <el-table :data="recentBacktests" stripe>
        <el-table-column label="策略" width="150">
          <template #default="{ row }">
            {{ getStrategyName(row.strategy_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="symbol" label="标的" width="120" />
        <el-table-column label="收益率" width="120">
          <template #default="{ row }">
            <span :class="row.total_return >= 0 ? 'text-green-500' : 'text-red-500'">
              {{ row.total_return.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="夏普比率" width="120">
          <template #default="{ row }">
            {{ row.sharpe_ratio.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="最大回撤" width="120">
          <template #default="{ row }">
            <span class="text-red-500">{{ row.max_drawdown.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { DataLine, Document, Grid, TrendCharts, Trophy } from '@element-plus/icons-vue'
import { useBacktestStore } from '@/stores/backtest'
import { useStrategyStore } from '@/stores/strategy'
import type { BacktestResult } from '@/types'

const backtestStore = useBacktestStore()
const strategyStore = useStrategyStore()

const stats = ref({
  backtestCount: 0,
  strategyCount: 0,
  avgReturn: 0,
  bestSharpe: 0,
})

const recentBacktests = ref<BacktestResult[]>([])

function getStatusType(status: string) {
  const types: Record<string, string> = {
    completed: 'success',
    running: 'warning',
    pending: 'info',
    failed: 'danger',
  }
  return types[status] || 'info'
}

function getStatusText(status: string) {
  const texts: Record<string, string> = {
    completed: '完成',
    running: '运行中',
    pending: '等待中',
    failed: '失败',
  }
  return texts[status] || status
}

function getStrategyName(id: string): string {
  const t = strategyStore.templates.find(t => t.id === id)
  if (t) return t.name
  return id
}

onMounted(async () => {
  await Promise.all([
    backtestStore.fetchResults(5),
    strategyStore.fetchStrategies(100),
    strategyStore.fetchTemplates(),
  ])
  
  recentBacktests.value = backtestStore.results
  
  // 计算统计数据
  stats.value.backtestCount = backtestStore.total
  stats.value.strategyCount = strategyStore.total
  
  if (backtestStore.results.length > 0) {
    const returns = backtestStore.results.map(r => r.total_return)
    const sharpes = backtestStore.results.map(r => r.sharpe_ratio)
    stats.value.avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length
    stats.value.bestSharpe = Math.max(...sharpes)
  }
})
</script>

<style scoped>
.stat-card {
  transition: transform 0.2s;
}
.stat-card:hover {
  transform: translateY(-4px);
}
</style>
