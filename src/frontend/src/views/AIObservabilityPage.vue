<template>
  <div class="space-y-6 ai-observability-page">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">
          AI 成本看板
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          跟踪 AI 调用用量、失败诊断与慢调用排查。
        </p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        @click="loadDashboard"
      >
        刷新
      </el-button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <el-card>
        <div class="text-sm text-gray-500">
          总调用数
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ usage?.summary.total_calls ?? 0 }}
        </div>
      </el-card>
      <el-card>
        <div class="text-sm text-gray-500">
          总 Token
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ formatInteger(usage?.summary.total_tokens) }}
        </div>
      </el-card>
      <el-card>
        <div class="text-sm text-gray-500">
          估算成本
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ formatUsd(usage?.summary.estimated_cost_usd) }}
        </div>
      </el-card>
      <el-card>
        <div class="text-sm text-gray-500">
          失败调用
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ usage?.summary.failed_calls ?? 0 }}
        </div>
      </el-card>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane
        label="用量趋势"
        name="usage"
      >
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <el-card>
            <template #header>
              <span class="font-bold">按服务统计</span>
            </template>
            <el-table :data="usage?.by_service ?? []">
              <el-table-column
                prop="service_name"
                label="服务"
              />
              <el-table-column
                prop="total_calls"
                label="调用数"
              />
              <el-table-column
                prop="total_tokens"
                label="Token"
              />
              <el-table-column label="成本">
                <template #default="scope">
                  {{ formatUsd(scope.row.estimated_cost_usd) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          <el-card>
            <template #header>
              <span class="font-bold">模型分布</span>
            </template>
            <el-table :data="usage?.by_model ?? []">
              <el-table-column
                prop="model_name"
                label="模型"
              />
              <el-table-column
                prop="total_calls"
                label="调用数"
              />
              <el-table-column
                prop="total_tokens"
                label="Token"
              />
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane
        label="失败诊断"
        name="failures"
      >
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <el-card>
            <template #header>
              <span class="font-bold">错误码分布</span>
            </template>
            <div class="flex flex-wrap gap-2 mb-3">
              <el-tag
                v-for="item in failures?.by_error_code ?? []"
                :key="item.error_code || 'unknown'"
                type="danger"
              >
                {{ item.error_code || 'unknown' }} × {{ item.failed_calls }}
              </el-tag>
            </div>
            <el-table :data="failures?.by_error_code ?? []">
              <el-table-column
                prop="error_code"
                label="错误码"
              />
              <el-table-column
                prop="failed_calls"
                label="失败次数"
              />
            </el-table>
          </el-card>
          <el-card>
            <template #header>
              <span class="font-bold">最近失败记录</span>
            </template>
            <el-table :data="failures?.recent_failures ?? []">
              <el-table-column
                prop="service_name"
                label="服务"
              />
              <el-table-column
                prop="error_code"
                label="错误码"
              />
              <el-table-column
                prop="created_at"
                label="时间"
              />
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane
        label="慢调用排查"
        name="slow"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <el-card>
            <div class="text-sm text-gray-500">
              P95 延迟
            </div>
            <div class="text-2xl font-bold mt-2">
              {{ slowCalls?.summary.p95_latency_ms ?? 0 }} ms
            </div>
          </el-card>
          <el-card>
            <div class="text-sm text-gray-500">
              P99 延迟
            </div>
            <div class="text-2xl font-bold mt-2">
              {{ slowCalls?.summary.p99_latency_ms ?? 0 }} ms
            </div>
          </el-card>
          <el-card>
            <div class="text-sm text-gray-500">
              平均延迟
            </div>
            <div class="text-2xl font-bold mt-2">
              {{ slowCalls?.summary.avg_latency_ms ?? 0 }} ms
            </div>
          </el-card>
        </div>
        <el-card>
          <template #header>
            <span class="font-bold">Top 慢调用样本</span>
          </template>
          <el-table :data="slowCalls?.top_calls ?? []">
            <el-table-column
              prop="service_name"
              label="服务"
            />
            <el-table-column
              prop="model_name"
              label="模型"
            />
            <el-table-column
              prop="latency_ms"
              label="延迟(ms)"
            />
            <el-table-column
              prop="created_at"
              label="时间"
            />
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { aiObservabilityApi } from '@/api/aiObservability'
import type { AIFailureStats, AISlowCallStats, AIUsageStats } from '@/api/aiObservability'

const activeTab = ref('usage')
const loading = ref(false)
const usage = ref<AIUsageStats | null>(null)
const failures = ref<AIFailureStats | null>(null)
const slowCalls = ref<AISlowCallStats | null>(null)

function formatUsd(value?: number): string {
  return `$${Number(value ?? 0).toFixed(6)}`
}

function formatInteger(value?: number): string {
  return Number(value ?? 0).toLocaleString()
}

async function loadDashboard() {
  loading.value = true
  try {
    const [usageData, failureData, slowData] = await Promise.all([
      aiObservabilityApi.getAdminUsage({}),
      aiObservabilityApi.getAdminFailures({ limit: 50 }),
      aiObservabilityApi.getAdminSlowCalls({ limit: 20 }),
    ])
    usage.value = usageData
    failures.value = failureData
    slowCalls.value = slowData
  } catch {
    ElMessage.error('AI 成本看板加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadDashboard()
})
</script>
