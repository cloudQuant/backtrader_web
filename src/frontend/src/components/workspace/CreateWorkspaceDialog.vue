<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="480px"
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
    >
      <el-form-item
        :label="t('workspace.nameLabel')"
        prop="name"
      >
        <el-input
          v-model="form.name"
          :placeholder="t('workspace.namePlaceholder')"
          maxlength="200"
          show-word-limit
        />
      </el-form-item>
      <el-form-item
        :label="t('workspace.descLabel')"
        prop="description"
      >
        <el-input
          v-model="form.description"
          type="textarea"
          :placeholder="t('workspace.descPlaceholder')"
          maxlength="500"
          show-word-limit
          :rows="3"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">
        {{ t('workspace.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="handleSubmit"
      >
        {{ isEdit ? t('workspace.save') : t('workspace.create') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import type { FormInstance, FormRules } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { useWorkspaceStore } from '@/stores/workspace'
import type { Workspace, WorkspaceType } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspace?: Workspace | null
  workspaceType?: WorkspaceType
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const { t } = useI18n()
const store = useWorkspaceStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = ref({
  name: '',
  description: '',
})

const isEdit = computed(() => !!props.workspace)
const targetWorkspaceType = computed<WorkspaceType>(() =>
  props.workspace?.workspace_type ?? props.workspaceType ?? 'research'
)
const dialogTitle = computed(() => {
  const label = targetWorkspaceType.value === 'trading' ? t('workspace.tradingWorkspaceLabel') : t('workspace.workspaceLabelType')
  return isEdit.value ? `${t('workspace.editPrefix')}${label}` : `${t('workspace.newPrefix')}${label}`
})

const rules: FormRules = {
  name: [
    { required: true, message: t('workspace.nameRequired'), trigger: 'blur' },
    { max: 200, message: t('workspace.nameTooLong'), trigger: 'blur' },
  ],
}

watch(() => props.workspace, (workspace) => {
  if (workspace) {
    form.value.name = workspace.name
    form.value.description = workspace.description || ''
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
      ElMessage.success(t('workspace.saveSuccess'))
    } else {
      await store.createWorkspace({
        name: form.value.name,
        description: form.value.description || undefined,
        workspace_type: targetWorkspaceType.value,
      })
      ElMessage.success(t('workspace.createSuccess'))
    }
    emit('saved')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspace.saveError')))
  } finally {
    submitting.value = false
  }
}
</script>
