<template>
  <el-card
    class="workspace-card mb-4 cursor-pointer transition-shadow hover:shadow-lg"
    :class="{ 'ring-2 ring-blue-400': selected }"
    shadow="hover"
  >
    <template #header>
      <div class="flex items-center justify-between">
        <div
          class="flex items-center gap-2 min-w-0"
          @click.stop="$emit('click')"
        >
          <el-checkbox
            :model-value="selected"
            @change="$emit('toggle-select')"
            @click.stop
          />
          <el-icon
            class="text-blue-500 flex-shrink-0"
            aria-hidden="true"
          >
            <FolderOpened />
          </el-icon>
          <span class="font-medium truncate">{{ workspace.name }}</span>
        </div>
        <el-tag
          :type="statusTagType"
          size="small"
        >
          {{ statusLabel }}
        </el-tag>
      </div>
    </template>

    <div
      class="space-y-2 text-sm text-gray-600"
      @click.stop="$emit('click')"
    >
      <p class="line-clamp-2 min-h-[2.5em]">
        {{ workspace.description || t('workspace.noDescription') }}
      </p>
      <div class="flex items-center justify-between">
        <span>{{ t('workspace.unitCountInline', { n: workspace.unit_count }) }}</span>
        <span>{{ t('workspace.completedInline', { n: workspace.completed_count }) }}</span>
      </div>
      <div class="text-xs text-gray-400 space-y-0.5">
        <div>{{ t('workspace.createdInline') }}: {{ formatTime(workspace.created_at) }}</div>
        <div>{{ t('workspace.updatedInline') }}: {{ formatTime(workspace.updated_at) }}</div>
      </div>
    </div>

    <div class="flex justify-end gap-2 mt-3 pt-3 border-t border-gray-100">
      <el-button
        size="small"
        @click.stop="$emit('edit')"
      >
        {{ t('workspace.edit') }}
      </el-button>
      <el-button
        size="small"
        type="danger"
        plain
        @click.stop="$emit('delete')"
      >
        {{ t('workspace.delete') }}
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FolderOpened } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import type { Workspace } from '@/types/workspace'
import type { TagType } from '@/constants/strategy'

const { t } = useI18n()

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

const statusTagType = computed<TagType>(() => {
  const map: Record<string, TagType> = { idle: 'info', running: 'warning', completed: 'success', error: 'danger' }
  return map[props.workspace.status] || 'info'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    idle: t('workspace.statusIdle'),
    running: t('workspace.statusRunning'),
    completed: t('workspace.statusCompleted'),
    error: t('workspace.statusError'),
  }
  return map[props.workspace.status] || props.workspace.status
})

function formatTime(iso: string) {
  if (!iso) return ''
  // Use browser locale instead of hardcoded zh-CN so en-US users see English dates
  return new Date(iso).toLocaleString()
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
