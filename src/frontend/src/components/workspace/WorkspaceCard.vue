<template>
  <el-card
    class="workspace-card"
    :class="{ 'workspace-card--selected': selected }"
    shadow="hover"
  >
    <template #header>
      <div class="workspace-card-head">
        <div
          class="workspace-card-title"
          @click.stop="$emit('click')"
        >
          <el-checkbox
            class="workspace-card-select"
            :model-value="selected"
            @change="$emit('toggle-select')"
            @click.stop
          />
          <el-icon
            class="workspace-card-icon"
            aria-hidden="true"
          >
            <FolderOpened />
          </el-icon>
          <span class="workspace-card-name">{{ workspace.name }}</span>
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
      class="workspace-card-body"
      @click.stop="$emit('click')"
    >
      <p class="workspace-card-description">
        {{ workspace.description || t('workspace.noDescription') }}
      </p>
      <div class="workspace-card-counts">
        <span>{{ t('workspace.unitCountInline', { n: workspace.unit_count }) }}</span>
        <span>{{ t('workspace.completedInline', { n: workspace.completed_count }) }}</span>
      </div>
      <div class="workspace-card-times">
        <div>{{ t('workspace.createdInline') }}: {{ formatTime(workspace.created_at) }}</div>
        <div>{{ t('workspace.updatedInline') }}: {{ formatTime(workspace.updated_at) }}</div>
      </div>
    </div>

    <div class="workspace-card-actions">
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
.workspace-card {
  height: 100%;
  margin-bottom: 0;
  border-color: var(--border-color);
  background: var(--bg-color);
  color: var(--text-color-primary);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.workspace-card:hover {
  border-color: var(--info-border-color);
  transform: translateY(-1px);
}

.workspace-card--selected {
  box-shadow: 0 0 0 2px var(--primary-color), 0 10px 24px var(--shadow-color);
}

.workspace-card :deep(.el-card__header) {
  padding: 14px 16px;
  border-bottom-color: var(--border-color-light);
}

.workspace-card :deep(.el-card__body) {
  padding: 16px;
}

.workspace-card-head,
.workspace-card-title,
.workspace-card-counts,
.workspace-card-actions {
  display: flex;
  align-items: center;
}

.workspace-card-head {
  justify-content: space-between;
  gap: 10px;
}

.workspace-card-title {
  min-width: 0;
  gap: 8px;
}

.workspace-card-select,
.workspace-card-icon {
  flex: none;
}

.workspace-card-icon {
  color: var(--primary-color);
}

.workspace-card-name {
  overflow: hidden;
  min-width: 0;
  color: var(--text-color-primary);
  font-weight: 700;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-card-body {
  display: grid;
  gap: 10px;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.55;
}

.workspace-card-description {
  display: -webkit-box;
  min-height: 2.8em;
  margin: 0;
  color: var(--text-color-regular);
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.workspace-card-counts {
  justify-content: space-between;
  gap: 12px;
  color: var(--text-color-regular);
}

.workspace-card-counts span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.workspace-card-times {
  display: grid;
  gap: 3px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.workspace-card-actions {
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color-light);
}

@media (max-width: 520px) {
  .workspace-card :deep(.el-card__header),
  .workspace-card :deep(.el-card__body) {
    padding: 14px;
  }

  .workspace-card-actions {
    justify-content: flex-end;
  }
}
</style>
