<template>
  <div
    class="data-scripts-page"
    data-test="data-scripts-page"
  >
    <section
      class="scripts-hero"
      data-test="data-scripts-hero"
    >
      <div class="scripts-hero-copy">
        <div class="scripts-kicker">
          {{ t('dataPages.scriptsHeroKicker') }}
        </div>
        <h1>{{ t('dataPages.scriptsPageTitle') }}</h1>
        <p>{{ t('dataPages.scriptsPageDesc') }}</p>
      </div>
      <div class="scripts-hero-actions">
        <button
          v-if="isAdmin"
          type="button"
          class="scripts-button"
          :disabled="scanLoading"
          @click="handleScan"
        >
          <el-icon aria-hidden="true">
            <Refresh />
          </el-icon>
          {{ t('dataPages.scriptsRescan') }}
        </button>
        <button
          v-if="isAdmin"
          type="button"
          class="scripts-button scripts-button-primary"
          @click="openCreateDialog"
        >
          <el-icon aria-hidden="true">
            <Plus />
          </el-icon>
          {{ t('dataPages.scriptsNewCustom') }}
        </button>
      </div>
      <div
        class="stats-grid"
        data-test="data-scripts-metrics"
      >
        <article class="stat-card">
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <span>{{ t('dataPages.scriptsStatTotal') }}</span>
          <strong>{{ stats.total_scripts }}</strong>
        </article>
        <article class="stat-card">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.scriptsStatActive') }}</span>
          <strong>{{ stats.active_scripts }}</strong>
        </article>
        <article class="stat-card">
          <el-icon aria-hidden="true">
            <Operation />
          </el-icon>
          <span>{{ t('dataPages.scriptsStatCustom') }}</span>
          <strong>{{ stats.custom_scripts }}</strong>
        </article>
        <article class="stat-card">
          <el-icon aria-hidden="true">
            <Collection />
          </el-icon>
          <span>{{ t('dataPages.scriptsStatCategories') }}</span>
          <strong>{{ stats.categories.length }}</strong>
        </article>
      </div>
    </section>

    <el-card
      class="scripts-workbench"
      data-test="data-scripts-workbench"
    >
      <template #header>
        <div class="header-row">
          <div>
            <div class="scripts-kicker">
              {{ t('dataPages.scriptsWorkbenchKicker') }}
            </div>
            <div class="page-title">
              {{ t('dataPages.scriptsWorkbenchTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.scriptsWorkbenchDesc') }}
            </div>
          </div>
          <div class="scripts-scope">
            <span>{{ t('dataPages.scriptsVisibleCount', { count: scripts.length }) }}</span>
            <span>{{ t('dataPages.scriptsTotalCount', { count: total }) }}</span>
          </div>
        </div>
      </template>

      <div class="toolbar">
        <el-select
          v-model="filters.category"
          clearable
          :placeholder="t('dataPages.scriptsCategoryPh')"
          class="toolbar-item"
          @change="reloadFirstPage"
        >
          <el-option
            v-for="category in categories"
            :key="category"
            :label="category"
            :value="category"
          />
        </el-select>

        <el-select
          v-model="activeFilter"
          :placeholder="t('dataPages.scriptsActivePh')"
          class="toolbar-item"
          @change="reloadFirstPage"
        >
          <el-option
            :label="t('dataPages.scriptsFilterAll')"
            value="all"
          />
          <el-option
            :label="t('dataPages.scriptsFilterActive')"
            value="active"
          />
          <el-option
            :label="t('dataPages.scriptsFilterInactive')"
            value="inactive"
          />
        </el-select>

        <el-input
          v-model="filters.keyword"
          clearable
          :placeholder="t('dataPages.scriptsSearchPh')"
          class="toolbar-search"
          :prefix-icon="Search"
          @keyup.enter="reloadFirstPage"
          @clear="reloadFirstPage"
        />
        <el-button
          class="scripts-query-button"
          @click="reloadFirstPage"
        >
          {{ t('dataPages.scriptsQuery') }}
        </el-button>
      </div>

      <div
        v-if="!loading && scripts.length === 0"
        class="scripts-empty"
      >
        <el-icon aria-hidden="true">
          <Document />
        </el-icon>
        <strong>{{ t('dataPages.scriptsEmptyTitle') }}</strong>
        <span>{{ t('dataPages.scriptsEmptyDesc') }}</span>
      </div>

      <div
        v-else
        class="scripts-table-wrap"
      >
        <el-table
          v-loading="loading"
          :data="scripts"
          stripe
        >
          <el-table-column
            prop="script_name"
            :label="t('dataPages.scriptsColName')"
            min-width="210"
          >
            <template #default="{ row }">
              <div class="script-name-cell">
                <strong>{{ row.script_name }}</strong>
                <span>{{ row.description || row.script_id }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="script_id"
            :label="t('dataPages.scriptsColScriptId')"
            min-width="160"
          />
          <el-table-column
            prop="category"
            :label="t('dataPages.scriptsColCategory')"
            width="130"
          >
            <template #default="{ row }">
              <el-tag>{{ row.category }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="target_table"
            :label="t('dataPages.scriptsColTargetTable')"
            min-width="150"
          />
          <el-table-column
            prop="frequency"
            :label="t('dataPages.scriptsColFrequency')"
            width="110"
          />
          <el-table-column
            :label="t('dataPages.scriptsColType')"
            width="110"
          >
            <template #default="{ row }">
              <el-tag :type="row.is_custom ? 'success' : 'info'">
                {{ row.is_custom ? t('dataPages.scriptsTypeCustom') : t('dataPages.scriptsTypeBuiltin') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.scriptsColStatus')"
            width="110"
          >
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'warning'">
                {{ row.is_active ? t('dataPages.scriptsStatusActive') : t('dataPages.scriptsStatusInactive') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="updated_at"
            :label="t('dataPages.scriptsColUpdatedAt')"
            width="170"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.scriptsColActions')"
            fixed="right"
            min-width="270"
          >
            <template #default="{ row }">
              <div class="table-actions">
                <el-button
                  link
                  type="primary"
                  @click="goDetail(row.script_id)"
                >
                  {{ t('dataPages.scriptsActionDetail') }}
                </el-button>
                <el-button
                  v-if="isAdmin"
                  link
                  type="success"
                  @click="runScript(row.script_id)"
                >
                  {{ t('dataPages.scriptsActionRun') }}
                </el-button>
                <el-button
                  v-if="isAdmin"
                  link
                  @click="toggleScript(row.script_id)"
                >
                  {{ row.is_active ? t('dataPages.scriptsActionDisable') : t('dataPages.scriptsActionEnable') }}
                </el-button>
                <el-button
                  v-if="isAdmin && row.is_custom"
                  link
                  @click="openEditDialog(row)"
                >
                  {{ t('dataPages.scriptsActionEdit') }}
                </el-button>
                <el-button
                  v-if="isAdmin && row.is_custom"
                  link
                  type="danger"
                  @click="deleteScript(row)"
                >
                  {{ t('dataPages.scriptsActionDelete') }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div
        v-if="scripts.length"
        class="scripts-mobile-list"
      >
        <article
          v-for="script in scripts"
          :key="script.script_id"
          class="script-card"
        >
          <div class="script-card-header">
            <div>
              <strong>{{ script.script_name }}</strong>
              <span>{{ script.script_id }}</span>
            </div>
            <el-tag :type="script.is_active ? 'success' : 'warning'">
              {{ script.is_active ? t('dataPages.scriptsStatusActive') : t('dataPages.scriptsStatusInactive') }}
            </el-tag>
          </div>
          <p>{{ script.description || t('dataPages.scriptsNoDescription') }}</p>
          <div class="script-card-meta">
            <span>{{ script.category }}</span>
            <span>{{ script.target_table || '-' }}</span>
            <span>{{ script.frequency || '-' }}</span>
            <span>{{ formatDateTime(script.updated_at) }}</span>
          </div>
          <div class="script-card-actions">
            <button
              type="button"
              @click="goDetail(script.script_id)"
            >
              <el-icon aria-hidden="true">
                <View />
              </el-icon>
              {{ t('dataPages.scriptsActionDetail') }}
            </button>
            <button
              v-if="isAdmin"
              type="button"
              @click="runScript(script.script_id)"
            >
              <el-icon aria-hidden="true">
                <VideoPlay />
              </el-icon>
              {{ t('dataPages.scriptsActionRun') }}
            </button>
            <button
              v-if="isAdmin && script.is_custom"
              type="button"
              @click="openEditDialog(script)"
            >
              <el-icon aria-hidden="true">
                <Edit />
              </el-icon>
              {{ t('dataPages.scriptsActionEdit') }}
            </button>
          </div>
        </article>
      </div>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadScripts"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? t('dataPages.scriptsDialogCreate') : t('dataPages.scriptsDialogEdit')"
      width="720px"
      class="scripts-dialog"
    >
      <el-form
        label-width="110px"
        :model="form"
      >
        <el-form-item :label="t('dataPages.scriptsFormScriptId')">
          <el-input
            v-model="form.script_id"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormName')">
          <el-input v-model="form.script_name" />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormCategory')">
          <el-input v-model="form.category" />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormSubCategory')">
          <el-input v-model="form.sub_category" />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormFrequency')">
          <el-select
            v-model="form.frequency"
            class="full-width"
          >
            <el-option
              v-for="item in frequencies"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormTargetTable')">
          <el-input v-model="form.target_table" />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormModulePath')">
          <el-input v-model="form.module_path" />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormFuncName')">
          <el-input v-model="form.function_name" />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormTimeout')">
          <el-input-number
            v-model="form.timeout"
            :min="1"
            :step="30"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormEstDuration')">
          <el-input-number
            v-model="form.estimated_duration"
            :min="1"
            :step="10"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormDesc')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormDeps')">
          <el-input
            v-model="dependenciesText"
            type="textarea"
            :rows="8"
            :placeholder="t('dataPages.scriptsDepsPh')"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.scriptsFormIsActive')">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="submitForm"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CircleCheck,
  Collection,
  Document,
  Edit,
  Operation,
  Plus,
  Refresh,
  Search,
  VideoPlay,
  View,
} from '@element-plus/icons-vue'
import { akshareScriptsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataScript, DataScriptFormPayload, ScriptStatsResponse } from '@/types'
import { formatDateTime, parseJsonText, toJsonText } from '@/views/data/utils'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const scanLoading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const scripts = ref<DataScript[]>([])
const categories = ref<string[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const activeFilter = ref<'all' | 'active' | 'inactive'>('all')
const stats = reactive<ScriptStatsResponse>({
  total_scripts: 0,
  active_scripts: 0,
  custom_scripts: 0,
  categories: [],
})
const filters = reactive({
  category: '',
  keyword: '',
})
const form = reactive<DataScriptFormPayload>({
  script_id: '',
  script_name: '',
  category: '',
  sub_category: '',
  frequency: 'manual',
  description: '',
  source: 'akshare',
  target_table: '',
  module_path: '',
  function_name: 'main',
  dependencies: {},
  estimated_duration: 60,
  timeout: 300,
  is_active: true,
})
const dependenciesText = ref('{}')

const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const frequencies = ['manual', 'hourly', 'daily', 'weekly', 'monthly', 'once'] as const

function resetForm() {
  form.script_id = ''
  form.script_name = ''
  form.category = ''
  form.sub_category = ''
  form.frequency = 'manual'
  form.description = ''
  form.source = 'akshare'
  form.target_table = ''
  form.module_path = ''
  form.function_name = 'main'
  form.dependencies = {}
  form.estimated_duration = 60
  form.timeout = 300
  form.is_active = true
  dependenciesText.value = '{}'
}

async function loadCategories() {
  categories.value = await akshareScriptsApi.getCategories()
}

async function loadStats() {
  Object.assign(stats, await akshareScriptsApi.getStats())
}

async function loadScripts() {
  loading.value = true
  try {
    const response = await akshareScriptsApi.list({
      page: page.value,
      page_size: pageSize.value,
      category: filters.category || undefined,
      keyword: filters.keyword || undefined,
      is_active:
        activeFilter.value === 'all'
          ? undefined
          : activeFilter.value === 'active',
    })
    scripts.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptsLoadFailed')))
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadCategories(), loadStats(), loadScripts()])
}

function reloadFirstPage() {
  page.value = 1
  void loadScripts()
}

function handleSizeChange() {
  page.value = 1
  void loadScripts()
}

function goDetail(scriptId: string) {
  void router.push({ name: 'ConfigDataScriptDetail', params: { id: scriptId } })
}

function openCreateDialog() {
  dialogMode.value = 'create'
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(script: DataScript) {
  dialogMode.value = 'edit'
  form.script_id = script.script_id
  form.script_name = script.script_name
  form.category = script.category
  form.sub_category = script.sub_category ?? ''
  form.frequency = script.frequency ?? 'manual'
  form.description = script.description ?? ''
  form.source = script.source
  form.target_table = script.target_table ?? ''
  form.module_path = script.module_path ?? ''
  form.function_name = script.function_name ?? 'main'
  form.dependencies = script.dependencies ?? {}
  form.estimated_duration = script.estimated_duration
  form.timeout = script.timeout
  form.is_active = script.is_active
  dependenciesText.value = toJsonText(script.dependencies ?? {})
  dialogVisible.value = true
}

async function submitForm() {
  if (!form.script_id.trim() || !form.script_name.trim() || !form.category.trim()) {
    ElMessage.warning(t('dataPages.scriptsValidationFill'))
    return
  }

  saving.value = true
  try {
    const payload: DataScriptFormPayload = {
      ...form,
      script_id: form.script_id.trim(),
      script_name: form.script_name.trim(),
      category: form.category.trim(),
      sub_category: form.sub_category?.trim() || null,
      description: form.description?.trim() || null,
      target_table: form.target_table?.trim() || null,
      module_path: form.module_path?.trim() || null,
      function_name: form.function_name?.trim() || null,
      dependencies: parseJsonText(dependenciesText.value),
    }

    if (dialogMode.value === 'create') {
      await akshareScriptsApi.create(payload)
      ElMessage.success(t('dataPages.scriptsCreated'))
    } else {
      const { script_id, ...updatePayload } = payload
      void script_id
      await akshareScriptsApi.update(form.script_id, updatePayload)
      ElMessage.success(t('dataPages.scriptsUpdated'))
    }
    dialogVisible.value = false
    await refreshAll()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptsSaveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleScan() {
  scanLoading.value = true
  try {
    const result = await akshareScriptsApi.scan()
    ElMessage.success(t('dataPages.scriptsScanned', { registered: result.registered, updated: result.updated }))
    await refreshAll()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptsScanFailed')))
  } finally {
    scanLoading.value = false
  }
}

async function runScript(scriptId: string) {
  try {
    const result = await akshareScriptsApi.run(scriptId, { parameters: {} })
    ElMessage.success(t('dataPages.scriptsRunTriggered', { id: result.execution_id }))
    void router.push({ name: 'ConfigDataExecutions', query: { script_id: scriptId } })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptsRunFailed')))
  }
}

async function toggleScript(scriptId: string) {
  try {
    await akshareScriptsApi.toggle(scriptId)
    ElMessage.success(t('dataPages.scriptsToggled'))
    await refreshAll()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.scriptsToggleFailed')))
  }
}

async function deleteScript(script: DataScript) {
  try {
    await ElMessageBox.confirm(
      t('dataPages.scriptsDeleteConfirmMsg', { name: script.script_name }),
      t('dataPages.scriptsDeleteConfirmTitle'),
      { type: 'warning' }
    )
    await akshareScriptsApi.delete(script.script_id)
    ElMessage.success(t('dataPages.scriptsDeleted'))
    await refreshAll()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('dataPages.scriptsDeleteFailed')))
    }
  }
}

onMounted(() => {
  void refreshAll()
})
</script>

<style scoped>
.data-scripts-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  --scripts-surface: var(--bg-color);
  --scripts-surface-soft: var(--fill-color-lighter);
  --scripts-surface-muted: var(--fill-color-light);
  --scripts-border: var(--border-color);
  --scripts-primary-soft: color-mix(in srgb, var(--bg-color) 82%, var(--primary-color) 18%);
  --scripts-success-soft: color-mix(in srgb, var(--bg-color) 84%, var(--success-color) 16%);
  --scripts-warning-soft: color-mix(in srgb, var(--bg-color) 84%, var(--warning-color) 16%);
  color: var(--text-color-primary);
}

.scripts-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: start;
  padding: 22px;
  border: 1px solid color-mix(in srgb, var(--scripts-border) 72%, var(--primary-color) 28%);
  border-radius: 8px;
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--scripts-surface) 88%, var(--primary-color) 12%),
      color-mix(in srgb, var(--scripts-surface-soft) 90%, var(--primary-color) 10%)
    );
}

.scripts-hero-copy {
  min-width: 0;
}

.scripts-kicker {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  text-transform: uppercase;
}

.scripts-hero h1 {
  margin: 8px 0 0;
  color: var(--text-color-primary);
  font-size: 34px;
  font-weight: 760;
  line-height: 1.15;
  letter-spacing: 0;
}

.scripts-hero p {
  max-width: 780px;
  margin: 10px 0 0;
  color: var(--text-color-secondary);
  font-size: 15px;
  line-height: 1.7;
}

.scripts-hero-actions,
.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.scripts-button,
.script-card-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  border: 1px solid var(--scripts-border);
  border-radius: 8px;
  background: var(--scripts-surface);
  padding: 8px 12px;
  color: var(--text-color-regular);
  cursor: pointer;
  font: inherit;
  font-size: 14px;
  font-weight: 650;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.scripts-button:hover:not(:disabled),
.script-card-actions button:hover {
  border-color: color-mix(in srgb, var(--primary-color) 42%, var(--scripts-border) 58%);
  background: var(--scripts-primary-soft);
  color: var(--primary-color);
}

.scripts-button-primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
}

.scripts-button-primary:hover:not(:disabled) {
  background: var(--primary-color-dark);
  color: var(--el-color-white);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  grid-column: 1 / -1;
  gap: 10px;
}

.stat-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 10px;
  align-items: center;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--scripts-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--scripts-surface) 90%, var(--scripts-surface-muted) 10%);
}

.stat-card .el-icon {
  grid-row: span 2;
  color: var(--primary-color);
  font-size: 18px;
}

.stat-card span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.stat-card strong {
  color: var(--text-color-primary);
  font-size: 24px;
  font-weight: 760;
  line-height: 1;
}

.data-scripts-page :deep(.el-card) {
  --el-card-bg-color: var(--scripts-surface);
  --el-card-border-color: var(--scripts-border);
  border-radius: 8px;
  color: var(--text-color-primary);
}

.data-scripts-page :deep(.el-card__header) {
  border-bottom-color: var(--scripts-border);
  background: color-mix(in srgb, var(--scripts-surface) 90%, var(--scripts-surface-muted) 10%);
}

.data-scripts-page :deep(.el-card__body) {
  background: var(--scripts-surface);
}

.header-row,
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  margin-top: 3px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 760;
}

.page-subtitle {
  margin-top: 4px;
  color: var(--text-color-secondary);
  line-height: 1.6;
}

.scripts-scope {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.scripts-scope span {
  border: 1px solid var(--scripts-border);
  border-radius: 9999px;
  background: var(--scripts-surface-soft);
  padding: 5px 9px;
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.toolbar {
  justify-content: flex-start;
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--scripts-border);
  border-radius: 8px;
  background: var(--scripts-surface-soft);
}

.toolbar-item {
  width: 180px;
}

.toolbar-search {
  flex: 1 1 260px;
  max-width: 320px;
}

.scripts-query-button {
  min-width: 86px;
}

.scripts-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--scripts-border);
  border-radius: 8px;
}

.scripts-table-wrap :deep(.el-table) {
  --el-table-bg-color: var(--scripts-surface);
  --el-table-tr-bg-color: var(--scripts-surface);
  --el-table-header-bg-color: var(--scripts-surface-soft);
  --el-table-border-color: var(--scripts-border);
  --el-table-text-color: var(--text-color-primary);
  --el-table-header-text-color: var(--text-color-secondary);
  --el-table-row-hover-bg-color: var(--scripts-surface-muted);
  color: var(--text-color-primary);
}

.scripts-table-wrap :deep(.el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: color-mix(in srgb, var(--scripts-surface) 92%, var(--scripts-surface-muted) 8%);
}

.scripts-table-wrap :deep(.el-table__fixed-right),
.scripts-table-wrap :deep(.el-table__fixed-right-patch) {
  background: var(--scripts-surface);
}

.script-name-cell {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.script-name-cell strong {
  color: var(--text-color-primary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.script-name-cell span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.table-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 6px;
}

.scripts-mobile-list {
  display: none;
}

.script-card {
  display: grid;
  gap: 10px;
  border: 1px solid var(--scripts-border);
  border-radius: 8px;
  background: var(--scripts-surface-soft);
  padding: 12px;
}

.script-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.script-card-header > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.script-card-header strong {
  color: var(--text-color-primary);
  font-size: 15px;
  overflow-wrap: anywhere;
}

.script-card-header span {
  color: var(--text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.script-card p {
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.script-card-meta,
.script-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.script-card-meta span {
  border: 1px solid var(--scripts-border);
  border-radius: 9999px;
  background: var(--scripts-surface);
  padding: 4px 8px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.script-card-actions button {
  min-height: 32px;
  padding: 6px 9px;
  font-size: 12px;
}

.scripts-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 260px;
  border: 1px dashed var(--scripts-border);
  border-radius: 8px;
  background: var(--scripts-surface-soft);
  color: var(--text-color-secondary);
  text-align: center;
}

.scripts-empty .el-icon {
  color: var(--primary-color);
  font-size: 34px;
}

.scripts-empty strong {
  color: var(--text-color-primary);
  font-size: 16px;
}

.scripts-empty span {
  max-width: 420px;
  font-size: 13px;
  line-height: 1.6;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.full-width {
  width: 100%;
}

.data-scripts-page :deep(.el-input__wrapper),
.data-scripts-page :deep(.el-select__wrapper),
.data-scripts-page :deep(.el-input-number),
:global(.scripts-dialog .el-input__wrapper),
:global(.scripts-dialog .el-select__wrapper),
:global(.scripts-dialog .el-textarea__inner),
:global(.scripts-dialog .el-input-number) {
  border-color: var(--border-color) !important;
  background: var(--bg-color) !important;
  color: var(--text-color-primary) !important;
  box-shadow: 0 0 0 1px var(--border-color) inset !important;
}

.data-scripts-page :deep(.el-button:not(.is-link)) {
  border-radius: 8px;
}

:global(.scripts-dialog .el-dialog) {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
}

:global(.scripts-dialog .el-dialog__header),
:global(.scripts-dialog .el-dialog__footer) {
  border-color: var(--border-color);
}

:global(.scripts-dialog .el-form-item__label) {
  color: var(--text-color-secondary);
}

@media (max-width: 960px) {
  .scripts-hero {
    grid-template-columns: 1fr;
  }

  .scripts-hero-actions {
    justify-content: flex-start;
  }

  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .header-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .scripts-scope {
    justify-content: flex-start;
  }
}

@media (max-width: 1100px) {
  .scripts-table-wrap {
    display: none;
  }

  .scripts-mobile-list {
    display: grid;
    gap: 10px;
  }
}

@media (max-width: 640px) {
  .scripts-hero {
    padding: 16px;
  }

  .scripts-hero h1 {
    font-size: 28px;
  }

  .scripts-hero-actions,
  .scripts-button {
    width: 100%;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-item,
  .toolbar-search {
    width: 100%;
    max-width: none;
  }

  .toolbar-search {
    flex: 0 1 auto;
  }

  .pagination-wrap {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
