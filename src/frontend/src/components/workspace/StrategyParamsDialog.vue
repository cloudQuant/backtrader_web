<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="860px"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="initForm"
  >
    <div
      v-if="unit"
      class="space-y-4"
    >
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
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
            行情对象
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ unit.symbol }} / {{ unit.timeframe }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            启用参数
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ enabledParamCount }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            参数总数
          </div>
          <div class="mt-1 text-sm font-semibold text-slate-700">
            {{ paramRows.length }}
          </div>
        </div>
      </div>

      <el-form label-width="100px">
        <el-table
          :data="paramRows"
          border
          size="small"
          class="mb-4"
        >
          <el-table-column
            label="启用"
            width="60"
            align="center"
          >
            <template #default="{ row }">
              <el-checkbox v-model="row.enabled" />
            </template>
          </el-table-column>
          <el-table-column
            prop="param_name"
            label="参数名"
            width="150"
          />
          <el-table-column
            prop="param_desc"
            label="参数说明"
            min-width="150"
          />
          <el-table-column
            label="类型"
            width="90"
            align="center"
          >
            <template #default="{ row }">
              {{ row.param_type }}
            </template>
          </el-table-column>
          <el-table-column
            label="参数值"
            width="180"
          >
            <template #default="{ row }">
              <el-input-number
                v-if="row.param_type === 'numeric'"
                v-model="row.param_value"
                :controls="false"
                size="small"
                style="width: 100%"
              />
              <el-input
                v-else
                v-model="row.param_value"
                size="small"
              />
            </template>
          </el-table-column>
        </el-table>

        <div class="flex gap-2">
          <el-button
            size="small"
            @click="addParam"
          >
            添加参数
          </el-button>
          <el-button
            size="small"
            :disabled="!paramRows.length"
            @click="removeSelected"
          >
            删除末行
          </el-button>
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

interface ParamRow {
  param_name: string
  param_desc: string
  param_type: string
  param_value: number | string
  enabled: boolean
}

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
const paramRows = ref<ParamRow[]>([])
const dialogTitle = computed(() =>
  `${props.workspaceType === 'trading' ? '策略交易' : '策略研究'}--公式应用设置`
)
const enabledParamCount = computed(() => paramRows.value.filter(row => row.enabled).length)

function initForm() {
  if (!props.unit) return
  const p = props.unit.params || {}
  const parameters = (p.parameters as ParamRow[]) || []
  if (parameters.length) {
    paramRows.value = parameters.map(item => ({ ...item }))
  } else {
    // Build from flat key-value params
    paramRows.value = Object.entries(p)
      .filter(([k]) => k !== 'parameters')
      .map(([k, v]) => ({
        param_name: k,
        param_desc: '',
        param_type: typeof v === 'number' ? 'numeric' : 'string',
        param_value: v as number | string,
        enabled: true,
      }))
  }
}

function addParam() {
  paramRows.value.push({
    param_name: '',
    param_desc: '',
    param_type: 'numeric',
    param_value: 0,
    enabled: true,
  })
}

function removeSelected() {
  if (paramRows.value.length) paramRows.value.pop()
}

async function handleSave() {
  if (!props.unit) return
  saving.value = true
  try {
    const paramsObj: Record<string, unknown> = {
      parameters: paramRows.value,
    }
    // Also flatten enabled params for backtest usage
    for (const row of paramRows.value) {
      if (row.enabled && row.param_name) {
        paramsObj[row.param_name] = row.param_value
      }
    }
    await store.updateUnit(props.workspaceId, props.unit.id, {
      params: paramsObj,
    })
    ElMessage.success('策略参数已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}
</script>
