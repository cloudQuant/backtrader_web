<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑工作区' : '新建工作区'"
    width="480px"
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入工作区名称" maxlength="200" show-word-limit />
      </el-form-item>
      <el-form-item label="描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          placeholder="请输入描述（可选）"
          maxlength="500"
          show-word-limit
          :rows="3"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'
import type { Workspace } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspace?: Workspace | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const store = useWorkspaceStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = ref({
  name: '',
  description: '',
})

const isEdit = computed(() => !!props.workspace)

const rules: FormRules = {
  name: [
    { required: true, message: '请输入工作区名称', trigger: 'blur' },
    { max: 200, message: '名称最多200个字符', trigger: 'blur' },
  ],
}

watch(() => props.workspace, (ws) => {
  if (ws) {
    form.value.name = ws.name
    form.value.description = ws.description || ''
  }
}, { immediate: true })

function resetForm() {
  form.value = { name: '', description: '' }
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEdit.value && props.workspace) {
      await store.updateWorkspace(props.workspace.id, {
        name: form.value.name,
        description: form.value.description || undefined,
      })
      ElMessage.success('工作区已更新')
    } else {
      await store.createWorkspace({
        name: form.value.name,
        description: form.value.description || undefined,
      })
      ElMessage.success('工作区已创建')
    }
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '操作失败'))
  } finally {
    submitting.value = false
  }
}
</script>
