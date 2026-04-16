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
            策略单元
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ unit.strategy_name || unit.strategy_id }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            品种
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ unit.symbol }} {{ unit.symbol_name }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            当前周期
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
            基础数据设置
          </div>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="周期">
                <el-select
                  v-model="form.timeframe"
                  style="width: 100%"
                >
                  <el-option
                    label="1分钟"
                    value="1m"
                  />
                  <el-option
                    label="5分钟"
                    value="5m"
                  />
                  <el-option
                    label="15分钟"
                    value="15m"
                  />
                  <el-option
                    label="30分钟"
                    value="30m"
                  />
                  <el-option
                    label="1小时"
                    value="1h"
                  />
                  <el-option
                    label="4小时"
                    value="4h"
                  />
                  <el-option
                    label="日线"
                    value="1d"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="N值">
                <el-input-number
                  v-model="form.timeframe_n"
                  :min="1"
                  :max="100"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="范围类型">
            <el-radio-group v-model="form.range_type">
              <el-radio value="date">
                日期
              </el-radio>
              <el-radio value="sample">
                样本数
              </el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item
            v-if="form.range_type === 'sample'"
            label="样本数"
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
              <el-form-item label="起始日期">
                <el-date-picker
                  v-model="form.start_date"
                  type="datetime"
                  placeholder="选择起始日期"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="结束日期">
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
            行情处理选项
          </div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="复权方式">
                <el-radio-group v-model="form.adjust_type">
                  <el-radio value="none">
                    不复权
                  </el-radio>
                  <el-radio value="forward">
                    后复权
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="分割方式">
                <el-radio-group v-model="form.split_type">
                  <el-radio value="natural">
                    自然
                  </el-radio>
                  <el-radio value="trading">
                    交易
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="数据范围">
                <el-select
                  v-model="form.data_range"
                  style="width: 100%"
                >
                  <el-option
                    label="全部"
                    value="all"
                  />
                  <el-option
                    label="主力"
                    value="main"
                  />
                  <el-option
                    label="夜盘"
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
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit, WorkspaceType } from '@/types/workspace'

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
  `${props.workspaceType === 'trading' ? '策略交易' : '策略研究'}--数据源设置`
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
    ElMessage.success('数据源设置已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>
