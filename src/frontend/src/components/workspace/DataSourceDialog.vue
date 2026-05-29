<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="760px"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="initForm"
  >
    <div
      v-if="unit"
      class="space-y-4"
    >
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.strategyUnit') }}
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ unit.strategy_name || unit.strategy_id }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.symbol') }}
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ unit.symbol }} {{ unit.symbol_name }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.currentTimeframe') }}
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ unit.timeframe }} / N={{ unit.timeframe_n }}
          </div>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        label-width="100px"
      >
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">
            {{ t('workspaceDialogs.baseDataSettings') }}
          </div>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('workspaceDialogs.timeframeLabel')">
                <el-select
                  v-model="form.timeframe"
                  style="width: 100%"
                >
                  <el-option
                    label="1m"
                    value="1m"
                  />
                  <el-option
                    label="5m"
                    value="5m"
                  />
                  <el-option
                    label="15m"
                    value="15m"
                  />
                  <el-option
                    label="30m"
                    value="30m"
                  />
                  <el-option
                    label="1h"
                    value="1h"
                  />
                  <el-option
                    label="4h"
                    value="4h"
                  />
                  <el-option
                    :label="t('workspaceDialogs.daily')"
                    value="1d"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="N">
                <el-input-number
                  v-model="form.timeframe_n"
                  :min="1"
                  :max="100"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item :label="t('workspaceDialogs.rangeType')">
            <el-radio-group v-model="form.range_type">
              <el-radio value="date">
                {{ t('workspaceDialogs.dateLabel') }}
              </el-radio>
              <el-radio value="sample">
                {{ t('workspaceDialogs.sampleCount') }}
              </el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item
            v-if="form.range_type === 'sample'"
            :label="t('workspaceDialogs.sampleCount')"
          >
            <el-input-number
              v-model="form.sample_count"
              :min="100"
              :max="100000"
              style="width: 200px"
            />
          </el-form-item>

          <el-row
            v-if="form.range_type === 'date'"
            :gutter="20"
          >
            <el-col :span="12">
              <el-form-item :label="t('workspaceDialogs.rangeStartDate')">
                <el-date-picker
                  v-model="form.start_date"
                  type="datetime"
                  :placeholder="t('workspaceDialogs.selectStartDate')"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('workspaceDialogs.rangeEndDate')">
                <div class="flex w-full items-center gap-3">
                  <el-checkbox v-model="form.use_end_date" />
                  <el-date-picker
                    v-model="form.end_date"
                    type="datetime"
                    :disabled="!form.use_end_date"
                    style="width: 100%"
                  />
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">
            {{ t('workspaceDialogs.adjustMode') }}
          </div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item :label="t('workspaceDialogs.adjustMode')">
                <el-radio-group v-model="form.adjust_type">
                  <el-radio value="none">
                    {{ t('workspaceDialogs.adjustNone') }}
                  </el-radio>
                  <el-radio value="forward">
                    {{ t('workspaceDialogs.adjustPost') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('workspaceDialogs.splitMode')">
                <el-radio-group v-model="form.split_type">
                  <el-radio value="natural">
                    {{ t('workspaceDialogs.natural') }}
                  </el-radio>
                  <el-radio value="trading">
                    {{ t('workspaceDialogs.trading') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('workspaceDialogs.dataRange')">
                <el-select
                  v-model="form.data_range"
                  style="width: 100%"
                >
                  <el-option
                    :label="t('workspaceDialogs.all')"
                    value="all"
                  />
                  <el-option
                    :label="t('workspaceDialogs.main')"
                    value="main"
                  />
                  <el-option
                    :label="t('workspaceDialogs.night')"
                    value="night"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </div>
      </el-form>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">
        {{ t('workspaceDialogs.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="handleSave"
      >
        {{ t('workspaceDialogs.confirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit, WorkspaceType } from '@/types/workspace'

const { t } = useI18n()
const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unit: StrategyUnit | null
  workspaceType?: WorkspaceType
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const store = useWorkspaceStore()
const saving = ref(false)
const dialogTitle = computed(() =>
  `${props.workspaceType === 'trading' ? t('workspaceDialogs.strategyTrading') : t('workspaceDialogs.strategyResearch')}--${t('workspaceDialogs.dataSourceTitle')}`
)

function defaultStartDate(): Date {
  return new Date('2020-01-01T00:00:00.000Z')
}

function defaultEndDate(): Date {
  return new Date()
}

function toPickerDate(value: unknown, fallback: Date): Date {
  if (value instanceof Date) return value
  if (typeof value === 'string' && value) {
    const parsed = new Date(value)
    if (!Number.isNaN(parsed.getTime())) return parsed
  }
  return fallback
}

const form = ref({
  timeframe: '1d',
  timeframe_n: 1,
  range_type: 'date' as 'date' | 'sample',
  sample_count: 1000,
  start_date: defaultStartDate(),
  end_date: defaultEndDate(),
  use_end_date: true,
  adjust_type: 'none',
  split_type: 'natural',
  data_range: 'all',
})

function initForm() {
  if (!props.unit) return
  const dc = props.unit.data_config || {}
  const rangeType: 'date' | 'sample' = dc.range_type === 'sample' ? 'sample' : 'date'
  form.value = {
    timeframe: props.unit.timeframe || '1d',
    timeframe_n: props.unit.timeframe_n || 1,
    range_type: rangeType,
    sample_count: (dc.sample_count as number) || 1000,
    start_date: toPickerDate(dc.start_date, defaultStartDate()),
    end_date: toPickerDate(dc.end_date, defaultEndDate()),
    use_end_date: dc.use_end_date !== false,
    adjust_type: (dc.adjust_type as string) || 'none',
    split_type: (dc.split_type as string) || 'natural',
    data_range: (dc.data_range as string) || 'all',
  }
}

async function handleSave() {
  if (!props.unit) return
  saving.value = true
  try {
    await store.updateUnit(props.workspaceId, props.unit.id, {
      timeframe: form.value.timeframe,
      timeframe_n: form.value.timeframe_n,
      data_config: {
        range_type: form.value.range_type,
        sample_count: form.value.sample_count,
        start_date: form.value.start_date ? new Date(form.value.start_date).toISOString() : '',
        end_date: form.value.end_date ? new Date(form.value.end_date).toISOString() : '',
        use_end_date: form.value.use_end_date,
        adjust_type: form.value.adjust_type,
        split_type: form.value.split_type,
        data_range: form.value.data_range,
      },
    })
    ElMessage.success(t('workspaceDialogs.dataSourceSaved'))
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, t('workspaceDialogs.dataSourceSaveFailed')))
  } finally {
    saving.value = false
  }
}
</script>
