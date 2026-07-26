<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('workspaceDialogs.csTitle')"
    width="420px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form
      label-width="80px"
      size="small"
    >
      <el-form-item :label="t('workspaceDialogs.csSymbolCode')">
        <el-input
          v-model="form.symbol"
          :placeholder="t('workspaceDialogs.csSymbolCodeHint')"
        />
      </el-form-item>
      <el-form-item :label="t('workspaceDialogs.csSymbolName')">
        <el-input
          v-model="form.symbol_name"
          :placeholder="t('workspaceDialogs.csSymbolNameHint')"
        />
      </el-form-item>
      <el-form-item :label="t('workspaceDialogs.csTimeframe')">
        <el-select
          v-model="form.timeframe"
          style="width: 100%"
        >
          <el-option
            label="M1"
            value="M1"
          />
          <el-option
            label="M5"
            value="M5"
          />
          <el-option
            label="M15"
            value="M15"
          />
          <el-option
            label="M30"
            value="M30"
          />
          <el-option
            label="H1"
            value="H1"
          />
          <el-option
            label="H4"
            value="H4"
          />
          <el-option
            label="D1"
            value="D1"
          />
          <el-option
            label="W1"
            value="W1"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('workspaceDialogs.csApplyScope')">
        <el-radio-group v-model="applyScope">
          <el-radio value="single">
            {{ t('workspaceDialogs.csScopeSingle') }}
          </el-radio>
          <el-radio value="selected">
            {{ t('workspaceDialogs.csScopeSelected') }}
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
        @click="handleSave"
      >
        {{ t('workspaceDialogs.csConfirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
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
  selectedUnitIds: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  saved: []
}>()

const form = reactive({
  symbol: '',
  symbol_name: '',
  timeframe: 'D1',
})
const applyScope = ref<'single' | 'selected'>('single')

watch(() => props.unit, (u) => {
  if (u) {
    form.symbol = u.symbol || ''
    form.symbol_name = u.symbol_name || ''
    form.timeframe = u.timeframe || 'D1'
  }
}, { immediate: true })

async function handleSave() {
  if (!form.symbol) {
    ElMessage.warning(t('workspaceDialogs.csInputSymbol'))
    return
  }
  try {
    const ids = applyScope.value === 'selected' ? props.selectedUnitIds : (props.unit ? [props.unit.id] : [])
    for (const id of ids) {
      await workspaceApi.updateUnit(props.workspaceId, id, {
        symbol: form.symbol,
        symbol_name: form.symbol_name,
        timeframe: form.timeframe,
      })
    }
    ElMessage.success(t('workspaceDialogs.csSwitchedNUnits', { n: ids.length }))
    emit('saved')
    emit('update:modelValue', false)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('workspaceDialogs.csSwitchFailed')))
  }
}
</script>
