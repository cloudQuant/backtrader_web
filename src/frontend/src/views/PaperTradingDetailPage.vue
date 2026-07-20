<template>
  <section class="paper-runtime-page">
    <header class="page-header">
      <div>
        <h1>模拟交易详情</h1>
        <p>以策略运行实例为边界查看权益、告警、风控与审核状态。</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>

    <div v-if="loading" class="page-state" role="status">查询中…</div>
    <el-result v-else-if="error" icon="error" title="加载失败" :sub-title="error">
      <template #extra><el-button type="primary" @click="load">重试</el-button></template>
    </el-result>

    <template v-else-if="runtime">
      <el-card class="runtime-overview">
        <template #header>
          <div class="card-header">
            <strong>{{ runtime.unit_name }} · {{ runtime.symbol }}</strong>
            <el-tag :type="runtime.paused ? 'warning' : 'success'">
              {{ runtime.paused ? '已暂停' : runtime.status }}
            </el-tag>
          </div>
        </template>
        <dl class="overview-grid">
          <div><dt>工作区</dt><dd>{{ runtime.workspace_name }}</dd></div>
          <div><dt>当前权益</dt><dd>{{ formatCurrency(runtime.latest_equity?.total_equity) }}</dd></div>
          <div><dt>可用资金</dt><dd>{{ formatCurrency(runtime.latest_equity?.cash) }}</dd></div>
          <div><dt>运行实例</dt><dd class="monospace">{{ runtime.instance_id }}</dd></div>
        </dl>
        <el-button :disabled="runtime.paused" type="warning" @click="pauseRuntime">暂停运行</el-button>
      </el-card>

      <el-row :gutter="16">
        <el-col :xs="24" :lg="14">
          <el-card>
            <template #header><strong>资金曲线</strong></template>
            <div v-if="equityLoading" class="page-state">查询中…</div>
            <el-empty v-else-if="!equity.length" description="尚无资金快照" />
            <el-table v-else :data="equity" size="small" max-height="360">
              <el-table-column prop="observed_at" label="时间" min-width="170" />
              <el-table-column label="权益" min-width="120"><template #default="{ row }">{{ formatCurrency(row.total_equity) }}</template></el-table-column>
              <el-table-column label="现金" min-width="120"><template #default="{ row }">{{ formatCurrency(row.cash) }}</template></el-table-column>
              <el-table-column prop="source" label="来源" min-width="120" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="10">
          <el-card>
            <template #header><strong>审核决策</strong></template>
            <p class="hint">审核结果会持久化，`requested_changes` 不会解除实盘锁定。</p>
            <div class="decision-actions">
              <el-button type="success" @click="decide('approved')">批准</el-button>
              <el-button type="danger" @click="decide('rejected')">拒绝</el-button>
              <el-button type="warning" @click="decide('requested_changes')">请求修改</el-button>
            </div>
          </el-card>
          <el-card class="rules-card">
            <template #header><strong>生效风控规则</strong></template>
            <div v-if="rulesLoading" class="page-state">查询中…</div>
            <el-empty v-else-if="!rules.length" description="暂无规则" />
            <ul v-else class="rule-list"><li v-for="rule in rules" :key="rule.id">{{ rule.name }} · {{ rule.rule_type }}</li></ul>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>当前持仓</strong></template>
            <el-empty v-if="!runtime.positions.length" description="当前无持仓" />
            <el-table v-else :data="runtime.positions" size="small" max-height="280">
              <el-table-column prop="data_name" label="标的" min-width="120" />
              <el-table-column prop="direction" label="方向" width="90" />
              <el-table-column prop="size" label="数量" width="100" />
              <el-table-column prop="market_value" label="市值" min-width="120" />
              <el-table-column prop="pnl" label="浮动盈亏" min-width="120" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>订单</strong></template>
            <el-empty v-if="!runtime.orders.length" description="暂无订单" />
            <el-table v-else :data="runtime.orders" size="small" max-height="280">
              <el-table-column prop="symbol" label="标的" min-width="120" />
              <el-table-column prop="side" label="方向" width="90" />
              <el-table-column prop="status" label="状态" width="100" />
              <el-table-column prop="size" label="数量" width="100" />
              <el-table-column prop="price" label="价格" min-width="100" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>成交记录</strong></template>
            <el-empty v-if="!runtime.trades.length" description="暂无成交" />
            <el-table v-else :data="runtime.trades" size="small" max-height="280">
              <el-table-column prop="dtclose" label="时间" min-width="150" />
              <el-table-column prop="data_name" label="标的" min-width="110" />
              <el-table-column prop="direction" label="方向" width="90" />
              <el-table-column prop="pnlcomm" label="净盈亏" min-width="120" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :xl="12">
          <el-card>
            <template #header><strong>策略信号</strong></template>
            <el-empty v-if="!runtime.signals.length" description="暂无可展示信号" />
            <el-table v-else :data="runtime.signals" size="small" max-height="280">
              <el-table-column prop="datetime" label="时间" min-width="150" />
              <el-table-column prop="symbol" label="标的" min-width="110" />
              <el-table-column prop="signal" label="信号" min-width="120" />
              <el-table-column prop="price" label="价格" min-width="100" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="alerts-card">
        <template #header><strong>运行告警</strong></template>
        <div v-if="alertsLoading" class="page-state">查询中…</div>
        <el-empty v-else-if="!alerts.length" description="暂无告警" />
        <el-table v-else :data="alerts" size="small">
          <el-table-column prop="created_at" label="时间" min-width="170" />
          <el-table-column prop="severity" label="级别" width="100" />
          <el-table-column prop="title" label="标题" min-width="150" />
          <el-table-column prop="message" label="内容" min-width="260" />
        </el-table>
      </el-card>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  paperRuntimeApi,
  type PaperEquityPoint,
  type PaperRuntimeAlert,
  type PaperRuntimeDetail,
  type RiskRule,
} from '@/api/paperRuntime'
import { getErrorMessage } from '@/api'

const route = useRoute()
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
    error.value = getErrorMessage(reason, '无法加载模拟交易运行实例')
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
    await ElMessageBox.confirm('暂停后运行器会停止接受新指令。确认暂停？', '确认暂停', { type: 'warning' })
    await paperRuntimeApi.pause(instanceId.value)
    if (runtime.value) runtime.value.paused = true
    ElMessage.success('已暂停模拟运行实例')
  } catch (reason) {
    if (reason !== 'cancel') ElMessage.error(getErrorMessage(reason, '暂停失败'))
  }
}

async function decide(decision: 'approved' | 'rejected' | 'requested_changes') {
  try {
    const result = await ElMessageBox.prompt('请输入审核说明（可选）', '审核决策', { inputPlaceholder: '审核依据' })
    await paperRuntimeApi.decideHandoff(instanceId.value, { decision, rationale: result.value || undefined })
    ElMessage.success('审核决策已保存')
  } catch (reason) {
    if (reason !== 'cancel') ElMessage.error(getErrorMessage(reason, '保存审核决策失败'))
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
