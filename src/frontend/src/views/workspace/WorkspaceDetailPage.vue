<template>
  <div class="workspace-detail-page">
    <teleport to="#page-header-title-extra">
      <span class="text-gray-400">/</span>
      <el-tag
        v-if="workspaceType === 'trading'"
        size="small"
        type="warning"
        effect="plain"
      >
        策略交易
      </el-tag>
      <span class="text-base text-gray-600 dark:text-gray-300 truncate max-w-[420px]">
        {{ store.currentWorkspace?.name || '加载中...' }}
      </span>
    </teleport>

    <teleport to="#page-header-actions">
      <el-button
        v-if="store.currentWorkspace && workspaceType !== 'trading'"
        size="small"
        @click="showDataSourceDialog = true"
      >
        <el-icon class="mr-1">
          <DataLine />
        </el-icon>
        数据源
        <span class="ml-1 text-xs text-gray-500">{{ dataSourceTypeLabel }}</span>
      </el-button>
    </teleport>

    <div
      v-if="store.loading && !store.currentWorkspace"
      class="flex justify-center py-20"
    >
      <el-icon class="is-loading text-3xl text-blue-500">
        <Loading />
      </el-icon>
    </div>

    <el-empty
      v-else-if="!store.currentWorkspace"
      description="工作区不存在或无权访问"
    />

    <template v-else>
      <el-tabs
        v-model="activeTab"
        type="border-card"
        @tab-remove="handleTabRemove"
      >
        <el-tab-pane
          label="策略单元"
          name="units"
        >
          <TradingWorkspaceUnitsTab
            v-if="workspaceType === 'trading'"
            :workspace-id="workspaceId"
            :active="activeTab === 'units'"
            :toolbar-in-header="true"
            @switch-tab="handleSwitchTab"
          />
          <WorkspaceUnitsTab
            v-else
            :workspace-id="workspaceId"
            :active="activeTab === 'units'"
            :toolbar-in-header="true"
            @switch-tab="handleSwitchTab"
          />
        </el-tab-pane>
        <el-tab-pane
          v-if="showOptTab"
          label="优化结果"
          name="optimization"
          closable
        >
          <WorkspaceOptimizationTab
            :workspace-id="workspaceId"
            :active="activeTab === 'optimization'"
            :toolbar-in-header="true"
            :initial-unit-id="initialOptUnitId"
          />
        </el-tab-pane>
        <el-tab-pane
          v-if="showReportTab"
          label="组合报告"
          name="report"
          closable
        >
          <WorkspaceReportTab
            :workspace-id="workspaceId"
            :active="activeTab === 'report'"
            :toolbar-in-header="true"
            :initial-unit-id="initialReportUnitId"
            :initial-unit-ids="initialReportUnitIds"
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
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { DataLine, Loading } from '@element-plus/icons-vue'
import TradingWorkspaceUnitsTab from '@/components/workspace/TradingWorkspaceUnitsTab.vue'
import WorkspaceDataSourceDialog from '@/components/workspace/WorkspaceDataSourceDialog.vue'
import WorkspaceOptimizationTab from '@/components/workspace/WorkspaceOptimizationTab.vue'
import WorkspaceReportTab from '@/components/workspace/WorkspaceReportTab.vue'
import WorkspaceUnitsTab from '@/components/workspace/WorkspaceUnitsTab.vue'
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceType } from '@/types/workspace'

const route = useRoute()
const store = useWorkspaceStore()

const workspaceId = computed(() => route.params.id as string)
const activeTab = ref('units')
const showDataSourceDialog = ref(false)
const showOptTab = ref(false)
const showReportTab = ref(false)

const initialOptUnitId = ref('')
const initialReportUnitId = ref('')
const initialReportUnitIds = ref<string[]>([])

const workspaceType = computed<WorkspaceType>(() =>
  store.currentWorkspace?.workspace_type
  ?? (route.meta.workspaceType === 'trading' ? 'trading' : 'research')
)

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

watch(workspaceId, async (id) => {
  activeTab.value = 'units'
  showOptTab.value = false
  showReportTab.value = false
  await store.fetchWorkspace(id)
  await store.fetchUnits(id)
}, { immediate: true })
</script>
