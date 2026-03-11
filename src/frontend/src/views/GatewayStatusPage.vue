<template>
  <div class="space-y-6">
    <!-- Header -->
    <el-card>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-bold">Gateway 状态监控</h3>
          <el-tag :type="healthyCount > 0 ? 'success' : 'info'" size="small">
            {{ healthyCount }} 健康 / {{ gateways.length }} 总计
          </el-tag>
        </div>
        <el-button :loading="loading" @click="fetchHealth">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </el-card>

    <!-- Loading -->
    <div v-if="loading && gateways.length === 0" class="flex justify-center py-12">
      <el-icon class="is-loading text-4xl text-blue-500"><Loading /></el-icon>
    </div>

    <!-- Empty -->
    <div v-else-if="gateways.length === 0" class="text-center py-12">
      <el-empty description="暂无活跃 Gateway，请先在实盘交易页面启动策略" />
    </div>

    <!-- Gateway Cards -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <el-card v-for="gw in gateways" :key="gw.gateway_key" shadow="hover">
        <!-- Card Header -->
        <template #header>
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <el-icon :color="gw.is_healthy ? '#67c23a' : '#f56c6c'" :size="18">
                <CircleCheckFilled v-if="gw.is_healthy" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span class="font-bold text-base">{{ gw.gateway_key }}</span>
            </div>
            <el-tag :type="stateTagType(gw.state)" size="small">{{ gw.state }}</el-tag>
          </div>
        </template>

        <!-- Info Grid -->
        <div class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <span class="text-gray-500">交易所</span>
            <div class="font-medium">{{ gw.exchange || '-' }}</div>
          </div>
          <div>
            <span class="text-gray-500">资产类型</span>
            <div class="font-medium">{{ gw.asset_type || '-' }}</div>
          </div>
          <div>
            <span class="text-gray-500">账户</span>
            <div class="font-medium">{{ gw.account_id || '-' }}</div>
          </div>
          <div>
            <span class="text-gray-500">运行时长</span>
            <div class="font-medium">{{ formatUptime(gw.uptime_sec) }}</div>
          </div>
          <div>
            <span class="text-gray-500">行情连接</span>
            <div>
              <el-tag :type="connTagType(gw.market_connection)" size="small">
                {{ gw.market_connection }}
              </el-tag>
            </div>
          </div>
          <div>
            <span class="text-gray-500">交易连接</span>
            <div>
              <el-tag :type="connTagType(gw.trade_connection)" size="small">
                {{ gw.trade_connection }}
              </el-tag>
            </div>
          </div>
        </div>

        <!-- Stats Row -->
        <el-divider />
        <div class="grid grid-cols-4 gap-2 text-center text-sm">
          <div>
            <div class="text-gray-500">策略数</div>
            <div class="text-lg font-bold text-blue-600">{{ gw.strategy_count }}</div>
          </div>
          <div>
            <div class="text-gray-500">订阅品种</div>
            <div class="text-lg font-bold text-blue-600">{{ gw.symbol_count }}</div>
          </div>
          <div>
            <div class="text-gray-500">Tick数</div>
            <div class="text-lg font-bold text-green-600">{{ formatNumber(gw.tick_count) }}</div>
          </div>
          <div>
            <div class="text-gray-500">订单数</div>
            <div class="text-lg font-bold text-orange-600">{{ gw.order_count }}</div>
          </div>
        </div>

        <!-- Heartbeat & Instances -->
        <el-divider />
        <div class="text-sm space-y-2">
          <div class="flex justify-between">
            <span class="text-gray-500">心跳延迟</span>
            <span :class="heartbeatClass(gw.heartbeat_age_sec)">
              {{ gw.heartbeat_age_sec != null ? gw.heartbeat_age_sec + 's' : '-' }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-500">引用计数</span>
            <span>{{ gw.ref_count }}</span>
          </div>
          <div v-if="gw.instances.length > 0">
            <span class="text-gray-500">关联实例：</span>
            <el-tag
              v-for="iid in gw.instances"
              :key="iid"
              size="small"
              class="ml-1 mb-1"
              effect="plain"
            >
              {{ iid.slice(0, 8) }}
            </el-tag>
          </div>
        </div>

        <!-- Recent Errors -->
        <template v-if="gw.recent_errors && gw.recent_errors.length > 0">
          <el-divider />
          <div class="text-sm">
            <div class="text-red-500 font-medium mb-1">
              最近错误 ({{ gw.recent_errors.length }})
            </div>
            <div
              v-for="(err, idx) in gw.recent_errors.slice(-3)"
              :key="idx"
              class="text-xs text-gray-600 truncate"
              :title="err.message"
            >
              [{{ err.source }}] {{ err.message }}
            </div>
          </div>
        </template>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  Refresh,
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
} from '@element-plus/icons-vue'
import { liveTradingApi } from '@/api/liveTrading'
import type { GatewayHealthInfo } from '@/api/liveTrading'

const loading = ref(false)
const gateways = ref<GatewayHealthInfo[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const healthyCount = computed(() => gateways.value.filter((g) => g.is_healthy).length)

async function fetchHealth() {
  loading.value = true
  try {
    const res = await liveTradingApi.listGatewayHealth()
    gateways.value = res.gateways
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function stateTagType(state: string) {
  switch (state) {
    case 'running':
      return 'success'
    case 'starting':
    case 'stopping':
      return 'warning'
    case 'error':
      return 'danger'
    default:
      return 'info'
  }
}

function connTagType(conn: string) {
  switch (conn) {
    case 'connected':
      return 'success'
    case 'connecting':
    case 'reconnecting':
      return 'warning'
    case 'error':
      return 'danger'
    default:
      return 'info'
  }
}

function heartbeatClass(age: number | null) {
  if (age == null) return 'text-gray-400'
  if (age < 5) return 'text-green-600 font-medium'
  if (age < 30) return 'text-yellow-600 font-medium'
  return 'text-red-600 font-medium'
}

function formatUptime(sec: number) {
  if (!sec || sec <= 0) return '-'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

function formatNumber(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

onMounted(() => {
  fetchHealth()
  pollTimer = setInterval(fetchHealth, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
