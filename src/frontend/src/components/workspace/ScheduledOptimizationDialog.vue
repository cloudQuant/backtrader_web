<template>
  <el-dialog
    v-model="visible"
    title="定时优化设置"
    width="760px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            当前状态
          </div>
          <div
            class="mt-1 text-lg font-semibold"
            :class="form.enabled ? 'text-emerald-600' : 'text-slate-700'"
          >
            {{ form.enabled ? '已启用' : '已关闭' }}
          </div>
          <div class="text-xs text-slate-400">
            定时优化调度
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            执行频率
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ frequencyLabel }}
          </div>
          <div class="text-xs text-slate-400">
            自动触发周期
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            执行时间
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ form.execution_time }}
          </div>
          <div class="text-xs text-slate-400">
            工作区计划时点
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            作用范围
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ scopeLabel }}
          </div>
          <div class="text-xs text-slate-400">
            已选 {{ store.selectedUnitIds.length }} 个单元
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <el-form
          label-width="110px"
          class="space-y-2"
        >
          <el-form-item label="启用定时优化">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="执行频率">
            <el-radio-group v-model="form.frequency">
              <el-radio value="daily">
                每日
              </el-radio>
              <el-radio value="weekly">
                每周
              </el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="执行时间">
            <el-time-picker
              v-model="form.execution_time"
              value-format="HH:mm"
              format="HH:mm"
              placeholder="选择时间"
              class="w-40"
            />
          </el-form-item>
          <el-form-item label="作用范围">
            <el-select
              v-model="form.unit_scope"
              class="w-48"
            >
              <el-option
                label="全部交易单元"
                value="all"
              />
              <el-option
                label="仅当前选中单元"
                value="selected"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="空闲时执行">
            <el-switch v-model="form.only_when_idle" />
          </el-form-item>
        </el-form>
      </div>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="当前版本保存工作区级定时优化策略配置，供后续调度器统一读取。"
      />
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
import { computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { useWorkspaceStore } from '@/stores/workspace'

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
const frequencyLabel = computed(() => (form.frequency === 'weekly' ? '每周' : '每日'))
const scopeLabel = computed(() => (form.unit_scope === 'selected' ? '当前选中单元' : '全部交易单元'))
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
    ElMessage.success('定时优化设置已保存')
    visible.value = false
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '保存定时优化设置失败'))
  }
}
</script>
