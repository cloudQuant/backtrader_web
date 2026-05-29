<template>
  <div class="space-y-6 ai-observability-page">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">
          {{ t('aiObs.title') }}
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          {{ t('aiObs.desc') }}
        </p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        @click="loadDashboard"
      >
        {{ t('aiObs.btnRefresh') }}
      </el-button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <el-card>
        <div class="text-sm text-gray-500">
          {{ t('aiObs.sumTotalCalls') }}
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ usage?.summary.total_calls ?? 0 }}
        </div>
      </el-card>
      <el-card>
        <div class="text-sm text-gray-500">
          {{ t('aiObs.sumTotalTokens') }}
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ formatInteger(usage?.summary.total_tokens) }}
        </div>
      </el-card>
      <el-card>
        <div class="text-sm text-gray-500">
          {{ t('aiObs.sumEstCost') }}
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ formatUsd(usage?.summary.estimated_cost_usd) }}
        </div>
      </el-card>
      <el-card>
        <div class="text-sm text-gray-500">
          {{ t('aiObs.sumFailedCalls') }}
        </div>
        <div class="text-2xl font-bold mt-2">
          {{ usage?.summary.failed_calls ?? 0 }}
        </div>
      </el-card>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane
        :label="t('aiObs.tabUsage')"
        name="usage"
      >
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <el-card>
            <template #header>
              <span class="font-bold">{{ t('aiObs.cardByService') }}</span>
            </template>
            <el-table :data="usage?.by_service ?? []">
              <el-table-column
                prop="service_name"
                :label="t('aiObs.colService')"
              />
              <el-table-column
                prop="total_calls"
                :label="t('aiObs.colCallCount')"
              />
              <el-table-column
                prop="total_tokens"
                :label="t('aiObs.colTokens')"
              />
              <el-table-column :label="t('aiObs.colCost')">
                <template #default="scope">
                  {{ formatUsd(scope.row.estimated_cost_usd) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          <el-card>
            <template #header>
              <span class="font-bold">{{ t('aiObs.cardByModel') }}</span>
            </template>
            <el-table :data="usage?.by_model ?? []">
              <el-table-column
                prop="model_name"
                :label="t('aiObs.colModel')"
              />
              <el-table-column
                prop="total_calls"
                :label="t('aiObs.colCallCount')"
              />
              <el-table-column
                prop="total_tokens"
                :label="t('aiObs.colTokens')"
              />
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane
        :label="t('aiObs.tabFailures')"
        name="failures"
      >
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <el-card>
            <template #header>
              <span class="font-bold">{{ t('aiObs.cardErrorCodes') }}</span>
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
                :label="t('aiObs.colErrorCode')"
              />
              <el-table-column
                prop="failed_calls"
                :label="t('aiObs.colFailedCount')"
              />
            </el-table>
          </el-card>
          <el-card>
            <template #header>
              <span class="font-bold">{{ t('aiObs.cardRecentFailures') }}</span>
            </template>
            <el-table :data="failures?.recent_failures ?? []">
              <el-table-column
                prop="service_name"
                :label="t('aiObs.colService')"
              />
              <el-table-column
                prop="error_code"
                :label="t('aiObs.colErrorCode')"
              />
              <el-table-column
                prop="created_at"
                :label="t('aiObs.colTime')"
              />
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane
        :label="t('aiObs.tabSlow')"
        name="slow"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <el-card>
            <div class="text-sm text-gray-500">
              {{ t('aiObs.statP95') }}
            </div>
            <div class="text-2xl font-bold mt-2">
              {{ slowCalls?.summary.p95_latency_ms ?? 0 }} ms
            </div>
          </el-card>
          <el-card>
            <div class="text-sm text-gray-500">
              {{ t('aiObs.statP99') }}
            </div>
            <div class="text-2xl font-bold mt-2">
              {{ slowCalls?.summary.p99_latency_ms ?? 0 }} ms
            </div>
          </el-card>
          <el-card>
            <div class="text-sm text-gray-500">
              {{ t('aiObs.statAvg') }}
            </div>
            <div class="text-2xl font-bold mt-2">
              {{ slowCalls?.summary.avg_latency_ms ?? 0 }} ms
            </div>
          </el-card>
        </div>
        <el-card>
          <template #header>
            <span class="font-bold">{{ t('aiObs.cardTopSlow') }}</span>
          </template>
          <el-table :data="slowCalls?.top_calls ?? []">
            <el-table-column
              prop="service_name"
              :label="t('aiObs.colService')"
            />
            <el-table-column
              prop="model_name"
              :label="t('aiObs.colModel')"
            />
            <el-table-column
              prop="latency_ms"
              :label="t('aiObs.colLatencyMs')"
            />
            <el-table-column
              prop="created_at"
              :label="t('aiObs.colTime')"
            />
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'

import { aiObservabilityApi } from '@/api/aiObservability'
import type { AIFailureStats, AISlowCallStats, AIUsageStats } from '@/api/aiObservability'

const { t } = useI18n()

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
    ElMessage.error(t('aiObs.msgLoadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadDashboard()
})
</script>
