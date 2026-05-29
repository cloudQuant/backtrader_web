<template>
  <div class="log-viewer">
    <!-- Toolbar -->
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <el-select
        v-model="selectedFile"
        :placeholder="t('commonUi.logSelectFile')"
        class="w-48"
        @change="onFileChange"
      >
        <el-option
          v-for="f in files"
          :key="f.name"
          :label="`${f.name} (${formatSize(f.size)})`"
          :value="f.name"
        />
      </el-select>
      <el-radio-group
        v-model="displayMode"
        size="small"
      >
        <el-radio-button value="raw">
          {{ t('commonUi.logModeRaw') }}
        </el-radio-button>
        <el-radio-button value="formatted">
          {{ t('commonUi.logModeFormatted') }}
        </el-radio-button>
      </el-radio-group>
      <el-input
        v-model="searchText"
        :placeholder="t('commonUi.logSearchPlaceholder')"
        clearable
        class="w-40"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select
        v-model="tailLines"
        class="w-32"
        @change="loadLog"
      >
        <el-option
          :label="t('commonUi.logTailAll')"
          :value="0"
        />
        <el-option
          :label="t('commonUi.logTail500')"
          :value="500"
        />
        <el-option
          :label="t('commonUi.logTail1000')"
          :value="1000"
        />
        <el-option
          :label="t('commonUi.logTail5000')"
          :value="5000"
        />
      </el-select>
      <el-button
        :icon="Refresh"
        :loading="loading"
        @click="loadLog"
      >
        {{ t('commonUi.logRefresh') }}
      </el-button>
      <el-button
        :icon="Download"
        @click="downloadLog"
      >
        {{ t('commonUi.logDownload') }}
      </el-button>
      <el-button
        :icon="Delete"
        type="warning"
        plain
        :disabled="!selectedFile"
        @click="handleClearCurrentLog"
      >
        {{ t('commonUi.logClearCurrent') }}
      </el-button>
      <el-button
        :icon="Delete"
        type="danger"
        plain
        @click="handleClearAllLogs"
      >
        {{ t('commonUi.logClearAll') }}
      </el-button>
    </div>

    <!-- Log content -->
    <div
      class="log-content rounded border overflow-auto font-mono text-sm"
      :class="displayMode === 'raw' ? 'bg-gray-900 text-gray-100' : 'bg-slate-50 text-slate-800 dark:bg-slate-900 dark:text-slate-200'"
      :style="{ height: viewerHeight + 'px' }"
    >
      <div
        v-if="loading"
        class="p-4 text-center text-gray-400"
      >
        <el-icon class="is-loading text-2xl">
          <Loading />
        </el-icon>
        <span class="ml-2">{{ t('commonUi.logLoading') }}</span>
      </div>
      <div
        v-else-if="error"
        class="p-4 text-red-400"
      >
        {{ error }}
      </div>
      <div
        v-else-if="!selectedFile"
        class="p-4 text-gray-400"
      >
        {{ t('commonUi.logSelectFilePrompt') }}
      </div>
      <!-- Raw mode -->
      <pre
        v-else-if="displayMode === 'raw'"
        ref="contentRef"
        class="p-4 m-0 whitespace-pre-wrap break-words"
      ><span
        v-for="(line, i) in displayLines"
        :key="i"
        :class="{ 'bg-yellow-800/50': searchText && lineMatchesSearch(line, searchText) }"
      >{{ String(i + 1).padStart(6) }} | {{ line }}</span></pre>
      <!-- Formatted mode -->
      <div
        v-else
        ref="contentRef"
        class="p-4 space-y-1.5"
      >
        <div
          v-for="(item, i) in formattedEntries"
          :key="i"
          class="log-entry rounded px-3 py-1.5 border-l-4 text-xs"
          :class="item.levelClass || 'border-slate-200 dark:border-slate-700 bg-white/50 dark:bg-slate-800/20'"
        >
          <span
            class="inline-block mr-3 w-10 shrink-0 text-slate-400 select-none"
          >{{ i + 1 }}</span>
          <span
            v-if="item.time"
            class="text-slate-500 dark:text-slate-400 mr-2 shrink-0"
          >{{ item.time }}</span>
          <span
            v-if="item.badge"
            class="badge px-1.5 py-0.5 rounded text-xs font-medium mr-2 shrink-0"
            :class="item.badgeClass"
          >{{ item.badge }}</span>
          <span
            :class="{ 'bg-amber-200 dark:bg-amber-800/50': searchText && (item.raw && lineMatchesSearch(item.raw, searchText) || (item.text && item.text.toLowerCase().includes(searchText.toLowerCase()))) }"
          >{{ item.text || item.raw }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, Refresh, Download, Loading, Delete } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { simulationApi } from '@/api/simulation'
import { formatLogLine, lineMatchesSearch, formatSize, type FormattedEntry } from './logViewerHelpers'

const { t } = useI18n()

const props = defineProps<{
  instanceId: string
  contentHeight?: number
}>()

const viewerHeight = computed(() => props.contentHeight ?? 400)

const files = ref<{ name: string; size: number }[]>([])
const selectedFile = ref<string>('')
const logContent = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const searchText = ref('')
const tailLines = ref<number>(0)
const contentRef = ref<HTMLElement | null>(null)

const displayMode = ref<'raw' | 'formatted'>('formatted')

const displayLines = computed(() => logContent.value.split('\n'))


const formattedEntries = computed((): FormattedEntry[] => {
  const lines = logContent.value.split('\n')
  return lines.map((raw) => formatLogLine(raw.trim()))
})


async function loadFiles() {
  try {
    const res = await simulationApi.listLogs(props.instanceId)
    files.value = res.files
    if (files.value.length > 0 && !selectedFile.value) {
      selectedFile.value = files.value[0].name
      await loadLog()
    }
  } catch (e: unknown) {
    error.value = (e as Error).message || t('commonUi.logFilesLoadFailed')
  }
}

async function loadLog() {
  if (!selectedFile.value) return
  loading.value = true
  error.value = null
  try {
    logContent.value = await simulationApi.getLog(
      props.instanceId,
      selectedFile.value,
      tailLines.value || undefined
    )
  } catch (e: unknown) {
    error.value = (e as Error).message || t('commonUi.logLoadFailed')
  } finally {
    loading.value = false
  }
}

function onFileChange() {
  loadLog()
}

async function downloadLog() {
  if (!selectedFile.value) return
  try {
    await simulationApi.downloadLog(props.instanceId, selectedFile.value)
  } catch {
    // Error handled by API interceptor
  }
}

async function handleClearCurrentLog() {
  if (!selectedFile.value) return
  try {
    await ElMessageBox.confirm(
      t('commonUi.logClearCurrentMsg', { name: selectedFile.value }),
      t('commonUi.logClearCurrentTitle'),
      { confirmButtonText: t('commonUi.logBtnConfirm'), cancelButtonText: t('commonUi.logBtnCancel'), type: 'warning' }
    )
    await simulationApi.clearLog(props.instanceId, selectedFile.value)
    ElMessage.success(t('commonUi.logCleared'))
    await loadLog()
    await loadFiles()
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { toString?: () => string })?.toString?.() !== 'cancel') {
      ElMessage.error(t('commonUi.logClearFailed'))
    }
  }
}

async function handleClearAllLogs() {
  try {
    await ElMessageBox.confirm(
      t('commonUi.logClearAllMsg'),
      t('commonUi.logClearAllTitle'),
      { confirmButtonText: t('commonUi.logBtnConfirm'), cancelButtonText: t('commonUi.logBtnCancel'), type: 'warning' }
    )
    const res = await simulationApi.clearAllLogs(props.instanceId)
    ElMessage.success(res.message || t('commonUi.logAllCleared'))
    await loadLog()
    await loadFiles()
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { toString?: () => string })?.toString?.() !== 'cancel') {
      ElMessage.error(t('commonUi.logClearFailed'))
    }
  }
}

watch(
  () => props.instanceId,
  () => {
    selectedFile.value = ''
    logContent.value = ''
    loadFiles()
  }
)

onMounted(() => {
  loadFiles()
})
</script>
