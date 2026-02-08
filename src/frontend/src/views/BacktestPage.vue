<template>
  <div class="space-y-6">
    <!-- 回测配置表单 -->
    <el-card>
      <template #header>
        <span class="font-bold">回测配置</span>
      </template>
      
      <el-form :model="form" label-width="120px" class="max-w-3xl">
        <!-- 策略选择 -->
        <el-form-item label="策略">
          <el-select v-model="form.strategy_id" placeholder="选择策略" class="w-full" filterable @change="onStrategyChange">
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>

        <!-- 策略描述 -->
        <el-form-item v-if="strategyConfig" label="策略说明">
          <div class="text-gray-500 text-sm">
            <span v-if="strategyConfig.strategy.description">{{ strategyConfig.strategy.description }}</span>
            <span v-if="strategyConfig.strategy.author" class="ml-2 text-gray-400">— {{ strategyConfig.strategy.author }}</span>
          </div>
        </el-form-item>

        <!-- 动态策略参数（从config.yaml的params段读取） -->
        <template v-if="Object.keys(dynamicParams).length > 0">
          <el-divider content-position="left">策略参数</el-divider>
          <el-row :gutter="20">
            <el-col :span="12" v-for="(val, key) in dynamicParams" :key="key">
              <el-form-item :label="String(key)">
                <el-input-number
                  v-if="typeof val === 'number'"
                  v-model="dynamicParams[key]"
                  :step="Number.isInteger(val) ? 1 : 0.01"
                  :precision="Number.isInteger(val) ? 0 : 4"
                  class="w-full"
                />
                <el-input
                  v-else
                  v-model="dynamicParams[key]"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="runBacktest">
            运行回测
          </el-button>
          <el-button v-if="loading && currentTaskId" type="danger" @click="cancelBacktest">
            取消
          </el-button>
        </el-form-item>
      </el-form>
      
      <!-- 进度条 -->
      <div v-if="loading && progressInfo.progress > 0" class="mt-4">
        <div class="flex justify-between text-sm text-gray-500 mb-1">
          <span>{{ progressInfo.message }}</span>
          <span>{{ progressInfo.progress }}%</span>
        </div>
        <el-progress :percentage="progressInfo.progress" :status="progressInfo.progress >= 100 ? 'success' : undefined" />
      </div>
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
        <el-table-column label="策略" width="180">
          <template #default="{ row }">
            {{ getStrategyName(row.strategy_id) }}
          </template>
        </el-table-column>
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
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useBacktestStore } from '@/stores/backtest'
import { useStrategyStore } from '@/stores/strategy'
import { strategyApi } from '@/api/strategy'
import { backtestApi } from '@/api/backtest'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import type { BacktestResult, StrategyConfig } from '@/types'
import dayjs from 'dayjs'

const router = useRouter()
const backtestStore = useBacktestStore()
const strategyStore = useStrategyStore()

const loading = ref(false)
const configLoading = ref(false)
const currentResult = ref<BacktestResult | null>(null)
const currentTaskId = ref('')
const progressInfo = ref({ progress: 0, message: '' })
const strategyConfig = ref<StrategyConfig | null>(null)
const dynamicParams = reactive<Record<string, number | string>>({})
let ws: WebSocket | null = null

const form = reactive({
  strategy_id: '',
})

async function onStrategyChange(strategyId: string) {
  if (!strategyId) {
    strategyConfig.value = null
    return
  }
  configLoading.value = true
  try {
    const config = await strategyApi.getTemplateConfig(strategyId)
    strategyConfig.value = config

    // 填充策略参数（仅 params 段）
    Object.keys(dynamicParams).forEach(k => delete dynamicParams[k])
    if (config.params) {
      Object.entries(config.params).forEach(([k, v]) => {
        dynamicParams[k] = v
      })
    }
  } catch {
    ElMessage.warning('无法加载策略配置，将使用默认参数')
    strategyConfig.value = null
  } finally {
    configLoading.value = false
  }
}

const strategies = computed(() => strategyStore.strategies)
const templates = computed(() => strategyStore.templates)
const results = computed(() => backtestStore.results)

function getStrategyName(id: string): string {
  const t = templates.value.find(t => t.id === id)
  if (t) return t.name
  const s = strategies.value.find(s => s.id === id)
  if (s) return s.name
  return id
}

function getStatusType(status: string) {
  const types: Record<string, string> = {
    completed: 'success',
    running: 'warning',
    pending: 'info',
    failed: 'danger',
    cancelled: 'warning',
  }
  return types[status] || 'info'
}

function getStatusText(status: string) {
  const texts: Record<string, string> = {
    completed: '完成',
    running: '运行中',
    pending: '等待中',
    failed: '失败',
    cancelled: '已取消',
  }
  return texts[status] || status
}

function connectWebSocket(taskId: string) {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/backtest/${taskId}`
  ws = new WebSocket(wsUrl)
  
  ws.onmessage = async (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'progress') {
      progressInfo.value = { progress: data.progress, message: data.message }
    } else if (data.type === 'completed') {
      progressInfo.value = { progress: 100, message: '回测完成' }
      const result = await backtestStore.fetchResult(taskId)
      if (result) {
        currentResult.value = result
        await backtestStore.fetchResults()
      }
      loading.value = false
      closeWebSocket()
      ElMessage.success('回测完成')
    } else if (data.type === 'failed') {
      loading.value = false
      closeWebSocket()
      ElMessage.error('回测失败: ' + data.message)
    } else if (data.type === 'cancelled') {
      loading.value = false
      closeWebSocket()
      ElMessage.warning('回测已取消')
    }
  }
  
  ws.onerror = () => {
    // WebSocket连接失败，回退到轮询
    closeWebSocket()
    pollResult(taskId)
  }
}

function closeWebSocket() {
  if (ws) {
    ws.close()
    ws = null
  }
}

async function runBacktest() {
  if (!form.strategy_id) {
    ElMessage.warning('请选择策略')
    return
  }
  
  loading.value = true
  progressInfo.value = { progress: 0, message: '提交任务中...' }
  try {
    const response = await backtestStore.runBacktest({
      strategy_id: form.strategy_id,
      symbol: strategyConfig.value?.data?.symbol || '',
      start_date: dayjs().subtract(10, 'year').format('YYYY-MM-DDTHH:mm:ss'),
      end_date: dayjs().format('YYYY-MM-DDTHH:mm:ss'),
      initial_cash: strategyConfig.value?.backtest?.initial_cash ?? 100000,
      commission: strategyConfig.value?.backtest?.commission ?? 0.001,
      params: { ...dynamicParams },
    })
    
    currentTaskId.value = response.task_id
    ElMessage.success('回测任务已提交')
    
    // 尝试WebSocket连接，失败则回退轮询
    connectWebSocket(response.task_id)
  } catch {
    loading.value = false
  }
}

async function cancelBacktest() {
  if (!currentTaskId.value) return
  try {
    await backtestApi.cancel(currentTaskId.value)
    loading.value = false
    closeWebSocket()
    ElMessage.success('已取消回测任务')
  } catch {
    ElMessage.error('取消失败')
  }
}

async function pollResult(taskId: string) {
  const maxAttempts = 60
  let attempts = 0
  
  while (attempts < maxAttempts && loading.value) {
    const result = await backtestStore.fetchResult(taskId)
    if (result && result.status === 'completed') {
      currentResult.value = result
      await backtestStore.fetchResults()
      loading.value = false
      return
    }
    if (result && result.status === 'failed') {
      ElMessage.error('回测失败: ' + result.error_message)
      loading.value = false
      return
    }
    await new Promise(resolve => setTimeout(resolve, 1000))
    attempts++
  }
  
  if (loading.value) {
    loading.value = false
    ElMessage.warning('回测超时，请稍后查看结果')
  }
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
    strategyStore.fetchTemplates(),
    backtestStore.fetchResults(),
  ])
  
  // Support ?strategy= query param from strategy gallery
  const route = useRoute()
  const queryStrategy = route.query.strategy as string
  if (queryStrategy) {
    form.strategy_id = queryStrategy
    await onStrategyChange(queryStrategy)
  } else if (templates.value.length > 0) {
    form.strategy_id = templates.value[0].id
    await onStrategyChange(templates.value[0].id)
  }
})
</script>
