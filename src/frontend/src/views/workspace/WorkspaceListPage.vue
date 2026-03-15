<template>
  <div class="workspace-list-page">
    <teleport to="#page-header-actions">
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon class="mr-1"><Plus /></el-icon>
        新建工作区
      </el-button>
      <el-button
        :disabled="!selectedIds.length"
        type="danger"
        plain
        @click="handleBatchDelete"
      >
        <el-icon class="mr-1"><Delete /></el-icon>
        删除工作区
      </el-button>
      <el-radio-group v-model="viewMode" size="default">
        <el-radio-button value="card">
          <el-icon><Grid /></el-icon>
        </el-radio-button>
        <el-radio-button value="table">
          <el-icon><List /></el-icon>
        </el-radio-button>
      </el-radio-group>
    </teleport>

    <!-- Loading -->
    <div v-if="store.loading" class="flex justify-center py-20">
      <el-icon class="is-loading text-3xl text-blue-500"><Loading /></el-icon>
    </div>

    <!-- Empty state -->
    <el-empty
      v-else-if="store.workspaces.length === 0"
      description="暂无工作区，点击「新建工作区」开始策略研究"
    />

    <!-- Card view -->
    <el-row v-else-if="viewMode === 'card'" :gutter="16">
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

    <!-- Table view -->
    <el-table
      v-else
      :data="store.workspaces"
      @selection-change="onTableSelectionChange"
      @row-click="(row: Workspace) => goToDetail(row.id)"
      stripe
      class="cursor-pointer"
    >
      <el-table-column type="selection" width="50" />
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="策略单元" width="100" align="center">
        <template #default="{ row }">{{ row.unit_count }}</template>
      </el-table-column>
      <el-table-column label="已完成" width="80" align="center">
        <template #default="{ row }">{{ row.completed_count }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click.stop="handleEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click.stop="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create / Edit Dialog -->
    <CreateWorkspaceDialog
      v-model="showCreateDialog"
      :workspace="editingWorkspace"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Grid, List, Loading } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'
import type { Workspace, ViewMode } from '@/types/workspace'
import WorkspaceCard from '@/components/workspace/WorkspaceCard.vue'
import CreateWorkspaceDialog from '@/components/workspace/CreateWorkspaceDialog.vue'

const router = useRouter()
const store = useWorkspaceStore()

const viewMode = ref<ViewMode>('card')
const selectedIds = ref<string[]>([])
const showCreateDialog = ref(false)
const editingWorkspace = ref<Workspace | null>(null)

onMounted(() => {
  store.fetchWorkspaces()
})

function goToDetail(id: string) {
  router.push(`/backtest/workspace/${id}`)
}

function toggleSelect(id: string) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function onTableSelectionChange(rows: Workspace[]) {
  selectedIds.value = rows.map(r => r.id)
}

function handleEdit(ws: Workspace) {
  editingWorkspace.value = ws
  showCreateDialog.value = true
}

async function handleDelete(ws: Workspace) {
  try {
    await ElMessageBox.confirm(`确认删除工作区「${ws.name}」？此操作不可撤销。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await store.deleteWorkspace(ws.id)
    selectedIds.value = selectedIds.value.filter(id => id !== ws.id)
    ElMessage.success('工作区已删除')
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(e, '删除失败'))
    }
  }
}

async function handleBatchDelete() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 个工作区？`, '批量删除确认', {
      type: 'warning',
    })
    for (const id of [...selectedIds.value]) {
      await store.deleteWorkspace(id)
    }
    selectedIds.value = []
    ElMessage.success('已删除')
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(e, '删除失败'))
    }
  }
}

function onSaved() {
  showCreateDialog.value = false
  editingWorkspace.value = null
  store.fetchWorkspaces()
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    idle: 'info',
    running: 'warning',
    completed: 'success',
    error: 'danger',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    idle: '空闲',
    running: '运行中',
    completed: '已完成',
    error: '异常',
  }
  return map[status] || status
}

function formatTime(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}
</script>
