<template>
  <div class="space-y-6">
    <el-page-header
      title="返回"
      @back="goBack"
    >
      <template #content>
        <span>{{ script?.script_name || '脚本详情' }}</span>
      </template>
    </el-page-header>

    <el-card v-loading="loading">
      <template #header>
        <div class="detail-header">
          <div>
            <div class="detail-title">{{ script?.script_name || '加载中' }}</div>
            <div class="detail-subtitle">{{ script?.script_id }}</div>
          </div>
          <div class="detail-tags">
            <el-tag v-if="script">{{ script.category }}</el-tag>
            <el-tag
              v-if="script"
              :type="script.is_active ? 'success' : 'warning'"
            >
              {{ script.is_active ? '启用' : '停用' }}
            </el-tag>
          </div>
        </div>
      </template>

      <el-descriptions
        v-if="script"
        :column="2"
        border
      >
        <el-descriptions-item label="模块路径">
          {{ script.module_path || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="函数名">
          {{ script.function_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="目标表">
          {{ script.target_table || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="频率">
          {{ script.frequency || '-' }}
        </el-descriptions-item>
        <el-descriptions-item
          label="描述"
          :span="2"
        >
          {{ script.description || '暂无描述' }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="run-panel">
        <div class="section-title">手动执行</div>
        <el-alert
          type="info"
          :closable="false"
          show-icon
        >
          这里直接向后端发送执行参数 JSON，执行结果会写入“执行记录”和“数据表”页面。
        </el-alert>
        <el-input
          v-model="paramsText"
          type="textarea"
          :rows="10"
          placeholder="请输入 JSON 参数对象"
        />
        <div class="run-actions">
          <el-button
            :disabled="!script"
            @click="openTaskCreate"
          >
            去创建定时任务
          </el-button>
          <el-button
            v-if="isAdmin"
            type="primary"
            :loading="running"
            :disabled="!script"
            @click="runNow"
          >
            立即执行
          </el-button>
        </div>
      </div>

      <div
        v-if="script"
        class="json-panel"
      >
        <div class="section-title">依赖参数定义</div>
        <pre>{{ toJsonText(script.dependencies || {}) }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { akshareScriptsApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataScript } from '@/types'
import { parseJsonText, toJsonText } from '@/views/data/utils'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const running = ref(false)
const script = ref<DataScript | null>(null)
const paramsText = ref('{\n  "symbol": "000001"\n}')

const isAdmin = computed(() => authStore.user?.is_admin ?? false)

function goBack() {
  void router.back()
}

async function loadDetail() {
  loading.value = true
  try {
    script.value = await akshareScriptsApi.getDetail(String(route.params.id))
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载脚本详情失败'))
  } finally {
    loading.value = false
  }
}

async function runNow() {
  if (!script.value) {
    return
  }

  running.value = true
  try {
    const result = await akshareScriptsApi.run(script.value.script_id, {
      parameters: parseJsonText(paramsText.value),
    })
    ElMessage.success(`执行已触发：${result.execution_id}`)
    void router.push({
      name: 'DataExecutions',
      query: { script_id: script.value.script_id },
    })
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '执行脚本失败'))
  } finally {
    running.value = false
  }
}

function openTaskCreate() {
  if (!script.value) {
    return
  }
  void router.push({
    name: 'DataTasks',
    query: { script_id: script.value.script_id },
  })
}

onMounted(() => {
  void loadDetail()
})
</script>

<style scoped>
.detail-header,
.detail-tags,
.run-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-title {
  font-size: 22px;
  font-weight: 700;
}

.detail-subtitle {
  margin-top: 4px;
  color: #64748b;
}

.run-panel,
.json-panel {
  margin-top: 24px;
}

.section-title {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 700;
}

.run-actions {
  justify-content: flex-end;
  margin-top: 12px;
}

pre {
  margin: 0;
  padding: 16px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 12px;
  overflow: auto;
}
</style>
