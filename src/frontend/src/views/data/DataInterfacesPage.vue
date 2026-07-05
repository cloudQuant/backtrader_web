<template>
  <div
    class="interfaces-page"
    data-test="interfaces-page"
  >
    <section
      class="interfaces-hero"
      data-test="interfaces-hero"
    >
      <div class="interfaces-hero-copy">
        <div class="interfaces-kicker">
          {{ t('dataPages.ifHeroKicker') }}
        </div>
        <h1>{{ t('dataPages.ifPageTitle') }}</h1>
        <p>{{ t('dataPages.ifPageDesc') }}</p>
      </div>

      <div class="interfaces-hero-actions">
        <el-button
          v-if="isAdmin"
          :icon="Refresh"
          :loading="bootstrapping"
          @click="bootstrapInterfaces"
        >
          {{ t('dataPages.ifBootstrap') }}
        </el-button>
        <el-button
          v-if="isAdmin"
          type="primary"
          :icon="Plus"
          @click="openCreateDialog"
        >
          {{ t('dataPages.ifNewInterface') }}
        </el-button>
      </div>

      <div
        class="interfaces-metrics"
        data-test="interfaces-metrics"
      >
        <article class="interfaces-metric">
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          <span>{{ t('dataPages.ifStatTotal') }}</span>
          <strong>{{ total }}</strong>
        </article>
        <article class="interfaces-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('dataPages.ifStatActive') }}</span>
          <strong>{{ activePageCount }}</strong>
        </article>
        <article class="interfaces-metric">
          <el-icon aria-hidden="true">
            <Setting />
          </el-icon>
          <span>{{ t('dataPages.ifStatParams') }}</span>
          <strong>{{ visibleParamCount }}</strong>
        </article>
        <article class="interfaces-metric">
          <el-icon aria-hidden="true">
            <Collection />
          </el-icon>
          <span>{{ t('dataPages.ifStatCategories') }}</span>
          <strong>{{ categories.length }}</strong>
        </article>
      </div>
    </section>

    <el-card
      class="interfaces-workbench"
      data-test="interfaces-workbench"
    >
      <template #header>
        <div class="interfaces-panel-heading">
          <div>
            <div class="interfaces-kicker">
              {{ t('dataPages.ifWorkbenchKicker') }}
            </div>
            <div class="interfaces-panel-title">
              {{ t('dataPages.ifWorkbenchTitle') }}
            </div>
            <p>{{ t('dataPages.ifWorkbenchDesc') }}</p>
          </div>
          <div class="interfaces-count">
            {{ t('dataPages.ifVisibleCount', { count: interfaces.length }) }}
            <span>{{ t('dataPages.ifTotalCount', { count: total }) }}</span>
          </div>
        </div>
      </template>

      <div class="interfaces-toolbar">
        <el-select
          v-model="categoryId"
          clearable
          class="toolbar-item"
          :placeholder="t('dataPages.ifCategoryPh')"
          @change="reloadFirstPage"
        >
          <el-option
            v-for="category in categories"
            :key="category.id"
            :label="category.description || category.name"
            :value="category.id"
          />
        </el-select>
        <el-select
          v-model="activeFilter"
          class="toolbar-item"
          @change="reloadFirstPage"
        >
          <el-option
            :label="t('dataPages.ifFilterAll')"
            value="all"
          />
          <el-option
            :label="t('dataPages.ifFilterActive')"
            value="active"
          />
          <el-option
            :label="t('dataPages.ifFilterInactive')"
            value="inactive"
          />
        </el-select>
        <el-input
          v-model="search"
          clearable
          :placeholder="t('dataPages.ifSearchPh')"
          class="toolbar-search"
          :prefix-icon="Search"
          @keyup.enter="reloadFirstPage"
          @clear="reloadFirstPage"
        />
        <el-button
          type="primary"
          @click="reloadFirstPage"
        >
          {{ t('dataPages.ifQuery') }}
        </el-button>
      </div>

      <div
        v-if="!loading && interfaces.length === 0"
        class="interfaces-empty"
      >
        <el-icon aria-hidden="true">
          <Connection />
        </el-icon>
        <strong>{{ t('dataPages.ifEmptyTitle') }}</strong>
        <span>{{ t('dataPages.ifEmptyDesc') }}</span>
      </div>

      <template v-else>
        <el-table
          v-loading="loading"
          :data="interfaces"
          stripe
          class="interfaces-table"
          data-test="interfaces-table"
        >
          <el-table-column
            :label="t('dataPages.ifColDisplayName')"
            min-width="240"
          >
            <template #default="{ row }">
              <div class="interface-name-cell">
                <strong>{{ row.display_name }}</strong>
                <span>{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.ifColCategory')"
            width="140"
          >
            <template #default="{ row }">
              <el-tag>{{ categoryLabel(row.category_id) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.ifColModuleFunc')"
            min-width="220"
          >
            <template #default="{ row }">
              <div class="table-main">
                {{ row.module_path || '-' }}
              </div>
              <div class="table-subtext">
                {{ row.function_name || row.name }}
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="return_type"
            :label="t('dataPages.ifColReturnType')"
            width="120"
          />
          <el-table-column
            :label="t('dataPages.ifColParamCount')"
            width="90"
          >
            <template #default="{ row }">
              {{ parameterCount(row) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.ifColStatus')"
            width="90"
          >
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'warning'">
                {{ row.is_active ? t('dataPages.ifStatusActive') : t('dataPages.ifStatusInactive') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="updated_at"
            :label="t('dataPages.ifColUpdatedAt')"
            width="180"
          >
            <template #default="{ row }">
              {{ formatDateTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="t('dataPages.ifColActions')"
            fixed="right"
            min-width="220"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                @click="openDetail(row.id)"
              >
                {{ t('dataPages.ifActionDetail') }}
              </el-button>
              <el-button
                v-if="isAdmin"
                link
                @click="openEditDialog(row)"
              >
                {{ t('dataPages.ifActionEdit') }}
              </el-button>
              <el-button
                v-if="isAdmin"
                link
                type="danger"
                @click="deleteInterface(row.id)"
              >
                {{ t('dataPages.ifActionDelete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div
          class="interfaces-mobile-list"
          data-test="interfaces-mobile-list"
        >
          <article
            v-for="item in interfaces"
            :key="item.id"
            class="interface-card"
          >
            <div class="interface-card-head">
              <div>
                <strong>{{ item.display_name }}</strong>
                <span>{{ item.name }}</span>
              </div>
              <el-tag :type="item.is_active ? 'success' : 'warning'">
                {{ item.is_active ? t('dataPages.ifStatusActive') : t('dataPages.ifStatusInactive') }}
              </el-tag>
            </div>
            <p>{{ interfaceDescription(item) }}</p>
            <div class="interface-card-grid">
              <span>{{ t('dataPages.ifColCategory') }}</span>
              <strong>{{ categoryLabel(item.category_id) }}</strong>
              <span>{{ t('dataPages.ifColReturnType') }}</span>
              <strong>{{ item.return_type }}</strong>
              <span>{{ t('dataPages.ifColParamCount') }}</span>
              <strong>{{ parameterCount(item) }}</strong>
              <span>{{ t('dataPages.ifColUpdatedAt') }}</span>
              <strong>{{ formatDateTime(item.updated_at) }}</strong>
            </div>
            <div class="interface-card-actions">
              <el-button
                size="small"
                type="primary"
                @click="openDetail(item.id)"
              >
                {{ t('dataPages.ifActionDetail') }}
              </el-button>
              <el-button
                v-if="isAdmin"
                size="small"
                @click="openEditDialog(item)"
              >
                {{ t('dataPages.ifActionEdit') }}
              </el-button>
              <el-button
                v-if="isAdmin"
                size="small"
                type="danger"
                @click="deleteInterface(item.id)"
              >
                {{ t('dataPages.ifActionDelete') }}
              </el-button>
            </div>
          </article>
        </div>
      </template>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadInterfaces"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? t('dataPages.ifDialogCreate') : t('dataPages.ifDialogEdit')"
      width="760px"
      class="interfaces-dialog"
    >
      <el-form
        :model="form"
        label-width="110px"
        class="interfaces-form"
      >
        <div class="form-grid">
          <el-form-item :label="t('dataPages.ifFormName')">
            <el-input
              v-model="form.name"
              :disabled="dialogMode === 'edit'"
            />
          </el-form-item>
          <el-form-item :label="t('dataPages.ifFormDisplayName')">
            <el-input v-model="form.display_name" />
          </el-form-item>
          <el-form-item :label="t('dataPages.ifFormCategory')">
            <el-select
              v-model="form.category_id"
              class="full-width"
            >
              <el-option
                v-for="category in categories"
                :key="category.id"
                :label="category.description || category.name"
                :value="category.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('dataPages.ifFormReturnType')">
            <el-input v-model="form.return_type" />
          </el-form-item>
          <el-form-item :label="t('dataPages.ifFormModulePath')">
            <el-input v-model="form.module_path" />
          </el-form-item>
          <el-form-item :label="t('dataPages.ifFormFuncName')">
            <el-input v-model="form.function_name" />
          </el-form-item>
        </div>
        <el-form-item :label="t('dataPages.ifFormDesc')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.ifFormParameters')">
          <el-input
            v-model="parametersText"
            type="textarea"
            :rows="8"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.ifFormExtraConfig')">
          <el-input
            v-model="extraConfigText"
            type="textarea"
            :rows="6"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.ifFormExample')">
          <el-input
            v-model="form.example"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item :label="t('dataPages.ifFormIsActive')">
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

    <el-drawer
      v-model="detailVisible"
      :title="t('dataPages.ifDetailTitle')"
      size="56%"
      class="interfaces-detail-drawer"
    >
      <div
        v-if="currentInterface"
        class="interface-detail"
        data-test="interface-detail"
      >
        <section class="detail-summary">
          <div>
            <div class="interfaces-kicker">
              {{ t('dataPages.ifDetailKicker') }}
            </div>
            <h3>{{ currentInterface.display_name }}</h3>
            <p>{{ interfaceDescription(currentInterface) }}</p>
          </div>
          <el-tag :type="currentInterface.is_active ? 'success' : 'warning'">
            {{ currentInterface.is_active ? t('dataPages.ifStatusActive') : t('dataPages.ifStatusInactive') }}
          </el-tag>
        </section>

        <div class="detail-meta-grid">
          <div>
            <span>{{ t('dataPages.ifFormName') }}</span>
            <strong>{{ currentInterface.name }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.ifFormCategory') }}</span>
            <strong>{{ categoryLabel(currentInterface.category_id) }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.ifFormModulePath') }}</span>
            <strong>{{ currentInterface.module_path || '-' }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.ifFormFuncName') }}</span>
            <strong>{{ currentInterface.function_name || currentInterface.name }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.ifFormReturnType') }}</span>
            <strong>{{ currentInterface.return_type }}</strong>
          </div>
          <div>
            <span>{{ t('dataPages.ifColParamCount') }}</span>
            <strong>{{ parameterCount(currentInterface) }}</strong>
          </div>
        </div>

        <div class="drawer-section">
          <div class="section-title">
            {{ t('dataPages.ifDetailParamList') }}
          </div>
          <el-table
            :data="currentInterface.params"
            stripe
          >
            <el-table-column
              prop="name"
              :label="t('dataPages.ifDetailColParamName')"
              min-width="140"
            />
            <el-table-column
              prop="param_type"
              :label="t('dataPages.ifDetailColType')"
              width="100"
            />
            <el-table-column
              :label="t('dataPages.ifDetailColRequired')"
              width="80"
            >
              <template #default="{ row }">
                <el-tag :type="row.required ? 'danger' : 'info'">
                  {{ row.required ? t('dataPages.ifReqYes') : t('dataPages.ifReqNo') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="default_value"
              :label="t('dataPages.ifDetailColDefault')"
              min-width="120"
            />
          </el-table>
        </div>

        <div class="drawer-section">
          <div class="section-title">
            {{ t('dataPages.ifDetailRawParams') }}
          </div>
          <pre>{{ toJsonText(currentInterface.parameters || {}) }}</pre>
        </div>
        <div class="drawer-section">
          <div class="section-title">
            {{ t('dataPages.ifDetailExtraConfig') }}
          </div>
          <pre>{{ toJsonText(currentInterface.extra_config || {}) }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CircleCheck,
  Collection,
  Connection,
  Plus,
  Refresh,
  Search,
  Setting,
} from '@element-plus/icons-vue'
import { akshareInterfacesApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataInterface, DataInterfaceFormPayload, InterfaceCategory } from '@/types'
import { parseJsonText, toJsonText } from '@/views/data/utils'

const { t } = useI18n()
const authStore = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const bootstrapping = ref(false)
const dialogVisible = ref(false)
const detailVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const categoryId = ref<number | undefined>(undefined)
const activeFilter = ref<'all' | 'active' | 'inactive'>('all')
const search = ref('')
const categories = ref<InterfaceCategory[]>([])
const interfaces = ref<DataInterface[]>([])
const currentInterface = ref<DataInterface | null>(null)
const editingInterfaceId = ref<number | null>(null)
const parametersText = ref('{}')
const extraConfigText = ref('{}')
const form = reactive<DataInterfaceFormPayload>({
  name: '',
  display_name: '',
  description: '',
  category_id: 0,
  module_path: 'akshare',
  function_name: '',
  parameters: {},
  extra_config: {},
  return_type: 'DataFrame',
  example: '',
  is_active: true,
})

const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const categoryNameMap = computed(() =>
  Object.fromEntries(categories.value.map((item) => [item.id, item.description || item.name]))
)
const activePageCount = computed(() => interfaces.value.filter(item => item.is_active).length)
const visibleParamCount = computed(() =>
  interfaces.value.reduce((sum, item) => sum + parameterCount(item), 0)
)

function parameterCount(item: Pick<DataInterface, 'params' | 'parameters'>) {
  return item.params?.length || Object.keys(item.parameters || {}).length
}

function categoryLabel(id: number) {
  return categoryNameMap.value[id] || String(id)
}

function interfaceDescription(item: DataInterface) {
  return item.description || t('dataPages.ifNoDescription')
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function resetForm() {
  form.name = ''
  form.display_name = ''
  form.description = ''
  form.category_id = categories.value[0]?.id || 0
  form.module_path = 'akshare'
  form.function_name = ''
  form.parameters = {}
  form.extra_config = {}
  form.return_type = 'DataFrame'
  form.example = ''
  form.is_active = true
  parametersText.value = '{}'
  extraConfigText.value = '{}'
  editingInterfaceId.value = null
}

async function loadCategories() {
  categories.value = await akshareInterfacesApi.getCategories()
  if (!form.category_id && categories.value[0]) {
    form.category_id = categories.value[0].id
  }
}

async function loadInterfaces() {
  loading.value = true
  try {
    const response = await akshareInterfacesApi.list({
      page: page.value,
      page_size: pageSize.value,
      category_id: categoryId.value,
      search: search.value || undefined,
      is_active:
        activeFilter.value === 'all'
          ? undefined
          : activeFilter.value === 'active',
    })
    interfaces.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.ifLoadFailed')))
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  page.value = 1
  void loadInterfaces()
}

function handleSizeChange() {
  page.value = 1
  void loadInterfaces()
}

function openCreateDialog() {
  dialogMode.value = 'create'
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(item: DataInterface) {
  dialogMode.value = 'edit'
  editingInterfaceId.value = item.id
  form.name = item.name
  form.display_name = item.display_name
  form.description = item.description ?? ''
  form.category_id = item.category_id
  form.module_path = item.module_path ?? ''
  form.function_name = item.function_name ?? ''
  form.parameters = item.parameters
  form.extra_config = item.extra_config
  form.return_type = item.return_type
  form.example = item.example ?? ''
  form.is_active = item.is_active
  parametersText.value = toJsonText(item.parameters)
  extraConfigText.value = toJsonText(item.extra_config)
  dialogVisible.value = true
}

async function submitForm() {
  if (!form.name.trim() || !form.display_name.trim() || !form.category_id) {
    ElMessage.warning(t('dataPages.ifValidationFill'))
    return
  }

  saving.value = true
  try {
    const payload: DataInterfaceFormPayload = {
      ...form,
      name: form.name.trim(),
      display_name: form.display_name.trim(),
      description: form.description?.trim() || null,
      module_path: form.module_path?.trim() || null,
      function_name: form.function_name?.trim() || null,
      example: form.example?.trim() || null,
      parameters: parseJsonText(parametersText.value),
      extra_config: parseJsonText(extraConfigText.value),
    }

    if (dialogMode.value === 'create') {
      await akshareInterfacesApi.create(payload)
      ElMessage.success(t('dataPages.ifCreated'))
    } else if (editingInterfaceId.value !== null) {
      await akshareInterfacesApi.update(editingInterfaceId.value, payload)
      ElMessage.success(t('dataPages.ifUpdated'))
    }

    dialogVisible.value = false
    await loadInterfaces()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.ifSaveFailed')))
  } finally {
    saving.value = false
  }
}

async function bootstrapInterfaces() {
  bootstrapping.value = true
  try {
    const result = await akshareInterfacesApi.bootstrap(true)
    ElMessage.success(t('dataPages.ifBootstrapped', { created: result.created, updated: result.updated }))
    await Promise.all([loadCategories(), loadInterfaces()])
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.ifBootstrapFailed')))
  } finally {
    bootstrapping.value = false
  }
}

async function openDetail(interfaceId: number) {
  try {
    currentInterface.value = await akshareInterfacesApi.getDetail(interfaceId)
    detailVisible.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error, t('dataPages.ifLoadDetailFailed')))
  }
}

async function deleteInterface(interfaceId: number) {
  try {
    await ElMessageBox.confirm(
      t('dataPages.ifDeleteConfirmMsg'),
      t('dataPages.ifDeleteConfirmTitle'),
      { type: 'warning' }
    )
    await akshareInterfacesApi.delete(interfaceId)
    ElMessage.success(t('dataPages.ifDeleted'))
    await loadInterfaces()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(getErrorMessage(error, t('dataPages.ifDeleteFailed')))
    }
  }
}

onMounted(() => {
  void Promise.all([loadCategories(), loadInterfaces()])
})
</script>

<style scoped>
.interfaces-page {
  display: grid;
  gap: 24px;
}

.interfaces-hero,
.interfaces-workbench {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.interfaces-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.interfaces-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.interfaces-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.interfaces-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.interfaces-hero p,
.interfaces-panel-heading p,
.detail-summary p {
  max-width: 820px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.interfaces-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.interfaces-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.interfaces-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.interfaces-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.interfaces-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.interfaces-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.interfaces-workbench {
  box-shadow: none;
}

.interfaces-workbench :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.interfaces-workbench :deep(.el-card__body) {
  padding: 18px;
}

.interfaces-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.interfaces-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.interfaces-count {
  display: grid;
  flex: none;
  gap: 4px;
  min-width: 120px;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 720;
  line-height: 1.35;
  text-align: right;
}

.interfaces-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.interfaces-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-item {
  width: 180px;
}

.toolbar-search {
  width: min(360px, 100%);
}

.interfaces-empty {
  display: grid;
  gap: 10px;
  min-height: 220px;
  place-items: center;
  padding: 32px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  text-align: center;
}

.interfaces-empty .el-icon {
  color: var(--primary-color);
  font-size: 24px;
}

.interfaces-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.interfaces-empty span {
  max-width: 520px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.interfaces-table {
  width: 100%;
}

.interfaces-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.interface-name-cell,
.table-main,
.table-subtext {
  min-width: 0;
}

.interface-name-cell {
  display: grid;
  gap: 4px;
}

.interface-name-cell strong,
.table-main {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
}

.interface-name-cell span,
.table-subtext {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.interfaces-mobile-list {
  display: none;
  gap: 12px;
}

.interface-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.interface-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.interface-card-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.interface-card-head strong {
  color: var(--text-color-primary);
  font-size: 14px;
  line-height: 1.3;
}

.interface-card-head span,
.interface-card p {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.interface-card p {
  margin: 0;
  color: var(--text-color-regular);
  font-size: 13px;
}

.interface-card-grid {
  display: grid;
  grid-template-columns: minmax(96px, 0.42fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.interface-card-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.interface-card-grid strong {
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.interface-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.interfaces-form {
  display: grid;
  gap: 12px;
}

.interfaces-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.interfaces-form :deep(.el-form-item__label) {
  color: var(--text-color-secondary);
  font-weight: 650;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.interfaces-dialog :deep(.el-dialog) {
  border-radius: 8px;
  background: var(--bg-color);
}

.interfaces-dialog :deep(.el-dialog__title) {
  color: var(--text-color-primary);
  font-weight: 760;
}

.interfaces-dialog :deep(.el-input__wrapper),
.interfaces-dialog :deep(.el-select__wrapper),
.interfaces-dialog :deep(.el-textarea__inner) {
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
}

.interface-detail {
  display: grid;
  gap: 18px;
}

.detail-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.detail-summary h3 {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.25;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-meta-grid div {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.detail-meta-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.detail-meta-grid strong {
  color: var(--text-color-primary);
  overflow-wrap: anywhere;
}

.drawer-section {
  margin-top: 20px;
}

.section-title {
  margin-bottom: 10px;
  font-weight: 700;
}

.full-width {
  width: 100%;
}

pre {
  margin: 0;
  padding: 14px;
  background: var(--code-bg-color);
  color: var(--code-text-color);
  border-radius: 12px;
  overflow: auto;
}

@media (max-width: 1100px) {
  .interfaces-hero,
  .interfaces-panel-heading {
    display: grid;
    grid-template-columns: 1fr;
  }

  .interfaces-hero-actions {
    justify-content: flex-start;
  }

  .interfaces-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .interfaces-count {
    width: fit-content;
    text-align: left;
  }
}

@media (max-width: 900px) {
  .interfaces-table {
    display: none;
  }

  .interfaces-mobile-list {
    display: grid;
  }
}

@media (max-width: 640px) {
  .interfaces-hero {
    padding: 18px;
  }

  .interfaces-hero h1 {
    font-size: 24px;
  }

  .interfaces-metrics,
  .form-grid,
  .detail-meta-grid {
    grid-template-columns: 1fr;
  }

  .interfaces-hero-actions,
  .interfaces-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .interfaces-hero-actions :deep(.el-button),
  .interfaces-toolbar :deep(.el-button),
  .toolbar-item,
  .toolbar-search {
    width: 100%;
  }
}
</style>
