<template>
  <div class="workspace-detail-page">
    <teleport to="#page-header-title-extra">
      <span class="text-gray-400">/</span>
      <span class="text-base text-gray-600 dark:text-gray-300 truncate max-w-[420px]">
        {{ store.currentWorkspace?.name || '加载中...' }}
      </span>
    </teleport>

    <teleport to="#page-header-actions">
      <el-button
        v-if="store.currentWorkspace"
        size="small"
        @click="showDataSourceDialog = true"
      >
        <el-icon class="mr-1"><DataLine /></el-icon>
        数据源
        <span class="ml-1 text-xs text-gray-500">{{ dataSourceTypeLabel }}</span>
      </el-button>
    </teleport>

    <!-- Loading -->
    <div v-if="store.loading && !store.currentWorkspace" class="flex justify-center py-20">
      <el-icon class="is-loading text-3xl text-blue-500"><Loading /></el-icon>
    </div>

    <!-- Not found -->
    <el-empty v-else-if="!store.currentWorkspace" description="工作区不存在或无权访问" />

    <!-- Content -->
    <template v-else>
      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane label="策略单元" name="units">
          <WorkspaceUnitsTab
            :workspace-id="workspaceId"
            :active="activeTab === 'units'"
            :toolbar-in-header="true"
            @switch-tab="(t: string) => activeTab = t"
          />
        </el-tab-pane>
        <el-tab-pane label="优化结果" name="optimization">
          <WorkspaceOptimizationTab
            :workspace-id="workspaceId"
            :active="activeTab === 'optimization'"
            :toolbar-in-header="true"
          />
        </el-tab-pane>
        <el-tab-pane label="组合报告" name="report">
          <WorkspaceReportTab
            :workspace-id="workspaceId"
            :active="activeTab === 'report'"
            :toolbar-in-header="true"
          />
        </el-tab-pane>
      </el-tabs>

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
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { DataLine, Loading } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import WorkspaceUnitsTab from '@/components/workspace/WorkspaceUnitsTab.vue'
import WorkspaceOptimizationTab from '@/components/workspace/WorkspaceOptimizationTab.vue'
import WorkspaceReportTab from '@/components/workspace/WorkspaceReportTab.vue'
import WorkspaceDataSourceDialog from '@/components/workspace/WorkspaceDataSourceDialog.vue'

const route = useRoute()
const store = useWorkspaceStore()

const workspaceId = route.params.id as string
const activeTab = ref('units')
const showDataSourceDialog = ref(false)

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

onMounted(async () => {
  await store.fetchWorkspace(workspaceId)
  await store.fetchUnits(workspaceId)
})
</script>
