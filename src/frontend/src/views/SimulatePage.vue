<template>
  <div class="space-y-6">
    <!-- 顶部操作栏 -->
    <el-card>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-bold">
            模拟交易
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
          <el-tooltip
            content="SimNow 单账号仅支持 1–2 个并发连接，建议分批启动"
            placement="bottom"
          >
            <el-button
              type="success"
              :loading="batchLoading"
              :disabled="instances.length === 0"
              @click="handleStartAll"
            >
              <el-icon><VideoPlay /></el-icon>一键启动
            </el-button>
          </el-tooltip>
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
      <el-empty description="暂无模拟策略，点击右上角添加" />
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

          <div
            v-if="inst.error"
            class="text-sm text-red-500 truncate mb-4"
            :title="inst.error"
          >
            错误: {{ inst.error }}
          </div>
          <div
            v-else
            class="mb-4"
          />

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
      title="添加模拟策略"
      width="600px"
    >
      <el-form
        :model="addForm"
        label-width="100px"
      >
        <el-form-item
          label="选择策略"
          required
        >
          <el-select
            v-model="addForm.strategy_id"
            placeholder="请选择策略"
            class="w-full"
            filterable
            @change="onStrategyChange"
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item
          v-if="strategyConfig"
          label="策略说明"
        >
          <div class="text-gray-500 text-sm">
            <span v-if="strategyConfig.strategy.description">{{ strategyConfig.strategy.description }}</span>
            <span
              v-if="strategyConfig.strategy.author"
              class="ml-2 text-gray-400"
            >— {{ strategyConfig.strategy.author }}</span>
          </div>
        </el-form-item>

        <template v-if="Object.keys(dynamicParams).length > 0">
          <el-divider content-position="left">
            策略参数
          </el-divider>
          <el-row :gutter="20">
            <el-col
              v-for="(val, key) in dynamicParams"
              :key="key"
              :span="12"
            >
              <el-form-item :label="String(key)">
                <el-input-number
                  v-if="typeof val === 'number'"
                  v-model="dynamicParams[key]"
                  :step="Number.isInteger(val) ? 1 : 0.01"
                  :precision="Number.isInteger(val) ? 0 : 4"
                  class="w-full"
                />
                <el-input
                  v-else
                  v-model="dynamicParams[key]"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="addLoading"
          @click="handleAdd"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api'
import { strategyApi } from '@/api/strategy'
import { useSimulationStore } from '@/stores/simulation'
import { useStrategyStore } from '@/stores/strategy'
import type { SimulationInstanceInfo } from '@/api/simulation'
import type { StrategyConfig } from '@/types'
import {
  useInstanceActions,
  statusLabel,
  formatStrategyId,
} from '@/composables/useInstanceActions'

const router = useRouter()
const simulationStore = useSimulationStore()
const strategyStore = useStrategyStore()

const loading = ref(false)
const viewMode = ref<'card' | 'list'>('card')
const showAddDialog = ref(false)
const addLoading = ref(false)
const detailDialogVisible = ref(false)
const detailInstance = ref<SimulationInstanceInfo | null>(null)

const strategyConfig = ref<StrategyConfig | null>(null)
const dynamicParams = reactive<Record<string, unknown>>({})

const addForm = reactive({
  strategy_id: '',
})

const { actionLoading, batchLoading, handleStart, handleStop, handleRemove, handleStartAll, handleStopAll } =
  useInstanceActions<SimulationInstanceInfo>({
    start: (id) => simulationStore.startInstance(id),
    stop: (id) => simulationStore.stopInstance(id),
    remove: (id) => simulationStore.removeInstance(id),
    startAll: () => simulationStore.startAll(),
    stopAll: () => simulationStore.stopAll(),
    loadData: () => simulationStore.fetchInstances(),
  })

const instances = computed(() => simulationStore.instances)
const visibleInstances = computed(() =>
  instances.value.filter(i => i.strategy_id && i.strategy_id.startsWith('simulate/'))
)
const templates = computed(() => strategyStore.templates)
const runningCount = computed(() => visibleInstances.value.filter(i => i.status === 'running').length)

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

let _pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      strategyStore.fetchTemplates('simulate'),
      simulationStore.fetchInstances(),
    ])
  } finally {
    loading.value = false
  }
  // Poll every 5 s so externally-started/stopped strategies are detected
  _pollTimer = setInterval(() => {
    simulationStore.fetchInstances()
  }, 5000)
})

onUnmounted(() => {
  if (_pollTimer) {
    clearInterval(_pollTimer)
    _pollTimer = null
  }
})

async function onStrategyChange(strategyId: string) {
  if (!strategyId) {
    strategyConfig.value = null
    return
  }
  try {
    const config = await strategyApi.getTemplateConfig(strategyId)
    strategyConfig.value = config

    Object.keys(dynamicParams).forEach(k => delete dynamicParams[k])
    if (config.params) {
      Object.entries(config.params).forEach(([k, v]) => {
        dynamicParams[k] = v
      })
    }
  } catch (e) {
    ElMessage.warning(getErrorMessage(e, '无法加载策略配置，将使用默认参数'))
    strategyConfig.value = null
  }
}

async function handleAdd() {
  if (!addForm.strategy_id) {
    ElMessage.warning('请选择策略')
    return
  }
  addLoading.value = true
  try {
    await simulationStore.addInstance(addForm.strategy_id, { ...dynamicParams })
    ElMessage.success('添加成功')
    showAddDialog.value = false
    addForm.strategy_id = ''
    Object.keys(dynamicParams).forEach(k => delete dynamicParams[k])
  } catch (e) {
    // Axios errors are already handled by api interceptor; only show for non-axios errors
    const isAxiosError = e && typeof e === 'object' && 'response' in e
    if (!isAxiosError) {
      ElMessage.error(getErrorMessage(e, '添加策略失败'))
    }
  } finally {
    addLoading.value = false
  }
}

function goToDetail(inst: SimulationInstanceInfo) {
  router.push(`/simulate/${inst.id}`)
}

function openDetail(inst: SimulationInstanceInfo) {
  detailInstance.value = inst
  detailDialogVisible.value = true
}
</script>
