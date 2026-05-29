<template>
  <div class="space-y-6">
    <section class="stats-grid">
      <el-card>
        <div class="stat-title">
          {{ t('dataPages.scriptsStatTotal') }}
        </div>
        <div class="stat-value">
          {{ stats.total_scripts }}
        </div>
      </el-card>
      <el-card>
        <div class="stat-title">
          {{ t('dataPages.scriptsStatActive') }}
        </div>
        <div class="stat-value">
          {{ stats.active_scripts }}
        </div>
      </el-card>
      <el-card>
        <div class="stat-title">
          {{ t('dataPages.scriptsStatCustom') }}
        </div>
        <div class="stat-value">
          {{ stats.custom_scripts }}
        </div>
      </el-card>
      <el-card>
        <div class="stat-title">
          {{ t('dataPages.scriptsStatCategories') }}
        </div>
        <div class="stat-value">
          {{ stats.categories.length }}
        </div>
      </el-card>
    </section>

    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">
              {{ t('dataPages.scriptsPageTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.scriptsPageDesc') }}
            </div>
          </div>
          <div class="actions">
            <el-button
              v-if="isAdmin"
              :loading="scanLoading"
              @click="handleScan"
            >
              {{ t('dataPages.scriptsRescan') }}
            </el-button>
            <el-button
              v-if="isAdmin"
              type="primary"
              @click="openCreateDialog"
            >
              {{ t('dataPages.scriptsNewCustom') }}
            </el-button>
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
          @keyup.enter="reloadFirstPage"
          @clear="reloadFirstPage"
        />
        <el-button @click="reloadFirstPage">
          {{ t('dataPages.scriptsQuery') }}
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="scripts"
        stripe
      >
        <el-table-column
          prop="script_name"
          :label="t('dataPages.scriptsColName')"
          min-width="180"
        />
        <el-table-column
          prop="script_id"
          :label="t('dataPages.scriptsColScriptId')"
          min-width="150"
        />
        <el-table-column
          prop="category"
          :label="t('dataPages.scriptsColCategory')"
          width="120"
        >
          <template #default="{ row }">
            <el-tag>{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="target_table"
          :label="t('dataPages.scriptsColTargetTable')"
          min-width="140"
        />
        <el-table-column
          :label="t('dataPages.scriptsColType')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_custom ? 'success' : 'info'">
              {{ row.is_custom ? t('dataPages.scriptsTypeCustom') : t('dataPages.scriptsTypeBuiltin') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.scriptsColStatus')"
          width="100"
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
          width="180"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('dataPages.scriptsColActions')"
          fixed="right"
          min-width="260"
        >
          <template #default="{ row }">
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
          </template>
        </el-table-column>
      </el-table>

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
  void router.push({ name: 'DataScriptDetail', params: { id: scriptId } })
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
    void router.push({ name: 'DataExecutions', query: { script_id: scriptId } })
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
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-title {
  font-size: 13px;
  color: var(--text-color-secondary);
}

.stat-value {
  margin-top: 8px;
  font-size: 30px;
  font-weight: 700;
  color: var(--text-color-primary);
}

.header-row,
.toolbar,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-color-primary);
}

.page-subtitle {
  margin-top: 4px;
  color: var(--text-color-secondary);
}

.toolbar {
  margin-bottom: 16px;
  justify-content: flex-start;
}

.toolbar-item {
  width: 180px;
}

.toolbar-search {
  max-width: 320px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.full-width {
  width: 100%;
}

@media (max-width: 960px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
