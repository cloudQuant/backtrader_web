<template>
  <el-dialog
    v-model="visible"
    :title="t('workspaceDialogs.autoTradingTitle')"
    width="860px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('common.status') }}
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="form.enabled ? 'text-emerald-600' : 'text-slate-700'"
          >
            {{ form.enabled ? t('workspaceDialogs.autoEnabled') : t('workspaceDialogs.autoDisabled') }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.autoTradingTitle') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.preOpenStart') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ form.buffer_minutes }} {{ t('workspaceDialogs.minute') }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.preOpenStartShort') }} / {{ t('workspaceDialogs.postCloseStopShort') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.sessionRange') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ scopeLabel }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.sessionRange') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('workspaceDialogs.sessionTime') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ form.sessions.length }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('workspaceDialogs.sessionList') }}
          </div>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('workspaceDialogs.todayPreview')"
      />

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <el-form
          label-width="100px"
          class="space-y-2"
        >
          <el-form-item :label="t('workspaceDialogs.enable')">
            <el-switch
              v-model="form.enabled"
              :active-text="t('workspaceDialogs.autoEnabled')"
              :inactive-text="t('workspaceDialogs.autoDisabled')"
            />
          </el-form-item>

          <el-form-item :label="t('workspaceDialogs.preOpenStart')">
            <el-input-number
              v-model="form.buffer_minutes"
              :min="0"
              :max="60"
              :step="5"
            />
            <span class="ml-2 text-sm text-gray-500">{{ t('workspaceDialogs.minute') }}（{{ t('workspaceDialogs.preOpenStart') }} / {{ t('workspaceDialogs.postCloseStop') }}）</span>
          </el-form-item>

          <el-form-item :label="t('workspaceDialogs.sessionRange')">
            <el-select
              v-model="form.scope"
              class="w-40"
            >
              <el-option
                :label="t('workspaceDialogs.sessionScopeAll')"
                value="all"
              />
              <el-option
                :label="t('workspaceDialogs.sessionScopeLive')"
                value="live"
              />
              <el-option
                :label="t('workspaceDialogs.sessionScopePaper')"
                value="simulation"
              />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('workspaceDialogs.sessionTime')">
            <div class="w-full space-y-2">
              <div
                v-for="(session, index) in form.sessions"
                :key="index"
                class="grid grid-cols-[120px_120px_24px_120px_80px] items-center gap-2"
              >
                <el-input
                  v-model="session.name"
                  :placeholder="t('workspaceDialogs.sessionName')"
                  size="small"
                />
                <el-time-picker
                  v-model="session.open"
                  :placeholder="t('workspaceDialogs.sessionStart')"
                  format="HH:mm"
                  value-format="HH:mm"
                  size="small"
                />
                <span class="text-center text-gray-400">-</span>
                <el-time-picker
                  v-model="session.close"
                  :placeholder="t('workspaceDialogs.sessionEnd')"
                  format="HH:mm"
                  value-format="HH:mm"
                  size="small"
                />
                <el-button
                  type="danger"
                  size="small"
                  plain
                  :disabled="form.sessions.length <= 1"
                  @click="removeSession(index)"
                >
                  {{ t('workspaceDialogs.delete') }}
                </el-button>
              </div>

              <el-button
                size="small"
                @click="addSession"
              >
                {{ t('workspaceDialogs.addSession') }}
              </el-button>
            </div>
          </el-form-item>
        </el-form>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-sm font-medium text-gray-700">
            {{ t('workspaceDialogs.todayPreview') }}
          </div>
          <el-button
            link
            type="primary"
            :loading="loading"
            @click="loadConfig"
          >
            {{ t('workspaceDialogs.refresh') }}
          </el-button>
        </div>

        <el-table
          :data="schedule"
          size="small"
          border
          class="dialog-table"
          :empty-text="t('workspaceDialogs.sessionEmpty')"
        >
          <el-table-column
            prop="session"
            :label="t('workspaceDialogs.sessionTime')"
            min-width="140"
          />
          <el-table-column
            prop="start"
            :label="t('workspaceDialogs.preOpenStart')"
            min-width="140"
          />
          <el-table-column
            prop="stop"
            :label="t('workspaceDialogs.postCloseStop')"
            min-width="140"
          />
        </el-table>
      </div>
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
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { TradingAutoConfig, TradingAutoScheduleItem, TradingAutoSession } from '@/types/workspace'

const { t } = useI18n()
const props = defineProps<{
  modelValue: boolean
  workspaceId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [payload: { config: TradingAutoConfig; schedule: TradingAutoScheduleItem[] }]
}>()

function createDefaultConfig(): TradingAutoConfig {
  return {
    enabled: false,
    buffer_minutes: 15,
    sessions: [
      { name: t('workspaceDialogs.daySession'), open: '09:00', close: '15:00' },
      { name: t('workspaceDialogs.nightSession'), open: '21:00', close: '23:00' },
    ],
    scope: 'all',
  }
}

function cloneSessions(sessions: TradingAutoSession[]) {
  return sessions.map(session => ({ ...session }))
}

function cloneConfig(config: TradingAutoConfig): TradingAutoConfig {
  return {
    ...config,
    sessions: cloneSessions(config.sessions),
  }
}

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const form = reactive<TradingAutoConfig>(createDefaultConfig())
const schedule = ref<TradingAutoScheduleItem[]>([])
const loading = ref(false)
const scopeLabel = computed(() => {
  const labels: Record<string, string> = {
    all: t('workspaceDialogs.sessionScopeAll'),
    live: t('workspaceDialogs.sessionScopeLive'),
    simulation: t('workspaceDialogs.sessionScopePaper'),
  }
  return labels[form.scope] || form.scope
})

function assignForm(config: TradingAutoConfig) {
  form.enabled = config.enabled
  form.buffer_minutes = config.buffer_minutes
  form.scope = config.scope
  form.sessions = cloneSessions(config.sessions)
}

async function loadConfig() {
  loading.value = true
  try {
    const [config, scheduleResponse] = await Promise.all([
      workspaceApi.getTradingAutoConfig(props.workspaceId),
      workspaceApi.getTradingAutoSchedule(props.workspaceId),
    ])
    assignForm(config)
    schedule.value = scheduleResponse
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.loadAutoFailed')))
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      void loadConfig()
    }
  },
)

function addSession() {
  form.sessions.push({ name: '', open: '09:00', close: '15:00' })
}

function removeSession(index: number) {
  if (form.sessions.length <= 1) {
    return
  }
  form.sessions.splice(index, 1)
}

function normalizeSessions() {
  return form.sessions.map((session, index) => ({
    name: (session.name || `${t('workspaceDialogs.sessionTime')}${index + 1}`).trim(),
    open: String(session.open || '').trim(),
    close: String(session.close || '').trim(),
  }))
}

function validateForm() {
  const sessions = normalizeSessions()
  if (sessions.length === 0) {
    throw new Error(t('workspaceDialogs.sessionTime'))
  }
  const invalid = sessions.find(session => !session.name || !session.open || !session.close)
  if (invalid) {
    throw new Error(t('workspaceDialogs.sessionName') + ', ' + t('workspaceDialogs.openCloseHint'))
  }
  return sessions
}

async function handleSave() {
  let sessions: TradingAutoSession[]
  try {
    sessions = validateForm()
  } catch (error: unknown) {
    ElMessage.warning(getErrorMessage(error, t('workspaceDialogs.saveFailed')))
    return
  }

  loading.value = true
  try {
    const updatedConfig = await workspaceApi.updateTradingAutoConfig(props.workspaceId, {
      enabled: form.enabled,
      buffer_minutes: form.buffer_minutes,
      scope: form.scope,
      sessions,
    })
    const scheduleResponse = await workspaceApi.getTradingAutoSchedule(props.workspaceId)
    assignForm(updatedConfig)
    schedule.value = scheduleResponse
    emit('saved', {
      config: cloneConfig(updatedConfig),
      schedule: scheduleResponse.map(item => ({ ...item })),
    })
    ElMessage.success(t('workspaceDialogs.autoTradingTitle') + ' ' + t('workspaceDialogs.save'))
    visible.value = false
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('workspaceDialogs.saveAutoFailed')))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.dialog-table :deep(.el-table__header th) {
  background: var(--bg-color-page);
  color: var(--text-color-regular);
  font-weight: 600;
}
</style>
