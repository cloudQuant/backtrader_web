<template>
  <div class="space-y-6">
    <!-- 顶部操作栏 -->
    <el-card>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-bold">
            实盘交易
          </h3>
          <el-tag
            :type="runningCount > 0 ? 'success' : 'info'"
            size="small"
          >
            {{ runningCount }} 运行中 / {{ visibleInstances.length }} 总计
          </el-tag>
        </div>
        <div class="flex gap-2 items-center">
          <el-button-group>
            <el-button
              :type="viewMode === 'card' ? 'primary' : 'default'"
              size="small"
              @click="viewMode = 'card'"
            >
              卡片
            </el-button>
            <el-button
              :type="viewMode === 'list' ? 'primary' : 'default'"
              size="small"
              @click="viewMode = 'list'"
            >
              列表
            </el-button>
          </el-button-group>
          <el-button
            type="success"
            :loading="batchLoading"
            :disabled="instances.length === 0"
            @click="handleStartAll"
          >
            <el-icon><VideoPlay /></el-icon>一键启动
          </el-button>
          <el-button
            type="danger"
            :loading="batchLoading"
            :disabled="runningCount === 0"
            @click="handleStopAll"
          >
            <el-icon><VideoPause /></el-icon>一键停止
          </el-button>
          <el-button
            type="primary"
            @click="showAddDialog = true"
          >
            <el-icon><Plus /></el-icon>添加策略
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 自动交易调度 -->
    <el-card>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <h4 class="text-md font-bold">
            自动交易调度
          </h4>
          <el-switch
            v-model="autoTradingEnabled"
            :loading="autoTradingLoading"
            active-text="已启用"
            inactive-text="已关闭"
            @change="handleAutoTradingToggle"
          />
          <el-tag
            v-if="autoTradingEnabled"
            type="success"
            size="small"
          >
            缓冲 {{ autoTradingConfig.buffer_minutes }} 分钟
          </el-tag>
        </div>
        <el-button
          size="small"
          :icon="Setting"
          @click="showAutoTradingDialog = true"
        >
          配置
        </el-button>
      </div>
      <div
        v-if="autoTradingSchedule.length > 0"
        class="mt-3"
      >
        <el-table
          :data="autoTradingSchedule"
          size="small"
          border
          class="w-full"
        >
          <el-table-column
            prop="session"
            label="交易时段"
            min-width="120"
          />
          <el-table-column
            prop="start"
            label="策略启动时间"
            min-width="140"
          />
          <el-table-column
            prop="stop"
            label="策略停止时间"
            min-width="140"
          />
        </el-table>
      </div>
    </el-card>

    <!-- 自动交易配置对话框 -->
    <el-dialog
      v-model="showAutoTradingDialog"
      title="自动交易配置"
      width="520px"
    >
      <el-form
        label-width="100px"
        class="space-y-2"
      >
        <el-form-item label="启用">
          <el-switch v-model="autoTradingForm.enabled" />
        </el-form-item>
        <el-form-item label="缓冲时间">
          <el-input-number
            v-model="autoTradingForm.buffer_minutes"
            :min="0"
            :max="60"
            :step="5"
          />
          <span class="ml-2 text-sm text-gray-500">分钟（开盘前启动 / 收盘后停止）</span>
        </el-form-item>
        <el-form-item label="作用范围">
          <el-select
            v-model="autoTradingForm.scope"
            class="w-40"
          >
            <el-option
              label="所有实例"
              value="all"
            />
            <el-option
              label="仅实盘"
              value="live"
            />
            <el-option
              label="仅模拟"
              value="simulation"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="交易时段">
          <div class="space-y-2 w-full">
            <div
              v-for="(sess, idx) in autoTradingForm.sessions"
              :key="idx"
              class="flex items-center gap-2"
            >
              <el-input
                v-model="sess.name"
                placeholder="时段名"
                class="w-28"
                size="small"
              />
              <el-time-picker
                v-model="sess.open"
                placeholder="开盘"
                format="HH:mm"
                value-format="HH:mm"
                size="small"
                class="w-28"
              />
              <span class="text-gray-400">–</span>
              <el-time-picker
                v-model="sess.close"
                placeholder="收盘"
                format="HH:mm"
                value-format="HH:mm"
                size="small"
                class="w-28"
              />
              <el-button
                type="danger"
                size="small"
                plain
                :disabled="autoTradingForm.sessions.length <= 1"
                @click="autoTradingForm.sessions.splice(idx, 1)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-button
              size="small"
              @click="autoTradingForm.sessions.push({ name: '', open: '09:00', close: '15:00' })"
            >
              <el-icon><Plus /></el-icon>添加时段
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAutoTradingDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="autoTradingLoading"
          @click="handleSaveAutoTrading"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 策略列表 -->
    <div
      v-if="loading"
      class="flex justify-center py-12"
    >
      <el-icon class="is-loading text-4xl text-blue-500">
        <Loading />
      </el-icon>
    </div>

    <div
      v-else-if="visibleInstances.length === 0"
      class="text-center py-12"
    >
      <el-empty description="暂无实盘策略，点击右上角添加" />
    </div>

    <div v-else>
      <!-- 卡片视图 -->
      <div
        v-if="viewMode === 'card'"
        class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
      >
        <el-card
          v-for="inst in visibleInstances"
          :key="inst.id"
          shadow="hover"
          class="cursor-pointer"
          @click="goToDetail(inst)"
        >
          <div class="flex justify-between items-start mb-3">
            <div>
              <h4 class="text-md font-bold">
                {{ inst.strategy_name || formatStrategyId(inst.strategy_id) }}
              </h4>
              <span class="text-xs text-gray-400">{{ formatStrategyId(inst.strategy_id) }}</span>
            </div>
            <el-tag
              :type="inst.status === 'running' ? 'success' : inst.status === 'error' ? 'danger' : 'info'"
              size="small"
            >
              {{ statusLabel(inst.status) }}
            </el-tag>
          </div>

          <div class="text-sm text-gray-500 space-y-1 mb-4">
            <div v-if="inst.started_at">
              启动: {{ inst.started_at }}
            </div>
            <div v-if="inst.stopped_at && inst.status !== 'running'">
              停止: {{ inst.stopped_at }}
            </div>
            <div>添加: {{ inst.created_at }}</div>
            <div v-if="gatewaySummaryLabel(inst)">
              网关: {{ gatewaySummaryLabel(inst) }}
            </div>
            <div
              v-if="inst.error"
              class="text-red-500 text-xs truncate"
              :title="inst.error"
            >
              错误: {{ inst.error }}
            </div>
          </div>

          <div
            class="flex gap-2"
            @click.stop
          >
            <el-button
              v-if="inst.status !== 'running'"
              type="success"
              size="small"
              :loading="actionLoading[inst.id] === 'start'"
              @click="handleStart(inst)"
            >
              <el-icon><VideoPlay /></el-icon>启动
            </el-button>
            <el-button
              v-else
              type="warning"
              size="small"
              :loading="actionLoading[inst.id] === 'stop'"
              @click="handleStop(inst)"
            >
              <el-icon><VideoPause /></el-icon>停止
            </el-button>
            <el-button
              size="small"
              @click="goToDetail(inst)"
            >
              <el-icon><View /></el-icon>分析
            </el-button>
            <el-button
              size="small"
              @click="openDetail(inst)"
            >
              详情
            </el-button>
            <el-popconfirm
              title="确定要删除该策略实例吗？"
              @confirm="handleRemove(inst)"
            >
              <template #reference>
                <el-button
                  type="danger"
                  size="small"
                  plain
                  :loading="actionLoading[inst.id] === 'remove'"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </div>

      <!-- 列表视图 -->
      <el-card v-else>
        <el-table
          :data="visibleInstances"
          stripe
          size="small"
          class="w-full"
        >
          <el-table-column
            prop="strategy_name"
            label="策略名称"
            min-width="160"
          >
            <template #default="{ row }">
              {{ row.strategy_name || formatStrategyId(row.strategy_id) }}
            </template>
          </el-table-column>
          <el-table-column
            label="策略ID"
            min-width="160"
          >
            <template #default="{ row }">
              {{ formatStrategyId(row.strategy_id) }}
            </template>
          </el-table-column>
          <el-table-column
            label="状态"
            width="100"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'running' ? 'success' : row.status === 'error' ? 'danger' : 'info'"
                size="small"
              >
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="网关"
            min-width="180"
          >
            <template #default="{ row }">
              <span class="text-xs text-gray-600">
                {{ gatewaySummaryLabel(row) || '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="260"
            align="center"
          >
            <template #default="{ row }">
              <div class="flex flex-wrap items-center justify-center gap-1">
                <el-button
                  v-if="row.status !== 'running'"
                  type="success"
                  size="small"
                  :loading="actionLoading[row.id] === 'start'"
                  @click="handleStart(row)"
                >
                  启动
                </el-button>
                <el-button
                  v-else
                  type="warning"
                  size="small"
                  :loading="actionLoading[row.id] === 'stop'"
                  @click="handleStop(row)"
                >
                  停止
                </el-button>
                <el-button
                  size="small"
                  link
                  @click="goToDetail(row)"
                >
                  分析
                </el-button>
                <el-button
                  size="small"
                  link
                  @click="openDetail(row)"
                >
                  详情
                </el-button>
                <el-popconfirm
                  title="确定要删除该策略实例吗？"
                  @confirm="handleRemove(row)"
                >
                  <template #reference>
                    <el-button
                      type="danger"
                      size="small"
                      plain
                      :loading="actionLoading[row.id] === 'remove'"
                    >
                      删除
                    </el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 实例时间日志对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="实例时间日志"
      width="520px"
    >
      <div v-if="detailInstance">
        <div class="mb-3 text-sm text-gray-600">
          <div>策略：{{ detailInstance.strategy_name || formatStrategyId(detailInstance.strategy_id) }}</div>
          <div class="text-xs text-gray-400 mt-1">
            ID：{{ detailInstance.id }}
          </div>
        </div>
        <div
          v-if="gatewayDetailItems(detailInstance).length"
          class="mb-4 rounded-md border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700"
        >
          <div class="mb-2 font-medium text-gray-900">
            Gateway
          </div>
          <div class="grid grid-cols-1 gap-2 md:grid-cols-2">
            <div
              v-for="item in gatewayDetailItems(detailInstance)"
              :key="item.label"
            >
              <div class="text-xs text-gray-500">
                {{ item.label }}
              </div>
              <div class="break-all">
                {{ item.value }}
              </div>
            </div>
          </div>
        </div>
        <el-table
          :data="detailTimeline"
          size="small"
          border
          class="w-full"
        >
          <el-table-column
            prop="label"
            label="事件"
            width="120"
          />
          <el-table-column
            prop="time"
            label="时间"
          />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">
          关闭
        </el-button>
      </template>
    </el-dialog>

    <!-- 添加策略对话框 -->
    <el-dialog
      v-model="showAddDialog"
      title="添加实盘策略"
      width="500px"
    >
      <el-form
        :model="addForm"
        label-width="80px"
      >
        <el-form-item label="策略">
          <el-select
            v-model="addForm.strategy_id"
            placeholder="选择策略"
            class="w-full"
            filterable
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="网关预设">
          <el-select
            v-model="addForm.gatewayPresetId"
            placeholder="可选，选择预设"
            class="w-full"
            clearable
          >
            <el-option
              v-for="preset in gatewayPresets"
              :key="preset.id"
              :label="preset.name"
              :value="preset.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-for="field in selectedGatewayEditableFields"
          :key="field.key"
          :label="field.label"
        >
          <el-checkbox
            v-if="field.input_type === 'boolean'"
            v-model="gatewayOverrides[field.key]"
          >
            启用 {{ field.key }}
          </el-checkbox>
          <el-input
            v-else
            v-model="gatewayOverrides[field.key]"
            :placeholder="field.placeholder || ''"
          />
        </el-form-item>
        <div
          v-if="selectedGatewayPreset"
          data-testid="gateway-preset-preview"
          class="rounded-md border border-blue-100 bg-blue-50 px-4 py-3 text-sm"
        >
          <div class="font-medium text-blue-900">
            {{ selectedGatewayPreset.name }}
          </div>
          <div
            v-if="selectedGatewayPreset.description"
            class="mt-1 text-xs text-blue-700"
          >
            {{ selectedGatewayPreset.description }}
          </div>
          <div class="mt-2 grid grid-cols-1 gap-2 text-gray-700 md:grid-cols-2">
            <div
              v-for="item in selectedGatewayPreviewItems"
              :key="item.label"
            >
              <div class="text-xs text-gray-500">
                {{ item.label }}
              </div>
              <div class="break-all">
                {{ item.value }}
              </div>
            </div>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="addLoading"
          :disabled="!addForm.strategy_id"
          @click="handleAdd"
        >
          添加
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  VideoPlay,
  VideoPause,
  Plus,
  Delete,
  View,
  Loading,
  Setting,
} from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api'
import { liveTradingApi } from '@/api/liveTrading'
import type {
  LiveGatewayPresetFieldInfo,
  LiveGatewayPresetInfo,
  LiveInstanceInfo,
} from '@/api/liveTrading'
import { autoTradingApi } from '@/api/autoTrading'
import type { AutoTradingConfig, ScheduleItem } from '@/api/autoTrading'
import { strategyApi } from '@/api/strategy'
import type { StrategyTemplate } from '@/types'
import {
  useInstanceActions,
  statusLabel,
  formatStrategyId,
} from '@/composables/useInstanceActions'

const router = useRouter()

const loading = ref(true)
const viewMode = ref<'card' | 'list'>('card')
const addLoading = ref(false)
const showAddDialog = ref(false)

const instances = ref<LiveInstanceInfo[]>([])
const gatewayPresets = ref<LiveGatewayPresetInfo[]>([])
const templates = ref<StrategyTemplate[]>([])
const detailDialogVisible = ref(false)
const detailInstance = ref<LiveInstanceInfo | null>(null)

const addForm = ref({ strategy_id: '', gatewayPresetId: '' })
const gatewayOverrides = reactive<Record<string, string | boolean>>({})

const autoTradingEnabled = ref(false)
const autoTradingLoading = ref(false)
const showAutoTradingDialog = ref(false)
const autoTradingConfig = reactive<AutoTradingConfig>({
  enabled: false,
  buffer_minutes: 15,
  sessions: [
    { name: '日盘', open: '09:00', close: '15:00' },
    { name: '夜盘', open: '21:00', close: '23:00' },
  ],
  scope: 'all',
})
const autoTradingForm = reactive<AutoTradingConfig>({
  enabled: false,
  buffer_minutes: 15,
  sessions: [
    { name: '日盘', open: '09:00', close: '15:00' },
    { name: '夜盘', open: '21:00', close: '23:00' },
  ],
  scope: 'all',
})
const autoTradingSchedule = ref<ScheduleItem[]>([])

async function loadAutoTradingConfig() {
  try {
    const [cfg, schedRes] = await Promise.all([
      autoTradingApi.getConfig(),
      autoTradingApi.getSchedule(),
    ])
    Object.assign(autoTradingConfig, cfg)
    autoTradingEnabled.value = cfg.enabled
    autoTradingSchedule.value = schedRes.schedule
  } catch {
    // silently ignore — auto-trading may not be available
  }
}

async function handleAutoTradingToggle(val: boolean | string | number) {
  autoTradingLoading.value = true
  try {
    const updated = await autoTradingApi.updateConfig({ enabled: !!val })
    Object.assign(autoTradingConfig, updated)
    autoTradingEnabled.value = updated.enabled
    ElMessage.success(updated.enabled ? '自动交易已启用' : '自动交易已关闭')
    const schedRes = await autoTradingApi.getSchedule()
    autoTradingSchedule.value = schedRes.schedule
  } catch (e: unknown) {
    autoTradingEnabled.value = !val
    ElMessage.error(getErrorMessage(e, '更新自动交易配置失败'))
  } finally {
    autoTradingLoading.value = false
  }
}

async function handleSaveAutoTrading() {
  autoTradingLoading.value = true
  try {
    const updated = await autoTradingApi.updateConfig({ ...autoTradingForm })
    Object.assign(autoTradingConfig, updated)
    autoTradingEnabled.value = updated.enabled
    showAutoTradingDialog.value = false
    ElMessage.success('自动交易配置已保存')
    const schedRes = await autoTradingApi.getSchedule()
    autoTradingSchedule.value = schedRes.schedule
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存自动交易配置失败'))
  } finally {
    autoTradingLoading.value = false
  }
}

watch(showAutoTradingDialog, (visible) => {
  if (visible) {
    autoTradingForm.enabled = autoTradingConfig.enabled
    autoTradingForm.buffer_minutes = autoTradingConfig.buffer_minutes
    autoTradingForm.sessions = autoTradingConfig.sessions.map(s => ({ ...s }))
    autoTradingForm.scope = autoTradingConfig.scope
  }
})

async function loadData() {
  loading.value = true
  try {
    const [listRes, presetRes, templateRes] = await Promise.all([
      liveTradingApi.list(),
      liveTradingApi.listPresets(),
      strategyApi.getTemplates('live'),
    ])
    instances.value = listRes.instances
    gatewayPresets.value = presetRes.presets
    templates.value = templateRes.templates.filter(t => t.id.startsWith('live/'))
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const { actionLoading, batchLoading, handleStart, handleStop, handleRemove, handleStartAll, handleStopAll } =
  useInstanceActions<LiveInstanceInfo>({
    start: (id) => liveTradingApi.start(id),
    stop: (id) => liveTradingApi.stop(id),
    remove: (id) => liveTradingApi.remove(id),
    startAll: () => liveTradingApi.startAll(),
    stopAll: () => liveTradingApi.stopAll(),
    loadData,
  })

const visibleInstances = computed(() =>
  instances.value.filter(i => i.strategy_id && i.strategy_id.startsWith('live/'))
)

const runningCount = computed(() => visibleInstances.value.filter(i => i.status === 'running').length)

const selectedGatewayPreset = computed(() =>
  gatewayPresets.value.find(preset => preset.id === addForm.value.gatewayPresetId) ?? null
)

const selectedGatewayEditableFields = computed(
  () => selectedGatewayPreset.value?.editable_fields ?? []
)

const selectedGatewayData = computed(() =>
  extractGatewayDataFromParams(selectedGatewayPreset.value?.params as Record<string, unknown> | undefined)
)

const mergedSelectedGatewayData = computed(() => {
  const gatewayData = selectedGatewayData.value
  if (!gatewayData) {
    return null
  }
  const mergedGatewayData = { ...gatewayData }
  for (const field of selectedGatewayEditableFields.value) {
    mergedGatewayData[field.key] = normalizeGatewayOverrideValue(field)
  }
  return mergedGatewayData
})

const selectedGatewayPreviewItems = computed(() => {
  const gatewayData = mergedSelectedGatewayData.value
  if (!gatewayData) {
    return []
  }
  const rows = [
    { label: 'Provider', value: gatewayData.provider },
    { label: 'Exchange', value: gatewayData.exchange_type },
    { label: 'Asset', value: gatewayData.asset_type },
    { label: 'Account', value: gatewayData.account_id },
    { label: 'Base URL', value: gatewayData.base_url },
    { label: 'Verify SSL', value: gatewayData.verify_ssl },
  ]
  return rows
    .filter(item => item.value !== undefined && item.value !== null && String(item.value).trim() !== '')
    .map(item => ({
      label: item.label,
      value: String(item.value),
    }))
})

watch(
  [selectedGatewayData, selectedGatewayEditableFields],
  ([gatewayData, editableFields]) => {
    resetGatewayOverrides()
    for (const field of editableFields) {
      gatewayOverrides[field.key] =
        field.input_type === 'boolean'
          ? Boolean(gatewayData?.[field.key])
          : String(gatewayData?.[field.key] ?? '')
    }
  },
  { immediate: true }
)

function resetGatewayOverrides() {
  for (const key of Object.keys(gatewayOverrides)) {
    delete gatewayOverrides[key]
  }
}

function normalizeGatewayOverrideValue(field: LiveGatewayPresetFieldInfo): string | boolean {
  const value = gatewayOverrides[field.key]
  if (field.input_type === 'boolean') {
    return Boolean(value)
  }
  return String(value ?? '').trim()
}

function extractGatewayDataFromParams(
  params: Record<string, unknown> | null | undefined
): Record<string, unknown> | null {
  if (!params || typeof params !== 'object') {
    return null
  }
  const gateway = params.gateway
  if (!gateway || typeof gateway !== 'object') {
    return null
  }
  return gateway as Record<string, unknown>
}

function extractGatewayData(inst: LiveInstanceInfo | null | undefined): Record<string, unknown> | null {
  return extractGatewayDataFromParams(inst?.params as Record<string, unknown> | undefined)
}

function gatewaySummaryLabel(inst: LiveInstanceInfo): string {
  const gateway = extractGatewayData(inst)
  if (!gateway) {
    return ''
  }
  const parts = [
    gateway.exchange_type,
    gateway.asset_type,
    gateway.account_id,
  ]
    .filter(value => value !== undefined && value !== null && String(value).trim() !== '')
    .map(value => String(value))
  return parts.join(' / ')
}

function gatewayDetailItems(inst: LiveInstanceInfo): Array<{ label: string; value: string }> {
  const gateway = extractGatewayData(inst)
  if (!gateway) {
    return []
  }
  const rows = [
    { label: 'Provider', value: gateway.provider },
    { label: 'Exchange', value: gateway.exchange_type },
    { label: 'Asset', value: gateway.asset_type },
    { label: 'Account', value: gateway.account_id },
    { label: 'Base URL', value: gateway.base_url },
  ]
  return rows
    .filter(item => item.value !== undefined && item.value !== null && String(item.value).trim() !== '')
    .map(item => ({
      label: item.label,
      value: String(item.value),
    }))
}

const detailTimeline = computed(() => {
  if (!detailInstance.value) return []
  const rows: { label: string; time: string }[] = []
  if (detailInstance.value.created_at) {
    rows.push({ label: '创建时间', time: detailInstance.value.created_at })
  }
  if (detailInstance.value.started_at) {
    rows.push({ label: '启动时间', time: detailInstance.value.started_at })
  }
  if (detailInstance.value.stopped_at) {
    rows.push({ label: '停止时间', time: detailInstance.value.stopped_at })
  }
  if (rows.length === 0) {
    rows.push({ label: '暂无记录', time: '-' })
  }
  return rows
})

async function handleAdd() {
  if (!addForm.value.strategy_id) return
  addLoading.value = true
  try {
    const selectedPreset = gatewayPresets.value.find(
      preset => preset.id === addForm.value.gatewayPresetId
    )
    const params = selectedPreset ? JSON.parse(JSON.stringify(selectedPreset.params)) : undefined
    const gatewayData = extractGatewayDataFromParams(params)
    if (gatewayData) {
      for (const field of selectedGatewayEditableFields.value) {
        gatewayData[field.key] = normalizeGatewayOverrideValue(field)
      }
    }
    await liveTradingApi.add(addForm.value.strategy_id, params)
    ElMessage.success('添加成功')
    showAddDialog.value = false
    addForm.value.strategy_id = ''
    addForm.value.gatewayPresetId = ''
    resetGatewayOverrides()
    await loadData()
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '添加失败'))
  } finally {
    addLoading.value = false
  }
}

function goToDetail(inst: LiveInstanceInfo) {
  router.push(`/live-trading/${inst.id}`)
}

function openDetail(inst: LiveInstanceInfo) {
  detailInstance.value = inst
  detailDialogVisible.value = true
}

onMounted(() => {
  loadData()
  loadAutoTradingConfig()
})
</script>
