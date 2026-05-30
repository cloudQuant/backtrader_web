<template>
  <el-card v-if="tasks.length > 0">
    <template #header>
      <div class="page-title small">
        {{ t('dataPages.syncProgressTitle') }}
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
