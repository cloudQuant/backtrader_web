<template>
  <div class="backtest-result-page p-6">
    <!-- 加载状态 -->
    <div
      v-if="loading"
      class="flex justify-center items-center h-64"
    >
      <el-icon class="is-loading text-4xl text-blue-500">
        <Loading />
      </el-icon>
    </div>
    
    <!-- 错误状态 -->
    <div
      v-else-if="error"
      class="text-center py-12"
    >
      <el-icon class="text-5xl text-red-400 mb-4">
        <CircleCloseFilled />
      </el-icon>
      <p class="text-gray-500">
        {{ error }}
      </p>
      <el-button
        class="mt-4"
        @click="loadData"
      >
        重试
      </el-button>
    </div>
    
    <!-- 内容 -->
    <template v-else-if="detail">
      <!-- 顶部标题和操作 -->
      <div class="flex justify-between items-center mb-6">
        <div>
          <h2 class="text-2xl font-bold">
            回测结果详情
          </h2>
          <p class="text-gray-500 mt-1">
            {{ detail.strategy_name }} | {{ detail.symbol }} | 
            {{ detail.start_date }} - {{ detail.end_date }}
          </p>
        </div>
        <div class="flex gap-2">
          <el-button
            v-if="isOptimizationArtifactMode"
            @click="handleOpenArtifactDir"
          >
            <el-icon><FolderOpened /></el-icon>打开 artifact 目录
          </el-button>
          <el-button
            v-if="isOptimizationArtifactMode"
            @click="handleDownloadArtifact"
          >
            <el-icon><Download /></el-icon>下载结果
          </el-button>
          <el-button
            v-if="!isOptimizationArtifactMode"
            @click="handleExport('csv')"
          >
            <el-icon><Download /></el-icon>导出CSV
          </el-button>
          <el-button
            type="primary"
            @click="handleBack"
          >
            <el-icon><Back /></el-icon>返回
          </el-button>
        </div>
      </div>
      
      <!-- 绩效指标面板 -->
      <el-card class="mb-6">
        <PerformancePanel :metrics="detail.metrics" />
      </el-card>
      
      <!-- 图表区域 -->
      <el-tabs
        v-model="activeTab"
        class="mb-6"
      >
        <el-tab-pane
          label="K线图"
          name="kline"
        >
          <el-card>
            <TradeSignalChart
              :klines="klineData?.klines || []"
              :signals="klineData?.signals || []"
              :indicators="klineData?.indicators"
              :height="550"
            />
          </el-card>
        </el-tab-pane>
        
        <el-tab-pane
          label="资金曲线"
          name="equity"
        >
          <el-card v-if="activeTab === 'equity'">
            <EquityCurve
              :data="detail.equity_curve"
              :height="350"
            />
            <DrawdownChart
              :data="detail.drawdown_curve"
              :height="180"
              class="mt-4"
            />
          </el-card>
        </el-tab-pane>
        
        <el-tab-pane
          label="收益分析"
          name="analysis"
        >
          <div
            v-if="activeTab === 'analysis'"
            class="space-y-4"
          >
            <el-card>
              <ReturnHeatmap
                :returns="monthlyReturns?.returns || []"
                :years="monthlyReturns?.years || []"
                :height="300"
              />
            </el-card>
            <el-card>
              <div class="p-4">
                <h4 class="text-md font-medium mb-3">
                  年度收益汇总
                </h4>
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2 max-h-48 overflow-y-auto">
                  <div 
                    v-for="(ret, year) in monthlyReturns?.summary" 
                    :key="year"
                    class="flex justify-between items-center px-3 py-2 bg-gray-50 rounded text-sm"
                  >
                    <span class="font-medium mr-2">{{ year }}</span>
                    <span
                      :class="ret >= 0 ? 'text-green-600' : 'text-red-600'"
                      class="whitespace-nowrap"
                    >
                      {{ ret >= 0 ? '+' : '' }}{{ (ret * 100).toFixed(2) }}%
                    </span>
                  </div>
                </div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
        
        <el-tab-pane
          label="交易记录"
          name="trades"
        >
          <el-card>
            <TradeRecordsTable :trades="detail.trades" />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, CircleCloseFilled, Download, Back, FolderOpened } from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api'
import { analyticsApi } from '@/api/analytics'
import { workspaceApi } from '@/api/workspace'
import PerformancePanel from '@/components/charts/PerformancePanel.vue'
import TradeSignalChart from '@/components/charts/TradeSignalChart.vue'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import DrawdownChart from '@/components/charts/DrawdownChart.vue'
import ReturnHeatmap from '@/components/charts/ReturnHeatmap.vue'
import TradeRecordsTable from '@/components/charts/TradeRecordsTable.vue'
import type {
  BacktestDetailResponse,
  KlineWithSignalsResponse,
  MonthlyReturnsResponse,
} from '@/types/analytics'

const route = useRoute()
const router = useRouter()

const taskId = computed(() => route.params.id as string)
const workspaceId = computed(() => {
  const value = route.query.workspaceId
  return typeof value === 'string' && value ? value : null
})
const optimizationUnitId = computed(() => {
  const value = route.query.optimizationUnitId
  return typeof value === 'string' && value ? value : null
})
const optimizationResultIndex = computed(() => {
  const value = route.query.optimizationResultIndex
  if (typeof value !== 'string' || !value) return null
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : null
})
const isOptimizationArtifactMode = computed(() => (
  !!workspaceId.value && !!optimizationUnitId.value && optimizationResultIndex.value !== null
))

const loading = ref(true)
const error = ref<string | null>(null)
const activeTab = ref('kline')

const detail = ref<BacktestDetailResponse | null>(null)
const klineData = ref<KlineWithSignalsResponse | null>(null)
const monthlyReturns = ref<MonthlyReturnsResponse | null>(null)

onMounted(() => {
  loadData()
})

async function loadData() {
  loading.value = true
  error.value = null
  
  try {
    let detailRes: BacktestDetailResponse
    let klineRes: KlineWithSignalsResponse
    let returnsRes: MonthlyReturnsResponse

    if (isOptimizationArtifactMode.value && workspaceId.value && optimizationUnitId.value && optimizationResultIndex.value !== null) {
      [detailRes, klineRes, returnsRes] = await Promise.all([
        workspaceApi.getOptimizationResultDetail(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value),
        workspaceApi.getOptimizationResultKline(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value),
        workspaceApi.getOptimizationResultMonthlyReturns(workspaceId.value, optimizationUnitId.value, optimizationResultIndex.value),
      ])
    } else {
      [detailRes, klineRes, returnsRes] = await Promise.all([
        analyticsApi.getBacktestDetail(taskId.value),
        analyticsApi.getKlineWithSignals(taskId.value),
        analyticsApi.getMonthlyReturns(taskId.value),
      ])
    }
    
    detail.value = detailRes
    klineData.value = klineRes
    monthlyReturns.value = returnsRes
    
  } catch (e: unknown) {
    error.value = getErrorMessage(e, '加载失败')
  } finally {
    loading.value = false
  }
}

function handleExport(format: 'csv' | 'json') {
  analyticsApi.exportResults(taskId.value, format)
}

async function handleOpenArtifactDir() {
  if (!workspaceId.value || !optimizationUnitId.value || optimizationResultIndex.value === null) return
  let artifactPath = detail.value?.artifact_path || null
  if (!artifactPath) {
    const artifact = await workspaceApi.getOptimizationResultArtifact(
      workspaceId.value,
      optimizationUnitId.value,
      optimizationResultIndex.value,
    )
    artifactPath = artifact.artifact_path
  }
  if (!artifactPath) {
    ElMessage.warning('未找到本地 artifact 目录')
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(artifactPath)
    }
  } catch {
    // Silently ignore clipboard errors
  }
  window.open(`file://${encodeURI(artifactPath.replace(/\\/g, '/'))}`, '_blank', 'noopener')
  ElMessage.success('已尝试打开 artifact 目录，并复制路径到剪贴板')
}

async function handleDownloadArtifact() {
  if (!workspaceId.value || !optimizationUnitId.value || optimizationResultIndex.value === null) return
  await workspaceApi.downloadOptimizationResultArtifact(
    workspaceId.value,
    optimizationUnitId.value,
    optimizationResultIndex.value,
  )
}

function handleBack() {
  if (workspaceId.value) {
    router.push({
      name: 'BacktestWorkspaceDetail',
      params: { id: workspaceId.value },
    })
    return
  }
  router.push('/backtest/legacy')
}

</script>
