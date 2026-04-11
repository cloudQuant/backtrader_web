<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="批量优化参数设置"
    width="800px"
    destroy-on-close
    @open="initForm"
  >
    <el-alert type="info" :closable="false" class="mb-4">
      将以下优化参数统一应用到选中的 <strong>{{ unitIds.length }}</strong> 个策略单元。
    </el-alert>

    <el-form ref="formRef" :model="form" label-width="120px" size="default">
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item label="优化目标">
            <el-select v-model="form.objective" style="width: 100%">
              <el-option label="夏普比率最大" value="sharpe_max" />
              <el-option label="最大收益" value="max_return" />
              <el-option label="最小回撤" value="min_drawdown" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="并行线程数">
            <el-input-number v-model="form.n_workers" :min="1" :max="32" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="最优显示">
            <el-input-number v-model="form.max_display" :min="100" :max="50000" :step="100" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-divider content-position="left">参数列表</el-divider>

      <el-table :data="form.param_layers" border size="small" class="mb-4">
        <el-table-column label="参数名" width="140">
          <template #default="{ row }">
            <el-input v-model="row.param_name" size="small" placeholder="参数名称" />
          </template>
        </el-table-column>
        <el-table-column label="优化设置" min-width="300">
          <template #default="{ row }">
            <div class="flex items-center gap-1">
              <el-select v-model="row.opt_type" size="small" style="width: 80px">
                <el-option label="等差" value="equal_diff" />
                <el-option label="固定" value="fixed" />
              </el-select>
              <template v-if="row.opt_type === 'equal_diff'">
                <el-input-number v-model="row.start" :controls="false" size="small" style="width: 80px" placeholder="起始" />
                <span>~</span>
                <el-input-number v-model="row.end" :controls="false" size="small" style="width: 80px" placeholder="结束" />
                <span>, 步长</span>
                <el-input-number v-model="row.step" :controls="false" size="small" style="width: 70px" placeholder="步长" />
                <span class="text-xs text-gray-400 ml-1">
                  ({{ calcCount(row) }}种)
                </span>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="form.param_layers.splice($index, 1)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex items-center gap-3">
        <el-button size="small" @click="addParamLayer">添加参数</el-button>
        <span class="text-sm text-gray-400">总组合数: <strong>{{ totalCombinations }}</strong></span>
      </div>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        保存到 {{ unitIds.length }} 个单元
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit } from '@/types/workspace'

interface ParamLayer {
  param_name: string
  opt_type: string
  start: number
  end: number
  step: number
}

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unitIds: string[]
  units: StrategyUnit[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const saving = ref(false)

const form = ref({
  objective: 'sharpe_max',
  n_workers: 4,
  max_display: 5000,
  param_layers: [] as ParamLayer[],
})

function calcCount(row: ParamLayer): number {
  if (row.opt_type !== 'equal_diff' || row.step <= 0 || row.end <= row.start) return 0
  return Math.floor((row.end - row.start) / row.step) + 1
}

const totalCombinations = computed(() => {
  const enabled = form.value.param_layers.filter(r => r.opt_type === 'equal_diff' && calcCount(r) > 0)
  if (enabled.length === 0) return 0
  return enabled.reduce((acc, r) => acc * Math.max(calcCount(r), 1), 1)
})

function initForm() {
  // Try to pre-fill from the first selected unit that has optimization_config
  const firstUnit = props.units.find(u => props.unitIds.includes(u.id) && u.optimization_config)
  if (firstUnit?.optimization_config) {
    const oc = firstUnit.optimization_config as Record<string, unknown>
    form.value.objective = (oc.objective as string) || 'sharpe_max'
    form.value.n_workers = (oc.n_workers as number) || 4
    form.value.max_display = (oc.max_display as number) || 5000
    const layers = (oc.param_layers as ParamLayer[]) || []
    if (layers.length) {
      form.value.param_layers = layers.map(l => ({ ...l }))
      return
    }
  }
  // Default: build from first unit's params
  const firstAny = props.units.find(u => props.unitIds.includes(u.id))
  if (firstAny?.params) {
    form.value.param_layers = Object.entries(firstAny.params)
      .filter(([k, val]) => k !== 'parameters' && typeof val === 'number')
      .map(([k]) => ({
        param_name: k,
        opt_type: 'equal_diff',
        start: 0,
        end: 0,
        step: 1,
      }))
  } else {
    form.value.param_layers = []
  }
}

function addParamLayer() {
  form.value.param_layers.push({
    param_name: '',
    opt_type: 'equal_diff',
    start: 0,
    end: 0,
    step: 1,
  })
}

async function handleSave() {
  if (!props.unitIds.length) return
  saving.value = true
  try {
    const config = {
      objective: form.value.objective,
      n_workers: form.value.n_workers,
      max_display: form.value.max_display,
      param_layers: form.value.param_layers,
      mode: 'grid',
      timeout: 0,
    }
    let success = 0
    for (const id of props.unitIds) {
      try {
        const unit = props.units.find(u => u.id === id)
        const existingOc = (unit?.optimization_config || {}) as Record<string, unknown>
        await workspaceApi.updateUnit(props.workspaceId, id, {
          optimization_config: { ...existingOc, ...config },
        })
        success++
      } catch { /* continue */ }
    }
    ElMessage.success(`优化参数已保存到 ${success} 个单元`)
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>
