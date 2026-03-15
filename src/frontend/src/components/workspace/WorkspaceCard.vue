<template>
  <el-card
    class="workspace-card mb-4 cursor-pointer transition-shadow hover:shadow-lg"
    :class="{ 'ring-2 ring-blue-400': selected }"
    shadow="hover"
  >
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 min-w-0" @click.stop="$emit('click')">
          <el-checkbox
            :model-value="selected"
            @change="$emit('toggle-select')"
            @click.stop
          />
          <el-icon class="text-blue-500 flex-shrink-0"><FolderOpened /></el-icon>
          <span class="font-medium truncate">{{ workspace.name }}</span>
        </div>
        <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
      </div>
    </template>

    <div @click.stop="$emit('click')" class="space-y-2 text-sm text-gray-600">
      <p class="line-clamp-2 min-h-[2.5em]">{{ workspace.description || '暂无描述' }}</p>
      <div class="flex items-center justify-between">
        <span>策略单元: {{ workspace.unit_count }}</span>
        <span>已完成: {{ workspace.completed_count }}</span>
      </div>
      <div class="text-xs text-gray-400 space-y-0.5">
        <div>创建: {{ formatTime(workspace.created_at) }}</div>
        <div>更新: {{ formatTime(workspace.updated_at) }}</div>
      </div>
    </div>

    <div class="flex justify-end gap-2 mt-3 pt-3 border-t border-gray-100">
      <el-button size="small" @click.stop="$emit('edit')">编辑</el-button>
      <el-button size="small" type="danger" plain @click.stop="$emit('delete')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FolderOpened } from '@element-plus/icons-vue'
import type { Workspace } from '@/types/workspace'

const props = defineProps<{
  workspace: Workspace
  selected: boolean
}>()

defineEmits<{
  click: []
  edit: []
  delete: []
  'toggle-select': []
}>()

const statusTagType = computed(() => {
  const map: Record<string, string> = { idle: 'info', running: 'warning', completed: 'success', error: 'danger' }
  return map[props.workspace.status] || 'info'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '空闲', running: '运行中', completed: '已完成', error: '异常' }
  return map[props.workspace.status] || props.workspace.status
})

function formatTime(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
