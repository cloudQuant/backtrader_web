<script setup lang="ts">
/**
 * AI Trading Page - Natural language driven trading interface.
 *
 * Allows users to describe trades in natural language, review AI-parsed
 * intents, confirm or reject trades, and view execution history.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CircleCheck,
  Connection,
  DataLine,
  Promotion,
  TrendCharts,
  Warning,
  Document,
} from '@element-plus/icons-vue'
import {
  executeTrade,
  confirmTrade,
  getTradingConfig,
  getTradingHistory,
} from '@/api/aiTrading'
import type {
  AITradingAccountOption,
  AITradingResponse,
  AITradingConfig,
  TradeHistoryItem,
} from '@/api/aiTrading'

const { t } = useI18n()

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

// Computed
const canSend = computed(() => message.value.trim().length > 0 && !loading.value)
const modeLabel = computed(() => dryRun.value ? t('aiTrading.modePaper') : t('aiTrading.modeLive'))
const modeClass = computed(() => dryRun.value ? 'mode-paper' : 'mode-live')
const availableAccounts = computed(() => config.value?.available_accounts ?? [])
const selectableAccounts = computed(() => {
  if (dryRun.value) {
    return availableAccounts.value.filter(account => account.source !== 'gateway')
  }
  return availableAccounts.value.filter(account => account.source === 'gateway' && account.gateway_id)
})
const selectedAccount = computed(() => (
  selectableAccounts.value.find(account => account.account_id === selectedAccountId.value) ?? null
))
const paperAccountCount = computed(() =>
  availableAccounts.value.filter(account => account.source !== 'gateway').length
)
const liveGatewayCount = computed(() =>
  availableAccounts.value.filter(account => account.source === 'gateway' && account.gateway_id).length
)
const connectedGatewayCount = computed(() =>
  (config.value?.available_gateways ?? []).filter(gateway => gateway.connected).length
)
const selectedAccountSummary = computed(() =>
  selectedAccount.value
    ? accountOptionLabel(selectedAccount.value)
    : (dryRun.value ? t('aiTrading.pickPaperAccount') : t('aiTrading.pickLiveGateway'))
)
const modeHelper = computed(() =>
  dryRun.value ? t('aiTrading.modePaperHelper') : t('aiTrading.modeLiveHelper')
)
const riskThreshold = computed(() => {
  const threshold = config.value?.require_confirmation_above
  if (typeof threshold !== 'number' || !Number.isFinite(threshold)) {
    return '--'
  }
  return `${Math.round(threshold * 100)}%`
})
const maxSingleTradeAmount = computed(() => formatAccountNumber(config.value?.max_single_trade_amount))
const commandStats = computed(() => [
  {
    key: 'accounts',
    label: t('aiTrading.statAccounts'),
    value: `${paperAccountCount.value}/${liveGatewayCount.value}`,
    helper: t('aiTrading.statAccountsHelper'),
    tone: 'primary',
    icon: DataLine,
  },
  {
    key: 'gateways',
    label: t('aiTrading.statGateways'),
    value: connectedGatewayCount.value,
    helper: t('aiTrading.statGatewaysHelper'),
    tone: connectedGatewayCount.value > 0 ? 'success' : 'warning',
    icon: Connection,
  },
  {
    key: 'risk',
    label: t('aiTrading.statRiskLimit'),
    value: maxSingleTradeAmount.value,
    helper: t('aiTrading.statRiskLimitHelper', { threshold: riskThreshold.value }),
    tone: 'warning',
    icon: Warning,
  },
  {
    key: 'history',
    label: t('aiTrading.statHistory'),
    value: history.value.length,
    helper: t('aiTrading.statHistoryHelper'),
    tone: 'neutral',
    icon: TrendCharts,
  },
])
const quickCommands = computed(() => [
  t('aiTrading.quickCommand1'),
  t('aiTrading.quickCommand2'),
  t('aiTrading.quickCommand3'),
])

// Methods
async function handleSend() {
  if (!canSend.value) return

  if (!selectedAccount.value) {
    ElMessage.warning(t('aiTrading.msgPickPaperAccount'))
    return
  }
  if (!dryRun.value && !selectedAccount.value.gateway_id) {
    ElMessage.warning(t('aiTrading.msgPickLiveGateway'))
    return
  }

  const input = message.value.trim()
  message.value = ''
  loading.value = true
  currentResponse.value = null

  try {
    const result = await executeTrade({
      message: input,
      gateway_id: dryRun.value ? undefined : selectedAccount.value.gateway_id ?? undefined,
      account_id: dryRun.value ? selectedAccount.value.account_id : undefined,
      dry_run: dryRun.value,
      auto_confirm: autoConfirm.value,
    })
    currentResponse.value = result
    responses.value.unshift(result)

    if (result.requires_confirmation) {
      await handleConfirmDialog(result)
    }
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : t('aiTrading.msgRequestFailed')
    ElMessage.error(`${t('aiTrading.msgTradeRequestFailed')}: ${msg}`)
  } finally {
    loading.value = false
  }
}

async function handleConfirmDialog(response: AITradingResponse) {
  try {
    await ElMessageBox.confirm(
      response.message,
      t('aiTrading.confirmTitle'),
      {
        confirmButtonText: t('aiTrading.confirmExecute'),
        cancelButtonText: t('aiTrading.btnCancel'),
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
    ElMessage.info(t('aiTrading.msgTradeCancelled'))
  }
}

async function loadConfig() {
  try {
    config.value = await getTradingConfig()
    selectDefaultAccountForMode()
  } catch {
    // Config load failure is non-critical
  }
}

function selectDefaultAccountForMode() {
  const firstAccount = selectableAccounts.value[0]
  selectedAccountId.value = firstAccount?.account_id ?? ''
}

function formatAccountNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '--'
  }
  return value.toFixed(2)
}

function accountOptionLabel(account: AITradingAccountOption): string {
  const parts = [account.name || account.account_id]
  if (account.exchange_type && !parts[0].includes(account.exchange_type)) {
    parts.push(account.exchange_type)
  }
  parts.push(`${t('aiTrading.accountTotalEquity')} ${formatAccountNumber(account.total_equity)}`)
  if (account.source === 'gateway' && account.connected === false) {
    parts.push(t('aiTrading.notConnectedSuffix').trim())
  }
  return parts.filter(Boolean).join(' · ')
}

function applyQuickCommand(command: string) {
  message.value = command
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
    filled: t('aiTrading.statusFilled'),
    confirmed: t('aiTrading.statusConfirmed'),
    pending_confirmation: t('aiTrading.statusPendingConfirm'),
    rejected: t('aiTrading.statusRejected'),
    cancelled: t('aiTrading.statusCancelled'),
    failed: t('aiTrading.statusFailed'),
    executing: t('aiTrading.statusExecuting'),
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
    buy: t('aiTrading.actionBuy'),
    sell: t('aiTrading.actionSell'),
    close: t('aiTrading.actionClose'),
    cancel: t('aiTrading.actionCancel'),
    query: t('aiTrading.actionQuery'),
    modify: t('aiTrading.actionModify'),
  }
  return labels[action] || action
}

watch(dryRun, () => {
  selectDefaultAccountForMode()
})

// Lifecycle
onMounted(async () => {
  await Promise.all([loadConfig(), loadHistory()])
})
</script>

<template>
  <div class="ai-trading-page">
    <section
      class="trading-hero"
      data-test="ai-trading-hero"
    >
      <div class="trading-hero-copy">
        <span class="eyebrow">
          {{ t('aiTrading.heroKicker') }}
        </span>
        <h1>{{ t('aiTrading.title') }}</h1>
        <p>{{ t('aiTrading.desc') }}</p>
      </div>

      <div class="hero-controls">
        <div class="mode-control">
          <span class="control-label">{{ t('aiTrading.executionMode') }}</span>
          <div
            class="mode-segment"
            role="group"
            :aria-label="t('aiTrading.executionMode')"
          >
            <button
              type="button"
              :class="{ active: dryRun }"
              @click="dryRun = true"
            >
              {{ t('aiTrading.modePaper') }}
            </button>
            <button
              type="button"
              :class="{ active: !dryRun }"
              @click="dryRun = false"
            >
              {{ t('aiTrading.modeLive') }}
            </button>
          </div>
          <span class="mode-helper">{{ modeHelper }}</span>
        </div>

        <label class="auto-confirm-toggle">
          <input
            v-model="autoConfirm"
            type="checkbox"
          >
          <span>{{ t('aiTrading.autoConfirm') }}</span>
        </label>
      </div>
    </section>

    <section
      class="command-overview"
      data-test="ai-trading-overview"
      :aria-label="t('aiTrading.overviewLabel')"
    >
      <article
        v-for="stat in commandStats"
        :key="stat.key"
        class="command-stat-card"
        :class="`is-${stat.tone}`"
      >
        <span class="command-stat-icon">
          <el-icon aria-hidden="true">
            <component :is="stat.icon" />
          </el-icon>
        </span>
        <span class="command-stat-copy">
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
          <em>{{ stat.helper }}</em>
        </span>
      </article>
    </section>

    <div class="trading-grid">
      <main class="trading-main">
        <section
          class="command-console"
          data-test="ai-trading-console"
        >
          <header class="section-header">
            <div>
              <span>{{ t('aiTrading.consoleKicker') }}</span>
              <h2>{{ t('aiTrading.consoleTitle') }}</h2>
            </div>
            <span
              class="mode-pill"
              :class="modeClass"
            >
              {{ modeLabel }}
            </span>
          </header>

          <div class="context-row">
            <label class="context-field">
              <span>{{ t('aiTrading.fieldPaperAccount') }}</span>
              <select
                v-model="selectedAccountId"
                :disabled="loading || selectableAccounts.length === 0"
              >
                <option value="">
                  {{ dryRun ? t('aiTrading.pickPaperAccount') : t('aiTrading.pickLiveGateway') }}
                </option>
                <option
                  v-for="account in selectableAccounts"
                  :key="account.account_id"
                  :value="account.account_id"
                >
                  {{ accountOptionLabel(account) }}
                </option>
              </select>
            </label>
            <span
              class="account-summary"
              :class="{ muted: !selectedAccount }"
            >
              {{ selectedAccountSummary }}
            </span>
          </div>

          <p
            v-if="dryRun && selectableAccounts.length === 0"
            class="context-hint"
          >
            {{ t('aiTrading.hintNoPaperAccount') }}
          </p>
          <p
            v-else-if="!dryRun && selectableAccounts.length === 0"
            class="context-hint"
          >
            {{ t('aiTrading.hintNoLiveGateway') }}
          </p>

          <div class="quick-command-row">
            <button
              v-for="command in quickCommands"
              :key="command"
              type="button"
              @click="applyQuickCommand(command)"
            >
              {{ command }}
            </button>
          </div>

          <div class="input-row">
            <textarea
              v-model="message"
              :disabled="loading"
              :placeholder="t('aiTrading.inputPlaceholder')"
              :maxlength="500"
              @keydown.enter.exact.prevent="handleSend"
            />
          </div>

          <footer class="command-footer">
            <span>{{ t('aiTrading.inputHints') }}</span>
            <button
              class="send-btn"
              :disabled="!canSend"
              @click="handleSend"
            >
              <el-icon aria-hidden="true">
                <Promotion />
              </el-icon>
              {{ loading ? t('aiTrading.btnSending') : t('aiTrading.btnSend') }}
            </button>
          </footer>
        </section>

        <section
          v-if="currentResponse"
          class="response-card"
          data-test="ai-trading-response"
        >
          <header class="response-header">
            <div>
              <span>{{ t('aiTrading.responseKicker') }}</span>
              <h2>{{ t('aiTrading.responseTitle') }}</h2>
            </div>
            <span
              class="status-badge"
              :style="{ backgroundColor: getStatusColor(currentResponse.status) }"
            >
              {{ getStatusLabel(currentResponse.status) }}
            </span>
          </header>

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
              >{{ t('aiTrading.marketTag') }}</span>
            </div>
            <div class="intent-meta">
              <span
                class="confidence-badge"
                :style="{ color: currentResponse.intent.confidence > 0.7 ? 'var(--success-color)' : 'var(--warning-color)' }"
              >
                {{ t('aiTrading.confidenceLabel') }}: {{ (currentResponse.intent.confidence * 100).toFixed(0) }}%
              </span>
              <span
                class="risk-badge"
                :style="{ color: getRiskColor(currentResponse.risk_assessment.risk_level) }"
              >
                {{ t('aiTrading.riskLabel') }}: {{ currentResponse.risk_assessment.risk_level }}
              </span>
              <span class="trade-id">{{ currentResponse.trade_id }}</span>
            </div>
          </div>

          <div
            v-if="currentResponse.degraded || currentResponse.diagnostic_message"
            class="diagnostic-box"
          >
            <el-icon aria-hidden="true">
              <Warning />
            </el-icon>
            <span>{{ currentResponse.diagnostic_message || t('aiTrading.diagnosticDefault') }}</span>
          </div>
          <div class="response-message">
            {{ currentResponse.message }}
          </div>

          <div
            v-if="currentResponse.risk_assessment.warnings.length"
            class="warnings-box"
          >
            <div
              v-for="(w, i) in currentResponse.risk_assessment.warnings"
              :key="i"
              class="warning-item"
            >
              <el-icon aria-hidden="true">
                <Warning />
              </el-icon>
              <span>{{ w }}</span>
            </div>
          </div>

          <div
            v-if="currentResponse.suggestions.length"
            class="suggestions-box"
          >
            <div class="suggestions-title">
              {{ t('aiTrading.suggestionsTitle') }}
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

          <div
            v-if="currentResponse.ai_reasoning"
            class="reasoning-box"
          >
            <div class="reasoning-title">
              {{ t('aiTrading.aiAnalysis') }}
            </div>
            <p>{{ currentResponse.ai_reasoning }}</p>
          </div>
        </section>

        <section
          v-else
          class="response-empty"
          data-test="ai-trading-empty"
        >
          <span class="empty-icon">
            <el-icon aria-hidden="true">
              <CircleCheck />
            </el-icon>
          </span>
          <div>
            <h2>{{ t('aiTrading.emptyResponseTitle') }}</h2>
            <p>{{ t('aiTrading.emptyResponseDesc') }}</p>
          </div>
        </section>

        <section
          v-if="responses.length > 1"
          class="response-history"
        >
          <h3>{{ t('aiTrading.historyHeading') }}</h3>
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
        </section>
      </main>

      <aside class="history-panel">
        <div class="panel-header">
          <div>
            <span>{{ t('aiTrading.sideKicker') }}</span>
            <h2>{{ t('aiTrading.panelHeading') }}</h2>
          </div>
          <span class="record-count">{{ history.length }} {{ t('aiTrading.recordCountSuffix') }}</span>
        </div>

        <div class="guardrail-panel">
          <span class="guardrail-kicker">{{ t('aiTrading.guardrailTitle') }}</span>
          <div class="guardrail-row">
            <span>{{ t('aiTrading.guardrailMaxTrade') }}</span>
            <strong>{{ maxSingleTradeAmount }}</strong>
          </div>
          <div class="guardrail-row">
            <span>{{ t('aiTrading.guardrailConfirm') }}</span>
            <strong>{{ riskThreshold }}</strong>
          </div>
        </div>

        <div
          v-if="history.length === 0"
          class="empty-state"
        >
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <p>{{ t('aiTrading.emptyState') }}</p>
        </div>
        <div
          v-else
          class="history-list"
        >
          <article
            v-for="item in history"
            :key="item.trade_id"
            class="history-card"
          >
            <header class="history-card-header">
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
            </header>
            <p class="history-card-input">
              {{ item.user_input }}
            </p>
            <div class="history-card-meta">
              <span v-if="item.quantity">{{ t('aiTrading.quantityLabel') }}: {{ item.quantity }}</span>
              <span
                v-if="item.dry_run"
                class="paper-tag"
              >{{ t('aiTrading.paperTag') }}</span>
              <span class="history-card-time">{{ item.created_at?.slice(0, 16) }}</span>
            </div>
          </article>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped src="./AITradingPage.styles.css"></style>
