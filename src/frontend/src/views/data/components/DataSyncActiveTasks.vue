<template>
  <el-card
    v-if="tasks.length > 0"
    class="sync-active-card"
    data-test="sync-active-card"
  >
    <template #header>
      <div class="sync-active-heading">
        <div>
          <div class="sync-active-kicker">
            {{ t('dataPages.syncProgressKicker') }}
          </div>
          <div class="sync-active-title">
            {{ t('dataPages.syncProgressTitle') }}
          </div>
        </div>
      </div>
    </template>

    <div class="task-list">
      <div
        v-for="task in tasks"
        :key="task.task_id"
        class="task-item"
      >
        <div class="task-top">
          <div>
            <div class="task-title">
              {{ task.direction === 'upload' ? t('dataPages.syncDirUpload') : t('dataPages.syncDirDownload') }}
              <span class="task-db">{{ task.current_database || task.databases.join(', ') }}</span>
            </div>
            <div class="task-subtitle">
              {{ task.message }}
            </div>
          </div>
          <el-tag :type="task.status === 'failed' ? 'danger' : task.status === 'completed' ? 'success' : 'warning'">
            {{ statusLabel(task.status) }}
          </el-tag>
        </div>
        <el-progress
          :percentage="task.progress_pct"
          :status="task.status === 'failed' ? 'exception' : undefined"
        />
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SyncTaskStatus } from '@/types'

const { t } = useI18n()

defineProps<{
  tasks: SyncTaskStatus[]
  statusLabel: (status: SyncTaskStatus['status']) => string
}>()
</script>

<style scoped>
.sync-active-card {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.sync-active-card :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.sync-active-card :deep(.el-card__body) {
  padding: 18px;
}

.sync-active-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.sync-active-title {
  margin-top: 4px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.task-list {
  display: grid;
  gap: 12px;
}

.task-item {
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.task-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.task-title {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
}

.task-db {
  margin-left: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.task-subtitle {
  margin-top: 4px;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
}

@media (max-width: 640px) {
  .task-top {
    display: grid;
  }
}
</style>
