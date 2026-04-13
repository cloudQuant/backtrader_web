<template>
  <el-dialog
    v-model="visible"
    title="导入策略单元"
    width="860px"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
        <div class="text-sm font-medium text-slate-700">
          导入来源
        </div>
        <el-radio-group v-model="sourceType" class="mt-3">
          <el-radio value="research">策略研究工作区</el-radio>
          <el-radio value="file">JSON 文件</el-radio>
        </el-radio-group>
      </div>

      <template v-if="sourceType === 'research'">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,280px)_1fr]">
          <el-select
            v-model="selectedWorkspaceId"
            filterable
            clearable
            :loading="workspaceLoading"
            placeholder="选择策略研究工作区"
            @change="handleWorkspaceChange"
          >
            <el-option
              v-for="workspace in researchWorkspaces"
              :key="workspace.id"
              :label="workspace.name"
              :value="workspace.id"
            />
          </el-select>
          <div class="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-500">
            <span>{{ selectedWorkspaceDescription }}</span>
            <span>已选 {{ selectedResearchUnitIds.length }} / {{ researchUnits.length }}</span>
          </div>
        </div>

        <el-table
          :data="researchUnits"
          stripe
          border
          size="small"
          height="340"
          empty-text="请选择一个策略研究工作区"
          @selection-change="onResearchSelectionChange"
        >
          <el-table-column type="selection" width="44" />
          <el-table-column prop="group_name" label="组名" min-width="120" show-overflow-tooltip />
          <el-table-column prop="strategy_name" label="单元名" min-width="140" show-overflow-tooltip />
          <el-table-column prop="strategy_id" label="公式" min-width="160" show-overflow-tooltip />
          <el-table-column prop="symbol" label="商品代码" width="120" />
          <el-table-column prop="timeframe" label="周期" width="90" align="center" />
          <el-table-column prop="category" label="分类" width="110" show-overflow-tooltip />
        </el-table>
      </template>

      <template v-else>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="支持导入策略研究或策略交易导出的 JSON 文件。"
        />
        <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center">
          <el-button type="primary" plain @click="fileInput?.click()">
            选择导入文件
          </el-button>
          <div class="mt-3 text-sm text-slate-600">
            {{ selectedFile?.name || '尚未选择文件' }}
          </div>
          <div class="mt-1 text-xs text-slate-400">
            文件中的策略单元会自动归一化为交易工作区格式
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
        @click="handleImport"
      >
        导入
      </el-button>
    </template>

    <input
      ref="fileInput"
      type="file"
      accept=".json"
      class="hidden"
      @change="onFileSelected"
    >
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { StrategyUnit, Workspace } from '@/types/workspace'
import { normalizeTransferUnits } from './tradingUnitTransfer'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  imported: [count: number]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const sourceType = ref<'research' | 'file'>('research')
const workspaceLoading = ref(false)
const unitsLoading = ref(false)
const submitting = ref(false)
const researchWorkspaces = ref<Workspace[]>([])
const selectedWorkspaceId = ref('')
const researchUnits = ref<StrategyUnit[]>([])
const selectedResearchUnitIds = ref<string[]>([])
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const selectedWorkspaceDescription = computed(() => {
  if (unitsLoading.value) {
    return '正在加载策略单元...'
  }
  const workspace = researchWorkspaces.value.find(item => item.id === selectedWorkspaceId.value)
  if (!workspace) {
    return '请选择导入源工作区'
  }
  return `${workspace.name} · 共 ${workspace.unit_count} 个策略单元`
})

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

async function handleWorkspaceChange() {
  selectedResearchUnitIds.value = []
  researchUnits.value = []
  if (!selectedWorkspaceId.value) {
    return
  }
  unitsLoading.value = true
  try {
    const response = await workspaceApi.listUnits(selectedWorkspaceId.value)
    researchUnits.value = response.items
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '加载策略单元失败'))
  } finally {
    unitsLoading.value = false
  }
}

function onResearchSelectionChange(rows: StrategyUnit[]) {
  selectedResearchUnitIds.value = rows.map(row => row.id)
}

function onFileSelected(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function readFilePayload() {
  if (!selectedFile.value) {
    throw new Error('请先选择导入文件')
  }
  const text = await selectedFile.value.text()
  const data = JSON.parse(text)
  const units = Array.isArray(data) ? data : data.units ?? []
  return normalizeTransferUnits(units, { includeTradingFields: true, defaultTradingMode: 'paper' })
}

function getSelectedResearchUnits() {
  const selected = researchUnits.value.filter(unit => selectedResearchUnitIds.value.includes(unit.id))
  return normalizeTransferUnits(selected, { includeTradingFields: true, defaultTradingMode: 'paper' })
}

function resetState() {
  sourceType.value = 'research'
  selectedWorkspaceId.value = ''
  researchUnits.value = []
  selectedResearchUnitIds.value = []
  selectedFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

async function handleImport() {
  submitting.value = true
  try {
    const units = sourceType.value === 'research'
      ? getSelectedResearchUnits()
      : await readFilePayload()
    if (!units.length) {
      throw new Error(sourceType.value === 'research' ? '请选择要导入的策略单元' : '文件中未找到可导入的策略单元')
    }
    await workspaceApi.batchCreateUnits(props.workspaceId, units)
    ElMessage.success(`成功导入 ${units.length} 个策略单元`)
    emit('imported', units.length)
    visible.value = false
    resetState()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '导入失败'))
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
