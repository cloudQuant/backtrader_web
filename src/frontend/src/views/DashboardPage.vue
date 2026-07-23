<template>
  <section
    class="dashboard-page"
    aria-labelledby="dashboard-overview-title"
  >
    <header class="dashboard-overview">
      <div class="dashboard-heading">
        <p class="dashboard-kicker">
          {{ t('dashboard.overviewKicker') }}
        </p>
        <h2 id="dashboard-overview-title">
          {{ t('dashboard.overviewTitle') }}
        </h2>
        <p>
          {{ t('dashboard.overviewSubtitle') }}
        </p>
      </div>

      <div
        class="dashboard-health"
        :aria-label="t('dashboard.operationalHealth')"
      >
        <div
          v-for="item in statusOverview"
          :key="item.id"
          class="dashboard-health-item"
          :class="`dashboard-health-item--${item.tone}`"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </header>

    <div class="dashboard-stat-grid">
      <article
        v-for="card in statCards"
        :key="card.id"
        class="dashboard-stat-card"
      >
        <div class="dashboard-stat-top">
          <span
            class="dashboard-stat-icon"
            :class="`dashboard-stat-icon--${card.tone}`"
          >
            <el-icon aria-hidden="true">
              <component :is="card.icon" />
            </el-icon>
          </span>
          <span class="dashboard-stat-meta">{{ card.meta }}</span>
        </div>
        <p class="dashboard-stat-label">
          {{ card.label }}
        </p>
        <strong
          class="dashboard-stat-value"
          :class="card.valueClass"
        >
          {{ card.value }}
        </strong>
      </article>
    </div>

    <el-card
      shadow="never"
      class="dashboard-panel"
    >
      <template #header>
        <div class="dashboard-panel-header">
          <div>
            <h3>{{ t('dashboard.quickStart') }}</h3>
            <p>{{ t('dashboard.quickStartDesc') }}</p>
          </div>
        </div>
      </template>

      <div class="dashboard-actions-grid">
        <button
          v-for="action in quickActions"
          :key="action.id"
          type="button"
          class="dashboard-action-card"
          :class="[
            `dashboard-action-card--${action.tone}`,
            `dashboard-action-card--priority-${action.priority}`,
          ]"
          :aria-label="action.title"
          @click="navigateTo(action.to)"
        >
          <span class="dashboard-action-icon">
            <el-icon aria-hidden="true">
              <component :is="action.icon" />
            </el-icon>
          </span>
          <span class="dashboard-action-copy">
            <strong>{{ action.title }}</strong>
            <span>{{ action.description }}</span>
          </span>
          <el-icon
            class="dashboard-action-arrow"
            aria-hidden="true"
          >
            <ArrowRight />
          </el-icon>
        </button>
      </div>
    </el-card>

    <el-card
      shadow="never"
      class="dashboard-panel"
    >
      <template #header>
        <div class="dashboard-panel-header dashboard-panel-header--split">
          <div>
            <h3>{{ t('dashboard.recentBacktests') }}</h3>
            <p>{{ t('dashboard.recentBacktestsDesc') }}</p>
          </div>
          <el-button
            type="primary"
            link
            @click="navigateTo('/research/workspaces')"
          >
            {{ t('dashboard.viewAll') }}
          </el-button>
        </div>
      </template>

      <div
        v-if="recentBacktests.length > 0"
        class="dashboard-table-scroll"
      >
        <el-table
          :data="recentBacktests"
          stripe
          size="small"
          class="dashboard-backtest-table"
        >
          <el-table-column
            :label="t('dashboard.strategy')"
            min-width="180"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ getStrategyName(row.strategy_id) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="symbol"
            :label="t('dashboard.symbol')"
            min-width="110"
          />
          <el-table-column
            :label="t('dashboard.returnRate')"
            min-width="120"
          >
            <template #default="{ row }">
              <span
                class="dashboard-table-number"
                :class="metricToneClass(row.total_return)"
              >
                {{ formatPercent(row.total_return) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dashboard.sharpeRatio')"
            min-width="120"
          >
            <template #default="{ row }">
              {{ formatNumber(row.sharpe_ratio) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dashboard.maxDrawdown')"
            min-width="130"
          >
            <template #default="{ row }">
              <span class="dashboard-table-number dashboard-number--danger">
                {{ formatPercent(row.max_drawdown) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('common.status')"
            min-width="120"
          >
            <template #default="{ row }">
              <el-tag
                :type="getStatusType(row.status)"
                size="small"
              >
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dashboard.createdAt')"
            min-width="160"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-empty
        v-else
        class="dashboard-empty"
        :description="t('dashboard.emptyBacktests')"
      >
        <el-button
          type="primary"
          @click="navigateTo('/research/workspaces')"
        >
          {{ t('dashboard.runBacktest') }}
        </el-button>
      </el-empty>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, ref, type Component } from 'vue'
import {
  ArrowRight,
  DataLine,
  Document,
  Grid,
  TrendCharts,
  Trophy,
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBacktestStore } from '@/stores/backtest'
import { useStrategyStore } from '@/stores/strategy'
import type { TagType } from '@/constants/strategy'
import type { BacktestResult, TaskStatus } from '@/types'

const { t } = useI18n()
const router = useRouter()

const backtestStore = useBacktestStore()
const strategyStore = useStrategyStore()

const stats = ref({
  backtestCount: 0,
  strategyCount: 0,
  avgReturn: 0,
  bestSharpe: 0,
})

const recentBacktests = ref<BacktestResult[]>([])

type DashboardTone = 'primary' | 'success' | 'warning' | 'danger'

interface DashboardStatCard {
  id: string
  label: string
  value: string
  meta: string
  icon: Component
  tone: DashboardTone
  valueClass?: string
}

interface DashboardAction {
  id: string
  title: string
  description: string
  to: string
  icon: Component
  tone: DashboardTone
  priority: 'primary' | 'secondary'
}

const dashboardIcons = {
  backtests: markRaw(DataLine),
  strategies: markRaw(Document),
  returns: markRaw(TrendCharts),
  sharpe: markRaw(Trophy),
  data: markRaw(Grid),
}

const statCards = computed<DashboardStatCard[]>(() => [
  {
    id: 'backtests',
    label: t('dashboard.backtestCount'),
    value: String(stats.value.backtestCount),
    meta: t('dashboard.totalBacktests'),
    icon: dashboardIcons.backtests,
    tone: 'primary',
  },
  {
    id: 'strategies',
    label: t('dashboard.strategyCount'),
    value: String(stats.value.strategyCount),
    meta: t('dashboard.strategyLibrary'),
    icon: dashboardIcons.strategies,
    tone: 'success',
  },
  {
    id: 'avg-return',
    label: t('dashboard.avgReturn'),
    value: formatPercent(stats.value.avgReturn),
    meta: t('dashboard.recentSample'),
    icon: dashboardIcons.returns,
    tone: stats.value.avgReturn >= 0 ? 'success' : 'danger',
    valueClass: metricToneClass(stats.value.avgReturn),
  },
  {
    id: 'best-sharpe',
    label: t('dashboard.bestSharpe'),
    value: formatNumber(stats.value.bestSharpe),
    meta: t('dashboard.bestRecentRun'),
    icon: dashboardIcons.sharpe,
    tone: 'warning',
  },
])

const quickActions = computed<DashboardAction[]>(() => [
  {
    id: 'run-backtest',
    title: t('dashboard.runBacktest'),
    description: t('dashboard.runBacktestDesc'),
    to: '/research/workspaces',
    icon: dashboardIcons.backtests,
    tone: 'primary',
    priority: 'primary',
  },
  {
    id: 'create-strategy',
    title: t('dashboard.createStrategy'),
    description: t('dashboard.createStrategyDesc'),
    to: '/research/strategies',
    icon: dashboardIcons.strategies,
    tone: 'success',
    priority: 'secondary',
  },
  {
    id: 'query-data',
    title: t('dashboard.queryData'),
    description: t('dashboard.queryDataDesc'),
    to: '/data/market',
    icon: dashboardIcons.data,
    tone: 'warning',
    priority: 'secondary',
  },
])

const statusOverview = computed(() => {
  const completed = countBacktestsByStatus(['completed'])
  const active = countBacktestsByStatus(['pending', 'running'])
  const failed = countBacktestsByStatus(['failed', 'cancelled'])

  return [
    { id: 'completed', label: t('dashboard.completedRuns'), value: completed, tone: 'success' },
    { id: 'active', label: t('dashboard.activeRuns'), value: active, tone: 'warning' },
    { id: 'failed', label: t('dashboard.failedRuns'), value: failed, tone: 'danger' },
  ]
})

function normalizeNumber(value: number | null | undefined): number {
  return Number.isFinite(value) ? Number(value) : 0
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return normalizeNumber(value).toFixed(digits)
}

function formatPercent(value: number | null | undefined): string {
  return `${formatNumber(value)}%`
}

function metricToneClass(value: number | null | undefined): string {
  const normalized = normalizeNumber(value)
  if (normalized > 0) return 'dashboard-number--success'
  if (normalized < 0) return 'dashboard-number--danger'
  return ''
}

function formatDateTime(value: string | undefined): string {
  if (!value) return t('common.noData')
  return value.replace('T', ' ').replace(/\.\d+Z?$/, '').slice(0, 16)
}

function countBacktestsByStatus(statuses: TaskStatus[]): number {
  return recentBacktests.value.filter(item => statuses.includes(item.status)).length
}

function navigateTo(path: string): void {
  void router.push(path)
}

function getStatusType(status: string): TagType {
  const types: Record<string, TagType> = {
    completed: 'success',
    running: 'warning',
    pending: 'info',
    failed: 'danger',
    cancelled: 'warning',
  }
  return types[status] || 'info'
}

function getStatusText(status: string) {
  const texts: Record<string, string> = {
    completed: t('backtest.completed'),
    running: t('backtest.running'),
    pending: t('backtest.pending'),
    failed: t('backtest.failed'),
    cancelled: t('dashboard.cancelled'),
  }
  return texts[status] || status
}

function getStrategyName(id: string): string {
  const templates = Array.isArray(strategyStore.templates) ? strategyStore.templates : []
  const template = templates.find(item => item.id === id)
  if (template) return template.name
  return id
}

onMounted(async () => {
  await Promise.allSettled([
    backtestStore.fetchResults(100),
    strategyStore.fetchStrategies(100),
    strategyStore.fetchTemplates(),
  ])
  
  recentBacktests.value = backtestStore.results.slice(0, 5)
  
  stats.value.backtestCount = backtestStore.total
  stats.value.strategyCount = strategyStore.total
  
  const completedResults = backtestStore.results.filter(result => (
    result.status === 'completed'
    && Number.isFinite(result.total_return)
    && Number.isFinite(result.sharpe_ratio)
  ))

  if (completedResults.length > 0) {
    const returns = completedResults.map(result => normalizeNumber(result.total_return))
    const sharpes = completedResults.map(result => normalizeNumber(result.sharpe_ratio))
    stats.value.avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length
    stats.value.bestSharpe = Math.max(...sharpes)
  }
})
</script>

<style scoped lang="scss">
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  color: var(--text-color-primary);
}

.dashboard-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: end;
  padding: 24px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background:
    linear-gradient(135deg, var(--bg-color), var(--fill-color-lighter));
}

.dashboard-heading {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.dashboard-heading h2,
.dashboard-heading p {
  margin: 0;
}

.dashboard-heading h2 {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--text-color-primary);
}

.dashboard-heading p {
  max-width: 760px;
  color: var(--text-color-secondary);
  line-height: 1.6;
}

.dashboard-kicker {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--primary-color) !important;
  text-transform: uppercase;
}

.dashboard-health {
  display: grid;
  grid-template-columns: repeat(3, minmax(96px, 1fr));
  gap: 10px;
  min-width: 336px;
}

.dashboard-health-item {
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.dashboard-health-item span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.25;
}

.dashboard-health-item strong {
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1;
}

.dashboard-health-item--success {
  border-color: var(--success-border-color);
}

.dashboard-health-item--warning {
  border-color: var(--warning-border-color);
}

.dashboard-health-item--danger {
  border-color: var(--danger-border-color);
}

.dashboard-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.dashboard-stat-card {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 8px 24px var(--shadow-color);
}

.dashboard-stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dashboard-stat-icon,
.dashboard-action-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-light);
  color: var(--primary-color);
  font-size: 20px;
  flex: none;
}

.dashboard-stat-icon--success,
.dashboard-action-card--success .dashboard-action-icon {
  border-color: var(--success-border-color);
  background: var(--fill-color-light);
  color: var(--success-color);
}

.dashboard-stat-icon--warning,
.dashboard-action-card--warning .dashboard-action-icon {
  border-color: var(--warning-border-color);
  background: var(--fill-color-light);
  color: var(--warning-color);
}

.dashboard-stat-icon--danger,
.dashboard-action-card--danger .dashboard-action-icon {
  border-color: var(--danger-border-color);
  background: var(--fill-color-light);
  color: var(--danger-color);
}

.dashboard-stat-meta,
.dashboard-stat-label,
.dashboard-panel-header p,
.dashboard-action-copy span {
  color: var(--text-color-secondary);
}

.dashboard-stat-meta {
  overflow: hidden;
  font-size: 12px;
  line-height: 1.25;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-stat-label {
  margin: 0;
  font-size: 13px;
  line-height: 1.4;
}

.dashboard-stat-value {
  overflow-wrap: anywhere;
  color: var(--text-color-primary);
  font-size: 30px;
  font-weight: 750;
  line-height: 1;
}

.dashboard-number--success {
  color: var(--success-text-strong);
}

.dashboard-number--danger {
  color: var(--danger-text-color);
}

.dashboard-panel {
  border-color: var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.dashboard-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom-color: var(--border-color-light);
}

.dashboard-panel :deep(.el-card__body) {
  padding: 18px;
}

.dashboard-panel-header {
  display: flex;
  gap: 16px;
  align-items: center;
  min-width: 0;
}

.dashboard-panel-header--split {
  justify-content: space-between;
}

.dashboard-panel-header h3,
.dashboard-panel-header p {
  margin: 0;
}

.dashboard-panel-header h3 {
  color: var(--text-color-primary);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
}

.dashboard-panel-header p {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.5;
}

.dashboard-actions-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.dashboard-action-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    transform 0.18s ease;
}

.dashboard-action-card:hover {
  border-color: color-mix(in srgb, var(--primary-color) 42%, var(--border-color) 58%);
  background: var(--fill-color-light);
  transform: translateY(-1px);
}

.dashboard-action-card--priority-primary {
  border-color: color-mix(in srgb, var(--primary-color) 52%, var(--border-color) 48%);
  background: color-mix(in srgb, var(--bg-color) 86%, var(--primary-color) 14%);
}

.dashboard-action-card--priority-primary:hover {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--bg-color) 78%, var(--primary-color) 22%);
}

.dashboard-action-card:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.dashboard-action-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.dashboard-action-copy strong {
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 15px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-action-copy span {
  display: -webkit-box;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.dashboard-action-card--priority-primary .dashboard-action-copy span {
  color: var(--text-color-regular);
}

.dashboard-action-arrow {
  color: var(--text-color-secondary);
}

.dashboard-table-scroll {
  overflow-x: auto;
}

.dashboard-backtest-table {
  min-width: 860px;
}

.dashboard-table-number {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.dashboard-empty {
  padding: 24px 0;
}

@media (max-width: 1100px) {
  .dashboard-overview {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .dashboard-health {
    min-width: 0;
  }

  .dashboard-stat-grid,
  .dashboard-actions-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .dashboard-page {
    gap: 16px;
  }

  .dashboard-overview {
    padding: 18px;
  }

  .dashboard-heading h2 {
    font-size: 20px;
  }

  .dashboard-health,
  .dashboard-stat-grid,
  .dashboard-actions-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-panel-header,
  .dashboard-panel-header--split {
    align-items: flex-start;
    flex-direction: column;
  }

  .dashboard-action-card:hover {
    transform: none;
  }
}
</style>
