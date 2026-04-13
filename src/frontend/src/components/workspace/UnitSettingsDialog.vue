<template>
  <el-dialog :model-value="modelValue" :title="dialogTitle" width="820px" @update:model-value="$emit('update:modelValue', $event)" @open="initForm">
    <div v-if="unit" class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">策略单元</div>
          <div class="mt-1 text-sm font-semibold text-slate-700">{{ unit.strategy_name || unit.strategy_id }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">交易模式</div>
          <div class="mt-1 text-sm font-semibold text-slate-700">{{ props.workspaceType === 'trading' ? (unit.trading_mode === 'live' ? '实盘交易' : '模拟交易') : '研究模式' }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">最新更新时间</div>
          <div class="mt-1 text-sm font-semibold text-slate-700">{{ new Date(unit.updated_at).toLocaleString('zh-CN') }}</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">当前资金</div>
          <div class="mt-1 text-sm font-semibold text-slate-700">{{ form.initial_cash }}</div>
        </div>
      </div>

      <el-form ref="formRef" :model="form" label-width="130px" size="default">
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">保证金 / 利率</div>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="保证金方式">
                <el-select v-model="form.margin_rate_method" style="width: 100%">
                  <el-option label="成交金额百分比" value="percent" />
                  <el-option label="每手固定金额" value="fixed" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="多头保证金率%">
                <el-input-number v-model="form.long_margin_rate" :min="0" :max="100" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="空头保证金率%">
                <el-input-number v-model="form.short_margin_rate" :min="0" :max="100" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="无风险利率%">
                <el-input-number v-model="form.risk_free_rate" :min="0" :max="100" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">公式交易设定</div>
          <el-form-item label="初始资金">
            <el-input-number v-model="form.initial_cash" :min="1000" :step="10000" style="width: 260px" />
          </el-form-item>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">手续费</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="费率方式">
                <el-select v-model="form.commission_method" style="width: 100%">
                  <el-option label="成交金额万分比" value="percent_10k" />
                  <el-option label="每手固定金额" value="fixed_per_lot" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="开仓费率">
                <el-input-number v-model="form.open_commission_rate" :min="0" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="平仓费率">
                <el-input-number v-model="form.close_commission_rate" :min="0" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="平今费率">
                <el-input-number v-model="form.close_today_commission_rate" :min="0" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">滑点</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="滑点单位">
                <el-select v-model="form.slippage_unit" style="width: 100%">
                  <el-option label="跳/手" value="tick" />
                  <el-option label="固定值" value="fixed" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="滑点值">
                <el-input-number v-model="form.slippage_value" :min="0" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>
      </el-form>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FormInstance } from 'element-plus'
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
const formRef = ref<FormInstance>()
const saving = ref(false)
const dialogTitle = computed(() =>
  `${props.workspaceType === 'trading' ? '策略交易' : '策略研究'}--策略单元设置`
)

const defaultSettings = () => ({
  margin_rate_method: 'percent',
  long_margin_rate: 8,
  short_margin_rate: 8,
  risk_free_rate: 0,
  initial_cash: 1000000,
  commission_method: 'percent_10k',
  open_commission_rate: 2,
  close_commission_rate: 2,
  close_today_commission_rate: 2,
  slippage_unit: 'tick',
  slippage_value: 0,
})

const form = ref(defaultSettings())

function initForm() {
  if (!props.unit) return
  const us = props.unit.unit_settings || {}
  form.value = {
    margin_rate_method: (us.margin_rate_method as string) || 'percent',
    long_margin_rate: (us.long_margin_rate as number) ?? 8,
    short_margin_rate: (us.short_margin_rate as number) ?? 8,
    risk_free_rate: (us.risk_free_rate as number) ?? 0,
    initial_cash: (us.initial_cash as number) ?? 1000000,
    commission_method: (us.commission_method as string) || 'percent_10k',
    open_commission_rate: (us.open_commission_rate as number) ?? 2,
    close_commission_rate: (us.close_commission_rate as number) ?? 2,
    close_today_commission_rate: (us.close_today_commission_rate as number) ?? 2,
    slippage_unit: (us.slippage_unit as string) || 'tick',
    slippage_value: (us.slippage_value as number) ?? 0,
  }
}

async function handleSave() {
  if (!props.unit) return
  saving.value = true
  try {
    await store.updateUnit(props.workspaceId, props.unit.id, {
      unit_settings: { ...form.value },
    })
    ElMessage.success('单元设置已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>
