<template>
  <el-dialog
    v-model="visible"
    title="导出策略单元"
    width="760px"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-sm font-medium text-slate-700">
              导出目标
            </div>
            <div class="mt-1 text-xs text-slate-500">
              当前已选 {{ units.length }} 个策略单元
            </div>
          </div>
          <el-radio-group v-model="targetType">
            <el-radio value="research">策略研究工作区</el-radio>
            <el-radio value="file">JSON 文件</el-radio>
          </el-radio-group>
        </div>
      </div>

      <template v-if="targetType === 'research'">
        <el-select
          v-model="selectedWorkspaceId"
          filterable
          clearable
          :loading="workspaceLoading"
          placeholder="选择导出的策略研究工作区"
          class="w-full"
        >
          <el-option
            v-for="workspace in researchWorkspaces"
            :key="workspace.id"
            :label="workspace.name"
            :value="workspace.id"
          />
        </el-select>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="导出到策略研究工作区时，将保留策略、品种、参数、优化配置等研究字段，不携带交易运行态。"
        />
      </template>

      <template v-else>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="导出文件会保留交易工作区字段，可再次导入到策略交易。"
        />
        <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-8">
          <div class="text-sm font-medium text-slate-700">
            文件内容预览
          </div>
          <div class="mt-2 text-xs leading-6 text-slate-500">
            包含组名、单元名、公式、商品代码、周期、分类、数据源参数、策略参数、优化配置以及交易模式配置。
          </div>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="handleExport"
      >
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { StrategyUnit, Workspace } from '@/types/workspace'
import { buildTransferUnitPayload, downloadTransferUnits } from './tradingUnitTransfer'

const props = defineProps<{
  modelValue: boolean
  units: StrategyUnit[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  exported: [count: number]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const targetType = ref<'research' | 'file'>('research')
const workspaceLoading = ref(false)
const submitting = ref(false)
const researchWorkspaces = ref<Workspace[]>([])
const selectedWorkspaceId = ref('')

async function loadResearchWorkspaces() {
  workspaceLoading.value = true
  try {
    const response = await workspaceApi.list(0, 200, 'research')
    researchWorkspaces.value = response.items
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '加载策略研究工作区失败'))
  } finally {
    workspaceLoading.value = false
  }
}

function resetState() {
  targetType.value = 'research'
  selectedWorkspaceId.value = ''
}

async function handleExport() {
  if (!props.units.length) {
    ElMessage.warning('请先选择要导出的策略单元')
    return
  }

  submitting.value = true
  try {
    if (targetType.value === 'research') {
      if (!selectedWorkspaceId.value) {
        throw new Error('请选择导出的策略研究工作区')
      }
      const payload = props.units.map(unit => buildTransferUnitPayload(unit, { includeTradingFields: false }))
      await workspaceApi.batchCreateUnits(selectedWorkspaceId.value, payload)
      ElMessage.success(`已导出 ${payload.length} 个策略单元到策略研究工作区`)
      emit('exported', payload.length)
      visible.value = false
      resetState()
      return
    }

    const payload = props.units.map(unit => buildTransferUnitPayload(unit, { includeTradingFields: true }))
    downloadTransferUnits(payload, 'trading_units')
    ElMessage.success(`已导出 ${payload.length} 个策略单元`)
    emit('exported', payload.length)
    visible.value = false
    resetState()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '导出失败'))
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.modelValue,
  async (value) => {
    if (!value) {
      return
    }
    await loadResearchWorkspaces()
  },
)
</script>
