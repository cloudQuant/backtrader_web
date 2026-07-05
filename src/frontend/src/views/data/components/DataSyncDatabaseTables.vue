<template>
  <div
    class="sync-database-grid"
    data-test="sync-database-grid"
  >
    <el-card class="sync-direction-card">
      <template #header>
        <div class="sync-direction-heading">
          <div>
            <div class="sync-direction-kicker">
              {{ t('dataPages.syncUploadKicker') }}
            </div>
            <div class="sync-direction-title">
              {{ t('dataPages.syncUploadTitle') }}
            </div>
            <p>{{ t('dataPages.syncUploadDesc') }}</p>
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
        class="sync-database-table"
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

      <div class="sync-database-mobile-list">
        <article
          v-for="row in databaseRows"
          :key="`upload-${row.name}`"
          class="sync-database-card"
        >
          <strong>{{ row.name }}</strong>
          <span>{{ t('dataPages.syncColLocalSize') }}: {{ row.local.exists ? row.local.size_display : t('dataPages.syncStateNotExists') }}</span>
          <span>{{ t('dataPages.syncColRemoteState') }}: {{ formatRemoteState(row) }}</span>
          <el-button
            size="small"
            type="primary"
            @click="emit('sync', 'upload', [row.name])"
          >
            {{ t('dataPages.syncActionUpload') }}
          </el-button>
        </article>
      </div>
    </el-card>

    <el-card class="sync-direction-card">
      <template #header>
        <div class="sync-direction-heading">
          <div>
            <div class="sync-direction-kicker">
              {{ t('dataPages.syncDownloadKicker') }}
            </div>
            <div class="sync-direction-title">
              {{ t('dataPages.syncDownloadTitle') }}
            </div>
            <p>{{ t('dataPages.syncDownloadDesc') }}</p>
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
        class="sync-database-table"
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

      <div class="sync-database-mobile-list">
        <article
          v-for="row in databaseRows"
          :key="`download-${row.name}`"
          class="sync-database-card"
        >
          <strong>{{ row.name }}</strong>
          <span>{{ t('dataPages.syncColRemoteSize') }}: {{ row.remote.exists ? row.remote.size_display : t('dataPages.syncStateNotExists') }}</span>
          <span>{{ t('dataPages.syncColLocalState') }}: {{ formatLocalState(row) }}</span>
          <el-button
            size="small"
            @click="emit('sync', 'download', [row.name])"
          >
            {{ t('dataPages.syncActionDownload') }}
          </el-button>
        </article>
      </div>
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

<style scoped>
.sync-database-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.sync-direction-card {
  min-width: 0;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
}

.sync-direction-card :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.sync-direction-card :deep(.el-card__body) {
  padding: 18px;
}

.sync-direction-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.sync-direction-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.sync-direction-title {
  margin-top: 4px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.sync-direction-heading p {
  margin: 4px 0 0;
  color: var(--text-color-regular);
  font-size: 13px;
  line-height: 1.5;
}

.sync-database-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.sync-database-mobile-list {
  display: none;
  gap: 12px;
}

.sync-database-card {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.sync-database-card strong {
  color: var(--text-color-primary);
  line-height: 1.3;
}

.sync-database-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

@media (max-width: 1100px) {
  .sync-database-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .sync-direction-heading {
    display: grid;
  }

  .sync-database-table {
    display: none;
  }

  .sync-database-mobile-list {
    display: grid;
  }
}
</style>
