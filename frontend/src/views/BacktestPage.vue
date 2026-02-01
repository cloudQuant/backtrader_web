<template>
  <div class="space-y-6">
    <!-- 回测配置表单 -->
    <el-card>
      <template #header>
        <span class="font-bold">回测配置</span>
      </template>
      
      <el-form :model="form" label-width="100px" class="max-w-3xl">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="策略">
              <el-select v-model="form.strategy_id" placeholder="选择策略" class="w-full">
                <el-option
                  v-for="s in strategies"
                  :key="s.id"
                  :label="s.name"
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标的代码">
              <el-input v-model="form.symbol" placeholder="如: 000001.SZ" />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker
                v-model="form.start_date"
                type="date"
                placeholder="选择开始日期"
                class="w-full"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker
                v-model="form.end_date"
                type="date"
                placeholder="选择结束日期"
                class="w-full"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="初始资金">
              <el-input-number
                v-model="form.initial_cash"
                :min="1000"
                :step="10000"
                class="w-full"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手续费率">
              <el-input-number
                v-model="form.commission"
                :min="0"
                :max="0.1"
                :step="0.0001"
                :precision="4"
                class="w-full"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="runBacktest">
            运行回测
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 回测结果 -->
    <el-card v-if="currentResult">
      <template #header>
        <span class="font-bold">回测结果</span>
      </template>
      
      <!-- 指标面板 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">总收益率</div>
          <div class="text-2xl font-bold" :class="currentResult.total_return >= 0 ? 'text-green-500' : 'text-red-500'">
            {{ currentResult.total_return.toFixed(2) }}%
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">年化收益</div>
          <div class="text-2xl font-bold" :class="currentResult.annual_return >= 0 ? 'text-green-500' : 'text-red-500'">
            {{ currentResult.annual_return.toFixed(2) }}%
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">夏普比率</div>
          <div class="text-2xl font-bold text-gray-800">
            {{ currentResult.sharpe_ratio.toFixed(2) }}
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">最大回撤</div>
          <div class="text-2xl font-bold text-red-500">
            {{ currentResult.max_drawdown.toFixed(2) }}%
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">胜率</div>
          <div class="text-2xl font-bold text-gray-800">
            {{ currentResult.win_rate.toFixed(1) }}%
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">总交易次数</div>
          <div class="text-2xl font-bold text-gray-800">
            {{ currentResult.total_trades }}
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">盈利次数</div>
          <div class="text-2xl font-bold text-green-500">
            {{ currentResult.profitable_trades }}
          </div>
        </div>
        <div class="p-4 bg-gray-50 rounded-lg">
          <div class="text-gray-500 text-sm">亏损次数</div>
          <div class="text-2xl font-bold text-red-500">
            {{ currentResult.losing_trades }}
          </div>
        </div>
      </div>
      
      <!-- 资金曲线图 -->
      <div class="h-80">
        <EquityCurve
          v-if="currentResult.equity_curve.length"
          :equity="currentResult.equity_curve"
          :dates="currentResult.equity_dates"
          :drawdown="currentResult.drawdown_curve"
        />
      </div>
    </el-card>
    
    <!-- 回测分析提示 -->
    <el-card v-if="results.length > 0">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold">查看回测分析</span>
        </div>
      </template>
      <div class="flex items-center gap-4">
        <span class="text-gray-500">在回测历史表格中点击"查看"按钮，可查看完整的回测分析可视化效果</span>
      </div>
    </el-card>
    
    <!-- 回测历史 -->
    <el-card>
      <template #header>
        <span class="font-bold">回测历史</span>
      </template>
      
      <el-table :data="results" stripe v-loading="backtestStore.loading">
        <el-table-column prop="strategy_id" label="策略" width="150" />
        <el-table-column prop="symbol" label="标的" width="120" />
        <el-table-column label="收益率" width="100">
          <template #default="{ row }">
            <span :class="row.total_return >= 0 ? 'text-green-500' : 'text-red-500'">
              {{ row.total_return.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="夏普" width="80">
          <template #default="{ row }">{{ row.sharpe_ratio.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="回撤" width="80">
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
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewResult(row)">
              查看
            </el-button>
            <el-button type="danger" link size="small" @click="deleteBacktest(row.task_id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useBacktestStore } from '@/stores/backtest'
import { useStrategyStore } from '@/stores/strategy'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import type { BacktestResult } from '@/types'
import dayjs from 'dayjs'

const router = useRouter()
const backtestStore = useBacktestStore()
const strategyStore = useStrategyStore()

const loading = ref(false)
const currentResult = ref<BacktestResult | null>(null)

const form = reactive({
  strategy_id: '',
  symbol: '000001.SZ',
  start_date: dayjs().subtract(1, 'year').toDate(),
  end_date: new Date(),
  initial_cash: 100000,
  commission: 0.001,
})

const strategies = computed(() => strategyStore.strategies)
const results = computed(() => backtestStore.results)

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

async function runBacktest() {
  if (!form.strategy_id) {
    ElMessage.warning('请选择策略')
    return
  }
  
  loading.value = true
  try {
    const response = await backtestStore.runBacktest({
      ...form,
      start_date: dayjs(form.start_date).format('YYYY-MM-DDTHH:mm:ss'),
      end_date: dayjs(form.end_date).format('YYYY-MM-DDTHH:mm:ss'),
    })
    
    ElMessage.success('回测任务已提交')
    
    // 轮询获取结果
    await pollResult(response.task_id)
  } finally {
    loading.value = false
  }
}

async function pollResult(taskId: string) {
  const maxAttempts = 30
  let attempts = 0
  
  while (attempts < maxAttempts) {
    const result = await backtestStore.fetchResult(taskId)
    if (result && result.status === 'completed') {
      currentResult.value = result
      await backtestStore.fetchResults()
      return
    }
    if (result && result.status === 'failed') {
      ElMessage.error('回测失败: ' + result.error_message)
      return
    }
    await new Promise(resolve => setTimeout(resolve, 1000))
    attempts++
  }
  
  ElMessage.warning('回测超时，请稍后查看结果')
}

function viewResult(result: BacktestResult) {
  // 导航到详细分析页面
  router.push(`/backtest/${result.task_id}`)
}

async function deleteBacktest(taskId: string) {
  await ElMessageBox.confirm('确定删除此回测记录？', '提示', {
    type: 'warning',
  })
  
  await backtestStore.deleteResult(taskId)
  ElMessage.success('删除成功')
}

onMounted(async () => {
  await Promise.all([
    strategyStore.fetchStrategies(),
    backtestStore.fetchResults(),
  ])
  
  if (strategies.value.length > 0) {
    form.strategy_id = strategies.value[0].id
  }
})
</script>
