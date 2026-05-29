<template>
  <div class="space-y-6">
    <el-page-header
      :title="t('dataPages.detailGoBack')"
      @back="goBack"
    >
      <template #content>
        <span>{{ script?.script_name || t('dataPages.scriptDetailFallback') }}</span>
      </template>
    </el-page-header>

    <el-card v-loading="loading">
      <template #header>
        <div class="detail-header">
          <div>
            <div class="detail-title">
              {{ script?.script_name || t('dataPages.scriptDetailLoading') }}
            </div>
            <div class="detail-subtitle">
              {{ script?.script_id }}
            </div>
          </div>
          <div class="detail-tags">
            <el-tag v-if="script">
              {{ script.category }}
            </el-tag>
            <el-tag
              v-if="script"
              :type="script.is_active ? 'success' : 'warning'"
            >
              {{ script.is_active ? t('dataPages.scriptDetailEnabled') : t('dataPages.scriptDetailDisabled') }}
            </el-tag>
          </div>
        </div>
      </template>

      <el-descriptions
        v-if="script"
        :column="2"
        border
      >
        <el-descriptions-item :label="t('dataPages.scriptDetailModulePath')">
          {{ script.module_path || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('dataPages.scriptDetailFuncName')">
          {{ script.function_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('dataPages.scriptDetailTargetTable')">
          {{ script.target_table || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('dataPages.scriptDetailFrequency')">
          {{ script.frequency || '-' }}
        </el-descriptions-item>
        <el-descriptions-item
          :label="t('dataPages.scriptDetailDescription')"
          :span="2"
        >
          {{ script.description || t('dataPages.scriptDetailNoDesc') }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="run-panel">
        <div class="section-title">
          {{ t('dataPages.scriptDetailManualRun') }}
        </div>
        <el-alert
          type="info"
          :closable="false"
          show-icon
        >
          {{ t('dataPages.scriptDetailRunNote') }}
        </el-alert>
        <el-input
          v-model="paramsText"
          type="textarea"
          :rows="10"
          :placeholder="t('dataPages.scriptDetailParamsPh')"
        />
        <div class="run-actions">
          <el-button
            :disabled="!script"
            @click="openTaskCreate"
          >
            {{ t('dataPages.scriptDetailGoCreateTask') }}
          </el-button>
          <el-button
            v-if="isAdmin"
            type="primary"
            :loading="running"
            :disabled="!script"
            @click="runNow"
          >
            {{ t('dataPages.scriptDetailRunNow') }}
          </el-button>
        </div>
      </div>

      <div
        v-if="script"
        class="json-panel"
      >
        <div class="section-title">
          {{ t('dataPages.scriptDetailDepsTitle') }}
        </div>
        <pre>{{ toJsonText(script.dependencies || {}) }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { akshareScriptsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataScript } from '@/types'
import { parseJsonText, toJsonText } from '@/views/data/utils'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const running = ref(false)
const script = ref<DataScript | null>(null)
const paramsText = ref('{\n  "symbol": "000001"\n}')

const isAdmin = computed(() => authStore.user?.is_admin ?? false)

function goBack() {
  void router.back()
}

async function loadDetail() {
  loading.value = true
  try {
    script.value = await akshareScriptsApi.getDetail(String(route.params.id))
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptDetailLoadFailed')))
  } finally {
    loading.value = false
  }
}

async function runNow() {
  if (!script.value) {
    return
  }

  running.value = true
  try {
    const result = await akshareScriptsApi.run(script.value.script_id, {
      parameters: parseJsonText(paramsText.value),
    })
    ElMessage.success(t('dataPages.scriptDetailRunTriggered', { id: result.execution_id }))
    void router.push({
      name: 'DataExecutions',
      query: { script_id: script.value.script_id },
    })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptDetailRunFailed')))
  } finally {
    running.value = false
  }
}

function openTaskCreate() {
  if (!script.value) {
    return
  }
  void router.push({
    name: 'DataTasks',
    query: { script_id: script.value.script_id },
  })
}

onMounted(() => {
  void loadDetail()
})
</script>

<style scoped>
.detail-header,
.detail-tags,
.run-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-title {
  font-size: 22px;
  font-weight: 700;
}

.detail-subtitle {
  margin-top: 4px;
  color: var(--text-color-secondary);
}

.run-panel,
.json-panel {
  margin-top: 24px;
}

.section-title {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 700;
}

.run-actions {
  justify-content: flex-end;
  margin-top: 12px;
}

pre {
  margin: 0;
  padding: 16px;
  background: var(--code-bg-color);
  color: var(--code-text-color);
  border-radius: 12px;
  overflow: auto;
}
</style>
