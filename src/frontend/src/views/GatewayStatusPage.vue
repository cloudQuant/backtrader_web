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
          <el-button type="primary" @click="openConnectDialog">
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
            <el-option label="MT5 (外汇/CFD)" value="MT5" />
            <el-option label="IB Web (美股)" value="IB_WEB" />
            <el-option label="Binance (币安)" value="BINANCE" />
            <el-option label="OKX (欧意)" value="OKX" />
          </el-select>
        </el-form-item>

        <!-- CTP Fields -->
        <template v-if="connectForm.exchange_type === 'CTP'">
          <el-form-item label="环境" required>
            <el-radio-group v-model="ctpEnv" @change="onCtpEnvChange">
              <el-radio-button value="simnow">SimNow 标准</el-radio-button>
              <el-radio-button value="simnow_7x24">SimNow 7×24</el-radio-button>
              <el-radio-button value="live" disabled>实盘</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="ctpEnv === 'simnow'" label="线路">
            <el-select v-model="ctpGroup" class="w-full" @change="onCtpGroupChange">
              <el-option label="第一组 (30001/30011)" :value="1" />
              <el-option label="第二组 (30002/30012)" :value="2" />
              <el-option label="第三组 (30003/30013)" :value="3" />
            </el-select>
          </el-form-item>
          <el-form-item label="账户" required>
            <el-input v-model="connectForm.credentials.user_id" placeholder="投资者代码" />
          </el-form-item>
          <el-form-item label="密码" required>
            <el-input v-model="connectForm.credentials.password" type="password" show-password placeholder="交易密码" />
          </el-form-item>
          <el-collapse class="mt-2 mb-2">
            <el-collapse-item title="高级设置">
              <el-form-item label="经纪商ID">
                <el-input v-model="connectForm.credentials.broker_id" placeholder="9999" />
              </el-form-item>
              <el-form-item label="交易前置">
                <el-input v-model="connectForm.credentials.td_front" placeholder="自动填入" />
              </el-form-item>
              <el-form-item label="行情前置">
                <el-input v-model="connectForm.credentials.md_front" placeholder="自动填入" />
              </el-form-item>
              <el-form-item label="AppID">
                <el-input v-model="connectForm.credentials.app_id" placeholder="simnow_client_test" />
              </el-form-item>
              <el-form-item label="认证码">
                <el-input v-model="connectForm.credentials.auth_code" placeholder="0000000000000000" />
              </el-form-item>
            </el-collapse-item>
          </el-collapse>
          <el-alert
            v-if="ctpEnv === 'simnow_7x24'"
            type="info"
            :closable="false"
            show-icon
            class="mb-3"
          >
            <template #title>7×24 环境说明</template>
            新注册用户需等到第三个交易日才可使用。账户/资金/持仓与标准环境上一交易日一致。
            服务时间：交易日 16:00～次日 09:00；非交易日 16:00～次日 12:00。
          </el-alert>
        </template>

        <template v-if="connectForm.exchange_type === 'MT5'">
          <el-form-item label="环境" required>
            <el-radio-group v-model="mt5Env" @change="onMt5EnvChange">
              <el-radio-button value="demo">模拟盘</el-radio-button>
              <el-radio-button value="live">实盘</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="登录号" required>
            <el-input v-model="connectForm.credentials.login" placeholder="MT5 Login" />
          </el-form-item>
          <el-form-item label="密码" required>
            <el-input v-model="connectForm.credentials.password" type="password" show-password placeholder="MT5 Password" />
          </el-form-item>
          <el-form-item label="服务器">
            <el-input v-model="connectForm.credentials.server" placeholder="Broker-Server" />
          </el-form-item>
          <el-form-item label="WS URI">
            <el-input v-model="connectForm.credentials.ws_uri" placeholder="ws://host:port 或 wss://host:port" />
          </el-form-item>
          <el-form-item label="后缀">
            <el-input v-model="connectForm.credentials.symbol_suffix" placeholder="如 .m 或留空" />
          </el-form-item>
          <el-form-item label="超时">
            <el-input v-model="connectForm.credentials.timeout" placeholder="60" />
          </el-form-item>
        </template>

        <!-- IB Web Fields -->
        <template v-if="connectForm.exchange_type === 'IB_WEB'">
          <el-form-item label="环境" required>
            <el-radio-group v-model="ibEnv" @change="onIbEnvChange">
              <el-radio-button value="paper">模拟盘</el-radio-button>
              <el-radio-button value="live">实盘</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="账户ID" required>
            <el-input v-model="connectForm.credentials.account_id" placeholder="如 DU123456" />
          </el-form-item>
          <el-form-item label="资产类型">
            <el-select v-model="connectForm.credentials.asset_type" class="w-full">
              <el-option label="股票 STK" value="STK" />
              <el-option label="期货 FUT" value="FUT" />
            </el-select>
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
          <el-form-item label="超时">
            <el-input v-model="connectForm.credentials.timeout" placeholder="10" />
          </el-form-item>
        </template>

        <!-- Binance Fields -->
        <template v-if="connectForm.exchange_type === 'BINANCE'">
          <el-form-item label="账户标识">
            <el-input v-model="connectForm.credentials.account_id" placeholder="自定义账户名称，可选" />
          </el-form-item>
          <el-form-item label="资产类型">
            <el-select v-model="connectForm.credentials.asset_type" class="w-full">
              <el-option label="永续/合约 SWAP" value="SWAP" />
              <el-option label="现货 SPOT" value="SPOT" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key" required>
            <el-input v-model="connectForm.credentials.api_key" placeholder="Binance API Key" />
          </el-form-item>
          <el-form-item label="Secret Key" required>
            <el-input v-model="connectForm.credentials.secret_key" type="password" show-password placeholder="Binance Secret Key" />
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="connectForm.credentials.base_url" placeholder="可选自定义 REST 地址" />
          </el-form-item>
          <el-form-item label="测试网">
            <el-switch v-model="connectForm.credentials.testnet" />
          </el-form-item>
        </template>

        <!-- OKX Fields -->
        <template v-if="connectForm.exchange_type === 'OKX'">
          <el-form-item label="账户标识">
            <el-input v-model="connectForm.credentials.account_id" placeholder="自定义账户名称，可选" />
          </el-form-item>
          <el-form-item label="资产类型">
            <el-select v-model="connectForm.credentials.asset_type" class="w-full">
              <el-option label="永续/合约 SWAP" value="SWAP" />
              <el-option label="现货 SPOT" value="SPOT" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key" required>
            <el-input v-model="connectForm.credentials.api_key" placeholder="OKX API Key" />
          </el-form-item>
          <el-form-item label="Secret Key" required>
            <el-input v-model="connectForm.credentials.secret_key" type="password" show-password placeholder="OKX Secret Key" />
          </el-form-item>
          <el-form-item label="Passphrase" required>
            <el-input v-model="connectForm.credentials.passphrase" type="password" show-password placeholder="OKX Passphrase" />
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="connectForm.credentials.base_url" placeholder="可选自定义 REST 地址" />
          </el-form-item>
          <el-form-item label="测试网">
            <el-switch v-model="connectForm.credentials.testnet" />
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

// ---- Saved Credentials from .env ----
const savedCredentials = ref<Record<string, Record<string, unknown>>>({})

async function fetchSavedCredentials() {
  try {
    savedCredentials.value = await liveTradingApi.getGatewayCredentials()
  } catch { /* ignore */ }
}

async function openConnectDialog() {
  await fetchSavedCredentials()
  connectForm.exchange_type = ''
  connectForm.credentials = {}
  showConnectDialog.value = true
}

// ---- CTP Environment Presets ----
const ctpEnv = ref<string>('simnow')
const ctpGroup = ref<number>(1)
const mt5Env = ref<string>('demo')
const ibEnv = ref<string>('paper')

const CTP_PRESETS: Record<string, { broker_id: string; td_front: string; md_front: string; app_id: string; auth_code: string }> = {
  simnow_1: { broker_id: '9999', td_front: 'tcp://182.254.243.31:30001', md_front: 'tcp://182.254.243.31:30011', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
  simnow_2: { broker_id: '9999', td_front: 'tcp://182.254.243.31:30002', md_front: 'tcp://182.254.243.31:30012', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
  simnow_3: { broker_id: '9999', td_front: 'tcp://182.254.243.31:30003', md_front: 'tcp://182.254.243.31:30013', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
  simnow_7x24: { broker_id: '9999', td_front: 'tcp://182.254.243.31:40001', md_front: 'tcp://182.254.243.31:40011', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
}

function applyCtpPreset() {
  const key = ctpEnv.value === 'simnow' ? `simnow_${ctpGroup.value}` : ctpEnv.value
  const preset = CTP_PRESETS[key]
  if (!preset) return
  const saved = (savedCredentials.value['CTP'] || {}) as Record<string, unknown>
  const userId = connectForm.credentials.user_id || saved.user_id || ''
  const password = connectForm.credentials.password || saved.password || ''
  connectForm.credentials = {
    ...preset,
    broker_id: saved.broker_id || preset.broker_id,
    app_id: saved.app_id || preset.app_id,
    auth_code: saved.auth_code || preset.auth_code,
    user_id: userId,
    password: password,
  }
}

function onCtpEnvChange() {
  applyCtpPreset()
}

function onCtpGroupChange() {
  applyCtpPreset()
}

function applyMt5Preset() {
  const saved = (savedCredentials.value['MT5'] || {}) as Record<string, unknown>
  const mode = (saved[mt5Env.value] || {}) as Record<string, unknown>
  connectForm.credentials = {
    login: mode.login || saved.login || '',
    password: mode.password || saved.password || '',
    server: mode.server || saved.server || '',
    ws_uri: mode.ws_uri || saved.ws_uri || '',
    symbol_suffix: mode.symbol_suffix || saved.symbol_suffix || '',
    timeout: mode.timeout || saved.timeout || 60,
  }
}

function onMt5EnvChange() {
  applyMt5Preset()
}

function applyIbPreset() {
  const saved = (savedCredentials.value['IB_WEB'] || {}) as Record<string, unknown>
  const mode = (saved[ibEnv.value] || {}) as Record<string, unknown>
  connectForm.credentials = {
    account_id: mode.account_id || saved.account_id || '',
    asset_type: mode.asset_type || saved.asset_type || 'STK',
    base_url: mode.base_url || saved.base_url || '',
    access_token: mode.access_token || saved.access_token || '',
    verify_ssl: mode.verify_ssl ?? saved.verify_ssl ?? false,
    timeout: mode.timeout || saved.timeout || 10,
    cookie_source: mode.cookie_source || saved.cookie_source || '',
    cookie_browser: mode.cookie_browser || saved.cookie_browser || 'chrome',
    cookie_path: mode.cookie_path || saved.cookie_path || '/sso',
  }
}

function onIbEnvChange() {
  applyIbPreset()
}

function onExchangeChange() {
  const exType = connectForm.exchange_type
  const saved = (savedCredentials.value[exType] || {}) as Record<string, unknown>
  if (exType === 'CTP') {
    ctpEnv.value = 'simnow'
    ctpGroup.value = 1
    connectForm.credentials = {}
    applyCtpPreset()
  } else if (exType === 'MT5') {
    mt5Env.value = 'demo'
    applyMt5Preset()
  } else if (exType === 'IB_WEB') {
    ibEnv.value = 'paper'
    applyIbPreset()
  } else if (exType === 'BINANCE') {
    connectForm.credentials = {
      account_id: saved.account_id || '',
      asset_type: saved.asset_type || 'SWAP',
      api_key: saved.api_key || '',
      secret_key: saved.secret_key || '',
      base_url: saved.base_url || '',
      testnet: saved.testnet ?? false,
    }
  } else if (exType === 'OKX') {
    connectForm.credentials = {
      account_id: saved.account_id || '',
      asset_type: saved.asset_type || 'SWAP',
      api_key: saved.api_key || '',
      secret_key: saved.secret_key || '',
      passphrase: saved.passphrase || '',
      base_url: saved.base_url || '',
      testnet: saved.testnet ?? false,
    }
  } else {
    connectForm.credentials = { ...saved }
  }
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
  fetchSavedCredentials()
  pollTimer = setInterval(fetchHealth, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
