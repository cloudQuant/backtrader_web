<template>
  <section class="paper-runtime-page">
    <header class="page-header">
      <div>
        <h1>{{ t('paperTradingDetail.title') }}</h1>
        <p>{{ t('paperTradingDetail.subtitle') }}</p>
      </div>
      <el-button @click="load">{{ t('paperTradingDetail.refresh') }}</el-button>
    </header>

    <div v-if="loading" class="page-state" role="status">{{ t('paperTradingDetail.loading') }}</div>
    <el-result v-else-if="error" icon="error" :title="t('paperTradingDetail.loadFailed')" :sub-title="error">
      <template #extra><el-button type="primary" @click="load">{{ t('paperTradingDetail.retry') }}</el-button></template>
    </el-result>

    <template v-else-if="runtime">
      <el-card class="runtime-overview">
        <template #header>
          <div class="card-header">
            <strong>{{ runtime.unit_name }} · {{ runtime.symbol }}</strong>
            <el-tag :type="runtime.paused ? 'warning' : 'success'">
              {{ runtime.paused ? t('paperTradingDetail.paused') : runtime.status }}
            </el-tag>
          </div>
        </template>
        <dl class="overview-grid">
          <div><dt>{{ t('paperTradingDetail.workspace') }}</dt><dd>{{ runtime.workspace_name }}</dd></div>
          <div><dt>{{ t('paperTradingDetail.currentEquity') }}</dt><dd>{{ formatCurrency(runtime.latest_equity?.total_equity) }}</dd></div>
          <div><dt>{{ t('paperTradingDetail.availableCash') }}</dt><dd>{{ formatCurrency(runtime.latest_equity?.cash) }}</dd></div>
          <div><dt>{{ t('paperTradingDetail.runtimeInstance') }}</dt><dd class="monospace">{{ runtime.instance_id }}</dd></div>
        </dl>
        <el-button :disabled="runtime.paused" type="warning" @click="pauseRuntime">{{ t('paperTradingDetail.pauseRuntime') }}</el-button>
      </el-card>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="14">
          <el-card>
            <template #header><strong>{{ t('paperTradingDetail.equityCurve') }}</strong></template>
            <div v-if="equityLoading" class="page-state">{{ t('paperTradingDetail.loading') }}</div>
            <el-empty v-else-if="!equity.length" :description="t('paperTradingDetail.noEquitySnapshots')" />
            <el-table v-else :data="equity" size="small" max-height="360">
              <el-table-column prop="observed_at" :label="t('paperTradingDetail.time')" min-width="170" />
              <el-table-column :label="t('paperTradingDetail.equity')" min-width="120"><template #default="{ row }">{{ formatCurrency(row.total_equity) }}</template></el-table-column>
              <el-table-column :label="t('paperTradingDetail.cash')" min-width="120"><template #default="{ row }">{{ formatCurrency(row.cash) }}</template></el-table-column>
              <el-table-column prop="source" :label="t('paperTradingDetail.source')" min-width="120" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="10">
          <el-card>
            <template #header><strong>{{ t('paperTradingDetail.reviewDecision') }}</strong></template>
            <p class="hint">{{ t('paperTradingDetail.reviewNote') }}</p>
            <div class="decision-actions">
              <el-button type="success" @click="decide('approved')">{{ t('paperTradingDetail.approve') }}</el-button>
              <el-button type="danger" @click="decide('rejected')">{{ t('paperTradingDetail.reject') }}</el-button>
              <el-button type="warning" @click="decide('requested_changes')">{{ t('paperTradingDetail.requestChanges') }}</el-button>
            </div>
          </el-card>
          <el-card class="rules-card">
            <template #header><strong>{{ t('paperTradingDetail.activeRiskRules') }}</strong></template>
            <div v-if="rulesLoading" class="page-state">{{ t('paperTradingDetail.loading') }}</div>
            <el-empty v-else-if="!rules.length" :description="t('paperTradingDetail.noRules')" />
            <ul v-else class="rule-list"><li v-for="rule in rules" :key="rule.id">{{ rule.name }} · {{ rule.rule_type }}</li></ul>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>{{ t('paperTradingDetail.currentPositions') }}</strong></template>
            <el-empty v-if="!runtime.positions.length" :description="t('paperTradingDetail.noPositions')" />
            <el-table v-else :data="runtime.positions" size="small" max-height="280">
              <el-table-column prop="data_name" :label="t('paperTradingDetail.symbol')" min-width="120" />
              <el-table-column prop="direction" :label="t('paperTradingDetail.direction')" width="90" />
              <el-table-column prop="size" :label="t('paperTradingDetail.quantity')" width="100" />
              <el-table-column prop="market_value" :label="t('paperTradingDetail.marketValue')" min-width="120" />
              <el-table-column prop="pnl" :label="t('paperTradingDetail.unrealizedPnl')" min-width="120" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>{{ t('paperTradingDetail.orders') }}</strong></template>
            <el-empty v-if="!runtime.orders.length" :description="t('paperTradingDetail.noOrders')" />
            <el-table v-else :data="runtime.orders" size="small" max-height="280">
              <el-table-column prop="symbol" :label="t('paperTradingDetail.symbol')" min-width="120" />
              <el-table-column prop="side" :label="t('paperTradingDetail.direction')" width="90" />
              <el-table-column prop="status" :label="t('paperTradingDetail.status')" width="100" />
              <el-table-column prop="size" :label="t('paperTradingDetail.quantity')" width="100" />
              <el-table-column prop="price" :label="t('paperTradingDetail.price')" min-width="100" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>{{ t('paperTradingDetail.trades') }}</strong></template>
            <el-empty v-if="!runtime.trades.length" :description="t('paperTradingDetail.noTrades')" />
            <el-table v-else :data="runtime.trades" size="small" max-height="280">
              <el-table-column prop="dtclose" :label="t('paperTradingDetail.time')" min-width="150" />
              <el-table-column prop="data_name" :label="t('paperTradingDetail.symbol')" min-width="110" />
              <el-table-column prop="direction" :label="t('paperTradingDetail.direction')" width="90" />
              <el-table-column prop="pnlcomm" :label="t('paperTradingDetail.netPnl')" min-width="120" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>{{ t('paperTradingDetail.strategySignals') }}</strong></template>
            <el-empty v-if="!runtime.signals.length" :description="t('paperTradingDetail.noSignals')" />
            <el-table v-else :data="runtime.signals" size="small" max-height="280">
              <el-table-column prop="datetime" :label="t('paperTradingDetail.time')" min-width="150" />
              <el-table-column prop="symbol" :label="t('paperTradingDetail.symbol')" min-width="110" />
              <el-table-column prop="signal" :label="t('paperTradingDetail.signal')" min-width="120" />
              <el-table-column prop="price" :label="t('paperTradingDetail.price')" min-width="100" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="alerts-card">
        <template #header><strong>{{ t('paperTradingDetail.runtimeAlerts') }}</strong></template>
        <div v-if="alertsLoading" class="page-state">{{ t('paperTradingDetail.loading') }}</div>
        <el-empty v-else-if="!alerts.length" :description="t('paperTradingDetail.noAlerts')" />
        <el-table v-else :data="alerts" size="small">
          <el-table-column prop="created_at" :label="t('paperTradingDetail.time')" min-width="170" />
          <el-table-column prop="severity" :label="t('paperTradingDetail.severity')" width="100" />
          <el-table-column prop="title" :label="t('paperTradingDetail.alertTitle')" min-width="150" />
          <el-table-column prop="message" :label="t('paperTradingDetail.content')" min-width="260" />
        </el-table>
      </el-card>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  paperRuntimeApi,
  type PaperEquityPoint,
  type PaperRuntimeAlert,
  type PaperRuntimeDetail,
  type RiskRule,
} from '@/api/paperRuntime'
import { getErrorMessage } from '@/api'

const route = useRoute()
const { t } = useI18n()
const instanceId = computed(() => String(route.params.instanceId || ''))
const loading = ref(true)
const error = ref('')
const equityLoading = ref(false)
const alertsLoading = ref(false)
const rulesLoading = ref(false)
const runtime = ref<PaperRuntimeDetail | null>(null)
const equity = ref<PaperEquityPoint[]>([])
const alerts = ref<PaperRuntimeAlert[]>([])
const rules = ref<RiskRule[]>([])

onMounted(load)
watch(instanceId, load)

async function load() {
  if (!instanceId.value) return
  loading.value = true
  error.value = ''
  try {
    runtime.value = await paperRuntimeApi.get(instanceId.value)
    void loadSecondary()
  } catch (reason) {
    error.value = getErrorMessage(reason, t('paperTradingDetail.loadRuntimeFailed'))
  } finally {
    loading.value = false
  }
}

async function loadSecondary() {
  equityLoading.value = true
  alertsLoading.value = true
  rulesLoading.value = true
  const [curve, runtimeAlerts, runtimeRules] = await Promise.allSettled([
    paperRuntimeApi.getEquity(instanceId.value),
    paperRuntimeApi.getAlerts(instanceId.value),
    paperRuntimeApi.listRules(instanceId.value),
  ])
  if (curve.status === 'fulfilled') equity.value = curve.value.points
  if (runtimeAlerts.status === 'fulfilled') alerts.value = runtimeAlerts.value
  if (runtimeRules.status === 'fulfilled') rules.value = runtimeRules.value
  equityLoading.value = false
  alertsLoading.value = false
  rulesLoading.value = false
}

async function pauseRuntime() {
  try {
    await ElMessageBox.confirm(
      t('paperTradingDetail.pauseConfirmMessage'),
      t('paperTradingDetail.pauseConfirmTitle'),
      { type: 'warning' }
    )
    await paperRuntimeApi.pause(instanceId.value)
    if (runtime.value) runtime.value.paused = true
    ElMessage.success(t('paperTradingDetail.pauseSuccess'))
  } catch (reason) {
    if (reason !== 'cancel') ElMessage.error(getErrorMessage(reason, t('paperTradingDetail.pauseFailed')))
  }
}

async function decide(decision: 'approved' | 'rejected' | 'requested_changes') {
  try {
    const result = await ElMessageBox.prompt(
      t('paperTradingDetail.reviewPromptMessage'),
      t('paperTradingDetail.reviewPromptTitle'),
      { inputPlaceholder: t('paperTradingDetail.reviewPromptPlaceholder') }
    )
    await paperRuntimeApi.decideHandoff(instanceId.value, { decision, rationale: result.value || undefined })
    ElMessage.success(t('paperTradingDetail.reviewSuccess'))
  } catch (reason) {
    if (reason !== 'cancel') ElMessage.error(getErrorMessage(reason, t('paperTradingDetail.reviewFailed')))
  }
}

function formatCurrency(value?: number) {
  return value === undefined || value === null ? '—' : value.toLocaleString('zh-CN', { style: 'currency', currency: 'CNY' })
}
</script>

<style scoped>
.paper-runtime-page { display: grid; gap: 16px; }
.page-header, .card-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-header h1 { margin: 0; }.page-header p, .hint { color: var(--el-text-color-secondary); margin: 6px 0 0; }
.page-state { padding: 32px; text-align: center; color: var(--el-text-color-secondary); }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 0 0 18px; }
.overview-grid dt { color: var(--el-text-color-secondary); font-size: 13px; }.overview-grid dd { margin: 4px 0 0; font-weight: 600; }
.monospace { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
.rules-card, .alerts-card { margin-top: 16px; }.rule-list { margin: 0; padding-left: 18px; }.decision-actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
