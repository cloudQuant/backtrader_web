<template>
  <div class="space-y-6">
    <!-- 顶部操作栏 -->
    <el-card>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-bold">实盘交易</h3>
          <el-tag :type="runningCount > 0 ? 'success' : 'info'" size="small">
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
          <el-button type="success" @click="handleStartAll" :loading="batchLoading" :disabled="instances.length === 0">
            <el-icon><VideoPlay /></el-icon>一键启动
          </el-button>
          <el-button type="danger" @click="handleStopAll" :loading="batchLoading" :disabled="runningCount === 0">
            <el-icon><VideoPause /></el-icon>一键停止
          </el-button>
          <el-button type="primary" @click="showAddDialog = true">
            <el-icon><Plus /></el-icon>添加策略
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 策略列表 -->
    <div v-if="loading" class="flex justify-center py-12">
      <el-icon class="is-loading text-4xl text-blue-500"><Loading /></el-icon>
    </div>

    <div v-else-if="visibleInstances.length === 0" class="text-center py-12">
      <el-empty description="暂无实盘策略，点击右上角添加" />
    </div>

    <div v-else>
      <!-- 卡片视图 -->
      <div v-if="viewMode === 'card'" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <el-card
          v-for="inst in visibleInstances"
          :key="inst.id"
          shadow="hover"
          class="cursor-pointer"
          @click="goToDetail(inst)"
        >
          <div class="flex justify-between items-start mb-3">
            <div>
              <h4 class="text-md font-bold">{{ inst.strategy_name || formatStrategyId(inst.strategy_id) }}</h4>
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
            <div v-if="inst.started_at">启动: {{ inst.started_at }}</div>
            <div v-if="inst.stopped_at && inst.status !== 'running'">停止: {{ inst.stopped_at }}</div>
            <div>添加: {{ inst.created_at }}</div>
            <div v-if="inst.error" class="text-red-500 text-xs truncate" :title="inst.error">
              错误: {{ inst.error }}
            </div>
          </div>

          <div class="flex gap-2" @click.stop>
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
            <el-button size="small" @click="goToDetail(inst)">
              <el-icon><View /></el-icon>分析
            </el-button>
            <el-button size="small" @click="openDetail(inst)">详情</el-button>
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
        <el-table :data="visibleInstances" stripe size="small" class="w-full">
          <el-table-column prop="strategy_name" label="策略名称" min-width="160">
            <template #default="{ row }">
              {{ row.strategy_name || formatStrategyId(row.strategy_id) }}
            </template>
          </el-table-column>
          <el-table-column label="策略ID" min-width="160">
            <template #default="{ row }">
              {{ formatStrategyId(row.strategy_id) }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'running' ? 'success' : row.status === 'error' ? 'danger' : 'info'"
                size="small"
              >
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" align="center">
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
                <el-button size="small" link @click="goToDetail(row)">分析</el-button>
                <el-button size="small" link @click="openDetail(row)">详情</el-button>
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
    <el-dialog v-model="detailDialogVisible" title="实例时间日志" width="520px">
      <div v-if="detailInstance">
        <div class="mb-3 text-sm text-gray-600">
          <div>策略：{{ detailInstance.strategy_name || formatStrategyId(detailInstance.strategy_id) }}</div>
          <div class="text-xs text-gray-400 mt-1">ID：{{ detailInstance.id }}</div>
        </div>
        <el-table
          :data="detailTimeline"
          size="small"
          border
          class="w-full"
        >
          <el-table-column prop="label" label="事件" width="120" />
          <el-table-column prop="time" label="时间" />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 添加策略对话框 -->
    <el-dialog v-model="showAddDialog" title="添加实盘策略" width="500px">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="策略">
          <el-select v-model="addForm.strategy_id" placeholder="选择策略" class="w-full" filterable>
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleAdd" :disabled="!addForm.strategy_id">
          添加
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  VideoPlay,
  VideoPause,
  Plus,
  Delete,
  View,
  Loading,
} from '@element-plus/icons-vue'
import { liveTradingApi } from '@/api/liveTrading'
import type { LiveInstanceInfo } from '@/api/liveTrading'
import { strategyApi } from '@/api/strategy'
import type { StrategyTemplate } from '@/types'

const router = useRouter()

const loading = ref(true)
const viewMode = ref<'card' | 'list'>('card')
const batchLoading = ref(false)
const addLoading = ref(false)
const showAddDialog = ref(false)

const instances = ref<LiveInstanceInfo[]>([])
const templates = ref<StrategyTemplate[]>([])
const actionLoading = ref<Record<string, string>>({})
const detailDialogVisible = ref(false)
const detailInstance = ref<LiveInstanceInfo | null>(null)

const addForm = ref({ strategy_id: '' })

const visibleInstances = computed(() =>
  instances.value.filter(i => i.strategy_id && i.strategy_id.startsWith('live/'))
)

const runningCount = computed(() => visibleInstances.value.filter(i => i.status === 'running').length)

function statusLabel(s: string) {
  return s === 'running' ? '运行中' : s === 'error' ? '异常' : '已停止'
}

function formatStrategyId(id?: string) {
  if (!id) return ''
  const idx = id.indexOf('/')
  return idx !== -1 ? id.slice(idx + 1) : id
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

async function loadData() {
  loading.value = true
  try {
    const [listRes, tplRes] = await Promise.all([
      liveTradingApi.list(),
      strategyApi.getTemplates('live'),
    ])
    instances.value = listRes.instances
    templates.value = tplRes.templates.filter(t => t.id.startsWith('live/'))
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function handleAdd() {
  if (!addForm.value.strategy_id) return
  addLoading.value = true
  try {
    await liveTradingApi.add(addForm.value.strategy_id)
    ElMessage.success('添加成功')
    showAddDialog.value = false
    addForm.value.strategy_id = ''
    await loadData()
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  } finally {
    addLoading.value = false
  }
}

async function handleRemove(inst: LiveInstanceInfo) {
  actionLoading.value[inst.id] = 'remove'
  try {
    await liveTradingApi.remove(inst.id)
    ElMessage.success('已删除')
    await loadData()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  } finally {
    delete actionLoading.value[inst.id]
  }
}

async function handleStart(inst: LiveInstanceInfo) {
  actionLoading.value[inst.id] = 'start'
  try {
    const updated = await liveTradingApi.start(inst.id)
    Object.assign(inst, updated)
    ElMessage.success(`${inst.strategy_name} 已启动`)
  } catch (e: any) {
    ElMessage.error(e.message || '启动失败')
  } finally {
    delete actionLoading.value[inst.id]
  }
}

async function handleStop(inst: LiveInstanceInfo) {
  actionLoading.value[inst.id] = 'stop'
  try {
    const updated = await liveTradingApi.stop(inst.id)
    Object.assign(inst, updated)
    ElMessage.success(`${inst.strategy_name} 已停止`)
  } catch (e: any) {
    ElMessage.error(e.message || '停止失败')
  } finally {
    delete actionLoading.value[inst.id]
  }
}

async function handleStartAll() {
  batchLoading.value = true
  try {
    const res = await liveTradingApi.startAll()
    ElMessage.success(`启动完成: 成功 ${res.success}, 失败 ${res.failed}`)
    await loadData()
  } catch (e: any) {
    ElMessage.error(e.message || '批量启动失败')
  } finally {
    batchLoading.value = false
  }
}

async function handleStopAll() {
  batchLoading.value = true
  try {
    const res = await liveTradingApi.stopAll()
    ElMessage.success(`停止完成: 成功 ${res.success}, 失败 ${res.failed}`)
    await loadData()
  } catch (e: any) {
    ElMessage.error(e.message || '批量停止失败')
  } finally {
    batchLoading.value = false
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
})
</script>
