<template>
  <el-form
    :model="config"
    label-width="120px"
    class="sync-config-form"
    data-test="sync-config-form"
  >
    <div class="config-section-title">
      {{ t('dataPages.syncSecMode') }}
    </div>
    <div class="form-grid">
      <el-form-item :label="t('dataPages.syncFormMethod')">
        <el-input
          :value="t('dataPages.syncMethodValue')"
          disabled
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormMode')">
        <el-select
          :model-value="syncMode"
          class="full-width"
          @update:model-value="(v: string) => emit('update:syncMode', v as SyncMode)"
        >
          <el-option
            :label="t('dataPages.syncModeFull')"
            value="full"
          />
          <el-option
            :label="t('dataPages.syncModeSchemaOnly')"
            value="schema_only"
          />
          <el-option
            :label="t('dataPages.syncModeDataOnly')"
            value="data_only"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormParallel')">
        <el-input-number
          :model-value="config.sync_parallel_workers"
          class="full-width"
          :min="1"
          :max="16"
          @update:model-value="
            (value: number | undefined) => updateConfigField('sync_parallel_workers', value ?? 1)
          "
        />
      </el-form-item>
    </div>

    <div class="config-section-title">
      {{ t('dataPages.syncSecLocal') }}
    </div>
    <div class="form-grid">
      <el-form-item :label="t('dataPages.syncFormLocalHost')">
        <el-input
          :model-value="config.local_mysql_host"
          placeholder="127.0.0.1"
          @update:model-value="(value: string) => updateConfigField('local_mysql_host', value)"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormLocalPort')">
        <el-input-number
          :model-value="config.local_mysql_port"
          class="full-width"
          :min="1"
          :max="65535"
          @update:model-value="
            (value: number | undefined) => updateConfigField('local_mysql_port', value ?? 1)
          "
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormLocalUser')">
        <el-input
          :model-value="config.local_mysql_user"
          placeholder="root"
          @update:model-value="(value: string) => updateConfigField('local_mysql_user', value)"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormLocalPwd')">
        <el-input
          :model-value="config.local_mysql_password"
          show-password
          :placeholder="t('dataPages.syncLocalPwdPh')"
          @update:model-value="
            (value: string) => updateConfigField('local_mysql_password', value)
          "
        />
      </el-form-item>
    </div>

    <div class="config-section-title">
      {{ t('dataPages.syncSecRemote') }}
    </div>
    <div class="form-grid">
      <el-form-item :label="t('dataPages.syncFormRemoteHost')">
        <el-input
          :model-value="config.remote_mysql_host"
          placeholder="43.167.221.188"
          @update:model-value="(value: string) => updateConfigField('remote_mysql_host', value)"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormRemotePort')">
        <el-input-number
          :model-value="config.remote_mysql_port"
          class="full-width"
          :min="1"
          :max="65535"
          @update:model-value="
            (value: number | undefined) => updateConfigField('remote_mysql_port', value ?? 1)
          "
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormRemoteUser')">
        <el-input
          :model-value="config.remote_mysql_user"
          placeholder="root"
          @update:model-value="(value: string) => updateConfigField('remote_mysql_user', value)"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormRemotePwd')">
        <el-input
          :model-value="config.remote_mysql_password"
          show-password
          :placeholder="t('dataPages.syncRemotePwdPh')"
          @update:model-value="
            (value: string) => updateConfigField('remote_mysql_password', value)
          "
        />
      </el-form-item>
    </div>

    <div class="config-section-title">
      {{ t('dataPages.syncSecScope') }}
    </div>
    <div class="form-grid single-column">
      <el-form-item :label="t('dataPages.syncFormDatabases')">
        <el-input
          :model-value="syncDatabasesInput"
          type="textarea"
          :rows="2"
          :placeholder="t('dataPages.syncDatabasesPh')"
          @update:model-value="(v: string) => emit('update:syncDatabasesInput', v)"
        />
      </el-form-item>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SyncConfig, SyncMode } from '@/types'

const { t } = useI18n()

const props = defineProps<{
  config: SyncConfig
  syncMode: SyncMode
  syncDatabasesInput: string
}>()

const emit = defineEmits<{
  (e: 'update:config', value: SyncConfig): void
  (e: 'update:syncMode', value: SyncMode): void
  (e: 'update:syncDatabasesInput', value: string): void
}>()

function updateConfigField<K extends keyof SyncConfig>(
  field: K,
  value: SyncConfig[K]
) {
  emit('update:config', { ...props.config, [field]: value })
}
</script>

<style scoped>
.sync-config-form {
  display: grid;
  gap: 18px;
}

.config-section-title {
  margin: 2px 0 -6px;
  color: var(--text-color-primary);
  font-size: 14px;
  font-weight: 780;
  line-height: 1.25;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
  min-width: 0;
}

.form-grid.single-column {
  grid-template-columns: 1fr;
}

.sync-config-form :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 0;
}

.sync-config-form :deep(.el-form-item__label) {
  color: var(--text-color-secondary);
  font-weight: 650;
}

.sync-config-form :deep(.el-input__wrapper),
.sync-config-form :deep(.el-select__wrapper),
.sync-config-form :deep(.el-textarea__inner) {
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
}

.full-width {
  width: 100%;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
