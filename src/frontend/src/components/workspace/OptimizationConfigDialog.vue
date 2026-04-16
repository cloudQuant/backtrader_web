<template>
  <el-dialog
    :model-value="modelValue"
    title="策略研究--优化参数设置"
    width="750px"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="initForm"
  >
    <el-form
      v-if="unit"
      ref="formRef"
      :model="form"
      label-width="120px"
      size="default"
    >
      <el-form-item label="源策略单元">
        <span class="font-medium">{{ unit.strategy_name || unit.strategy_id }} @ {{ unit.symbol }}_{{ unit.timeframe }}</span>
      </el-form-item>

      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="优化目标">
            <el-select
              v-model="form.objective"
              style="width: 100%"
            >
              <el-option
                label="夏普比率最大"
                value="sharpe_max"
              />
              <el-option
                label="最大收益"
                value="max_return"
              />
              <el-option
                label="最小回撤"
                value="min_drawdown"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="最优显示">
            <el-input-number
              v-model="form.max_display"
              :min="100"
              :max="50000"
              :step="100"
              style="width: 140px"
            />
            <span class="ml-1 text-gray-400">条</span>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="初始资金(万)">
            <el-input-number
              v-model="form.initial_cash_wan"
              :min="1"
              :precision="2"
              style="width: 160px"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="计算方式">
            <el-radio-group v-model="form.calculation_method">
              <el-radio value="geometric">
                几何
              </el-radio>
              <el-radio value="arithmetic">
                算术
              </el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
      </el-row>

      <el-divider content-position="left">
        参数列表
      </el-divider>

      <el-table
        :data="form.param_layers"
        border
        size="small"
        class="mb-4"
      >
        <el-table-column
          label="参数名"
          width="120"
        >
          <template #default="{ row }">
            <el-input
              v-model="row.param_name"
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column
          label="类型"
          width="80"
          align="center"
        >
          <template #default>
            数值型
          </template>
        </el-table-column>
        <el-table-column
          label="当前值"
          width="100"
        >
          <template #default="{ row }">
            <el-input-number
              v-model="row.current_value"
              :controls="false"
              size="small"
              style="width: 100%"
            />
          </template>
        </el-table-column>
        <el-table-column
          label="优化设置"
          min-width="240"
        >
          <template #default="{ row }">
            <div class="flex items-center gap-1">
              <el-select
                v-model="row.opt_type"
                size="small"
                style="width: 80px"
              >
                <el-option
                  label="等差"
                  value="equal_diff"
                />
                <el-option
                  label="固定"
                  value="fixed"
                />
              </el-select>
              <template v-if="row.opt_type === 'equal_diff'">
                <el-input-number
                  v-model="row.start"
                  :controls="false"
                  size="small"
                  style="width: 70px"
                  placeholder="起始"
                />
                <span>~</span>
                <el-input-number
                  v-model="row.end"
                  :controls="false"
                  size="small"
                  style="width: 70px"
                  placeholder="结束"
                />
                <span>,</span>
                <el-input-number
                  v-model="row.step"
                  :controls="false"
                  size="small"
                  style="width: 60px"
                  placeholder="步长"
                />
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label=""
          width="50"
          align="center"
        >
          <template #default="{ $index }">
            <el-button
              link
              type="danger"
              size="small"
              @click="form.param_layers.splice($index, 1)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-button
        size="small"
        @click="addParamLayer"
      >
        添加参数
      </el-button>
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
        保存配置
      </el-button>
      <el-button
        type="success"
        :loading="submitting"
        @click="handleSubmitOptimization"
      >
        保存并提交优化
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit } from '@/types/workspace'

interface ParamLayer {
  param_name: string
  current_value: number
  opt_type: string
  start: number
  end: number
  step: number
}

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
const formRef = ref<FormInstance>()
const saving = ref(false)
const submitting = ref(false)

const form = ref({
  objective: 'sharpe_max',
  max_display: 5000,
  initial_cash_wan: 100,
  calculation_method: 'geometric' as 'geometric' | 'arithmetic',
  param_layers: [] as ParamLayer[],
})

function initForm() {
  if (!props.unit) return
  const oc = props.unit.optimization_config || {}
  form.value.objective = (oc.objective as string) || 'sharpe_max'
  form.value.max_display = (oc.max_display as number) || 5000
  form.value.initial_cash_wan = (oc.initial_cash_wan as number) || 100
  form.value.calculation_method = ((oc.calculation_method as string) || 'geometric') as 'geometric' | 'arithmetic'

  // Reconstruct param layers from optimization_config
  const layers = (oc.param_layers as ParamLayer[]) || []
  if (layers.length) {
    form.value.param_layers = layers.map(l => ({ ...l }))
  } else {
    // Build from unit params
    const p = props.unit.params || {}
    form.value.param_layers = Object.entries(p)
      .filter(([k]) => k !== 'parameters' && typeof p[k] === 'number')
      .map(([k, v]) => ({
        param_name: k,
        current_value: v as number,
        opt_type: 'equal_diff',
        start: 0,
        end: 0,
        step: 1,
      }))
  }
}

function addParamLayer() {
  form.value.param_layers.push({
    param_name: '',
    current_value: 0,
    opt_type: 'equal_diff',
    start: 0,
    end: 0,
    step: 1,
  })
}

function inferParamType(layer: ParamLayer): 'int' | 'float' {
  const values = [layer.current_value, layer.start, layer.end, layer.step]
  return values.every(v => Number.isInteger(v)) ? 'int' : 'float'
}

function calculateTotalCombinations(
  paramRanges: Record<string, { start: number; end: number; step: number; type: string }>,
): number {
  const counts = Object.values(paramRanges).map(spec => {
    const distance = spec.end - spec.start
    if (distance <= 0 || spec.step <= 0) {
      return 0
    }
    return Math.floor(distance / spec.step) + 1
  })
  if (!counts.length) {
    return 0
  }
  return counts.reduce((product, count) => product * count, 1)
}

function initializeLocalOptimizationState(
  unit: StrategyUnit,
  totalCombinations: number | null,
  taskId?: string,
) {
  const now = Date.now()
  if (taskId) {
    unit.last_optimization_task_id = taskId
  }
  unit.opt_status = 'pending'
  unit.opt_elapsed_time = 0
  unit.opt_remaining_time = 0
  unit.opt_total = totalCombinations
  unit.opt_completed = totalCombinations == null ? null : 0
  unit.opt_progress = 0
  unit.opt_started_at_ms = now
  unit.opt_last_sync_at_ms = now
}

async function handleSave() {
  if (!props.unit) return
  saving.value = true
  try {
    const existingOc = props.unit.optimization_config || {}
    await store.updateUnit(props.workspaceId, props.unit.id, {
      optimization_config: {
        ...existingOc,
        objective: form.value.objective,
        max_display: form.value.max_display,
        initial_cash_wan: form.value.initial_cash_wan,
        calculation_method: form.value.calculation_method,
        param_layers: form.value.param_layers,
      },
    })
    ElMessage.success('优化参数设置已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

function _buildParamRanges(): Record<string, { start: number; end: number; step: number; type: string }> {
  const ranges: Record<string, { start: number; end: number; step: number; type: string }> = {}
  for (const layer of form.value.param_layers) {
    if (!layer.param_name) continue
    if (layer.opt_type === 'equal_diff' && layer.step > 0 && layer.end > layer.start) {
      ranges[layer.param_name] = {
        start: layer.start,
        end: layer.end,
        step: layer.step,
        type: inferParamType(layer),
      }
    }
  }
  return ranges
}

async function handleSubmitOptimization() {
  if (!props.unit) return
  const paramRanges = _buildParamRanges()
  if (Object.keys(paramRanges).length === 0) {
    ElMessage.warning('请至少设置一个有效的等差优化参数（起始 < 结束，步长 > 0）')
    return
  }
  const totalCombinations = calculateTotalCombinations(paramRanges)

  submitting.value = true
  try {
    // Capture unit info before async operations (props.unit may become null after store refresh)
    const unitId = props.unit.id
    const existingOc = { ...(props.unit.optimization_config || {}) } as Record<string, unknown>

    // Save config first — merge to preserve thread settings (n_workers/mode/timeout)
    await store.updateUnit(props.workspaceId, unitId, {
      optimization_config: {
        ...existingOc,
        objective: form.value.objective,
        max_display: form.value.max_display,
        initial_cash_wan: form.value.initial_cash_wan,
        calculation_method: form.value.calculation_method,
        param_layers: form.value.param_layers,
      },
    })

    // Submit optimization task — read thread config from captured config
    const nWorkers = (existingOc.n_workers as number) || 4
    const mode = (existingOc.mode as string) || 'grid'
    const timeout = (existingOc.timeout as number) || 0

    const localUnit = store.units.find(u => u.id === unitId)
    if (localUnit) {
      initializeLocalOptimizationState(localUnit, totalCombinations || null)
    }

    const result = await workspaceApi.submitOptimization(props.workspaceId, {
      unit_id: unitId,
      param_ranges: paramRanges,
      n_workers: nWorkers,
      mode,
      timeout,
    })

    if (localUnit) {
      initializeLocalOptimizationState(localUnit, result.total_combinations, result.task_id)
    }

    await store.pollStatus(props.workspaceId)

    ElMessage.success(`优化任务已提交，共 ${result.total_combinations} 种组合`)
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '提交优化失败'))
  } finally {
    submitting.value = false
  }
}
</script>
