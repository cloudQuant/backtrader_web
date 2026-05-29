<template>
  <el-dialog
    v-model="visible"
    :title="t('workspaceDialogs.scheduledOptTitle')"
    width="760px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.currentStatus') }}
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="form.enabled ? 'text-emerald-600' : 'text-slate-700'"
          >
            {{ form.enabled ? t('workspaceDialogs.enabledStatus') : t('workspaceDialogs.disabledStatus') }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.scheduledOpt') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.runFreq') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ frequencyLabel }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.autoTrigger') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.runTime') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ form.execution_time }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.workspaceTimePoint') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.sessionScope') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ scopeLabel }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.selectedSuffix') }} {{ store.selectedUnitIds.length }} {{ t('workspaceDialogs.nUnitsCount') }}
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <el-form
          label-width="110px"
          class="space-y-2"
        >
          <el-form-item :label="t('workspaceDialogs.enabledScheduledOpt')">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item :label="t('workspaceDialogs.runFreq')">
            <el-radio-group v-model="form.frequency">
              <el-radio value="daily">
                {{ t('workspaceDialogs.freqDaily') }}
              </el-radio>
              <el-radio value="weekly">
                {{ t('workspaceDialogs.weekly') }}
              </el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('workspaceDialogs.runTime')">
            <el-time-picker
              v-model="form.execution_time"
              value-format="HH:mm"
              format="HH:mm"
              :placeholder="t('workspaceDialogs.selectTime')"
              class="w-40"
            />
          </el-form-item>
          <el-form-item :label="t('workspaceDialogs.sessionScope')">
            <el-select
              v-model="form.unit_scope"
              class="w-48"
            >
              <el-option
                :label="t('workspaceDialogs.allTradingUnits')"
                value="all"
              />
              <el-option
                :label="t('workspaceDialogs.onlySelectedUnits')"
                value="selected"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('workspaceDialogs.runWhenIdle')">
            <el-switch v-model="form.only_when_idle" />
          </el-form-item>
        </el-form>
      </div>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        :title="t('workspaceDialogs.saveScheduledHint') + ', ' + t('workspaceDialogs.forSchedulerRead') + '.'"
      />
    </div>

    <template #footer>
      <el-button @click="visible = false">
        {{ t('workspaceDialogs.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="handleSave"
      >
        {{ t('workspaceDialogs.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import { useWorkspaceStore } from '@/stores/workspace'

const { t } = useI18n()
const props = defineProps<{
  modelValue: boolean
  workspaceId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [value: Record<string, unknown>]
}>()

const store = useWorkspaceStore()
const loading = computed(() => store.loading)
const frequencyLabel = computed(() => (form.frequency === 'weekly' ? t('workspaceDialogs.weekly') : t('workspaceDialogs.freqDaily')))
const scopeLabel = computed(() => (form.unit_scope === 'selected' ? t('workspaceDialogs.selectedUnits') : t('workspaceDialogs.allTradingUnits')))
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const form = reactive({
  enabled: false,
  frequency: 'daily',
  execution_time: '20:30',
  unit_scope: 'all',
  only_when_idle: true,
})

function loadFromWorkspace() {
  const tradingConfig = (store.currentWorkspace?.trading_config || {}) as Record<string, unknown>
  const config = (tradingConfig.scheduled_optimization || {}) as Record<string, unknown>
  form.enabled = Boolean(config.enabled)
  form.frequency = String(config.frequency || 'daily')
  form.execution_time = String(config.execution_time || '20:30')
  form.unit_scope = String(config.unit_scope || 'all')
  form.only_when_idle = config.only_when_idle !== false
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      loadFromWorkspace()
    }
  },
)

async function handleSave() {
  try {
    const tradingConfig = {
      ...((store.currentWorkspace?.trading_config || {}) as Record<string, unknown>),
      scheduled_optimization: {
        enabled: form.enabled,
        frequency: form.frequency,
        execution_time: form.execution_time,
        unit_scope: form.unit_scope,
        only_when_idle: form.only_when_idle,
      },
    }
    await store.updateWorkspace(props.workspaceId, { trading_config: tradingConfig })
    emit('saved', tradingConfig)
    ElMessage.success(t('workspaceDialogs.scheduledOptSaved'))
    visible.value = false
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.scheduledOptSaveFailed')))
  }
}
</script>
