/** Gateway health data, polling, and connection operations. */

import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api'
import { liveTradingApi } from '@/api/liveTrading'
import type { GatewayHealthInfo } from '@/api/liveTrading'
import {
  connLabel,
  connTagType,
  formatHeartbeatAge,
  formatNumber,
  formatUptime,
  getHeartbeatAge,
  heartbeatClass,
  stateLabel,
  stateTagType,
} from '../gatewayStatusHelpers'

export function useGatewayStatusPage() {
  const { t } = useI18n()

  const loading = ref(false)
  const gateways = ref<GatewayHealthInfo[]>([])
  const loadError = ref('')
  const viewMode = ref<'card' | 'table'>('card')
  const gatewaySearch = ref('')
  const stateFilter = ref('all')
  const healthFilter = ref('all')
  const nowMs = ref(Date.now())
  const lastHealthFetchMs = ref(Date.now())
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  const baseGateways = computed(() => gateways.value.filter((g) => !g.gateway_key.startsWith('direct:')))
  const visibleGateways = computed(() => {
    const keyword = gatewaySearch.value.trim().toLowerCase()
    return baseGateways.value.filter((gateway) => {
      if (stateFilter.value !== 'all' && gateway.state !== stateFilter.value) return false
      if (healthFilter.value === 'healthy' && !gateway.is_healthy) return false
      if (healthFilter.value === 'unhealthy' && gateway.is_healthy) return false
      if (!keyword) return true
      return [
        gateway.gateway_key,
        gateway.strategy_name,
        gateway.exchange,
        gateway.asset_type,
        gateway.account_id,
        gateway.state,
        gateway.market_connection,
        gateway.trade_connection,
        ...gateway.instances,
        ...(gateway.recent_errors || []).map((item) => `${item.source} ${item.message}`),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword))
    })
  })
  const healthyCount = computed(() => visibleGateways.value.filter((g) => g.is_healthy).length)
  const totalSymbolCount = computed(() => visibleGateways.value.reduce((sum, item) => sum + item.symbol_count, 0))
  const totalOrderCount = computed(() => visibleGateways.value.reduce((sum, item) => sum + item.order_count, 0))
  const staleHeartbeatCount = computed(() =>
    visibleGateways.value.filter((gateway) => {
      const age = getHeartbeatAge(gateway, nowMs.value, lastHealthFetchMs.value)
      return age != null && age >= 30
    }).length
  )

  // ---- Connect Dialog ----
  const showConnectDialog = ref(false)
  const connecting = ref(false)
  const disconnecting = ref<string | null>(null)

  type GatewayCredentialScalar = string | number | boolean | null | undefined

  interface GatewayCredentials {
    account_id?: string
    access_token?: string
    api_key?: string
    app_id?: string
    asset_type?: string
    auth_code?: string
    base_url?: string
    broker_id?: string
    cookie_browser?: string
    cookie_output?: string
    cookie_path?: string
    cookie_source?: string
    login?: string | number
    login_browser?: string
    login_headless?: boolean
    login_mode?: string
    login_timeout?: number
    md_front?: string
    passphrase?: string
    password?: string
    secret_key?: string
    server?: string
    symbol_suffix?: string
    td_front?: string
    testnet?: boolean
    timeout?: number
    user_id?: string
    username?: string
    verify_ssl?: boolean
    ws_uri?: string
    [key: string]: GatewayCredentialScalar
  }

  type SavedGatewayCredentials = GatewayCredentials & Record<string, GatewayCredentials | GatewayCredentialScalar>

  const connectForm = reactive<{
    exchange_type: string
    credentials: GatewayCredentials
  }>({
    exchange_type: '',
    credentials: {},
  })

  // ---- Saved Credentials from .env ----
  const savedCredentials = ref<Record<string, SavedGatewayCredentials>>({})

  async function fetchSavedCredentials() {
    try {
      savedCredentials.value = await liveTradingApi.getGatewayCredentials() as Record<string, SavedGatewayCredentials>
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
    const saved = savedCredentials.value['CTP'] || {}
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

  function toGatewayCredentials(value: GatewayCredentials | GatewayCredentialScalar): GatewayCredentials {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {}
    }
    return value
  }

  function applyMt5Preset() {
    const saved = savedCredentials.value['MT5'] || {}
    const mode = toGatewayCredentials(saved[mt5Env.value])
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
    const saved = savedCredentials.value['IB_WEB'] || {}
    const mode = toGatewayCredentials(saved[ibEnv.value])
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
      username: mode.username || saved.username || '',
      password: mode.password || saved.password || '',
      login_mode: ibEnv.value,
      login_browser: mode.login_browser || saved.login_browser || 'chrome',
      login_headless: mode.login_headless ?? saved.login_headless ?? false,
      login_timeout: mode.login_timeout || saved.login_timeout || 180,
      cookie_output: mode.cookie_output || saved.cookie_output || '',
    }
  }

  function onIbEnvChange() {
    applyIbPreset()
  }

  function onExchangeChange() {
    const exType = connectForm.exchange_type
    const saved = savedCredentials.value[exType] || {}
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
      const credentials = { ...connectForm.credentials }
      if (connectForm.exchange_type === 'IB_WEB') {
        credentials.login_mode = ibEnv.value
      }
      const res = await liveTradingApi.connectGateway({
        exchange_type: connectForm.exchange_type,
        credentials,
      })
      ElMessage.success(res.message || t('gatewayStatus.msgConnected'))
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
      gateways.value = gateways.value.filter((gw) => gw.gateway_key !== gatewayKey)
      ElMessage.success(res.message || t('gatewayStatus.msgDisconnected'))
      try {
        await fetchHealth()
      } catch {
        // fetchHealth already handles UI state; keep optimistic removal result
      }
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
      nowMs.value = Date.now()
      lastHealthFetchMs.value = nowMs.value
      loadError.value = ''
    } catch (error) {
      loadError.value = getErrorMessage(error, t('gatewayStatus.msgLoadFailed'))
    } finally {
      loading.value = false
    }
  }


  onMounted(() => {
    void fetchHealth()
    void fetchSavedCredentials()
    heartbeatTimer = setInterval(() => {
      nowMs.value = Date.now()
    }, 1_000)
    pollTimer = setInterval(fetchHealth, 10_000)
  })

  onUnmounted(() => {
    if (pollTimer) clearInterval(pollTimer)
    if (heartbeatTimer) clearInterval(heartbeatTimer)
  })


  return {
    connLabel,
    connTagType,
    connectForm,
    connecting,
    ctpEnv,
    ctpGroup,
    disconnecting,
    fetchHealth,
    formatHeartbeatAge,
    formatNumber,
    formatUptime,
    gatewaySearch,
    gateways,
    getHeartbeatAge,
    handleConnect,
    handleDisconnect,
    healthFilter,
    healthyCount,
    heartbeatClass,
    ibEnv,
    lastHealthFetchMs,
    loadError,
    loading,
    mt5Env,
    nowMs,
    onCtpEnvChange,
    onCtpGroupChange,
    onExchangeChange,
    onIbEnvChange,
    onMt5EnvChange,
    openConnectDialog,
    showConnectDialog,
    staleHeartbeatCount,
    stateFilter,
    stateLabel,
    stateTagType,
    t,
    totalOrderCount,
    totalSymbolCount,
    viewMode,
    visibleGateways,
  }
}
