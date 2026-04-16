<template>
  <div class="space-y-6">
    <section class="stats-grid">
      <el-card>
        <div class="stat-title">
          脚本总数
        </div>
        <div class="stat-value">
          {{ stats.total_scripts }}
        </div>
      </el-card>
      <el-card>
        <div class="stat-title">
          启用脚本
        </div>
        <div class="stat-value">
          {{ stats.active_scripts }}
        </div>
      </el-card>
      <el-card>
        <div class="stat-title">
          自定义脚本
        </div>
        <div class="stat-value">
          {{ stats.custom_scripts }}
        </div>
      </el-card>
      <el-card>
        <div class="stat-title">
          覆盖分类
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
              数据脚本
            </div>
            <div class="page-subtitle">
              扫描内置脚本、管理自定义脚本并手动触发执行。
            </div>
          </div>
          <div class="actions">
            <el-button
              v-if="isAdmin"
              :loading="scanLoading"
              @click="handleScan"
            >
              重新扫描
            </el-button>
            <el-button
              v-if="isAdmin"
              type="primary"
              @click="openCreateDialog"
            >
              新建自定义脚本
            </el-button>
          </div>
        </div>
      </template>

      <div class="toolbar">
        <el-select
          v-model="filters.category"
          clearable
          placeholder="按分类筛选"
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
          placeholder="启用状态"
          class="toolbar-item"
          @change="reloadFirstPage"
        >
          <el-option
            label="全部状态"
            value="all"
          />
          <el-option
            label="仅启用"
            value="active"
          />
          <el-option
            label="仅停用"
            value="inactive"
          />
        </el-select>

        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="搜索脚本名称、ID、描述"
          class="toolbar-search"
          @keyup.enter="reloadFirstPage"
          @clear="reloadFirstPage"
        />
        <el-button @click="reloadFirstPage">
          查询
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="scripts"
        stripe
      >
        <el-table-column
          prop="script_name"
          label="名称"
          min-width="180"
        />
        <el-table-column
          prop="script_id"
          label="脚本 ID"
          min-width="150"
        />
        <el-table-column
          prop="category"
          label="分类"
          width="120"
        >
          <template #default="{ row }">
            <el-tag>{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="target_table"
          label="目标表"
          min-width="140"
        />
        <el-table-column
          label="类型"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_custom ? 'success' : 'info'">
              {{ row.is_custom ? '自定义' : '内置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'warning'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="updated_at"
          label="更新时间"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          fixed="right"
          min-width="260"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="goDetail(row.script_id)"
            >
              详情
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="success"
              @click="runScript(row.script_id)"
            >
              执行
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              @click="toggleScript(row.script_id)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-if="isAdmin && row.is_custom"
              link
              @click="openEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="isAdmin && row.is_custom"
              link
              type="danger"
              @click="deleteScript(row)"
            >
              删除
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
      :title="dialogMode === 'create' ? '新建自定义脚本' : '编辑自定义脚本'"
      width="720px"
    >
      <el-form
        label-width="110px"
        :model="form"
      >
        <el-form-item label="脚本 ID">
          <el-input
            v-model="form.script_id"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.script_name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" />
        </el-form-item>
        <el-form-item label="子分类">
          <el-input v-model="form.sub_category" />
        </el-form-item>
        <el-form-item label="频率">
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
        <el-form-item label="目标表">
          <el-input v-model="form.target_table" />
        </el-form-item>
        <el-form-item label="模块路径">
          <el-input v-model="form.module_path" />
        </el-form-item>
        <el-form-item label="函数名">
          <el-input v-model="form.function_name" />
        </el-form-item>
        <el-form-item label="超时秒数">
          <el-input-number
            v-model="form.timeout"
            :min="1"
            :step="30"
          />
        </el-form-item>
        <el-form-item label="预计时长">
          <el-input-number
            v-model="form.estimated_duration"
            :min="1"
            :step="10"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="依赖参数">
          <el-input
            v-model="dependenciesText"
            type="textarea"
            :rows="8"
            placeholder="请输入 JSON 对象"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="submitForm"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { akshareScriptsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataScript, DataScriptFormPayload, ScriptStatsResponse } from '@/types'
import { formatDateTime, parseJsonText, toJsonText } from '@/views/data/utils'

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
    ElMessage.error(getErrorMessage(error, '加载脚本失败'))
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
    ElMessage.warning('请填写脚本 ID、名称和分类')
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
      ElMessage.success('脚本已创建')
    } else {
      const { script_id, ...updatePayload } = payload
      void script_id
      await akshareScriptsApi.update(form.script_id, updatePayload)
      ElMessage.success('脚本已更新')
    }
    dialogVisible.value = false
    await refreshAll()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '保存脚本失败'))
  } finally {
    saving.value = false
  }
}

async function handleScan() {
  scanLoading.value = true
  try {
    const result = await akshareScriptsApi.scan()
    ElMessage.success(`扫描完成：新增 ${result.registered}，更新 ${result.updated}`)
    await refreshAll()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '扫描脚本失败'))
  } finally {
    scanLoading.value = false
  }
}

async function runScript(scriptId: string) {
  try {
    const result = await akshareScriptsApi.run(scriptId, { parameters: {} })
    ElMessage.success(`已触发执行：${result.execution_id}`)
    void router.push({ name: 'DataExecutions', query: { script_id: scriptId } })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '执行脚本失败'))
  }
}

async function toggleScript(scriptId: string) {
  try {
    await akshareScriptsApi.toggle(scriptId)
    ElMessage.success('脚本状态已更新')
    await refreshAll()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '更新脚本状态失败'))
  }
}

async function deleteScript(script: DataScript) {
  try {
    await ElMessageBox.confirm(`确认删除脚本 ${script.script_name}？`, '删除确认', { type: 'warning' })
    await akshareScriptsApi.delete(script.script_id)
    ElMessage.success('脚本已删除')
    await refreshAll()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '删除脚本失败'))
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
  color: #64748b;
}

.stat-value {
  margin-top: 8px;
  font-size: 30px;
  font-weight: 700;
  color: #0f172a;
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
  color: #0f172a;
}

.page-subtitle {
  margin-top: 4px;
  color: #64748b;
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
