<template>
  <div class="space-y-6">
    <el-card>
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">接口管理</div>
            <div class="page-subtitle">管理 akshare 接口元数据和参数定义。</div>
          </div>
          <div class="actions">
            <el-button
              v-if="isAdmin"
              :loading="bootstrapping"
              @click="bootstrapInterfaces"
            >
              从 akshare 引导
            </el-button>
            <el-button
              v-if="isAdmin"
              type="primary"
              @click="openCreateDialog"
            >
              新建接口
            </el-button>
          </div>
        </div>
      </template>

      <div class="toolbar">
        <el-select
          v-model="categoryId"
          clearable
          class="toolbar-item"
          placeholder="接口分类"
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
          <el-option label="全部状态" value="all" />
          <el-option label="启用" value="active" />
          <el-option label="停用" value="inactive" />
        </el-select>
        <el-input
          v-model="search"
          clearable
          placeholder="搜索接口名、展示名、描述"
          class="toolbar-search"
          @keyup.enter="reloadFirstPage"
          @clear="reloadFirstPage"
        />
        <el-button
          type="primary"
          @click="reloadFirstPage"
        >
          查询
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="interfaces"
        stripe
      >
        <el-table-column
          prop="display_name"
          label="展示名"
          min-width="180"
        />
        <el-table-column
          prop="name"
          label="接口名"
          min-width="180"
        />
        <el-table-column
          label="分类"
          width="140"
        >
          <template #default="{ row }">
            {{ categoryNameMap[row.category_id] || row.category_id }}
          </template>
        </el-table-column>
        <el-table-column
          prop="return_type"
          label="返回类型"
          width="120"
        />
        <el-table-column
          label="参数数"
          width="90"
        >
          <template #default="{ row }">
            {{ row.params?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="90"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'warning'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          fixed="right"
          min-width="220"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="openDetail(row.id)"
            >
              详情
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              @click="openEditDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="danger"
              @click="deleteInterface(row.id)"
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
          @current-change="loadInterfaces"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建接口' : '编辑接口'"
      width="760px"
    >
      <el-form
        :model="form"
        label-width="110px"
      >
        <el-form-item label="接口名">
          <el-input
            v-model="form.name"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item label="展示名">
          <el-input v-model="form.display_name" />
        </el-form-item>
        <el-form-item label="分类">
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
        <el-form-item label="模块路径">
          <el-input v-model="form.module_path" />
        </el-form-item>
        <el-form-item label="函数名">
          <el-input v-model="form.function_name" />
        </el-form-item>
        <el-form-item label="返回类型">
          <el-input v-model="form.return_type" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="参数定义">
          <el-input
            v-model="parametersText"
            type="textarea"
            :rows="8"
          />
        </el-form-item>
        <el-form-item label="额外配置">
          <el-input
            v-model="extraConfigText"
            type="textarea"
            :rows="6"
          />
        </el-form-item>
        <el-form-item label="示例">
          <el-input
            v-model="form.example"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="submitForm"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="detailVisible"
      title="接口详情"
      size="50%"
    >
      <div v-if="currentInterface">
        <el-descriptions
          :column="2"
          border
        >
          <el-descriptions-item label="接口名">
            {{ currentInterface.name }}
          </el-descriptions-item>
          <el-descriptions-item label="展示名">
            {{ currentInterface.display_name }}
          </el-descriptions-item>
          <el-descriptions-item label="分类">
            {{ categoryNameMap[currentInterface.category_id] || currentInterface.category_id }}
          </el-descriptions-item>
          <el-descriptions-item label="返回类型">
            {{ currentInterface.return_type }}
          </el-descriptions-item>
          <el-descriptions-item
            label="描述"
            :span="2"
          >
            {{ currentInterface.description || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="drawer-section">
          <div class="section-title">参数列表</div>
          <el-table
            :data="currentInterface.params"
            stripe
          >
            <el-table-column
              prop="name"
              label="参数名"
              min-width="140"
            />
            <el-table-column
              prop="param_type"
              label="类型"
              width="100"
            />
            <el-table-column
              label="必填"
              width="80"
            >
              <template #default="{ row }">
                <el-tag :type="row.required ? 'danger' : 'info'">
                  {{ row.required ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="default_value"
              label="默认值"
              min-width="120"
            />
          </el-table>
        </div>

        <div class="drawer-section">
          <div class="section-title">原始参数定义</div>
          <pre>{{ toJsonText(currentInterface.parameters || {}) }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { akshareInterfacesApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataInterface, DataInterfaceFormPayload, InterfaceCategory } from '@/types'
import { parseJsonText, toJsonText } from '@/views/data/utils'

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
    ElMessage.error(getErrorMessage(error, '加载接口失败'))
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
    ElMessage.warning('请填写接口名、展示名并选择分类')
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
      ElMessage.success('接口已创建')
    } else if (editingInterfaceId.value !== null) {
      await akshareInterfacesApi.update(editingInterfaceId.value, payload)
      ElMessage.success('接口已更新')
    }

    dialogVisible.value = false
    await loadInterfaces()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '保存接口失败'))
  } finally {
    saving.value = false
  }
}

async function bootstrapInterfaces() {
  bootstrapping.value = true
  try {
    const result = await akshareInterfacesApi.bootstrap(true)
    ElMessage.success(`引导完成：新增 ${result.created}，更新 ${result.updated}`)
    await Promise.all([loadCategories(), loadInterfaces()])
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '引导接口失败'))
  } finally {
    bootstrapping.value = false
  }
}

async function openDetail(interfaceId: number) {
  try {
    currentInterface.value = await akshareInterfacesApi.getDetail(interfaceId)
    detailVisible.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载接口详情失败'))
  }
}

async function deleteInterface(interfaceId: number) {
  try {
    await ElMessageBox.confirm('确认删除该接口？', '删除确认', { type: 'warning' })
    await akshareInterfacesApi.delete(interfaceId)
    ElMessage.success('接口已删除')
    await loadInterfaces()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '删除接口失败'))
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
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 12px;
  overflow: auto;
}
</style>
