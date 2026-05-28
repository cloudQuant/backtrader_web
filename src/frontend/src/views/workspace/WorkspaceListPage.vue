<template>
  <div class="workspace-list-page">
    <teleport
      v-if="headerActionsTargetReady"
      to="#page-header-actions"
    >
      <el-button
        type="primary"
        :aria-label="t('workspace.createNew')"
        @click="showCreateDialog = true"
      >
        <el-icon
          class="mr-1"
          aria-hidden="true"
        >
          <Plus />
        </el-icon>
        {{ t('workspace.createNew') }}
      </el-button>
      <el-button
        :disabled="!selectedIds.length"
        type="danger"
        plain
        :aria-label="t('workspace.deleteSelected')"
        @click="handleBatchDelete"
      >
        <el-icon
          class="mr-1"
          aria-hidden="true"
        >
          <Delete />
        </el-icon>
        {{ t('workspace.deleteSelected') }}
      </el-button>
      <el-radio-group
        v-model="viewMode"
        size="default"
        :aria-label="t('common.action')"
      >
        <el-radio-button
          value="card"
          :aria-label="'card view'"
        >
          <el-icon aria-hidden="true">
            <Grid />
          </el-icon>
        </el-radio-button>
        <el-radio-button
          value="table"
          :aria-label="'table view'"
        >
          <el-icon aria-hidden="true">
            <List />
          </el-icon>
        </el-radio-button>
      </el-radio-group>
    </teleport>

    <div
      v-if="store.loading"
      class="flex justify-center py-20"
    >
      <el-icon class="is-loading text-3xl text-blue-500">
        <Loading />
      </el-icon>
    </div>

    <el-empty
      v-else-if="store.workspaces.length === 0"
      :description="emptyDescription"
    />

    <el-row
      v-else-if="viewMode === 'card'"
      :gutter="16"
    >
      <el-col
        v-for="ws in store.workspaces"
        :key="ws.id"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="6"
      >
        <WorkspaceCard
          :workspace="ws"
          :selected="selectedIds.includes(ws.id)"
          @click="goToDetail(ws.id)"
          @edit="handleEdit(ws)"
          @delete="handleDelete(ws)"
          @toggle-select="toggleSelect(ws.id)"
        />
      </el-col>
    </el-row>

    <el-table
      v-else
      :data="store.workspaces"
      stripe
      class="cursor-pointer"
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
          <el-tag
            :type="statusTagType(row.status)"
            size="small"
          >
            {{ statusLabel(row.status) }}
          </el-tag>
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
import { useWorkspaceStore } from '@/stores/workspace'
import type { ViewMode, Workspace, WorkspaceType } from '@/types/workspace'
import type { TagType } from '@/constants/strategy'
import CreateWorkspaceDialog from '@/components/workspace/CreateWorkspaceDialog.vue'
import WorkspaceCard from '@/components/workspace/WorkspaceCard.vue'

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

const emptyDescription = computed(() =>
  workspaceType.value === 'trading'
    ? t('workspace.emptyTrading')
    : t('workspace.emptyResearch')
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
  router.push(`/workspace/${id}`)
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

function statusTagType(status: string): TagType {
  const map: Record<string, TagType> = {
    idle: 'info',
    running: 'warning',
    completed: 'success',
    error: 'danger',
  }
  return map[status] || 'info'
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
