<template>
  <el-dialog
    v-model="visible"
    :title="t('workspaceDialogs.exportTitle')"
    width="760px"
  >
    <div class="space-y-4">
      <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-sm font-medium text-slate-700">
              {{ t('workspaceDialogs.exportTarget') }}
            </div>
            <div class="mt-1 text-xs text-slate-500">
              {{ t('workspaceDialogs.selectedNow') }} {{ units.length }} {{ t('workspaceDialogs.nUnits') }}
            </div>
          </div>
          <el-radio-group v-model="targetType">
            <el-radio value="research">
              {{ t('workspaceDialogs.researchWorkspace') }}
            </el-radio>
            <el-radio value="file">
              JSON {{ t('workspaceDialogs.file') }}
            </el-radio>
          </el-radio-group>
        </div>
      </div>

      <template v-if="targetType === 'research'">
        <el-select
          v-model="selectedWorkspaceId"
          filterable
          clearable
          :loading="workspaceLoading"
          :placeholder="t('workspaceDialogs.researchWorkspace')"
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
          :title="t('workspaceDialogs.exportToResearchHint') + ': ' + t('workspaceDialogs.willKeepStrategy') + '/' + t('workspaceDialogs.symbol') + '/' + t('workspaceDialogs.paramsLabel') + '/' + t('workspaceDialogs.optConfigResearchFields') + '. ' + t('workspaceDialogs.notKeepRunState') + '.'"
        />
      </template>

      <template v-else>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          :title="t('workspaceDialogs.fileWillContain') + '. ' + t('workspaceDialogs.canReimport') + '.'"
        />
        <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-8">
          <div class="text-sm font-medium text-slate-700">
            {{ t('workspaceDialogs.fileContentPreview') }}
          </div>
          <div class="mt-2 text-xs leading-6 text-slate-500">
            {{ t('workspaceDialogs.includeGroupName') }}, {{ t('workspaceDialogs.unitName') }}, {{ t('workspaceDialogs.formula') }}, {{ t('workspaceDialogs.symbolCode') }}, {{ t('workspaceDialogs.timeframeCol') }}, {{ t('workspaceDialogs.categoryCol') }}, {{ t('workspaceDialogs.dataSourceParams') }}, {{ t('workspaceDialogs.strategyParams') }}, {{ t('workspaceDialogs.optConfigEtc') }}.
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
        @click="handleExport"
      >
        {{ t('workspaceDialogs.export') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { StrategyUnit, Workspace } from '@/types/workspace'
import { buildTransferUnitPayload, downloadTransferUnits } from './tradingUnitTransfer'

const { t } = useI18n()
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
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.loadResearchFailed')))
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
    ElMessage.warning(t('tradingUnits.selectUnitForExport'))
    return
  }

  submitting.value = true
  try {
    if (targetType.value === 'research') {
      if (!selectedWorkspaceId.value) {
        throw new Error(t('workspaceDialogs.researchWorkspace'))
      }
      const payload = props.units.map(unit => buildTransferUnitPayload(unit, { includeTradingFields: false }))
      await workspaceApi.batchCreateUnits(selectedWorkspaceId.value, payload)
      ElMessage.success(`${t('workspaceDialogs.exported')} ${payload.length} ${t('workspaceDialogs.nUnits')} -> ${t('workspaceDialogs.researchWorkspace')}`)
      emit('exported', payload.length)
      visible.value = false
      resetState()
      return
    }

    const payload = props.units.map(unit => buildTransferUnitPayload(unit, { includeTradingFields: true }))
    downloadTransferUnits(payload, 'trading_units')
    ElMessage.success(`${t('workspaceDialogs.exported')} ${payload.length} ${t('workspaceDialogs.nUnits')}`)
    emit('exported', payload.length)
    visible.value = false
    resetState()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.exportFailed')))
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
