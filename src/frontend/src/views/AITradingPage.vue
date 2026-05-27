<script setup lang="ts">
/**
 * AI Trading Page - Natural language driven trading interface.
 *
 * Allows users to describe trades in natural language, review AI-parsed
 * intents, confirm or reject trades, and view execution history.
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Promotion,
  Warning,
  Document,
} from '@element-plus/icons-vue'
import {
  executeTrade,
  confirmTrade,
  getTradingConfig,
  getTradingHistory,
} from '@/api/aiTrading'
import type { AITradingResponse, AITradingConfig, TradeHistoryItem } from '@/api/aiTrading'

// Reactive state
const message = ref('')
const loading = ref(false)
const dryRun = ref(true)
const autoConfirm = ref(false)
const config = ref<AITradingConfig | null>(null)
const history = ref<TradeHistoryItem[]>([])
const currentResponse = ref<AITradingResponse | null>(null)
const responses = ref<AITradingResponse[]>([])
const selectedAccountId = ref('')
const selectedGatewayId = ref('')

// Computed
const canSend = computed(() => message.value.trim().length > 0 && !loading.value)
const modeLabel = computed(() => dryRun.value ? '模拟模式' : '实盘模式')
const modeClass = computed(() => dryRun.value ? 'mode-paper' : 'mode-live')
const availableAccounts = computed(() => config.value?.available_accounts ?? [])
const availableGateways = computed(() => config.value?.available_gateways ?? [])

// Methods
async function handleSend() {
  if (!canSend.value) return

  if (dryRun.value && !selectedAccountId.value) {
    ElMessage.warning('请先选择一个模拟交易账户')
    return
  }
  if (!dryRun.value && !selectedGatewayId.value) {
    ElMessage.warning('请先选择一个已连接的实盘网关')
    return
  }

  const input = message.value.trim()
  message.value = ''
  loading.value = true
  currentResponse.value = null

  try {
    const result = await executeTrade({
      message: input,
      gateway_id: dryRun.value ? undefined : selectedGatewayId.value,
      account_id: dryRun.value ? selectedAccountId.value : undefined,
      dry_run: dryRun.value,
      auto_confirm: autoConfirm.value,
    })
    currentResponse.value = result
    responses.value.unshift(result)

    if (result.requires_confirmation) {
      await handleConfirmDialog(result)
    }
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : '请求失败'
    ElMessage.error(`交易请求失败: ${msg}`)
  } finally {
    loading.value = false
  }
}

async function handleConfirmDialog(response: AITradingResponse) {
  try {
    await ElMessageBox.confirm(
      response.message,
      '确认交易',
      {
        confirmButtonText: '确认执行',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false,
      }
    )
    // User confirmed
    const result = await confirmTrade({
      trade_id: response.trade_id,
      confirmed: true,
    })
    ElMessage.success(result.message)
    await loadHistory()
  } catch {
    // User cancelled
    await confirmTrade({
      trade_id: response.trade_id,
      confirmed: false,
    })
    ElMessage.info('交易已取消')
  }
}

async function loadConfig() {
  try {
    config.value = await getTradingConfig()
    if (!selectedAccountId.value && config.value.available_accounts.length > 0) {
      selectedAccountId.value = config.value.available_accounts[0].account_id
    }
    if (!selectedGatewayId.value) {
      const connectedGateway = config.value.available_gateways.find(item => item.connected)
      if (connectedGateway) {
        selectedGatewayId.value = connectedGateway.gateway_id
      }
    }
  } catch {
    // Config load failure is non-critical
  }
}

async function loadHistory() {
  try {
    const result = await getTradingHistory(20)
    history.value = result.items
  } catch {
    // History load failure is non-critical
  }
}

function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    filled: 'var(--success-color)',
    confirmed: 'var(--primary-color)',
    pending_confirmation: 'var(--warning-color)',
    rejected: 'var(--danger-color)',
    cancelled: 'var(--text-color-secondary)',
    failed: 'var(--danger-color)',
  }
  return colors[status] || 'var(--text-color-secondary)'
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    filled: '已成交',
    confirmed: '已确认',
    pending_confirmation: '待确认',
    rejected: '已拒绝',
    cancelled: '已取消',
    failed: '失败',
    executing: '执行中',
  }
  return labels[status] || status
}

function getRiskColor(level: string): string {
  const colors: Record<string, string> = {
    low: 'var(--success-color)',
    medium: 'var(--warning-color)',
    high: 'var(--danger-color)',
    critical: 'var(--danger-color)',
  }
  return colors[level] || 'var(--text-color-secondary)'
}

function getActionLabel(action: string): string {
  const labels: Record<string, string> = {
    buy: '买入',
    sell: '卖出',
    close: '平仓',
    cancel: '撤单',
    query: '查询',
    modify: '修改',
  }
  return labels[action] || action
}

// Lifecycle
onMounted(async () => {
  await Promise.all([loadConfig(), loadHistory()])
})
</script>

<template>
  <div class="ai-trading-page">
    <!-- Header -->
    <section class="trading-hero">
      <div>
        <div class="eyebrow">
          AI Trading
        </div>
        <h2>自然语言交易</h2>
        <p>用自然语言描述交易意图，AI 自动解析并执行。支持多交易所、多品种。</p>
      </div>
      <div class="hero-controls">
        <label
          class="mode-switch"
          :class="modeClass"
        >
          <input
            v-model="dryRun"
            type="checkbox"
          >
          <span>{{ modeLabel }}</span>
        </label>
        <label class="auto-confirm-toggle">
          <input
            v-model="autoConfirm"
            type="checkbox"
          >
          <span>自动确认</span>
        </label>
      </div>
    </section>

    <!-- Main content -->
    <div class="trading-grid">
      <!-- Left: Input + Response -->
      <main class="trading-main">
        <!-- Input area -->
        <div class="input-section">
          <div class="input-hints">
            <span>示例: "买入1手螺纹钢主力合约" | "以3500限价卖出2手铁矿石" | "帮我在币安买入0.1个BTC"</span>
          </div>
          <div class="context-row">
            <label
              v-if="dryRun"
              class="context-field"
            >
              <span>模拟账户</span>
              <select
                v-model="selectedAccountId"
                :disabled="loading || availableAccounts.length === 0"
              >
                <option value="">
                  请选择模拟账户
                </option>
                <option
                  v-for="account in availableAccounts"
                  :key="account.account_id"
                  :value="account.account_id"
                >
                  {{ account.name }} · 总资产 {{ account.total_equity.toFixed(2) }}
                </option>
              </select>
            </label>
            <label
              v-else
              class="context-field"
            >
              <span>实盘网关</span>
              <select
                v-model="selectedGatewayId"
                :disabled="loading || availableGateways.length === 0"
              >
                <option value="">
                  请选择实盘网关
                </option>
                <option
                  v-for="gateway in availableGateways"
                  :key="gateway.gateway_id"
                  :value="gateway.gateway_id"
                >
                  {{ gateway.exchange_type }} · {{ gateway.account_id || gateway.gateway_id }}{{ gateway.connected ? '' : '（未连接）' }}
                </option>
              </select>
            </label>
            <span
              v-if="dryRun && availableAccounts.length === 0"
              class="context-hint"
            >暂无可用模拟账户，请先在模拟交易页面创建账户。</span>
            <span
              v-else-if="!dryRun && availableGateways.length === 0"
              class="context-hint"
            >暂无可用网关，请先在实盘交易页面连接网关。</span>
          </div>
          <div class="input-row">
            <textarea
              v-model="message"
              :disabled="loading"
              placeholder="输入交易指令..."
              :maxlength="500"
              @keydown.enter.exact.prevent="handleSend"
            />
            <button
              class="send-btn"
              :disabled="!canSend"
              @click="handleSend"
            >
              <el-icon><Promotion /></el-icon>
              {{ loading ? '解析中...' : '发送' }}
            </button>
          </div>
        </div>

        <!-- Current response -->
        <div
          v-if="currentResponse"
          class="response-card"
        >
          <div class="response-header">
            <span
              class="status-badge"
              :style="{ backgroundColor: getStatusColor(currentResponse.status) }"
            >
              {{ getStatusLabel(currentResponse.status) }}
            </span>
            <span class="trade-id">{{ currentResponse.trade_id }}</span>
          </div>

          <!-- Intent summary -->
          <div class="intent-summary">
            <div class="intent-action">
              <strong>{{ getActionLabel(currentResponse.intent.action) }}</strong>
              <span v-if="currentResponse.intent.quantity">
                {{ currentResponse.intent.quantity }}
              </span>
              <span v-if="currentResponse.intent.symbol">
                {{ currentResponse.intent.symbol }}
              </span>
              <span v-if="currentResponse.intent.price">
                @ {{ currentResponse.intent.price }}
              </span>
              <span
                v-else
                class="market-tag"
              >市价</span>
            </div>
            <div class="intent-meta">
              <span
                class="confidence-badge"
                :style="{ color: currentResponse.intent.confidence > 0.7 ? 'var(--success-color)' : 'var(--warning-color)' }"
              >
                置信度: {{ (currentResponse.intent.confidence * 100).toFixed(0) }}%
              </span>
              <span
                class="risk-badge"
                :style="{ color: getRiskColor(currentResponse.risk_assessment.risk_level) }"
              >
                风险: {{ currentResponse.risk_assessment.risk_level }}
              </span>
            </div>
          </div>

          <!-- Message -->
          <div
            v-if="currentResponse.degraded || currentResponse.diagnostic_message"
            class="diagnostic-box"
          >
            <el-icon><Warning /></el-icon>
            <span>{{ currentResponse.diagnostic_message || '当前请求处于降级模式，系统未执行自动交易。' }}</span>
          </div>
          <div class="response-message">
            {{ currentResponse.message }}
          </div>

          <!-- Warnings -->
          <div
            v-if="currentResponse.risk_assessment.warnings.length"
            class="warnings-box"
          >
            <div
              v-for="(w, i) in currentResponse.risk_assessment.warnings"
              :key="i"
              class="warning-item"
            >
              <el-icon><Warning /></el-icon>
              <span>{{ w }}</span>
            </div>
          </div>

          <!-- Suggestions -->
          <div
            v-if="currentResponse.suggestions.length"
            class="suggestions-box"
          >
            <div class="suggestions-title">
              💡 建议
            </div>
            <ul>
              <li
                v-for="(s, i) in currentResponse.suggestions"
                :key="i"
              >
                {{ s }}
              </li>
            </ul>
          </div>

          <!-- AI Reasoning -->
          <div
            v-if="currentResponse.ai_reasoning"
            class="reasoning-box"
          >
            <div class="reasoning-title">
              AI 分析
            </div>
            <p>{{ currentResponse.ai_reasoning }}</p>
          </div>
        </div>

        <!-- Response history -->
        <div
          v-if="responses.length > 1"
          class="response-history"
        >
          <h4>历史指令</h4>
          <div
            v-for="resp in responses.slice(1, 6)"
            :key="resp.trade_id"
            class="history-item-inline"
          >
            <span
              class="status-dot"
              :style="{ backgroundColor: getStatusColor(resp.status) }"
            />
            <span class="history-action">{{ getActionLabel(resp.intent.action) }}</span>
            <span v-if="resp.intent.symbol">{{ resp.intent.symbol }}</span>
            <span class="history-status">{{ getStatusLabel(resp.status) }}</span>
          </div>
        </div>
      </main>

      <!-- Right: History panel -->
      <aside class="history-panel">
        <div class="panel-header">
          <h3>交易记录</h3>
          <span class="record-count">{{ history.length }} 条</span>
        </div>
        <div
          v-if="history.length === 0"
          class="empty-state"
        >
          <el-icon><Document /></el-icon>
          <p>暂无交易记录</p>
        </div>
        <div
          v-else
          class="history-list"
        >
          <div
            v-for="item in history"
            :key="item.trade_id"
            class="history-card"
          >
            <div class="history-card-header">
              <span class="history-card-action">{{ getActionLabel(item.action) }}</span>
              <span
                v-if="item.symbol"
                class="history-card-symbol"
              >{{ item.symbol }}</span>
              <span
                class="history-card-status"
                :style="{ color: getStatusColor(item.status) }"
              >
                {{ getStatusLabel(item.status) }}
              </span>
            </div>
            <div class="history-card-input">
              {{ item.user_input }}
            </div>
            <div class="history-card-meta">
              <span v-if="item.quantity">数量: {{ item.quantity }}</span>
              <span
                v-if="item.dry_run"
                class="paper-tag"
              >模拟</span>
              <span class="history-card-time">{{ item.created_at?.slice(0, 16) }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.ai-trading-page {
  max-width: 1400px;
  margin: 0 auto;
}

.trading-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  padding: 20px 24px;
  background: var(--el-bg-color);
  border-radius: var(--el-border-radius-base);
  border: 1px solid var(--el-border-color-lighter);
}

.trading-hero .eyebrow {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--el-color-primary);
  margin-bottom: 4px;
}

.trading-hero h2 {
  margin: 0 0 4px;
  font-size: 20px;
}

.trading-hero p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.hero-controls {
  display: flex;
  gap: 16px;
  align-items: center;
}

.mode-switch, .auto-confirm-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}

.mode-paper span { color: var(--el-color-success); }
.mode-live span { color: var(--el-color-danger); font-weight: 600; }

.trading-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 20px;
}

.input-section {
  background: var(--el-bg-color);
  border-radius: var(--el-border-radius-base);
  border: 1px solid var(--el-border-color-lighter);
  padding: 16px;
  margin-bottom: 16px;
}

.input-hints {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.context-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.context-field {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.context-field select {
  min-width: 260px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
}

.context-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.input-row {
  display: flex;
  gap: 8px;
}

.input-row textarea {
  flex: 1;
  min-height: 44px;
  max-height: 120px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  resize: vertical;
  font-size: 14px;
  font-family: inherit;
}

.send-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 16px;
  background: var(--el-color-primary);
  color: white;
  border: none;
  border-radius: var(--el-border-radius-base);
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.response-card {
  background: var(--el-bg-color);
  border-radius: var(--el-border-radius-base);
  border: 1px solid var(--el-border-color-lighter);
  padding: 16px;
  margin-bottom: 16px;
}

.response-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  color: white;
  font-size: 12px;
  font-weight: 500;
}

.trade-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.intent-summary {
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: var(--el-border-radius-base);
  margin-bottom: 12px;
}

.intent-action {
  font-size: 16px;
  margin-bottom: 4px;
}

.intent-action strong {
  color: var(--el-color-primary);
}

.market-tag {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  padding: 1px 6px;
  border-radius: 3px;
}

.intent-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
}

.response-message {
  margin-bottom: 12px;
  font-size: 14px;
  line-height: 1.5;
}

.diagnostic-box {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 4px;
  background: var(--warning-surface);
  color: var(--warning-text-color);
  font-size: 13px;
}

.warnings-box {
  padding: 8px 12px;
  background: var(--warning-surface);
  border-radius: 4px;
  margin-bottom: 8px;
}

.warning-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--warning-color);
  margin-bottom: 4px;
}

.suggestions-box {
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  margin-bottom: 8px;
}

.suggestions-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
}

.suggestions-box ul {
  margin: 0;
  padding-left: 16px;
  font-size: 13px;
}

.reasoning-box {
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 13px;
}

.reasoning-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.response-history h4 {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.history-item-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.history-panel {
  background: var(--el-bg-color);
  border-radius: var(--el-border-radius-base);
  border: 1px solid var(--el-border-color-lighter);
  padding: 16px;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
}

.record-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.empty-state {
  text-align: center;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}

.empty-state .el-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.history-card {
  padding: 10px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.history-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.history-card-action {
  font-weight: 500;
  font-size: 13px;
}

.history-card-symbol {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-family: monospace;
}

.history-card-status {
  margin-left: auto;
  font-size: 12px;
}

.history-card-input {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.history-card-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.paper-tag {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
  padding: 0 4px;
  border-radius: 2px;
}

@media (max-width: 900px) {
  .trading-grid {
    grid-template-columns: 1fr;
  }
}
</style>
