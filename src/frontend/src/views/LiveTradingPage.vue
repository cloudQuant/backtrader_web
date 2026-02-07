<template>
  <div class="space-y-6">
    <!-- 顶部操作栏 -->
    <el-card>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-bold">实盘交易</h3>
          <el-tag :type="runningCount > 0 ? 'success' : 'info'" size="small">
            {{ runningCount }} 运行中 / {{ instances.length }} 总计
          </el-tag>
        </div>
        <div class="flex gap-2">
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

    <div v-else-if="instances.length === 0" class="text-center py-12">
      <el-empty description="暂无实盘策略，点击右上角添加" />
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <el-card
        v-for="inst in instances"
        :key="inst.id"
        shadow="hover"
        class="cursor-pointer"
        @click="goToDetail(inst)"
      >
        <div class="flex justify-between items-start mb-3">
          <div>
            <h4 class="text-md font-bold">{{ inst.strategy_name || inst.strategy_id }}</h4>
            <span class="text-xs text-gray-400">{{ inst.strategy_id }}</span>
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
          <el-button
            size="small"
            @click="goToDetail(inst)"
          >
            <el-icon><View /></el-icon>分析
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

const router = useRouter()

const loading = ref(true)
const batchLoading = ref(false)
const addLoading = ref(false)
const showAddDialog = ref(false)

const instances = ref<LiveInstanceInfo[]>([])
const templates = ref<{ id: string; name: string }[]>([])
const actionLoading = ref<Record<string, string>>({})

const addForm = ref({ strategy_id: '' })

const runningCount = computed(() => instances.value.filter(i => i.status === 'running').length)

function statusLabel(s: string) {
  return s === 'running' ? '运行中' : s === 'error' ? '异常' : '已停止'
}

async function loadData() {
  loading.value = true
  try {
    const [listRes, tplRes] = await Promise.all([
      liveTradingApi.list(),
      strategyApi.getTemplates(),
    ])
    instances.value = listRes.instances
    templates.value = tplRes.templates
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

onMounted(() => {
  loadData()
})
</script>
