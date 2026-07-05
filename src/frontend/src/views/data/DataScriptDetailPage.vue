<template>
  <div
    class="script-detail-page"
    data-test="script-detail-page"
  >
    <section
      class="script-detail-hero"
      data-test="script-detail-hero"
    >
      <div class="script-detail-hero-copy">
        <div class="script-detail-kicker">
          {{ t('dataPages.scriptDetailHeroKicker') }}
        </div>
        <h1>{{ script?.script_name || t('dataPages.scriptDetailFallback') }}</h1>
        <p>{{ t('dataPages.scriptDetailHeroSubtitle') }}</p>
        <div
          v-if="script"
          class="script-detail-tags"
        >
          <span>{{ script.script_id }}</span>
          <span>{{ script.category }}</span>
          <span>{{ script.is_custom ? t('dataPages.scriptsTypeCustom') : t('dataPages.scriptsTypeBuiltin') }}</span>
          <span :class="script.is_active ? 'is-success' : 'is-warning'">
            {{ script.is_active ? t('dataPages.scriptDetailEnabled') : t('dataPages.scriptDetailDisabled') }}
          </span>
        </div>
      </div>

      <div class="script-detail-actions">
        <button
          type="button"
          class="script-detail-button"
          @click="goBack"
        >
          <el-icon aria-hidden="true">
            <ArrowLeft />
          </el-icon>
          {{ t('dataPages.detailGoBack') }}
        </button>
        <button
          v-if="isAdmin"
          type="button"
          class="script-detail-button script-detail-button-primary"
          :disabled="!script || running"
          @click="runNow"
        >
          <el-icon aria-hidden="true">
            <VideoPlay />
          </el-icon>
          {{ t('dataPages.scriptDetailRunNow') }}
        </button>
      </div>

      <div
        v-if="script"
        class="script-detail-metrics"
        data-test="script-detail-metrics"
      >
        <article class="script-detail-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.scriptDetailStatus') }}</span>
          <strong>{{ script.is_active ? t('dataPages.scriptDetailEnabled') : t('dataPages.scriptDetailDisabled') }}</strong>
        </article>
        <article class="script-detail-metric">
          <el-icon aria-hidden="true">
            <Clock />
          </el-icon>
          <span>{{ t('dataPages.scriptDetailFrequency') }}</span>
          <strong>{{ script.frequency || '-' }}</strong>
        </article>
        <article class="script-detail-metric">
          <el-icon aria-hidden="true">
            <Timer />
          </el-icon>
          <span>{{ t('dataPages.scriptDetailTimeout') }}</span>
          <strong>{{ script.timeout }}s</strong>
        </article>
        <article class="script-detail-metric">
          <el-icon aria-hidden="true">
            <Operation />
          </el-icon>
          <span>{{ t('dataPages.scriptDetailEstDuration') }}</span>
          <strong>{{ script.estimated_duration }}s</strong>
        </article>
      </div>
    </section>

    <div
      v-if="loading"
      class="script-detail-state"
    >
      {{ t('dataPages.scriptDetailLoading') }}
    </div>

    <template v-else-if="script">
      <div class="script-detail-workbench">
        <el-card
          class="script-detail-panel script-detail-config-panel"
          data-test="script-detail-config-panel"
        >
          <template #header>
            <div class="panel-heading">
              <div>
                <div class="script-detail-kicker">
                  {{ t('dataPages.scriptDetailConfigKicker') }}
                </div>
                <div class="panel-title">
                  {{ t('dataPages.scriptDetailConfigTitle') }}
                </div>
              </div>
            </div>
          </template>

          <div class="script-detail-grid">
            <div class="script-detail-field">
              <span>{{ t('dataPages.scriptDetailModulePath') }}</span>
              <strong>{{ script.module_path || '-' }}</strong>
            </div>
            <div class="script-detail-field">
              <span>{{ t('dataPages.scriptDetailFuncName') }}</span>
              <strong>{{ script.function_name || '-' }}</strong>
            </div>
            <div class="script-detail-field">
              <span>{{ t('dataPages.scriptDetailTargetTable') }}</span>
              <strong>{{ script.target_table || '-' }}</strong>
            </div>
            <div class="script-detail-field">
              <span>{{ t('dataPages.scriptDetailSource') }}</span>
              <strong>{{ script.source }}</strong>
            </div>
            <div class="script-detail-field">
              <span>{{ t('dataPages.scriptDetailSubCategory') }}</span>
              <strong>{{ script.sub_category || '-' }}</strong>
            </div>
            <div class="script-detail-field">
              <span>{{ t('dataPages.scriptDetailUpdatedAt') }}</span>
              <strong>{{ formatDateTime(script.updated_at) }}</strong>
            </div>
            <div class="script-detail-field script-detail-field-wide">
              <span>{{ t('dataPages.scriptDetailDescription') }}</span>
              <strong>{{ script.description || t('dataPages.scriptDetailNoDesc') }}</strong>
            </div>
          </div>
        </el-card>

        <el-card
          class="script-detail-panel script-detail-run-panel"
          data-test="script-detail-run-panel"
        >
          <template #header>
            <div class="panel-heading">
              <div>
                <div class="script-detail-kicker">
                  {{ t('dataPages.scriptDetailRunKicker') }}
                </div>
                <div class="panel-title">
                  {{ t('dataPages.scriptDetailManualRun') }}
                </div>
              </div>
            </div>
          </template>

          <div class="run-note">
            {{ t('dataPages.scriptDetailRunNote') }}
          </div>
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
        </el-card>

        <el-card
          class="script-detail-panel script-detail-json-panel"
          data-test="script-detail-json-panel"
        >
          <template #header>
            <div class="panel-heading">
              <div>
                <div class="script-detail-kicker">
                  {{ t('dataPages.scriptDetailDepsKicker') }}
                </div>
                <div class="panel-title">
                  {{ t('dataPages.scriptDetailDepsTitle') }}
                </div>
              </div>
            </div>
          </template>
          <pre>{{ toJsonText(script.dependencies || {}) }}</pre>
        </el-card>
      </div>
    </template>

    <div
      v-else
      class="script-detail-state"
    >
      {{ t('dataPages.scriptDetailFallback') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  CircleCheck,
  Clock,
  Operation,
  Timer,
  VideoPlay,
} from '@element-plus/icons-vue'
import { akshareScriptsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataScript } from '@/types'
import { formatDateTime, parseJsonText, toJsonText } from '@/views/data/utils'

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
  void router.push({ name: 'ConfigDataScripts' })
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
      name: 'ConfigDataExecutions',
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
    name: 'ConfigDataTasks',
    query: { script_id: script.value.script_id },
  })
}

onMounted(() => {
  void loadDetail()
})
</script>

<style scoped>
.script-detail-page {
  display: grid;
  gap: 24px;
}

.script-detail-hero,
.script-detail-panel,
.script-detail-state {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.script-detail-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.script-detail-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.script-detail-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.script-detail-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
  overflow-wrap: anywhere;
}

.script-detail-hero p {
  max-width: 760px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.script-detail-tags,
.script-detail-actions,
.run-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.script-detail-tags {
  margin-top: 4px;
}

.script-detail-tags span {
  max-width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.script-detail-tags .is-success {
  border-color: var(--success-border-color);
  background: var(--success-surface);
  color: var(--success-text-color);
}

.script-detail-tags .is-warning {
  border-color: var(--warning-border-color);
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

.script-detail-actions {
  justify-content: flex-end;
  align-self: start;
}

.script-detail-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 36px;
  padding: 8px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.script-detail-button:hover:not(:disabled),
.script-detail-button:focus-visible:not(:disabled) {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.script-detail-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.script-detail-button-primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
}

.script-detail-button-primary:hover:not(:disabled),
.script-detail-button-primary:focus-visible:not(:disabled) {
  background: var(--primary-color-dark);
  color: var(--el-color-white);
}

.script-detail-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.script-detail-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.script-detail-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.script-detail-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.script-detail-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.script-detail-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  padding: 24px;
  color: var(--text-color-secondary);
  font-weight: 700;
}

.script-detail-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
  gap: 18px;
  align-items: start;
}

.script-detail-panel {
  box-shadow: none;
}

.script-detail-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.script-detail-panel :deep(.el-card__body) {
  padding: 18px;
}

.script-detail-config-panel {
  min-width: 0;
}

.script-detail-run-panel,
.script-detail-json-panel {
  min-width: 0;
}

.script-detail-json-panel {
  grid-column: 1 / -1;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-title {
  margin-top: 4px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.script-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.script-detail-field {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.script-detail-field-wide {
  grid-column: 1 / -1;
}

.script-detail-field span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.script-detail-field strong {
  color: var(--text-color-primary);
  font-size: 14px;
  font-weight: 720;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.run-note {
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--info-border-color);
  border-radius: 8px;
  background: var(--info-surface);
  color: var(--info-text-color);
  font-size: 13px;
  line-height: 1.55;
}

.script-detail-run-panel :deep(.el-textarea__inner) {
  min-height: 220px !important;
  border-color: var(--border-color);
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
}

.run-actions {
  justify-content: flex-end;
  margin-top: 14px;
}

pre {
  margin: 0;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  background: var(--code-bg-color);
  color: var(--code-text-color);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
  overflow: auto;
}

@media (max-width: 1100px) {
  .script-detail-hero,
  .script-detail-workbench {
    grid-template-columns: 1fr;
  }

  .script-detail-actions {
    justify-content: flex-start;
  }

  .script-detail-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .script-detail-hero {
    padding: 18px;
  }

  .script-detail-hero h1 {
    font-size: 24px;
  }

  .script-detail-metrics,
  .script-detail-grid {
    grid-template-columns: 1fr;
  }

  .script-detail-field-wide,
  .script-detail-json-panel {
    grid-column: auto;
  }

  .script-detail-actions,
  .run-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .script-detail-button,
  .run-actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
