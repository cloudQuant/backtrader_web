<template>
  <div class="space-y-6">
    <!-- 回测配置表单 -->
    <el-card>
      <template #header>
        <span class="font-bold">回测配置</span>
      </template>
      
      <el-form
        :model="form"
        label-width="120px"
        class="max-w-3xl"
      >
        <!-- 策略选择 -->
        <el-form-item label="策略">
          <el-select
            v-model="form.strategy_id"
            placeholder="选择策略"
            class="w-full"
            filterable
            @change="onStrategyChange"
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>

        <!-- 策略描述 -->
        <el-form-item
          v-if="strategyConfig"
          label="策略说明"
        >
          <div class="text-gray-500 text-sm">
            <span v-if="strategyConfig.strategy.description">{{ strategyConfig.strategy.description }}</span>
            <span
              v-if="strategyConfig.strategy.author"
              class="ml-2 text-gray-400"
            >— {{ strategyConfig.strategy.author }}</span>
          </div>
        </el-form-item>

        <!-- 动态策略参数（从config.yaml的params段读取） -->
        <template v-if="Object.keys(dynamicParams).length > 0">
          <el-divider content-position="left">
            策略参数
          </el-divider>
          <el-row :gutter="20">
            <el-col
              v-for="(val, key) in dynamicParams"
              :key="key"
              :span="12"
            >
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
          <el-button
            type="primary"
            :loading="loading"
            @click="runBacktest"
          >
            运行回测
          </el-button>
          <el-button
            v-if="loading && currentTaskId"
            type="danger"
            @click="cancelBacktest"
          >
            取消
          </el-button>
        </el-form-item>
      </el-form>
      
      <!-- 进度条 -->
      <div
        v-if="loading && progressInfo.progress > 0"
        class="mt-4"
      >
        <div class="flex justify-between text-sm text-gray-500 mb-1">
          <span>{{ progressInfo.message }}</span>
          <span>{{ progressInfo.progress }}%</span>
        </div>
        <el-progress
          :percentage="progressInfo.progress"
          :status="progressInfo.progress >= 100 ? 'success' : undefined"
        />
      </div>
    </el-card>
    
    <!-- 回测结果 -->
    <BacktestMetricsPanel
      v-if="currentResult"
      :result="currentResult"
    />
    
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
    <BacktestHistoryTable
      :results="results"
      :templates="templates"
      :strategies="strategies"
      :loading="backtestStore.loading"
      @view="viewResult"
      @delete="deleteBacktest"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { useBacktestStore } from '@/stores/backtest'
import { useStrategyStore } from '@/stores/strategy'
import { strategyApi } from '@/api/strategy'
import BacktestMetricsPanel from '@/components/backtest/BacktestMetricsPanel.vue'
import BacktestHistoryTable from '@/components/backtest/BacktestHistoryTable.vue'
import { useBacktestRuntime } from '@/composables/useBacktestRuntime'
import type { BacktestResult, StrategyConfig } from '@/types'
import dayjs from 'dayjs'

const router = useRouter()
const route = useRoute()
const backtestStore = useBacktestStore()
const strategyStore = useStrategyStore()

const configLoading = ref(false)
const currentResult = ref<BacktestResult | null>(null)
const strategyConfig = ref<StrategyConfig | null>(null)
const dynamicParams = reactive<Record<string, number | string>>({})

const {
  loading,
  currentTaskId,
  progressInfo,
  cancelBacktest,
  closeWebSocket,
  connectWebSocket,
  disposeRuntime,
  startRuntime,
  stopRuntime,
} = useBacktestRuntime({
  currentResult,
  fetchResult: (taskId) => backtestStore.fetchResult(taskId),
  refreshResults: () => backtestStore.fetchResults(),
})

defineExpose({
  closeWebSocket,
  connectWebSocket,
})

const form = reactive({
  strategy_id: '',
})

function hasAxiosResponse(e: unknown): e is { response: unknown } {
  return !!e && typeof e === 'object' && 'response' in e
}

function showRequestMessage(
  e: unknown,
  fallback: string,
  level: 'error' | 'warning' = 'error'
): void {
  // error 场景：全局响应拦截器已处理 Axios 错误，此处不重复显示
  if (level === 'error' && hasAxiosResponse(e)) {
    return
  }

  // warning 场景：全局拦截器只显示 error，此处需要单独处理 warning
  // 提取实际错误消息显示，而非只显示 fallback
  const message = getErrorMessage(e, fallback)
  if (level === 'warning') {
    ElMessage.warning(message)
    return
  }
  ElMessage.error(message)
}

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
  } catch (e: unknown) {
    showRequestMessage(e, '无法加载策略配置，将使用默认参数', 'warning')
    strategyConfig.value = null
  } finally {
    configLoading.value = false
  }
}

const strategies = computed(() => strategyStore.strategies)
const templates = computed(() => strategyStore.templates)
const results = computed(() => backtestStore.results)

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

    ElMessage.success('回测任务已提交')

    startRuntime(response.task_id)
  } catch (e: unknown) {
    stopRuntime()
    showRequestMessage(e, '提交回测失败')
  }
}

function viewResult(result: BacktestResult) {
  // 导航到详细分析页面
  router.push(`/backtest/result/${result.task_id}`)
}

async function deleteBacktest(taskId: string) {
  await ElMessageBox.confirm('确定删除此回测记录？', '提示', {
    type: 'warning',
  })
  
  await backtestStore.deleteResult(taskId)
  ElMessage.success('删除成功')
}

onMounted(async () => {
  try {
    await Promise.all([
      strategyStore.fetchStrategies(),
      strategyStore.fetchTemplates(),
      backtestStore.fetchResults(),
    ])
  
    // Support ?strategy= query param from strategy gallery
    const queryStrategy = route.query.strategy as string
    if (queryStrategy) {
      form.strategy_id = queryStrategy
      await onStrategyChange(queryStrategy)
    } else if (templates.value.length > 0) {
      form.strategy_id = templates.value[0].id
      await onStrategyChange(templates.value[0].id)
    }
  } catch (e: unknown) {
    showRequestMessage(e, '初始化回测页面失败')
  }
})

onBeforeUnmount(() => {
  disposeRuntime()
})
</script>
