<template>
  <div class="dual-grid">
    <el-card>
      <template #header>
        <div class="section-header">
          <div>
            <div class="page-title small">
              {{ t('dataPages.syncUploadTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.syncUploadDesc') }}
            </div>
          </div>
          <el-button
            type="primary"
            :loading="submittingBulkUpload"
            @click="emit('sync', 'upload', databaseNames)"
          >
            {{ t('dataPages.syncUploadAll') }}
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="loadingDatabases"
        :data="databaseRows"
        stripe
      >
        <el-table-column
          prop="name"
          :label="t('dataPages.syncColDatabase')"
          min-width="160"
        />
        <el-table-column
          :label="t('dataPages.syncColLocalSize')"
          width="120"
        >
          <template #default="{ row }">
            {{ row.local.exists ? row.local.size_display : t('dataPages.syncStateNotExists') }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncColRemoteState')"
          min-width="160"
        >
          <template #default="{ row }">
            {{ formatRemoteState(row) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncColActions')"
          width="120"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="emit('sync', 'upload', [row.name])"
            >
              {{ t('dataPages.syncActionUpload') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="section-header">
          <div>
            <div class="page-title small">
              {{ t('dataPages.syncDownloadTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.syncDownloadDesc') }}
            </div>
          </div>
          <el-button
            :loading="submittingBulkDownload"
            @click="emit('sync', 'download', databaseNames)"
          >
            {{ t('dataPages.syncDownloadAll') }}
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="loadingDatabases"
        :data="databaseRows"
        stripe
      >
        <el-table-column
          prop="name"
          :label="t('dataPages.syncColDatabase')"
          min-width="160"
        />
        <el-table-column
          :label="t('dataPages.syncColRemoteSize')"
          width="120"
        >
          <template #default="{ row }">
            {{ row.remote.exists ? row.remote.size_display : t('dataPages.syncStateNotExists') }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncColLocalState')"
          min-width="160"
        >
          <template #default="{ row }">
            {{ formatLocalState(row) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.syncColActions')"
          width="120"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="emit('sync', 'download', [row.name])"
            >
              {{ t('dataPages.syncActionDownload') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DatabaseSyncInfo, SyncDirection } from '@/types'

const { t } = useI18n()

defineProps<{
  databaseRows: DatabaseSyncInfo[]
  databaseNames: string[]
  loadingDatabases: boolean
  submittingBulkUpload: boolean
  submittingBulkDownload: boolean
  formatRemoteState: (row: DatabaseSyncInfo) => string
  formatLocalState: (row: DatabaseSyncInfo) => string
}>()

const emit = defineEmits<{
  (e: 'sync', direction: SyncDirection, databases: string[]): void
}>()
</script>
