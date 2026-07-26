<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('workspaceDialogs.otdTitle')"
    width="420px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form
      label-width="120px"
      size="small"
    >
      <el-form-item :label="t('workspaceDialogs.otdParallelThreads')">
        <el-input-number
          v-model="form.n_workers"
          :min="1"
          :max="32"
        />
      </el-form-item>
      <el-form-item :label="t('workspaceDialogs.otdRunMode')">
        <el-radio-group v-model="form.mode">
          <el-radio value="grid">
            {{ t('workspaceDialogs.otdModeGrid') }}
          </el-radio>
          <el-radio value="random">
            {{ t('workspaceDialogs.otdModeRandom') }}
          </el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('workspaceDialogs.otdTimeoutSec')">
        <el-input-number
          v-model="form.timeout"
          :min="0"
          :max="86400"
          :step="60"
        />
        <div class="text-xs text-gray-400 mt-1">
          {{ t('workspaceDialogs.otdTimeoutZeroHint') }}
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        @click="handleSave"
      >
        {{ t('workspaceDialogs.otdConfirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit } from '@/types/workspace'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unit: StrategyUnit | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  saved: []
}>()

const form = reactive({
  n_workers: 4,
  mode: 'grid' as 'grid' | 'random',
  timeout: 0,
})

watch(() => props.unit, (u) => {
  if (u?.optimization_config) {
    const oc = u.optimization_config as Record<string, unknown>
    form.n_workers = (oc.n_workers as number) ?? 4
    form.mode = (oc.mode as 'grid' | 'random') ?? 'grid'
    form.timeout = (oc.timeout as number) ?? 0
  }
}, { immediate: true })

async function handleSave() {
  if (!props.unit) return
  try {
    const existingConfig = props.unit.optimization_config || {}
    await workspaceApi.updateUnit(props.workspaceId, props.unit.id, {
      optimization_config: {
        ...existingConfig,
        n_workers: form.n_workers,
        mode: form.mode,
        timeout: form.timeout,
      },
    })
    ElMessage.success(t('workspaceDialogs.otdSaved'))
    emit('saved')
    emit('update:modelValue', false)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('workspaceDialogs.otdSaveFailed')))
  }
}
</script>
