<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('workspaceDialogs.rnUnitTitle')"
    width="480px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form
      v-if="unit"
      :model="form"
      label-width="120px"
    >
      <el-form-item :label="t('workspaceDialogs.rnOriginalName')">
        <span class="font-medium">{{ unit.symbol }}_{{ unit.timeframe }}</span>
      </el-form-item>

      <el-form-item :label="t('workspaceDialogs.rnMode')">
        <el-radio-group
          v-model="form.mode"
          class="flex flex-col gap-2"
        >
          <el-radio value="custom">
            {{ t('workspaceDialogs.rnModeCustom') }}
            <el-input
              v-model="form.value"
              :disabled="form.mode !== 'custom'"
              style="width: 200px; margin-left: 8px"
              :placeholder="t('workspaceDialogs.rnInputNewName')"
            />
          </el-radio>
          <el-radio value="strategy">
            {{ t('workspaceDialogs.rnModeStrategy') }}
          </el-radio>
          <el-radio value="symbol">
            {{ t('workspaceDialogs.rnModeSymbol') }}
          </el-radio>
          <el-radio value="symbol_name">
            {{ t('workspaceDialogs.rnModeSymbolName') }}
          </el-radio>
          <el-radio value="category">
            {{ t('workspaceDialogs.rnModeCategory') }}
          </el-radio>
          <el-radio value="replace">
            {{ t('workspaceDialogs.rnModeReplace') }}
            <span
              v-if="form.mode === 'replace'"
              class="ml-2"
            >
              {{ t('workspaceDialogs.rnSearchLabel') }} <el-input
                v-model="form.search"
                style="width: 100px"
                size="small"
              />
              {{ t('workspaceDialogs.rnReplaceLabel') }} <el-input
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
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="handleSave"
      >
        {{ t('workspaceDialogs.rnConfirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit } from '@/types/workspace'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unit: StrategyUnit | null
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
  if (!props.unit) return
  saving.value = true
  try {
    await store.renameUnit(props.workspaceId, {
      unit_id: props.unit.id,
      mode: form.value.mode,
      value: form.value.value,
      search: form.value.search,
      replace: form.value.replace,
    })
    ElMessage.success(t('workspaceDialogs.rnUnitRenamed'))
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('workspaceDialogs.rnRenameFailed')))
  } finally {
    saving.value = false
  }
}
</script>
