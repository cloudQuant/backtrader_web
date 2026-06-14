<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? t('strategy.editStrategy') : t('strategy.createStrategy')"
    width="800px"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <el-form
      :model="form"
      label-width="100px"
    >
      <el-form-item
        :label="t('strategy.strategyName')"
        required
      >
        <el-input
          :model-value="form.name"
          :placeholder="t('strategy.strategyName')"
          @update:model-value="(value: string) => updateFormField('name', value)"
        />
      </el-form-item>
      <el-form-item :label="t('strategy.description')">
        <el-input
          :model-value="form.description"
          type="textarea"
          :rows="2"
          :placeholder="t('strategy.description')"
          @update:model-value="(value: string) => updateFormField('description', value)"
        />
      </el-form-item>
      <el-form-item :label="t('strategy.title')">
        <el-select
          :model-value="form.category"
          class="w-full"
          @update:model-value="(value: string) => updateFormField('category', value)"
        >
          <el-option
            :label="t('strategy.categoryTrend')"
            value="trend"
          />
          <el-option
            :label="t('strategy.categoryMeanReversion')"
            value="mean_reversion"
          />
          <el-option
            :label="t('strategy.categoryVolatility')"
            value="volatility"
          />
          <el-option
            :label="t('strategy.indicatorStrategy')"
            value="indicator"
          />
          <el-option
            :label="t('strategy.arbitrageStrategy')"
            value="arbitrage"
          />
          <el-option
            :label="t('strategy.categoryOther')"
            value="custom"
          />
        </el-select>
      </el-form-item>
      <el-form-item
        :label="t('strategy.strategyCode')"
        required
      >
        <MonacoEditor
          :model-value="form.code"
          language="python"
          :height="400"
          theme="vs"
          @update:model-value="(value: string) => updateFormField('code', value)"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">
        {{ t('strategy.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="emit('save')"
      >
        {{ isEdit ? t('strategy.save') : t('strategy.create') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MonacoEditor from '@/components/common/MonacoEditor.vue'

const { t } = useI18n()

interface StrategyEditForm {
  name: string
  description: string
  code: string
  category: string
}

const props = defineProps<{
  visible: boolean
  isEdit: boolean
  saving: boolean
  form: StrategyEditForm
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'update:form', value: StrategyEditForm): void
  (e: 'save'): void
}>()

function updateFormField<K extends keyof StrategyEditForm>(
  field: K,
  value: StrategyEditForm[K]
) {
  emit('update:form', { ...props.form, [field]: value })
}
</script>
