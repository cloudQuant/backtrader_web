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
        <textarea
          class="strategy-code-input"
          :value="form.code"
          :placeholder="t('strategy.strategyCode')"
          :aria-label="t('strategy.strategyCode')"
          rows="18"
          spellcheck="false"
          autocomplete="off"
          autocapitalize="off"
          @input="updateCode"
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

function updateCode(event: Event) {
  const target = event.target as HTMLTextAreaElement
  updateFormField('code', target.value)
}
</script>

<style scoped>
.strategy-code-input {
  box-sizing: border-box;
  display: block;
  width: 100%;
  min-height: 400px;
  padding: 12px;
  resize: vertical;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 14px;
  line-height: 1.55;
}

.strategy-code-input:focus {
  border-color: var(--el-color-primary);
  outline: 2px solid color-mix(in srgb, var(--el-color-primary) 20%, transparent);
  outline-offset: 1px;
}
</style>
