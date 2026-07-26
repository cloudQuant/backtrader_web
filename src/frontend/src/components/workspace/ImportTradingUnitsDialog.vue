<template>
  <el-dialog
    v-model="visible"
    :title="t('workspaceDialogs.importTitle')"
    width="860px"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
        <div class="text-sm font-medium text-slate-700">
          {{ t('workspaceDialogs.importSource') }}
        </div>
        <el-radio-group
          v-model="sourceType"
          class="mt-3"
        >
          <el-radio value="research">
            {{ t('workspaceDialogs.researchWorkspace') }}
          </el-radio>
          <el-radio value="file">
            JSON {{ t('workspaceDialogs.file') }}
          </el-radio>
        </el-radio-group>
      </div>

      <template v-if="sourceType === 'research'">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,280px)_1fr]">
          <el-select
            v-model="selectedWorkspaceId"
            filterable
            clearable
            :loading="workspaceLoading"
            :placeholder="t('workspaceDialogs.selectResearchWs')"
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
            <span>{{ t('workspaceDialogs.selectedSuffix') }} {{ selectedResearchUnitIds.length }} / {{ researchUnits.length }}</span>
          </div>
        </div>

        <el-table
          :data="researchUnits"
          stripe
          border
          size="small"
          height="340"
          :empty-text="t('workspaceDialogs.pleaseSelectResearchWs')"
          @selection-change="onResearchSelectionChange"
        >
          <el-table-column
            type="selection"
            width="44"
          />
          <el-table-column
            prop="group_name"
            :label="t('workspaceDialogs.groupName')"
            min-width="120"
            show-overflow-tooltip
          />
          <el-table-column
            prop="strategy_name"
            :label="t('workspaceDialogs.unitName')"
            min-width="140"
            show-overflow-tooltip
          />
          <el-table-column
            prop="strategy_id"
            :label="t('workspaceDialogs.formula')"
            min-width="160"
            show-overflow-tooltip
          />
          <el-table-column
            prop="symbol"
            :label="t('workspaceDialogs.symbolCode')"
            width="120"
          />
          <el-table-column
            prop="timeframe"
            :label="t('workspaceDialogs.timeframeCol')"
            width="90"
            align="center"
          />
          <el-table-column
            prop="category"
            :label="t('workspaceDialogs.categoryCol')"
            width="110"
            show-overflow-tooltip
          />
        </el-table>
      </template>

      <template v-else>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          :title="t('workspaceDialogs.supportImportFromBoth') + ' JSON ' + t('workspaceDialogs.file') + '.'"
        />
        <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center">
          <el-button
            type="primary"
            plain
            @click="fileInput?.click()"
          >
            {{ t('workspaceDialogs.selectFile') }}
          </el-button>
          <div class="mt-3 text-sm text-slate-600">
            {{ selectedFile?.name || t('workspaceDialogs.fileNotSelected') }}
          </div>
          <div class="mt-1 text-xs text-slate-400">
            {{ t('workspaceDialogs.importNoramlizedHint') }}
          </div>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">
        {{ t('workspaceDialogs.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="handleImport"
      >
        {{ t('workspaceDialogs.import') }}
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
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { StrategyUnit, Workspace } from '@/types/workspace'
import { normalizeTransferUnits } from './tradingUnitTransfer'

const { t } = useI18n()
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
    return t('workspaceDialogs.importingUnits') + '...'
  }
  const workspace = researchWorkspaces.value.find(item => item.id === selectedWorkspaceId.value)
  if (!workspace) {
    return t('workspaceDialogs.pleaseSelectImportWorkspace')
  }
  return `${workspace.name} · ${t('workspaceDialogs.totalCounter')} ${workspace.unit_count} ${t('workspaceDialogs.nUnits')}`
})

async function loadResearchWorkspaces() {
  workspaceLoading.value = true
  try {
    const response = await workspaceApi.list(0, 200, 'research')
    researchWorkspaces.value = response.items
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.loadResearchFailed')))
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
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.loadUnitsFailed')))
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
    throw new Error(t('workspaceDialogs.pleaseSelectFile'))
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
      throw new Error(sourceType.value === 'research' ? t('workspaceDialogs.pleaseSelectImportUnits') : t('workspaceDialogs.importEmpty'))
    }
    await workspaceApi.batchCreateUnits(props.workspaceId, units)
    ElMessage.success(`${t('workspaceDialogs.importSuccess')} ${units.length} ${t('workspaceDialogs.nUnits')}`)
    emit('imported', units.length)
    visible.value = false
    resetState()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.importFailed')))
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
