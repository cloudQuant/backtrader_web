<template>
  <div class="workspace-detail-page">
    <teleport
      v-if="headerTitleTargetReady"
      to="#page-header-title-extra"
    >
      <span class="workspace-detail-header-separator">/</span>
      <el-tag
        v-if="store.currentWorkspace"
        size="small"
        :type="workspaceType === 'trading' ? 'warning' : 'info'"
        effect="plain"
      >
        {{ workspaceType === 'trading' ? t('workspaceDetail.tagTrading') : t('workspaceDetail.tagResearch') }}
      </el-tag>
      <span class="workspace-detail-header-name">
        {{ store.currentWorkspace?.name || t('workspaceDetail.nameLoading') }}
      </span>
    </teleport>

    <teleport
      v-if="headerActionsTargetReady"
      to="#page-header-actions"
    >
      <el-button
        v-if="store.currentWorkspace && workspaceType !== 'trading'"
        class="workspace-detail-header-action"
        size="small"
        @click="showDataSourceDialog = true"
      >
        <el-icon
          class="button-icon"
          aria-hidden="true"
        >
          <DataLine />
        </el-icon>
        {{ t('workspaceDetail.btnDataSource') }}
        <span>{{ dataSourceTypeLabel }}</span>
      </el-button>
    </teleport>

    <div
      v-if="store.loading && !store.currentWorkspace"
      class="workspace-detail-state"
    >
      <el-icon
        class="workspace-detail-loading is-loading"
        aria-hidden="true"
      >
        <Loading />
      </el-icon>
      <span>{{ t('common.loading') }}</span>
    </div>

    <div
      v-else-if="!store.currentWorkspace"
      class="workspace-detail-empty"
    >
      <el-empty :description="t('workspaceDetail.emptyNotFound')" />
    </div>

    <template v-else>
      <section
        class="workspace-detail-hero"
        data-test="workspace-detail-hero"
        aria-labelledby="workspace-detail-title"
      >
        <div class="workspace-detail-copy">
          <span class="workspace-detail-kicker">{{ workspaceHero.kicker }}</span>
          <div class="workspace-detail-title-row">
            <h1 id="workspace-detail-title">
              {{ store.currentWorkspace.name }}
            </h1>
            <el-tag
              :type="statusTagType(store.currentWorkspace.status)"
              effect="plain"
            >
              {{ statusLabel(store.currentWorkspace.status) }}
            </el-tag>
          </div>
          <p>{{ workspaceDescription }}</p>
        </div>

        <div class="workspace-detail-actions">
          <el-button
            v-if="workspaceType !== 'trading'"
            type="primary"
            :aria-label="t('workspaceDetail.btnConfigureDataSource')"
            @click="showDataSourceDialog = true"
          >
            <el-icon
              class="button-icon"
              aria-hidden="true"
            >
              <DataLine />
            </el-icon>
            {{ t('workspaceDetail.btnConfigureDataSource') }}
          </el-button>
        </div>

        <div class="workspace-detail-meta">
          <span>{{ t('workspaceDetail.createdAt') }}: {{ formatTime(store.currentWorkspace.created_at) }}</span>
          <span>{{ t('workspaceDetail.updatedAt') }}: {{ formatTime(store.currentWorkspace.updated_at) }}</span>
        </div>

        <div
          class="workspace-detail-metrics"
          :aria-label="t('workspaceDetail.metricsLabel')"
        >
          <article
            v-for="metric in workspaceStats"
            :key="metric.key"
            class="workspace-detail-metric"
          >
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
          </article>
        </div>
      </section>

      <section
        v-if="workspaceType === 'trading'"
        class="trading-detail-ops"
        data-test="trading-detail-ops"
        aria-labelledby="trading-detail-ops-title"
      >
        <header class="trading-detail-ops-head">
          <div>
            <span>{{ t('workspaceDetail.tradingOpsKicker') }}</span>
            <h2 id="trading-detail-ops-title">
              {{ t('workspaceDetail.tradingOpsTitle') }}
            </h2>
            <p>{{ t('workspaceDetail.tradingOpsDesc') }}</p>
          </div>
          <el-tag
            :type="tradingReadiness.tagType"
            effect="plain"
          >
            {{ tradingReadiness.label }}
          </el-tag>
        </header>

        <div class="trading-detail-ops-grid">
          <article
            v-for="card in tradingOpsCards"
            :key="card.key"
            class="trading-detail-ops-card"
            :class="`is-${card.tone}`"
          >
            <span class="trading-detail-ops-icon">
              <el-icon aria-hidden="true">
                <component :is="resolveDetailIcon(card.icon)" />
              </el-icon>
            </span>
            <span class="trading-detail-ops-copy">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <em>{{ card.helper }}</em>
            </span>
          </article>
        </div>

        <div class="trading-detail-readiness">
          <div class="trading-detail-readiness-copy">
            <span>{{ t('workspaceDetail.tradingReadinessTitle') }}</span>
            <p>{{ tradingReadiness.description }}</p>
          </div>
          <div
            class="trading-detail-checks"
            :aria-label="t('workspaceDetail.tradingReadinessTitle')"
          >
            <span
              v-for="check in tradingReadinessChecks"
              :key="check.key"
              class="trading-detail-check"
              :class="{ 'is-ok': check.ok }"
            >
              <el-icon aria-hidden="true">
                <component :is="check.ok ? CircleCheck : Warning" />
              </el-icon>
              {{ check.label }}
            </span>
          </div>
        </div>
      </section>

      <section
        class="workspace-detail-panel"
        data-test="workspace-detail-panel"
      >
        <header class="workspace-detail-panel-head">
          <div>
            <span>{{ workspacePanel.kicker }}</span>
            <h2>{{ workspacePanel.title }}</h2>
          </div>
          <p>{{ workspacePanel.meta }}</p>
        </header>

        <el-tabs
          v-model="activeTab"
          class="workspace-detail-tabs"
          type="border-card"
          @tab-remove="handleTabRemove"
        >
          <el-tab-pane
            :label="t('workspaceDetail.tabUnits')"
            name="units"
          >
            <TradingWorkspaceUnitsTab
              v-if="workspaceType === 'trading'"
              :workspace-id="workspaceId"
              :active="activeTab === 'units'"
              :toolbar-in-header="false"
              @switch-tab="handleSwitchTab"
            />
            <WorkspaceUnitsTab
              v-else
              :workspace-id="workspaceId"
              :active="activeTab === 'units'"
              :toolbar-in-header="false"
              @switch-tab="handleSwitchTab"
            />
          </el-tab-pane>
          <el-tab-pane
            v-if="showOptTab"
            :label="t('workspaceDetail.tabOptimization')"
            name="optimization"
            closable
          >
            <WorkspaceOptimizationTab
              :workspace-id="workspaceId"
              :active="activeTab === 'optimization'"
              :toolbar-in-header="false"
              :initial-unit-id="initialOptUnitId"
            />
          </el-tab-pane>
          <el-tab-pane
            v-if="showReportTab"
            :label="t('workspaceDetail.tabReport')"
            name="report"
            closable
          >
            <WorkspaceReportTab
              :workspace-id="workspaceId"
              :active="activeTab === 'report'"
              :toolbar-in-header="false"
              :initial-unit-id="initialReportUnitId"
              :initial-unit-ids="initialReportUnitIds"
            />
          </el-tab-pane>
        </el-tabs>
      </section>

      <WorkspaceDataSourceDialog
        v-model="showDataSourceDialog"
        :workspace-id="workspaceId"
        :workspace="store.currentWorkspace"
        @saved="store.fetchWorkspace(workspaceId)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import {
  CircleCheck,
  Connection,
  DataLine,
  Loading,
  Lock,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'
import TradingWorkspaceUnitsTab from '@/components/workspace/TradingWorkspaceUnitsTab.vue'
import WorkspaceDataSourceDialog from '@/components/workspace/WorkspaceDataSourceDialog.vue'
import WorkspaceOptimizationTab from '@/components/workspace/WorkspaceOptimizationTab.vue'
import WorkspaceReportTab from '@/components/workspace/WorkspaceReportTab.vue'
import WorkspaceUnitsTab from '@/components/workspace/WorkspaceUnitsTab.vue'
import type { TagType } from '@/constants/strategy'
import { useWorkspaceStore } from '@/stores/workspace'
import type { UnitRunStatus, WorkspaceStatus, WorkspaceType } from '@/types/workspace'

const { t } = useI18n()
const route = useRoute()
const store = useWorkspaceStore()

const workspaceId = computed(() => route.params.id as string)
const activeTab = ref('units')
const showDataSourceDialog = ref(false)
const showOptTab = ref(false)
const showReportTab = ref(false)
const headerTitleTargetReady = ref(false)
const headerActionsTargetReady = ref(false)
let headerTargetTimer: ReturnType<typeof setInterval> | null = null

const initialOptUnitId = ref('')
const initialReportUnitId = ref('')
const initialReportUnitIds = ref<string[]>([])

const detailIcons: Record<string, Component> = {
  Connection,
  DataLine,
  Lock,
  TrendCharts,
}

const workspaceType = computed<WorkspaceType>(() =>
  store.currentWorkspace?.workspace_type
  ?? (route.meta.workspaceType === 'trading' ? 'trading' : 'research')
)

const workspaceHero = computed(() => {
  if (workspaceType.value === 'trading') {
    return {
      kicker: t('workspaceDetail.heroTradingKicker'),
      fallbackDescription: t('workspaceDetail.heroTradingSubtitle'),
    }
  }

  return {
    kicker: t('workspaceDetail.heroResearchKicker'),
    fallbackDescription: t('workspaceDetail.heroResearchSubtitle'),
  }
})

const workspaceDescription = computed(() =>
  store.currentWorkspace?.description?.trim()
  || workspaceHero.value.fallbackDescription
)

const unitCount = computed(() =>
  store.units.length || store.currentWorkspace?.unit_count || 0
)

const completedUnitCount = computed(() => {
  const completed = store.units.filter(unit => unit.run_status === 'completed').length
  return completed || store.currentWorkspace?.completed_count || 0
})

const activeUnitCount = computed(() =>
  store.units.filter(unit => isActiveUnitStatus(unit.run_status)).length
)

const liveUnitCount = computed(() =>
  store.units.filter(unit => unit.trading_mode === 'live').length
)

const paperUnitCount = computed(() =>
  store.units.filter(unit => unit.trading_mode !== 'live').length
)

const lockedUnitCount = computed(() =>
  store.units.filter(unit => unit.lock_running || unit.lock_trading).length
)

const failedUnitCount = computed(() =>
  store.units.filter(unit =>
    unit.run_status === 'failed'
    || unit.run_status === 'cancelled'
    || unit.run_status === 'timeout'
    || String(unit.trading_snapshot?.instance_status || '').toLowerCase() === 'error',
  ).length
)

const runtimeActiveUnitCount = computed(() =>
  store.units.filter(unit => isTradingRuntimeActive(unit)).length
)

const gatewayConfiguredCount = computed(() =>
  store.units.filter(unit => hasGatewayConfig(unit.gateway_config)).length
)

const gatewayRequiredCount = computed(() =>
  liveUnitCount.value || unitCount.value
)

const todayPnl = computed(() => {
  const values = store.units
    .map(unit => unit.trading_snapshot?.today_pnl)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (!values.length) {
    return null
  }
  return values.reduce((sum, value) => sum + value, 0)
})

const tradingLastUpdatedAt = computed(() => {
  const timestamps = store.units
    .map(unit => parseTimeValue(unit.trading_snapshot?.updated_at || unit.updated_at))
    .filter((value): value is number => typeof value === 'number')
  const latest = timestamps.length ? Math.max(...timestamps) : parseTimeValue(store.currentWorkspace?.updated_at)
  return latest ? formatTime(latest) : '-'
})

const tradingGatewayCoverage = computed(() => {
  if (!unitCount.value) {
    return '0/0'
  }
  return `${gatewayConfiguredCount.value}/${unitCount.value}`
})

const tradingModeLabel = computed(() => `${liveUnitCount.value}/${paperUnitCount.value}`)

const workspaceStats = computed(() => {
  if (workspaceType.value === 'trading') {
    return [
      { key: 'units', label: t('workspaceDetail.metricUnits'), value: unitCount.value },
      { key: 'runtime', label: t('workspaceDetail.tradingMetricRuntime'), value: runtimeActiveUnitCount.value },
      { key: 'mode', label: t('workspaceDetail.tradingMetricMode'), value: tradingModeLabel.value },
      { key: 'pnl', label: t('workspaceDetail.tradingMetricTodayPnl'), value: formatSignedNumber(todayPnl.value) },
    ]
  }
  return [
    { key: 'units', label: t('workspaceDetail.metricUnits'), value: unitCount.value },
    { key: 'completed', label: t('workspaceDetail.metricCompleted'), value: completedUnitCount.value },
    { key: 'active', label: t('workspaceDetail.metricActive'), value: activeUnitCount.value },
    { key: 'dataSource', label: t('workspaceDetail.metricDataSource'), value: dataSourceTypeLabel.value },
  ]
})

const workspacePanel = computed(() => {
  if (workspaceType.value === 'trading') {
    return {
      kicker: t('workspaceDetail.tradingPanelKicker'),
      title: t('workspaceDetail.tradingPanelTitle'),
      meta: t('workspaceDetail.tradingPanelMeta', { count: unitCount.value }),
    }
  }
  return {
    kicker: t('workspaceDetail.panelKicker'),
    title: t('workspaceDetail.panelTitle'),
    meta: t('workspaceDetail.panelMeta', { count: unitCount.value }),
  }
})

const tradingOpsCards = computed(() => [
  {
    key: 'runtime',
    icon: 'TrendCharts',
    tone: runtimeActiveUnitCount.value > 0 ? 'success' : 'neutral',
    label: t('workspaceDetail.tradingRuntimeLabel'),
    value: runtimeActiveUnitCount.value,
    helper: t('workspaceDetail.tradingRuntimeHelper', {
      total: unitCount.value,
      updated: tradingLastUpdatedAt.value,
    }),
  },
  {
    key: 'mode',
    icon: 'DataLine',
    tone: liveUnitCount.value > 0 ? 'warning' : 'neutral',
    label: t('workspaceDetail.tradingModeLabel'),
    value: tradingModeLabel.value,
    helper: t('workspaceDetail.tradingModeHelper'),
  },
  {
    key: 'gateway',
    icon: 'Connection',
    tone: gatewayRequiredCount.value > 0 && gatewayConfiguredCount.value >= gatewayRequiredCount.value
      ? 'success'
      : 'warning',
    label: t('workspaceDetail.tradingGatewayLabel'),
    value: tradingGatewayCoverage.value,
    helper: t('workspaceDetail.tradingGatewayHelper'),
  },
  {
    key: 'locks',
    icon: 'Lock',
    tone: lockedUnitCount.value > 0 ? 'danger' : 'success',
    label: t('workspaceDetail.tradingLockLabel'),
    value: lockedUnitCount.value,
    helper: lockedUnitCount.value > 0
      ? t('workspaceDetail.tradingLockHelperReview')
      : t('workspaceDetail.tradingLockHelperClear'),
  },
])

const tradingReadinessChecks = computed(() => [
  {
    key: 'units',
    ok: unitCount.value > 0,
    label: t('workspaceDetail.tradingCheckUnits'),
  },
  {
    key: 'gateway',
    ok: gatewayRequiredCount.value === 0 || gatewayConfiguredCount.value >= gatewayRequiredCount.value,
    label: t('workspaceDetail.tradingCheckGateway'),
  },
  {
    key: 'result',
    ok: completedUnitCount.value > 0 || runtimeActiveUnitCount.value > 0,
    label: t('workspaceDetail.tradingCheckResult'),
  },
  {
    key: 'risk',
    ok: failedUnitCount.value === 0 && lockedUnitCount.value === 0,
    label: t('workspaceDetail.tradingCheckRisk'),
  },
])

const tradingReadiness = computed(() => {
  if (!unitCount.value) {
    return {
      label: t('workspaceDetail.tradingReadinessEmpty'),
      description: t('workspaceDetail.tradingReadinessEmptyDesc'),
      tagType: 'info' as TagType,
    }
  }

  const failedChecks = tradingReadinessChecks.value.filter(check => !check.ok).length
  if (failedUnitCount.value > 0 || lockedUnitCount.value > 0) {
    return {
      label: t('workspaceDetail.tradingReadinessReview'),
      description: t('workspaceDetail.tradingReadinessReviewDesc'),
      tagType: 'warning' as TagType,
    }
  }

  if (failedChecks === 0) {
    return {
      label: t('workspaceDetail.tradingReadinessReady'),
      description: t('workspaceDetail.tradingReadinessReadyDesc'),
      tagType: 'success' as TagType,
    }
  }

  return {
    label: t('workspaceDetail.tradingReadinessPartial'),
    description: t('workspaceDetail.tradingReadinessPartialDesc'),
    tagType: 'warning' as TagType,
  }
})

function handleSwitchTab(tab: string, unitId?: string, unitIds?: string[]) {
  if (tab === 'optimization') {
    showOptTab.value = true
    if (unitId) initialOptUnitId.value = unitId
  } else if (tab === 'report') {
    showReportTab.value = true
    if (unitId) initialReportUnitId.value = unitId
    initialReportUnitIds.value = unitIds?.length ? [...unitIds] : (unitId ? [unitId] : [])
  }
  activeTab.value = tab
}

function handleTabRemove(name: string | number) {
  if (name === 'optimization') {
    showOptTab.value = false
  } else if (name === 'report') {
    showReportTab.value = false
  }
  activeTab.value = 'units'
}

const dataSourceTypeLabel = computed(() => {
  const type = store.currentWorkspace?.settings?.data_source?.type || 'csv'
  const labels: Record<string, string> = {
    csv: 'CSV',
    mysql: 'MySQL',
    postgresql: 'PostgreSQL',
    mongodb: 'MongoDB',
  }
  return labels[type] || type
})

function resolveDetailIcon(name: string): Component {
  return detailIcons[name] ?? DataLine
}

function isActiveUnitStatus(status: UnitRunStatus): boolean {
  return status === 'queued' || status === 'running'
}

function isTradingRuntimeActive(unit: {
  run_status: UnitRunStatus
  trading_instance_id?: string | null
  trading_snapshot?: { instance_status?: string | null }
}) {
  const status = String(unit.trading_snapshot?.instance_status || '').toLowerCase()
  return isActiveUnitStatus(unit.run_status)
    || Boolean(unit.trading_instance_id)
    || ['starting', 'running', 'live', 'connected'].includes(status)
}

function hasGatewayConfig(config: unknown): boolean {
  if (!config || typeof config !== 'object') {
    return false
  }
  const gateway = config as Record<string, unknown>
  if (gateway.preset_id || gateway.name) {
    return true
  }
  const params = gateway.params
  return Boolean(params && typeof params === 'object' && Object.keys(params).length > 0)
}

function statusTagType(status: WorkspaceStatus): TagType {
  const map: Record<WorkspaceStatus, TagType> = {
    idle: 'info',
    running: 'warning',
    completed: 'success',
    error: 'danger',
  }
  return map[status] || 'info'
}

function statusLabel(status: WorkspaceStatus): string {
  const map: Record<WorkspaceStatus, string> = {
    idle: t('workspace.statusIdle'),
    running: t('workspace.statusRunning'),
    completed: t('workspace.statusCompleted'),
    error: t('workspace.statusError'),
  }
  return map[status] || status
}

function parseTimeValue(value: string | number | null | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value) {
    const timestamp = new Date(value).getTime()
    return Number.isNaN(timestamp) ? null : timestamp
  }
  return null
}

function formatTime(value: string | number | null | undefined) {
  const timestamp = parseTimeValue(value)
  return timestamp ? new Date(timestamp).toLocaleString() : ''
}

function formatSignedNumber(value: number | null) {
  if (value === null) {
    return '-'
  }
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${value.toFixed(2)}`
}

watch(workspaceId, async (id) => {
  activeTab.value = 'units'
  showOptTab.value = false
  showReportTab.value = false
  await store.fetchWorkspace(id)
  await store.fetchUnits(id)
}, { immediate: true })

function updateHeaderTargetsReady() {
  if (typeof document === 'undefined') {
    headerTitleTargetReady.value = false
    headerActionsTargetReady.value = false
    return false
  }
  headerTitleTargetReady.value = document.getElementById('page-header-title-extra') !== null
  headerActionsTargetReady.value = document.getElementById('page-header-actions') !== null
  return headerTitleTargetReady.value && headerActionsTargetReady.value
}

onMounted(async () => {
  await nextTick()
  if (!updateHeaderTargetsReady()) {
    headerTargetTimer = setInterval(() => {
      if (updateHeaderTargetsReady() && headerTargetTimer) {
        clearInterval(headerTargetTimer)
        headerTargetTimer = null
      }
    }, 100)
  }
})

onUnmounted(() => {
  if (headerTargetTimer) {
    clearInterval(headerTargetTimer)
    headerTargetTimer = null
  }
})
</script>

<style scoped>
.workspace-detail-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--text-color-primary);
}

.workspace-detail-header-separator {
  color: var(--text-color-placeholder);
}

.workspace-detail-header-name {
  display: inline-block;
  overflow: hidden;
  max-width: 420px;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.button-icon {
  margin-right: 4px;
}

.workspace-detail-header-action {
  gap: 6px;
}

.workspace-detail-header-action span:last-child {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.workspace-detail-state,
.workspace-detail-empty,
.workspace-detail-hero,
.trading-detail-ops,
.workspace-detail-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.workspace-detail-state,
.workspace-detail-empty {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.workspace-detail-state {
  gap: 10px;
  color: var(--text-color-secondary);
  font-size: 14px;
}

.workspace-detail-loading {
  color: var(--primary-color);
  font-size: 28px;
}

.workspace-detail-empty {
  background: var(--fill-color-lighter);
}

.workspace-detail-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 20px;
}

.workspace-detail-copy {
  min-width: 0;
}

.workspace-detail-kicker,
.workspace-detail-panel-head span {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.workspace-detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.workspace-detail-title-row h1 {
  overflow: hidden;
  margin: 0;
  color: var(--text-color-primary);
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
  text-overflow: ellipsis;
}

.workspace-detail-copy p {
  max-width: 760px;
  margin: 8px 0 0;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.workspace-detail-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
}

.workspace-detail-actions :deep(.el-button) {
  gap: 6px;
}

.workspace-detail-meta {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.workspace-detail-metrics {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.workspace-detail-metric {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.workspace-detail-metric span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.workspace-detail-metric strong {
  display: block;
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trading-detail-ops {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.trading-detail-ops-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.trading-detail-ops-head > div {
  min-width: 0;
}

.trading-detail-ops-head span,
.trading-detail-readiness-copy span {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.trading-detail-ops-head h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 740;
  line-height: 1.25;
}

.trading-detail-ops-head p,
.trading-detail-readiness-copy p {
  max-width: 820px;
  margin: 7px 0 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.trading-detail-ops-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.trading-detail-ops-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
  min-width: 0;
  min-height: 116px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.trading-detail-ops-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-secondary);
  flex: none;
}

.trading-detail-ops-card.is-success .trading-detail-ops-icon {
  border-color: var(--success-border-color);
  background: var(--success-surface);
  color: var(--success-text-color);
}

.trading-detail-ops-card.is-warning .trading-detail-ops-icon {
  border-color: var(--warning-border-color);
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

.trading-detail-ops-card.is-danger .trading-detail-ops-icon {
  border-color: var(--danger-border-color);
  background: var(--danger-surface);
  color: var(--danger-text-color);
}

.trading-detail-ops-copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.trading-detail-ops-copy > span {
  overflow: hidden;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trading-detail-ops-copy strong {
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 21px;
  font-weight: 760;
  line-height: 1.1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trading-detail-ops-copy em {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.trading-detail-readiness {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.8fr);
  gap: 14px;
  align-items: start;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-light);
}

.trading-detail-checks {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.trading-detail-check {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 7px;
  padding: 8px 10px;
  border: 1px solid var(--warning-border-color);
  border-radius: 8px;
  background: var(--warning-surface);
  color: var(--warning-text-color);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.trading-detail-check.is-ok {
  border-color: var(--success-border-color);
  background: var(--success-surface);
  color: var(--success-text-color);
}

.trading-detail-check .el-icon {
  flex: none;
}

.workspace-detail-panel {
  padding: 18px;
}

.workspace-detail-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.workspace-detail-panel-head div {
  min-width: 0;
}

.workspace-detail-panel-head h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 740;
  line-height: 1.25;
}

.workspace-detail-panel-head p {
  flex: 0 0 auto;
  max-width: 360px;
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
  text-align: right;
}

.workspace-detail-tabs {
  overflow: hidden;
  border-color: var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
}

.workspace-detail-tabs :deep(.el-tabs__header) {
  border-color: var(--border-color-light);
  background: var(--fill-color-lighter);
}

.workspace-detail-tabs :deep(.el-tabs__content) {
  padding: 14px;
  background: var(--bg-color);
}

.workspace-detail-tabs :deep(.el-tabs__item) {
  color: var(--text-color-secondary);
}

.workspace-detail-tabs :deep(.el-tabs__item.is-active) {
  color: var(--primary-color);
  font-weight: 700;
}

.workspace-detail-tabs :deep(.el-table) {
  --el-table-header-bg-color: var(--fill-color-lighter);
  --el-table-tr-bg-color: var(--bg-color);
  --el-table-row-hover-bg-color: var(--fill-color-light);
  --el-table-border-color: var(--border-color-light);
  --el-table-text-color: var(--text-color-regular);
  --el-table-header-text-color: var(--text-color-secondary);
  min-width: 1120px;
}

.workspace-detail-tabs :deep(.el-table__header-wrapper th) {
  font-weight: 700;
}

.workspace-detail-tabs :deep(.workspace-units-tab),
.workspace-detail-tabs :deep(.workspace-optimization-tab),
.workspace-detail-tabs :deep(.workspace-report-tab) {
  overflow-x: auto;
}

@media (max-width: 1180px) {
  .workspace-detail-hero {
    grid-template-columns: 1fr;
  }

  .workspace-detail-actions {
    justify-content: flex-start;
  }

  .workspace-detail-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trading-detail-ops-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trading-detail-readiness {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .workspace-detail-page {
    gap: 14px;
  }

  .workspace-detail-hero,
  .trading-detail-ops,
  .workspace-detail-panel {
    padding: 14px;
  }

  .workspace-detail-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .workspace-detail-title-row h1 {
    font-size: 22px;
  }

  .workspace-detail-actions :deep(.el-button) {
    width: 100%;
    justify-content: center;
  }

  .workspace-detail-panel-head {
    flex-direction: column;
  }

  .workspace-detail-panel-head p {
    max-width: none;
    text-align: left;
  }

  .workspace-detail-metrics {
    grid-template-columns: 1fr;
  }

  .trading-detail-ops-head {
    flex-direction: column;
  }

  .trading-detail-ops-grid,
  .trading-detail-checks {
    grid-template-columns: 1fr;
  }

  .trading-detail-readiness {
    padding: 12px;
  }

  .workspace-detail-tabs :deep(.el-tabs__content) {
    padding: 10px;
  }
}
</style>
