<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">
              {{ t('dataPages.ifPageTitle') }}
            </div>
            <div class="page-subtitle">
              {{ t('dataPages.ifPageDesc') }}
            </div>
          </div>
          <div class="actions">
            <el-button
              v-if="isAdmin"
              :loading="bootstrapping"
              @click="bootstrapInterfaces"
            >
              {{ t('dataPages.ifBootstrap') }}
            </el-button>
            <el-button
              v-if="isAdmin"
              type="primary"
              @click="openCreateDialog"
            >
              {{ t('dataPages.ifNewInterface') }}
            </el-button>
          </div>
        </div>
      </template>

      <div class="toolbar">
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

      <el-table
        v-loading="loading"
        :data="interfaces"
        stripe
      >
        <el-table-column
          prop="display_name"
          :label="t('dataPages.ifColDisplayName')"
          min-width="180"
        />
        <el-table-column
          prop="name"
          :label="t('dataPages.ifColName')"
          min-width="180"
        />
        <el-table-column
          :label="t('dataPages.ifColCategory')"
          width="140"
        >
          <template #default="{ row }">
            {{ categoryNameMap[row.category_id] || row.category_id }}
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
            {{ row.params?.length || 0 }}
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
    >
      <el-form
        :model="form"
        label-width="110px"
      >
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
        <el-form-item :label="t('dataPages.ifFormModulePath')">
          <el-input v-model="form.module_path" />
        </el-form-item>
        <el-form-item :label="t('dataPages.ifFormFuncName')">
          <el-input v-model="form.function_name" />
        </el-form-item>
        <el-form-item :label="t('dataPages.ifFormReturnType')">
          <el-input v-model="form.return_type" />
        </el-form-item>
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
      size="50%"
    >
      <div v-if="currentInterface">
        <el-descriptions
          :column="2"
          border
        >
          <el-descriptions-item :label="t('dataPages.ifFormName')">
            {{ currentInterface.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.ifFormDisplayName')">
            {{ currentInterface.display_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.ifFormCategory')">
            {{ categoryNameMap[currentInterface.category_id] || currentInterface.category_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('dataPages.ifFormReturnType')">
            {{ currentInterface.return_type }}
          </el-descriptions-item>
          <el-descriptions-item
            :label="t('dataPages.ifFormDesc')"
            :span="2"
          >
            {{ currentInterface.description || '-' }}
          </el-descriptions-item>
        </el-descriptions>

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
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
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
.header-row,
.actions,
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
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
</style>
