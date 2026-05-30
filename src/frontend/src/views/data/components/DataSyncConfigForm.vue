<template>
  <el-form
    :model="config"
    label-width="120px"
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
          v-model="config.sync_parallel_workers"
          class="full-width"
          :min="1"
          :max="16"
        />
      </el-form-item>
    </div>

    <div class="config-section-title">
      {{ t('dataPages.syncSecLocal') }}
    </div>
    <div class="form-grid">
      <el-form-item :label="t('dataPages.syncFormLocalHost')">
        <el-input
          v-model="config.local_mysql_host"
          placeholder="127.0.0.1"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormLocalPort')">
        <el-input-number
          v-model="config.local_mysql_port"
          class="full-width"
          :min="1"
          :max="65535"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormLocalUser')">
        <el-input
          v-model="config.local_mysql_user"
          placeholder="root"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormLocalPwd')">
        <el-input
          v-model="config.local_mysql_password"
          show-password
          :placeholder="t('dataPages.syncLocalPwdPh')"
        />
      </el-form-item>
    </div>

    <div class="config-section-title">
      {{ t('dataPages.syncSecRemote') }}
    </div>
    <div class="form-grid">
      <el-form-item :label="t('dataPages.syncFormRemoteHost')">
        <el-input
          v-model="config.remote_mysql_host"
          placeholder="43.167.221.188"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormRemotePort')">
        <el-input-number
          v-model="config.remote_mysql_port"
          class="full-width"
          :min="1"
          :max="65535"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormRemoteUser')">
        <el-input
          v-model="config.remote_mysql_user"
          placeholder="root"
        />
      </el-form-item>
      <el-form-item :label="t('dataPages.syncFormRemotePwd')">
        <el-input
          v-model="config.remote_mysql_password"
          show-password
          :placeholder="t('dataPages.syncRemotePwdPh')"
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

// ``config`` is a reactive object owned by the parent; Vue 3 passes it by
// reference so ``v-model="config.x"`` mutates the same object the parent reads.
// ``syncMode`` / ``syncDatabasesInput`` are parent refs, surfaced as v-model props.
defineProps<{
  config: SyncConfig
  syncMode: SyncMode
  syncDatabasesInput: string
}>()

const emit = defineEmits<{
  (e: 'update:syncMode', value: SyncMode): void
  (e: 'update:syncDatabasesInput', value: string): void
}>()
</script>
