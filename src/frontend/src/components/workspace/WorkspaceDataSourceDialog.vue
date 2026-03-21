<template>
  <el-dialog
    :model-value="modelValue"
    title="工作区数据源配置"
    width="720px"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="initForm"
  >
    <el-form :model="form" label-width="110px">
      <el-form-item label="数据源类型">
        <el-radio-group v-model="form.type">
          <el-radio value="csv">本地 CSV</el-radio>
          <el-radio value="mysql">MySQL</el-radio>
          <el-radio value="postgresql">PostgreSQL</el-radio>
          <el-radio value="mongodb">MongoDB</el-radio>
        </el-radio-group>
      </el-form-item>

      <template v-if="form.type === 'csv'">
        <el-form-item label="数据目录">
          <el-input
            v-model="form.csv.directory_path"
            placeholder="请输入保存 CSV 数据的文件夹路径"
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="分隔符">
              <el-input v-model="form.csv.delimiter" maxlength="3" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="编码">
              <el-input v-model="form.csv.encoding" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="包含表头">
              <el-switch v-model="form.csv.has_header" />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <template v-else-if="form.type === 'mysql'">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="主机">
              <el-input v-model="form.mysql.host" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="端口">
              <el-input-number v-model="form.mysql.port" :min="1" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="数据库">
              <el-input v-model="form.mysql.database" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="表名">
              <el-input v-model="form.mysql.table" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="form.mysql.username" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="form.mysql.password" type="password" show-password />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <template v-else-if="form.type === 'postgresql'">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="主机">
              <el-input v-model="form.postgresql.host" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="端口">
              <el-input-number v-model="form.postgresql.port" :min="1" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="数据库">
              <el-input v-model="form.postgresql.database" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="Schema">
              <el-input v-model="form.postgresql.schema" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="表名">
              <el-input v-model="form.postgresql.table" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="form.postgresql.username" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="form.postgresql.password" type="password" show-password />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <template v-else-if="form.type === 'mongodb'">
        <el-form-item label="连接 URI">
          <el-input v-model="form.mongodb.uri" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="数据库">
              <el-input v-model="form.mongodb.database" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="集合">
              <el-input v-model="form.mongodb.collection" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="用户名">
              <el-input v-model="form.mongodb.username" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="密码">
              <el-input v-model="form.mongodb.password" type="password" show-password />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="认证库">
              <el-input v-model="form.mongodb.auth_source" />
            </el-form-item>
          </el-col>
        </el-row>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'
import type { Workspace, WorkspaceDataSourceConfig } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  workspace: Workspace | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const store = useWorkspaceStore()
const saving = ref(false)

function createDefaultDataSourceConfig(): WorkspaceDataSourceConfig {
  return {
    type: 'csv',
    csv: {
      directory_path: '',
      delimiter: ',',
      encoding: 'utf-8',
      has_header: true,
    },
    mysql: {
      host: '127.0.0.1',
      port: 3306,
      database: '',
      username: '',
      password: '',
      table: '',
    },
    postgresql: {
      host: '127.0.0.1',
      port: 5432,
      database: '',
      schema: 'public',
      username: '',
      password: '',
      table: '',
    },
    mongodb: {
      uri: 'mongodb://127.0.0.1:27017',
      database: '',
      collection: '',
      username: '',
      password: '',
      auth_source: 'admin',
    },
  }
}

const form = ref<WorkspaceDataSourceConfig>(createDefaultDataSourceConfig())

function initForm() {
  const defaultConfig = createDefaultDataSourceConfig()
  const source = props.workspace?.settings?.data_source
  if (!source) {
    form.value = defaultConfig
    return
  }

  const legacyCsv = source.csv as Record<string, unknown> | undefined
  form.value = {
    ...defaultConfig,
    ...source,
    csv: {
      ...defaultConfig.csv,
      ...(source.csv || {}),
      directory_path:
        source.csv?.directory_path ||
        (typeof legacyCsv?.file_path === 'string' ? legacyCsv.file_path : '') ||
        defaultConfig.csv.directory_path,
    },
    mysql: { ...defaultConfig.mysql, ...(source.mysql || {}) },
    postgresql: { ...defaultConfig.postgresql, ...(source.postgresql || {}) },
    mongodb: { ...defaultConfig.mongodb, ...(source.mongodb || {}) },
  }
}

async function handleSave() {
  saving.value = true
  try {
    await store.updateWorkspace(props.workspaceId, {
      settings: {
        data_source: JSON.parse(JSON.stringify(form.value)),
      },
    })
    ElMessage.success('工作区数据源配置已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>
