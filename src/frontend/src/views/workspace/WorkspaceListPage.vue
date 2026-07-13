<template>
  <div class="workspace-list-page">
    <teleport
      v-if="headerActionsTargetReady"
      to="#page-header-actions"
    >
      <el-button
        class="workspace-header-action"
        type="primary"
        :aria-label="t('workspace.createNew')"
        @click="showCreateDialog = true"
      >
        <el-icon
          class="button-icon"
          aria-hidden="true"
        >
          <Plus />
        </el-icon>
        {{ t('workspace.createNew') }}
      </el-button>
      <el-button
        class="workspace-header-action"
        :disabled="!selectedIds.length"
        type="danger"
        plain
        :aria-label="t('workspace.deleteSelected')"
        @click="handleBatchDelete"
      >
        <el-icon
          class="button-icon"
          aria-hidden="true"
        >
          <Delete />
        </el-icon>
        {{ t('workspace.deleteSelected') }}
      </el-button>
      <el-radio-group
        v-model="viewMode"
        class="workspace-header-view"
        size="default"
        :aria-label="t('workspace.viewMode')"
      >
        <el-radio-button
          value="card"
          :aria-label="t('workspace.viewCard')"
          :title="t('workspace.viewCard')"
        >
          <el-icon aria-hidden="true">
            <Grid />
          </el-icon>
        </el-radio-button>
        <el-radio-button
          value="table"
          :aria-label="t('workspace.viewTable')"
          :title="t('workspace.viewTable')"
        >
          <el-icon aria-hidden="true">
            <List />
          </el-icon>
        </el-radio-button>
      </el-radio-group>
    </teleport>

    <section
      class="workspace-hero"
      data-test="workspace-hero"
      aria-labelledby="workspace-list-title"
    >
      <div class="workspace-hero-copy">
        <span class="workspace-kicker">{{ workspaceHero.kicker }}</span>
        <h1 id="workspace-list-title">
          {{ workspaceHero.title }}
        </h1>
        <p>{{ workspaceHero.subtitle }}</p>
      </div>

      <div class="workspace-hero-actions">
        <el-button
          type="primary"
          size="large"
          :aria-label="t('workspace.createNew')"
          @click="showCreateDialog = true"
        >
          <el-icon
            class="button-icon"
            aria-hidden="true"
          >
            <Plus />
          </el-icon>
          {{ t('workspace.createNew') }}
        </el-button>
        <el-radio-group
          v-model="viewMode"
          size="large"
          :aria-label="t('workspace.viewMode')"
        >
          <el-radio-button
            value="card"
            :aria-label="t('workspace.viewCard')"
            :title="t('workspace.viewCard')"
          >
            <el-icon aria-hidden="true">
              <Grid />
            </el-icon>
          </el-radio-button>
          <el-radio-button
            value="table"
            :aria-label="t('workspace.viewTable')"
            :title="t('workspace.viewTable')"
          >
            <el-icon aria-hidden="true">
              <List />
            </el-icon>
          </el-radio-button>
        </el-radio-group>
      </div>

      <div
        class="workspace-metrics"
        :aria-label="t('workspace.metricsLabel')"
      >
        <article
          v-for="metric in workspaceStats"
          :key="metric.key"
          class="workspace-metric"
        >
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </article>
      </div>
    </section>

    <section
      v-if="isTradingWorkspace"
      class="trading-ops-panel"
      data-test="trading-ops-panel"
      aria-labelledby="trading-ops-title"
    >
      <div class="trading-ops-heading">
        <div>
          <span>{{ t('workspace.tradingOpsKicker') }}</span>
          <h2 id="trading-ops-title">
            {{ t('workspace.tradingOpsTitle') }}
          </h2>
          <p>{{ t('workspace.tradingOpsDesc') }}</p>
        </div>
        <span class="trading-ops-pill">
          {{ t('workspace.tradingCompletionPercent', { value: tradingCompletionRate }) }}
        </span>
      </div>

      <div class="trading-ops-grid">
        <article
          v-for="item in tradingOpsCards"
          :key="item.key"
          class="trading-ops-card"
          :class="`trading-ops-card--${item.tone}`"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.helper }}</small>
        </article>
      </div>
    </section>

    <section
      class="workspace-panel"
      data-test="workspace-list-panel"
    >
      <header class="workspace-panel-head">
        <div>
          <span>{{ t('workspace.panelKicker') }}</span>
          <h2>{{ workspacePanelTitle }}</h2>
        </div>
        <p>{{ workspacePanelMeta }}</p>
      </header>

      <div
        v-if="store.loading"
        class="workspace-state"
      >
        <el-icon
          class="workspace-loading is-loading"
          aria-hidden="true"
        >
          <Loading />
        </el-icon>
        <span>{{ t('common.loading') }}</span>
      </div>

      <div
        v-else-if="store.workspaces.length === 0"
        class="workspace-empty"
      >
        <ResearchWorkflowGuide
          v-if="!isTradingWorkspace"
          data-test="research-workflow-guide"
          :kicker="t('workspace.flowKicker')"
          :title="t('workspace.flowTitle')"
          :steps="researchStartSteps"
          :complete-label="t('workspace.flowStateComplete')"
          :current-label="t('workspace.flowStateCurrent')"
          :upcoming-label="t('workspace.flowStateUpcoming')"
          :attention-label="t('workspace.flowStateAttention')"
          @action="handleResearchFlowAction"
        />
        <template v-else>
          <el-empty
            :description="emptyDescription"
          />
          <el-button
            type="primary"
            :aria-label="t('workspace.createNew')"
            @click="showCreateDialog = true"
          >
            <el-icon
              class="button-icon"
              aria-hidden="true"
            >
              <Plus />
            </el-icon>
            {{ t('workspace.createNew') }}
          </el-button>
        </template>
      </div>

      <div
        v-else-if="viewMode === 'card'"
        class="workspace-card-grid"
      >
        <WorkspaceCard
          v-for="ws in store.workspaces"
          :key="ws.id"
          :workspace="ws"
          :selected="selectedIds.includes(ws.id)"
          @click="goToDetail(ws.id)"
          @edit="handleEdit(ws)"
          @delete="handleDelete(ws)"
          @toggle-select="toggleSelect(ws.id)"
        />
      </div>

      <div
        v-else
        class="workspace-table-wrap"
      >
        <el-table
          :data="store.workspaces"
          stripe
          class="workspace-table cursor-pointer"
          @selection-change="onTableSelectionChange"
          @row-click="(row: Workspace) => goToDetail(row.id)"
        >
          <el-table-column
            type="selection"
            width="50"
          />
          <el-table-column
            prop="name"
            :label="t('workspace.name')"
            min-width="180"
          />
          <el-table-column
            prop="description"
            :label="t('workspace.description')"
            min-width="200"
            show-overflow-tooltip
          />
          <el-table-column
            :label="t('workspace.status')"
            width="100"
          >
            <template #default="{ row }">
              <span
                class="workspace-status-pill"
                :class="`workspace-status-pill--${statusTone(row.status)}`"
              >
                {{ statusLabel(row.status) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('workspace.units')"
            width="100"
            align="center"
          >
            <template #default="{ row }">
              {{ row.unit_count }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('workspace.completed')"
            width="80"
            align="center"
          >
            <template #default="{ row }">
              {{ row.completed_count }}
            </template>
          </el-table-column>
          <el-table-column
            v-if="isTradingWorkspace"
            :label="t('workspace.tradingReadiness')"
            min-width="150"
          >
            <template #default="{ row }">
              <span
                class="trading-readiness-pill"
                :class="workspaceReadinessClass(row)"
              >
                {{ workspaceReadinessLabel(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('workspace.createdAt')"
            width="170"
          >
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('workspace.updatedAt')"
            width="170"
          >
            <template #default="{ row }">
              {{ formatTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('workspace.action')"
            width="120"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                @click.stop="handleEdit(row)"
              >
                {{ t('workspace.edit') }}
              </el-button>
              <el-button
                link
                type="danger"
                size="small"
                @click.stop="handleDelete(row)"
              >
                {{ t('workspace.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <CreateWorkspaceDialog
      v-model="showCreateDialog"
      :workspace="editingWorkspace"
      :workspace-type="workspaceType"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Grid, List, Loading, Plus } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import ResearchWorkflowGuide from '@/components/research/ResearchWorkflowGuide.vue'
import { APP_PATHS } from '@/navigation/routes'
import { useWorkspaceStore } from '@/stores/workspace'
import type { ResearchWorkflowStep } from '@/types/researchWorkflow'
import type { ViewMode, Workspace, WorkspaceType } from '@/types/workspace'
import CreateWorkspaceDialog from '@/components/workspace/CreateWorkspaceDialog.vue'
import WorkspaceCard from '@/components/workspace/WorkspaceCard.vue'

type TradingOpsTone = 'primary' | 'success' | 'warning' | 'danger'

interface TradingOpsCard {
  key: string
  label: string
  value: string | number
  helper: string
  tone: TradingOpsTone
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()

const viewMode = ref<ViewMode>('card')
const selectedIds = ref<string[]>([])
const showCreateDialog = ref(false)
const editingWorkspace = ref<Workspace | null>(null)
const headerActionsTargetReady = ref(false)
let headerTargetTimer: ReturnType<typeof setInterval> | null = null

const workspaceType = computed<WorkspaceType>(() =>
  route.meta.workspaceType === 'trading' ? 'trading' : 'research'
)

const isTradingWorkspace = computed(() => workspaceType.value === 'trading')

const emptyDescription = computed(() =>
  isTradingWorkspace.value
    ? t('workspace.emptyTrading')
    : t('workspace.emptyResearch')
)

const workspaceHero = computed(() => {
  if (isTradingWorkspace.value) {
    return {
      kicker: t('workspace.tradingHeroKicker'),
      title: t('workspace.tradingHeroTitle'),
      subtitle: t('workspace.tradingHeroSubtitle'),
    }
  }

  return {
    kicker: t('workspace.researchHeroKicker'),
    title: t('workspace.researchHeroTitle'),
    subtitle: t('workspace.researchHeroSubtitle'),
  }
})

const researchStartSteps = computed<ResearchWorkflowStep[]>(() => [
  {
    id: 'workspace',
    label: t('workspace.flowCreateTitle'),
    description: t('workspace.flowCreateDesc'),
    state: 'current',
    action: 'create-workspace',
    actionLabel: t('workspace.createNew'),
  },
  {
    id: 'configure',
    label: t('workspace.flowConfigureTitle'),
    description: t('workspace.flowConfigureDesc'),
    state: 'upcoming',
  },
  {
    id: 'backtest',
    label: t('workspace.flowBacktestTitle'),
    description: t('workspace.flowBacktestDesc'),
    state: 'upcoming',
  },
  {
    id: 'review',
    label: t('workspace.flowReviewTitle'),
    description: t('workspace.flowReviewDesc'),
    state: 'upcoming',
  },
])

const workspaceStats = computed(() => {
  const total = store.total || store.workspaces.length
  const running = store.workspaces.filter(workspace => workspace.status === 'running').length
  const completed = store.workspaces.filter(workspace => workspace.status === 'completed').length

  return [
    { key: 'total', label: t('workspace.metricTotal'), value: total },
    { key: 'running', label: t('workspace.metricRunning'), value: running },
    { key: 'completed', label: t('workspace.metricCompleted'), value: completed },
    { key: 'selected', label: t('workspace.metricSelected'), value: selectedIds.value.length },
  ]
})

const tradingTotals = computed(() => {
  const totalUnits = store.workspaces.reduce((sum, workspace) => sum + Number(workspace.unit_count || 0), 0)
  const completedUnits = store.workspaces.reduce((sum, workspace) => sum + Number(workspace.completed_count || 0), 0)
  const runningWorkspaces = store.workspaces.filter(workspace => workspace.status === 'running').length
  const errorWorkspaces = store.workspaces.filter(workspace => workspace.status === 'error').length
  const idleWorkspaces = store.workspaces.filter(workspace => workspace.status === 'idle').length
  const pendingUnits = Math.max(totalUnits - completedUnits, 0)

  return {
    totalUnits,
    completedUnits,
    runningWorkspaces,
    errorWorkspaces,
    idleWorkspaces,
    pendingUnits,
  }
})

const tradingCompletionRate = computed(() => {
  if (tradingTotals.value.totalUnits <= 0) return 0
  return Math.round((tradingTotals.value.completedUnits / tradingTotals.value.totalUnits) * 100)
})

const tradingOpsCards = computed<TradingOpsCard[]>(() => [
  {
    key: 'runtime',
    label: t('workspace.tradingRuntimeLabel'),
    value: tradingTotals.value.runningWorkspaces,
    helper: t('workspace.tradingRuntimeHelper', { idle: tradingTotals.value.idleWorkspaces }),
    tone: tradingTotals.value.runningWorkspaces > 0 ? 'success' : 'primary',
  },
  {
    key: 'units',
    label: t('workspace.tradingUnitsLabel'),
    value: `${tradingTotals.value.completedUnits}/${tradingTotals.value.totalUnits}`,
    helper: t('workspace.tradingUnitsHelper', { pending: tradingTotals.value.pendingUnits }),
    tone: tradingTotals.value.totalUnits > 0 ? 'success' : 'warning',
  },
  {
    key: 'attention',
    label: t('workspace.tradingAttentionLabel'),
    value: tradingTotals.value.errorWorkspaces,
    helper: t('workspace.tradingAttentionHelper'),
    tone: tradingTotals.value.errorWorkspaces > 0 ? 'danger' : 'success',
  },
  {
    key: 'completion',
    label: t('workspace.tradingCompletionLabel'),
    value: `${tradingCompletionRate.value}%`,
    helper: t('workspace.tradingCompletionHelper'),
    tone: tradingCompletionRate.value >= 80 ? 'success' : 'warning',
  },
])

const workspacePanelTitle = computed(() =>
  isTradingWorkspace.value
    ? t('workspace.tradingPanelTitle')
    : t('workspace.researchPanelTitle')
)

const workspacePanelMeta = computed(() =>
  selectedIds.value.length
    ? t('workspace.selectedCount', { count: selectedIds.value.length })
    : t('workspace.panelMeta', { count: store.workspaces.length })
)

watch(workspaceType, async (value) => {
  selectedIds.value = []
  await store.fetchWorkspaces(0, 50, value)
}, { immediate: true })

function goToDetail(id: string) {
  if (workspaceType.value === 'trading') {
    router.push(`/trading/${id}`)
    return
  }
  if (route.path.startsWith('/backtest')) {
    router.push(`/backtest/workspace/${id}`)
    return
  }
  router.push(APP_PATHS.research.workspace(id))
}

function toggleSelect(id: string) {
  const index = selectedIds.value.indexOf(id)
  if (index >= 0) {
    selectedIds.value.splice(index, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function onTableSelectionChange(rows: Workspace[]) {
  selectedIds.value = rows.map(row => row.id)
}

function handleResearchFlowAction(action: string) {
  if (action === 'create-workspace') {
    showCreateDialog.value = true
  }
}

function handleEdit(workspace: Workspace) {
  editingWorkspace.value = workspace
  showCreateDialog.value = true
}

async function handleDelete(workspace: Workspace) {
  try {
    await ElMessageBox.confirm(
      t('workspace.deleteConfirm', { name: workspace.name }),
      t('workspace.deleteConfirmTitle'),
      {
        type: 'warning',
        confirmButtonText: t('workspace.delete'),
        cancelButtonText: t('common.cancel'),
      },
    )
    await store.deleteWorkspace(workspace.id)
    selectedIds.value = selectedIds.value.filter(id => id !== workspace.id)
    ElMessage.success(t('workspace.deleted'))
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('messages.deleteFailed')))
    }
  }
}

async function handleBatchDelete() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(
      t('workspace.batchDeleteConfirm', { count: selectedIds.value.length }),
      t('workspace.batchDeleteConfirmTitle'),
      {
        type: 'warning',
      },
    )
    for (const id of [...selectedIds.value]) {
      await store.deleteWorkspace(id)
    }
    selectedIds.value = []
    ElMessage.success(t('workspace.deletedAll'))
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('messages.deleteFailed')))
    }
  }
}

function onSaved() {
  showCreateDialog.value = false
  editingWorkspace.value = null
  store.fetchWorkspaces(0, 50, workspaceType.value)
}

function statusTone(status: string) {
  const map: Record<string, string> = {
    idle: 'idle',
    running: 'running',
    completed: 'completed',
    error: 'error',
  }
  return map[status] || 'idle'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    idle: t('workspace.statusIdle'),
    running: t('workspace.statusRunning'),
    completed: t('workspace.statusCompleted'),
    error: t('workspace.statusError'),
  }
  return map[status] || status
}

function workspaceReadinessLabel(workspace: Workspace) {
  if (!workspace.unit_count) return t('workspace.tradingReadinessEmpty')
  if (workspace.status === 'error') return t('workspace.tradingReadinessReview')
  if (workspace.completed_count >= workspace.unit_count) return t('workspace.tradingReadinessReady')
  return t('workspace.tradingReadinessPartial')
}

function workspaceReadinessClass(workspace: Workspace) {
  if (!workspace.unit_count) return 'trading-readiness-pill--empty'
  if (workspace.status === 'error') return 'trading-readiness-pill--review'
  if (workspace.completed_count >= workspace.unit_count) return 'trading-readiness-pill--ready'
  return 'trading-readiness-pill--partial'
}

function formatTime(iso: string) {
  // Use browser's locale (respects `lang` attribute / locale store) so en-US
  // users see English-formatted dates instead of zh-CN literal output.
  return iso ? new Date(iso).toLocaleString() : ''
}

function updateHeaderActionsTargetReady() {
  if (typeof document === 'undefined') {
    headerActionsTargetReady.value = false
    return false
  }
  headerActionsTargetReady.value = document.getElementById('page-header-actions') !== null
  return headerActionsTargetReady.value
}

onMounted(async () => {
  await nextTick()
  if (!updateHeaderActionsTargetReady()) {
    headerTargetTimer = setInterval(() => {
      if (updateHeaderActionsTargetReady() && headerTargetTimer) {
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
.workspace-list-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--text-color-primary);
}

.button-icon {
  margin-right: 4px;
}

.workspace-header-action :deep(.el-icon),
.workspace-header-view :deep(.el-icon) {
  margin-right: 4px;
}

.workspace-hero,
.workspace-panel,
.trading-ops-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.workspace-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 20px;
}

.workspace-hero-copy {
  min-width: 0;
}

.workspace-kicker,
.workspace-panel-head span {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.workspace-hero-copy h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
}

.workspace-hero-copy p {
  max-width: 760px;
  margin: 8px 0 0;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.workspace-hero-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
}

.workspace-hero-actions :deep(.el-button),
.workspace-empty :deep(.el-button) {
  gap: 6px;
}

.workspace-metrics {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.workspace-metric {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.workspace-metric span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.workspace-metric strong {
  display: block;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.15;
}

.trading-ops-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.trading-ops-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.trading-ops-heading > div {
  min-width: 0;
}

.trading-ops-heading span:first-child {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
  text-transform: uppercase;
}

.trading-ops-heading h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 20px;
  font-weight: 760;
  line-height: 1.25;
}

.trading-ops-heading p {
  max-width: 760px;
  margin: 7px 0 0;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.trading-ops-pill,
.workspace-status-pill,
.trading-readiness-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  max-width: 100%;
  min-height: 26px;
  padding: 4px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 999px;
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
  white-space: nowrap;
}

.trading-ops-pill {
  flex: none;
  border-color: color-mix(in srgb, var(--primary-color) 40%, var(--border-color-light));
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
}

.trading-ops-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.trading-ops-card {
  display: grid;
  gap: 8px;
  min-width: 0;
  min-height: 116px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.trading-ops-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.3;
}

.trading-ops-card strong {
  color: var(--text-color-primary);
  font-size: 24px;
  line-height: 1.15;
}

.trading-ops-card small {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.trading-ops-card--success {
  border-color: color-mix(in srgb, var(--success-color) 46%, var(--border-color-light));
}

.trading-ops-card--warning {
  border-color: color-mix(in srgb, var(--warning-color) 40%, var(--border-color-light));
}

.trading-ops-card--danger {
  border-color: color-mix(in srgb, var(--danger-color) 46%, var(--border-color-light));
}

.workspace-panel {
  padding: 18px;
}

.workspace-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.workspace-panel-head div {
  min-width: 0;
}

.workspace-panel-head h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 740;
  line-height: 1.25;
}

.workspace-panel-head p {
  flex: 0 0 auto;
  max-width: 360px;
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
  text-align: right;
}

.workspace-state,
.workspace-empty {
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.workspace-state {
  gap: 10px;
  color: var(--text-color-secondary);
  font-size: 14px;
}

.workspace-loading {
  color: var(--primary-color);
  font-size: 28px;
}

.workspace-empty {
  flex-direction: column;
  gap: 12px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.workspace-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

.workspace-card-grid :deep(.workspace-card) {
  height: 100%;
  margin-bottom: 0;
}

.workspace-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
}

.workspace-table {
  min-width: 1080px;
}

.workspace-table :deep(.el-table__header-wrapper th),
.workspace-table :deep(.el-table__fixed-header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 700;
}

.workspace-table :deep(.el-table__body tr:hover > td) {
  background: var(--fill-color-light);
}

.workspace-table :deep(.el-table__body td),
.workspace-table :deep(.el-table__fixed-right td) {
  border-color: var(--border-color-light);
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.workspace-table :deep(.el-table__inner-wrapper::before) {
  background: var(--border-color-light);
}

.workspace-table :deep(.el-loading-mask) {
  background-color: color-mix(in srgb, var(--bg-color) 82%, transparent);
}

.workspace-status-pill--running {
  border-color: color-mix(in srgb, var(--warning-color) 54%, transparent);
  background: color-mix(in srgb, var(--warning-color) 12%, transparent);
  color: var(--warning-color);
}

.workspace-status-pill--completed {
  border-color: color-mix(in srgb, var(--success-color) 58%, transparent);
  background: color-mix(in srgb, var(--success-color) 12%, transparent);
  color: var(--success-color);
}

.workspace-status-pill--error {
  border-color: color-mix(in srgb, var(--danger-color) 58%, transparent);
  background: color-mix(in srgb, var(--danger-color) 12%, transparent);
  color: var(--danger-color);
}

.workspace-status-pill--idle {
  border-color: var(--border-color-light);
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
}

.trading-readiness-pill--ready {
  border-color: color-mix(in srgb, var(--success-color) 58%, transparent);
  background: color-mix(in srgb, var(--success-color) 12%, transparent);
  color: var(--success-color);
}

.trading-readiness-pill--partial {
  border-color: color-mix(in srgb, var(--warning-color) 54%, transparent);
  background: color-mix(in srgb, var(--warning-color) 12%, transparent);
  color: var(--warning-color);
}

.trading-readiness-pill--review {
  border-color: color-mix(in srgb, var(--danger-color) 58%, transparent);
  background: color-mix(in srgb, var(--danger-color) 12%, transparent);
  color: var(--danger-color);
}

.trading-readiness-pill--empty {
  border-color: var(--border-color-light);
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
}

@media (max-width: 1180px) {
  .workspace-hero {
    grid-template-columns: 1fr;
  }

  .workspace-hero-actions {
    justify-content: flex-start;
  }

  .workspace-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trading-ops-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .workspace-list-page {
    gap: 14px;
  }

  .workspace-hero,
  .workspace-panel {
    padding: 14px;
  }

  .workspace-hero-copy h1 {
    font-size: 22px;
  }

  .workspace-hero-actions,
  .workspace-panel-head,
  .trading-ops-heading {
    flex-direction: column;
  }

  .workspace-hero-actions :deep(.el-button),
  .workspace-empty :deep(.el-button) {
    width: 100%;
    justify-content: center;
  }

  .workspace-panel-head p {
    max-width: none;
    text-align: left;
  }

  .workspace-metrics,
  .workspace-card-grid,
  .trading-ops-grid {
    grid-template-columns: 1fr;
  }

  .trading-ops-pill {
    width: 100%;
  }
}
</style>
