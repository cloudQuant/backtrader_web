<template>
  <el-dialog
    :model-value="modelValue"
    title="策略研究--分组更名"
    width="480px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form
      :model="form"
      label-width="120px"
    >
      <el-form-item label="重命名方式">
        <el-radio-group
          v-model="form.mode"
          class="flex flex-col gap-2"
        >
          <el-radio value="custom">
            自定义
            <el-input
              v-model="form.value"
              :disabled="form.mode !== 'custom'"
              style="width: 200px; margin-left: 8px"
              placeholder="输入新组名"
            />
          </el-radio>
          <el-radio value="strategy">
            使用公式名
          </el-radio>
          <el-radio value="symbol">
            使用代码
          </el-radio>
          <el-radio value="symbol_name">
            使用名称
          </el-radio>
          <el-radio value="category">
            使用分类
          </el-radio>
          <el-radio value="replace">
            替换
            <span
              v-if="form.mode === 'replace'"
              class="ml-2"
            >
              原字符: <el-input
                v-model="form.search"
                style="width: 100px"
                size="small"
              />
              替换为: <el-input
                v-model="form.replace"
                style="width: 100px"
                size="small"
              />
            </span>
          </el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="handleSave"
      >
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unitIds: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const store = useWorkspaceStore()
const saving = ref(false)

type RenameMode = 'custom' | 'strategy' | 'symbol' | 'symbol_name' | 'category' | 'replace'

const form = ref({
  mode: 'custom' as RenameMode,
  value: '',
  search: '',
  replace: '',
})

async function handleSave() {
  if (!props.unitIds.length) return
  saving.value = true
  try {
    await store.renameGroup(props.workspaceId, {
      unit_ids: [...props.unitIds],
      mode: form.value.mode,
      value: form.value.value,
      search: form.value.search,
      replace: form.value.replace,
    })
    ElMessage.success('分组已重命名')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '重命名失败'))
  } finally {
    saving.value = false
  }
}
</script>
