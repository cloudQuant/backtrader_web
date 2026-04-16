<template>
  <el-dialog
    :model-value="modelValue"
    title="策略单元运行文件"
    width="1120px"
    @close="emit('update:modelValue', false)"
  >
    <div
      v-if="unit"
      class="space-y-4"
    >
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            策略单元
          </div>
          <div class="mt-1 font-semibold text-slate-700">
            {{ unit.strategy_name || unit.strategy_id }}
          </div>
          <div class="text-xs text-slate-400">
            {{ unit.symbol }} / {{ unit.timeframe }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            实例状态
          </div>
          <div class="mt-1 font-semibold text-slate-700">
            {{ unit.trading_snapshot?.instance_status || unit.run_status }}
          </div>
          <div class="text-xs text-slate-400">
            {{ unit.trading_instance_id || '未分配实例' }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            日志目录
          </div>
          <div class="mt-1 break-all font-mono text-xs text-slate-700">
            {{ runtimeInfo?.log_dir || '-' }}
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="text-sm font-medium text-slate-700">
              运行目录
            </div>
            <div class="font-mono text-xs text-slate-500">
              {{ runtimeInfo?.runtime_dir || '-' }}
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <el-select
              v-model="selectedFile"
              class="w-72"
              placeholder="选择文件"
              :loading="loadingInfo"
              @change="loadSelectedFile"
            >
              <el-option
                v-for="file in runtimeInfo?.files || []"
                :key="file.relative_path"
                :label="fileLabel(file)"
                :value="file.relative_path"
              />
            </el-select>
            <el-select
              v-model="tailLines"
              class="w-28"
              @change="loadSelectedFile"
            >
              <el-option
                label="全部"
                :value="null"
              />
              <el-option
                label="200 行"
                :value="200"
              />
              <el-option
                label="500 行"
                :value="500"
              />
              <el-option
                label="1000 行"
                :value="1000"
              />
            </el-select>
            <el-button
              :loading="loadingInfo || loadingContent"
              @click="refreshAll"
            >
              刷新
            </el-button>
            <el-button
              type="primary"
              :loading="openingDir"
              @click="openRuntimeDir"
            >
              打开策略单元
            </el-button>
          </div>
        </div>

        <div class="mb-3 flex flex-wrap gap-2">
          <el-tag
            v-for="file in runtimeInfo?.files || []"
            :key="file.relative_path"
            :type="selectedFile === file.relative_path ? 'primary' : 'info'"
            effect="plain"
            class="cursor-pointer"
            @click="selectFile(file.relative_path)"
          >
            {{ file.relative_path }}
          </el-tag>
        </div>

        <div class="rounded-lg border border-slate-200 bg-slate-950 text-slate-100">
          <div class="border-b border-slate-800 px-4 py-2 font-mono text-xs text-slate-400">
            {{ selectedFile || '未选择文件' }}
          </div>
          <div class="unit-runtime-dialog__content">
            <div
              v-if="loadingContent"
              class="px-4 py-6 text-center text-sm text-slate-400"
            >
              加载中...
            </div>
            <div
              v-else-if="contentError"
              class="px-4 py-6 text-sm text-rose-300"
            >
              {{ contentError }}
            </div>
            <div
              v-else-if="!selectedFile"
              class="px-4 py-6 text-sm text-slate-400"
            >
              请选择要查看的文件
            </div>
            <pre
              v-else
              class="m-0 whitespace-pre-wrap break-words px-4 py-4 font-mono text-xs leading-6"
            >{{ fileContent }}</pre>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { StrategyUnit, StrategyUnitRuntimeFile, StrategyUnitRuntimeInfo } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unit: StrategyUnit | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const runtimeInfo = ref<StrategyUnitRuntimeInfo | null>(null)
const selectedFile = ref('')
const fileContent = ref('')
const contentError = ref('')
const tailLines = ref<number | null>(500)
const loadingInfo = ref(false)
const loadingContent = ref(false)
const openingDir = ref(false)

watch(
  () => [props.modelValue, props.unit?.id] as const,
  ([visible, unitId]) => {
    if (!visible || !unitId) {
      if (!visible) {
        runtimeInfo.value = null
        selectedFile.value = ''
        fileContent.value = ''
        contentError.value = ''
      }
      return
    }
    void loadRuntimeInfo()
  },
  { immediate: true },
)

function pickDefaultFile(files: StrategyUnitRuntimeFile[]): string {
  const preferred = [
    'logs/error.log',
    'logs/system.log',
    'logs/monitor.log',
    'logs/signal.log',
    'config.yaml',
    'run.py',
  ]
  for (const path of preferred) {
    if (files.some(file => file.relative_path === path)) {
      return path
    }
  }
  return files[0]?.relative_path || ''
}

function fileLabel(file: StrategyUnitRuntimeFile): string {
  return `${file.relative_path} (${formatSize(file.size)})`
}

function formatSize(size: number): string {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
  }
  if (size >= 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${size} B`
}

function selectFile(relativePath: string) {
  selectedFile.value = relativePath
  void loadSelectedFile()
}

async function loadRuntimeInfo() {
  if (!props.unit) return
  loadingInfo.value = true
  contentError.value = ''
  try {
    const info = await workspaceApi.getUnitRuntimeInfo(props.workspaceId, props.unit.id)
    runtimeInfo.value = info
    const nextFile = info.files.some(file => file.relative_path === selectedFile.value)
      ? selectedFile.value
      : pickDefaultFile(info.files)
    selectedFile.value = nextFile
    if (nextFile) {
      await loadSelectedFile()
    } else {
      fileContent.value = ''
    }
  } catch (error: unknown) {
    runtimeInfo.value = null
    fileContent.value = ''
    contentError.value = getErrorMessage(error, '加载运行文件失败')
  } finally {
    loadingInfo.value = false
  }
}

async function loadSelectedFile() {
  if (!props.unit || !selectedFile.value) {
    fileContent.value = ''
    return
  }
  loadingContent.value = true
  contentError.value = ''
  try {
    fileContent.value = await workspaceApi.getUnitRuntimeFile(
      props.workspaceId,
      props.unit.id,
      selectedFile.value,
      tailLines.value,
    )
  } catch (error: unknown) {
    fileContent.value = ''
    contentError.value = getErrorMessage(error, '读取文件失败')
  } finally {
    loadingContent.value = false
  }
}

async function openRuntimeDir() {
  if (!props.unit) return
  openingDir.value = true
  try {
    const result = await workspaceApi.openUnitRuntimeDir(props.workspaceId, props.unit.id)
    ElMessage.success(result.message || '策略单元目录已打开')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '打开策略单元失败'))
  } finally {
    openingDir.value = false
  }
}

function refreshAll() {
  void loadRuntimeInfo()
}
</script>

<style scoped>
.unit-runtime-dialog__content {
  max-height: 520px;
  overflow: auto;
}
</style>
