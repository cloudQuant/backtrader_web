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
        <div class="flex gap-2">
          <el-button type="primary" @click="showConnectDialog = true">
            <el-icon><Connection /></el-icon>连接 Gateway
          </el-button>
          <el-button :loading="loading" @click="fetchHealth">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
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
              <span class="font-bold text-base">{{ gw.strategy_name || gw.gateway_key }}</span>
              <el-tag v-if="gw.gateway_key.startsWith('direct:')" size="small" type="warning" effect="plain">直连</el-tag>
            </div>
            <div class="flex items-center gap-2">
              <el-tag :type="stateTagType(gw.state)" size="small">{{ gw.state }}</el-tag>
              <el-popconfirm
                v-if="gw.gateway_key.startsWith('manual:')"
                title="确定断开此 Gateway？"
                @confirm="handleDisconnect(gw.gateway_key)"
              >
                <template #reference>
                  <el-button type="danger" size="small" plain :loading="disconnecting === gw.gateway_key">
                    断开
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
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

    <!-- Connect Gateway Dialog -->
    <el-dialog v-model="showConnectDialog" title="连接 Gateway" width="560px">
      <el-form :model="connectForm" label-width="100px">
        <el-form-item label="交易所" required>
          <el-select v-model="connectForm.exchange_type" placeholder="选择交易所" class="w-full" @change="onExchangeChange">
            <el-option label="CTP (国内期货)" value="CTP" />
            <el-option label="IB Web (美股)" value="IB_WEB" />
            <el-option label="Binance (币安)" value="BINANCE" />
            <el-option label="OKX (欧意)" value="OKX" />
          </el-select>
        </el-form-item>

        <!-- CTP Fields -->
        <template v-if="connectForm.exchange_type === 'CTP'">
          <el-form-item label="经纪商ID" required>
            <el-input v-model="connectForm.credentials.broker_id" placeholder="如 9999" />
          </el-form-item>
          <el-form-item label="账户" required>
            <el-input v-model="connectForm.credentials.user_id" placeholder="投资者代码" />
          </el-form-item>
          <el-form-item label="密码" required>
            <el-input v-model="connectForm.credentials.password" type="password" show-password placeholder="交易密码" />
          </el-form-item>
          <el-form-item label="交易前置">
            <el-input v-model="connectForm.credentials.td_front" placeholder="tcp://180.168.146.187:10201" />
          </el-form-item>
          <el-form-item label="行情前置">
            <el-input v-model="connectForm.credentials.md_front" placeholder="tcp://180.168.146.187:10211" />
          </el-form-item>
          <el-form-item label="AppID">
            <el-input v-model="connectForm.credentials.app_id" placeholder="simnow_client_test" />
          </el-form-item>
          <el-form-item label="认证码">
            <el-input v-model="connectForm.credentials.auth_code" placeholder="0000000000000000" />
          </el-form-item>
        </template>

        <!-- IB Web Fields -->
        <template v-if="connectForm.exchange_type === 'IB_WEB'">
          <el-form-item label="账户ID" required>
            <el-input v-model="connectForm.credentials.account_id" placeholder="如 DU123456" />
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="connectForm.credentials.base_url" placeholder="https://localhost:5000" />
          </el-form-item>
          <el-form-item label="Access Token">
            <el-input v-model="connectForm.credentials.access_token" placeholder="可选" />
          </el-form-item>
          <el-form-item label="SSL校验">
            <el-switch v-model="connectForm.credentials.verify_ssl" />
          </el-form-item>
        </template>

        <!-- Binance Fields -->
        <template v-if="connectForm.exchange_type === 'BINANCE'">
          <el-form-item label="API Key" required>
            <el-input v-model="connectForm.credentials.api_key" placeholder="Binance API Key" />
          </el-form-item>
          <el-form-item label="Secret Key" required>
            <el-input v-model="connectForm.credentials.secret_key" type="password" show-password placeholder="Binance Secret Key" />
          </el-form-item>
        </template>

        <!-- OKX Fields -->
        <template v-if="connectForm.exchange_type === 'OKX'">
          <el-form-item label="API Key" required>
            <el-input v-model="connectForm.credentials.api_key" placeholder="OKX API Key" />
          </el-form-item>
          <el-form-item label="Secret Key" required>
            <el-input v-model="connectForm.credentials.secret_key" type="password" show-password placeholder="OKX Secret Key" />
          </el-form-item>
          <el-form-item label="Passphrase" required>
            <el-input v-model="connectForm.credentials.passphrase" type="password" show-password placeholder="OKX Passphrase" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showConnectDialog = false">取消</el-button>
        <el-button type="primary" :loading="connecting" :disabled="!connectForm.exchange_type" @click="handleConnect">
          连接
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import {
  Refresh,
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  Connection,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { liveTradingApi } from '@/api/liveTrading'
import type { GatewayHealthInfo } from '@/api/liveTrading'

const loading = ref(false)
const gateways = ref<GatewayHealthInfo[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const healthyCount = computed(() => gateways.value.filter((g) => g.is_healthy).length)

// ---- Connect Dialog ----
const showConnectDialog = ref(false)
const connecting = ref(false)
const disconnecting = ref<string | null>(null)

const connectForm = reactive<{
  exchange_type: string
  credentials: Record<string, unknown>
}>({
  exchange_type: '',
  credentials: {},
})

function onExchangeChange() {
  connectForm.credentials = {}
}

async function handleConnect() {
  if (!connectForm.exchange_type) return
  connecting.value = true
  try {
    const res = await liveTradingApi.connectGateway({
      exchange_type: connectForm.exchange_type,
      credentials: { ...connectForm.credentials },
    })
    ElMessage.success(res.message || '连接成功')
    showConnectDialog.value = false
    connectForm.exchange_type = ''
    connectForm.credentials = {}
    await fetchHealth()
  } catch {
    // Error already shown by Axios interceptor
  } finally {
    connecting.value = false
  }
}

async function handleDisconnect(gatewayKey: string) {
  disconnecting.value = gatewayKey
  try {
    const res = await liveTradingApi.disconnectGateway(gatewayKey)
    ElMessage.success(res.message || '已断开')
    await fetchHealth()
  } catch {
    // Error already shown by Axios interceptor
  } finally {
    disconnecting.value = null
  }
}

// ---- Health Fetch ----
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
