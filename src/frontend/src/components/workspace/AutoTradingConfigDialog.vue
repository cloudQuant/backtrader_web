<template>
  <el-dialog
    v-model="visible"
    title="自动交易配置"
    width="860px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">状态</div>
          <div class="mt-1 text-lg font-semibold" :class="form.enabled ? 'text-emerald-600' : 'text-slate-700'">
            {{ form.enabled ? '已启用' : '已关闭' }}
          </div>
          <div class="text-xs text-slate-400">自动启停调度</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">缓冲时间</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ form.buffer_minutes }} 分钟</div>
          <div class="text-xs text-slate-400">开盘前 / 收盘后</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">作用范围</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ scopeLabel }}</div>
          <div class="text-xs text-slate-400">调度实例范围</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">交易时段</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ form.sessions.length }}</div>
          <div class="text-xs text-slate-400">已配置场次</div>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="自动交易会按设定时段批量启动或停止已注册的交易实例。"
      />

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <el-form
          label-width="100px"
          class="space-y-2"
        >
          <el-form-item label="启用">
            <el-switch
              v-model="form.enabled"
              active-text="已启用"
              inactive-text="已关闭"
            />
          </el-form-item>

          <el-form-item label="缓冲时间">
            <el-input-number
              v-model="form.buffer_minutes"
              :min="0"
              :max="60"
              :step="5"
            />
            <span class="ml-2 text-sm text-gray-500">分钟（开盘前启动 / 收盘后停止）</span>
          </el-form-item>

          <el-form-item label="作用范围">
            <el-select
              v-model="form.scope"
              class="w-40"
            >
              <el-option label="所有实例" value="all" />
              <el-option label="仅实盘" value="live" />
              <el-option label="仅模拟" value="simulation" />
            </el-select>
          </el-form-item>

          <el-form-item label="交易时段">
            <div class="w-full space-y-2">
              <div
                v-for="(session, index) in form.sessions"
                :key="index"
                class="grid grid-cols-[120px_120px_24px_120px_80px] items-center gap-2"
              >
                <el-input
                  v-model="session.name"
                  placeholder="时段名"
                  size="small"
                />
                <el-time-picker
                  v-model="session.open"
                  placeholder="开盘"
                  format="HH:mm"
                  value-format="HH:mm"
                  size="small"
                />
                <span class="text-center text-gray-400">-</span>
                <el-time-picker
                  v-model="session.close"
                  placeholder="收盘"
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
                  删除
                </el-button>
              </div>

              <el-button
                size="small"
                @click="addSession"
              >
                添加时段
              </el-button>
            </div>
          </el-form-item>
        </el-form>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-sm font-medium text-gray-700">
            当日调度预览
          </div>
          <el-button
            link
            type="primary"
            :loading="loading"
            @click="loadConfig"
          >
            刷新
          </el-button>
        </div>

        <el-table
          :data="schedule"
          size="small"
          border
          class="dialog-table"
          empty-text="暂无调度计划"
        >
          <el-table-column prop="session" label="交易时段" min-width="140" />
          <el-table-column prop="start" label="策略启动时间" min-width="140" />
          <el-table-column prop="stop" label="策略停止时间" min-width="140" />
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="handleSave"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { TradingAutoConfig, TradingAutoScheduleItem, TradingAutoSession } from '@/types/workspace'

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
      { name: '日盘', open: '09:00', close: '15:00' },
      { name: '夜盘', open: '21:00', close: '23:00' },
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
    all: '所有实例',
    live: '仅实盘',
    simulation: '仅模拟',
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
    ElMessage.error(getErrorMessage(error, '加载自动交易配置失败'))
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
    name: (session.name || `时段${index + 1}`).trim(),
    open: String(session.open || '').trim(),
    close: String(session.close || '').trim(),
  }))
}

function validateForm() {
  const sessions = normalizeSessions()
  if (sessions.length === 0) {
    throw new Error('至少保留一个交易时段')
  }
  const invalid = sessions.find(session => !session.name || !session.open || !session.close)
  if (invalid) {
    throw new Error('请完整填写交易时段名称、开盘时间和收盘时间')
  }
  return sessions
}

async function handleSave() {
  let sessions: TradingAutoSession[]
  try {
    sessions = validateForm()
  } catch (error: unknown) {
    ElMessage.warning(getErrorMessage(error, '表单校验失败'))
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
    ElMessage.success('自动交易配置已保存')
    visible.value = false
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '保存自动交易配置失败'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.dialog-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
</style>
