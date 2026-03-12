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
            模拟策略分析
          </h2>
          <p class="text-gray-500 mt-1">
            {{ detail.strategy_name }} | {{ detail.symbol }} |
            {{ detail.start_date }} - {{ detail.end_date }}
          </p>
        </div>
        <div class="flex gap-2">
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
          <el-card v-show="activeTab === 'kline'">
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
          <el-card v-show="activeTab === 'equity'">
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
            v-show="activeTab === 'analysis'"
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

        <el-tab-pane
          label="运行日志"
          name="logs"
        >
          <el-card v-show="activeTab === 'logs'">
            <LogViewer
              :instance-id="instanceId"
              :content-height="450"
            />
          </el-card>
        </el-tab-pane>

        <el-tab-pane
          label="参数管理"
          name="config"
        >
          <el-card v-show="activeTab === 'config'">
            <div class="flex justify-between items-center mb-4">
              <h4 class="text-md font-medium">
                策略配置 (config.yaml)
              </h4>
              <div class="flex gap-2">
                <el-button
                  :loading="configLoading"
                  @click="loadConfig"
                >
                  <el-icon><Refresh /></el-icon>刷新
                </el-button>
                <el-button
                  type="primary"
                  :loading="configSaving"
                  @click="saveConfig"
                >
                  <el-icon><Check /></el-icon>保存
                </el-button>
              </div>
            </div>
            <div
              v-if="configLoading && !configRaw"
              class="flex justify-center items-center h-48"
            >
              <el-icon class="is-loading text-2xl text-blue-500">
                <Loading />
              </el-icon>
            </div>
            <div
              v-else-if="configError"
              class="text-red-500 p-4"
            >
              {{ configError }}
            </div>
            <el-input
              v-else
              v-model="configRaw"
              type="textarea"
              :autosize="{ minRows: 15, maxRows: 30 }"
              class="font-mono text-sm"
              placeholder="暂无配置文件"
            />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loading, CircleCloseFilled, Back, Refresh, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { simulationApi } from '@/api/simulation'
import PerformancePanel from '@/components/charts/PerformancePanel.vue'
import TradeSignalChart from '@/components/charts/TradeSignalChart.vue'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import DrawdownChart from '@/components/charts/DrawdownChart.vue'
import ReturnHeatmap from '@/components/charts/ReturnHeatmap.vue'
import TradeRecordsTable from '@/components/charts/TradeRecordsTable.vue'
import LogViewer from '@/components/common/LogViewer.vue'
import type {
  BacktestDetailResponse,
  KlineWithSignalsResponse,
  MonthlyReturnsResponse,
} from '@/types/analytics'
import request, { getErrorMessage } from '@/api'

const route = useRoute()
const router = useRouter()

const instanceId = computed(() => route.params.id as string)

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
    const [detailRes, klineRes, returnsRes] = await Promise.all([
      request.get(`/simulation/${instanceId.value}/detail`) as Promise<BacktestDetailResponse>,
      request.get(`/simulation/${instanceId.value}/kline`) as Promise<KlineWithSignalsResponse>,
      request.get(`/simulation/${instanceId.value}/monthly-returns`) as Promise<MonthlyReturnsResponse>,
    ])

    detail.value = detailRes
    klineData.value = klineRes
    monthlyReturns.value = returnsRes
  } catch (e: unknown) {
    error.value = getErrorMessage(e, '加载失败')
  } finally {
    loading.value = false
  }
}

function handleBack() {
  router.push('/simulate')
}

watch(activeTab, (tab) => {
  if (tab === 'config' && !configRaw.value && !configLoading.value) {
    loadConfig()
  }
})

// ==================== Config Management ====================
const configRaw = ref('')
const configLoading = ref(false)
const configSaving = ref(false)
const configError = ref<string | null>(null)

async function loadConfig() {
  configLoading.value = true
  configError.value = null
  try {
    const res = await simulationApi.getConfig(instanceId.value)
    configRaw.value = res.raw || ''
  } catch (e: unknown) {
    configError.value = getErrorMessage(e, '加载配置失败')
  } finally {
    configLoading.value = false
  }
}

async function saveConfig() {
  configSaving.value = true
  try {
    await simulationApi.updateConfig(instanceId.value, { raw: configRaw.value })
    ElMessage.success('配置保存成功')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存配置失败'))
  } finally {
    configSaving.value = false
  }
}
</script>
