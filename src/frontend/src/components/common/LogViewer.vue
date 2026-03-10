<template>
  <div class="log-viewer">
    <!-- 工具栏 -->
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <el-select
        v-model="selectedFile"
        placeholder="选择日志文件"
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
      <el-radio-group v-model="displayMode" size="small">
        <el-radio-button value="raw">原始</el-radio-button>
        <el-radio-button value="formatted">格式化</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="searchText"
        placeholder="搜索并高亮"
        clearable
        class="w-40"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select v-model="tailLines" class="w-32" @change="loadLog">
        <el-option label="全部" :value="null" />
        <el-option label="最近 500 行" :value="500" />
        <el-option label="最近 1000 行" :value="1000" />
        <el-option label="最近 5000 行" :value="5000" />
      </el-select>
      <el-button :icon="Refresh" @click="loadLog" :loading="loading">刷新</el-button>
      <el-button :icon="Download" @click="downloadLog">下载</el-button>
    </div>

    <!-- 日志内容 -->
    <div
      class="log-content rounded border overflow-auto font-mono text-sm"
      :class="displayMode === 'raw' ? 'bg-gray-900 text-gray-100' : 'bg-slate-50 text-slate-800 dark:bg-slate-900 dark:text-slate-200'"
      :style="{ height: viewerHeight + 'px' }"
    >
      <div v-if="loading" class="p-4 text-center text-gray-400">
        <el-icon class="is-loading text-2xl"><Loading /></el-icon>
        <span class="ml-2">加载中...</span>
      </div>
      <div v-else-if="error" class="p-4 text-red-400">{{ error }}</div>
      <div v-else-if="!selectedFile" class="p-4 text-gray-400">
        请选择要查看的日志文件
      </div>
      <!-- 原始模式 -->
      <pre
        v-else-if="displayMode === 'raw'"
        class="p-4 m-0 whitespace-pre-wrap break-words"
        ref="contentRef"
      ><span
        v-for="(line, i) in displayLines"
        :key="i"
        :class="{ 'bg-yellow-800/50': searchText && lineMatchesSearch(line) }"
      >{{ String(i + 1).padStart(6) }} | {{ line }}</span></pre>
      <!-- 格式化模式 -->
      <div v-else class="p-4 space-y-1.5" ref="contentRef">
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
            :class="{ 'bg-amber-200 dark:bg-amber-800/50': searchText && (item.raw && lineMatchesSearch(item.raw) || (item.text && item.text.toLowerCase().includes(searchText.toLowerCase()))) }"
          >{{ item.text || item.raw }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Refresh, Download, Loading } from '@element-plus/icons-vue'
import { simulationApi } from '@/api/simulation'

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
const tailLines = ref<number | null>(null)
const contentRef = ref<HTMLElement | null>(null)

const displayMode = ref<'raw' | 'formatted'>('formatted')

const displayLines = computed(() => logContent.value.split('\n'))

interface FormattedEntry {
  raw: string
  text?: string
  time?: string
  badge?: string
  badgeClass?: string
  levelClass?: string
}

const formattedEntries = computed((): FormattedEntry[] => {
  const lines = logContent.value.split('\n')
  return lines.map((raw) => formatLogLine(raw.trim()))
})

function formatLogLine(line: string): FormattedEntry {
  const raw = line
  if (!line) return { raw, text: ' ', levelClass: 'border-transparent' }

  // 尝试解析 JSON 行
  if (line.startsWith('{')) {
    try {
      const obj = JSON.parse(line) as Record<string, unknown>
      // 优先 event_time（通常是本地时间），否则用 log_time（ISO 需转本地）
      const eventTime = obj.event_time as string
      const logTime = obj.log_time as string
      const datetime = obj.datetime as string
      const time = formatLogTime(
        eventTime && !eventTime.startsWith('1970-') ? eventTime : logTime || datetime
      )
      const level = String(obj.level || '').toUpperCase()
      const eventType = String(obj.event_type || '')
      const status = String(obj.status || '')
      const dataName = obj.data_name != null && obj.data_name !== '' ? String(obj.data_name) : ''
      const strategyName = String(obj.strategy_name || '')
      const accountMasked = obj.account_id_masked ? String(obj.account_id_masked) : ''
      const provider = obj.provider ? String(obj.provider) : ''
      const errorCode = obj.error_code ? String(obj.error_code) : ''
      const errorMsg = obj.error_msg ? String(obj.error_msg) : ''

      // 系统事件日志 (system.log)
      if (eventType) {
        const levelColors = {
          INFO: 'border-blue-400 bg-blue-50/50 dark:bg-blue-900/20',
          ERROR: 'border-red-400 bg-red-50/50 dark:bg-red-900/20',
          WARNING: 'border-amber-400 bg-amber-50/50 dark:bg-amber-900/20',
          DEBUG: 'border-slate-400 bg-slate-50/50 dark:bg-slate-800/30',
        }
        const badgeColors: Record<string, string> = {
          INFO: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200',
          ERROR: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200',
          WARNING: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200',
          DEBUG: 'bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300',
        }
        const levelClass = levelColors[level] || levelColors.INFO
        const badgeClass = badgeColors[level] || badgeColors.INFO
        const parts: string[] = [eventType]
        if (status) parts.push(`[${status}]`)
        if (dataName) parts.push(`品种:${dataName}`)
        if (strategyName) parts.push(`策略:${strategyName}`)
        if (provider) parts.push(`来源:${provider}`)
        if (accountMasked) parts.push(`账户:${accountMasked}`)
        if (errorCode) parts.push(`错误码:${errorCode}`)
        if (errorMsg) parts.push(`错误:${errorMsg}`)
        const details = obj.details as Record<string, unknown> | undefined
        if (details && Object.keys(details).length > 0) {
          const d = JSON.stringify(details)
          if (d !== '{}') parts.push(d)
        }
        return {
          raw: line,
          text: parts.join(' | '),
          time,
          badge: level || 'LOG',
          badgeClass,
          levelClass,
        }
      }

      // 持仓日志 (position.log)
      if (obj.data_name != null && obj.size != null) {
        const size = Number(obj.size)
        const price = Number(obj.price ?? 0)
        const value = Number(obj.value ?? 0)
        const text = `品种 ${dataName} | 数量 ${size} | 价格 ${price.toFixed(2)} | 市值 ${value}`
        return {
          raw: line,
          text,
          time,
          levelClass: 'border-emerald-400 bg-emerald-50/30 dark:bg-emerald-900/10',
        }
      }

      // 指标日志 (indicator.log) - 仅显示关键数据
      const close = obj.data_BtApiFeed_close ?? obj.dataprimary_BtApiFeed_close
      if (close != null) {
        const open = obj.data_BtApiFeed_open ?? obj.dataprimary_BtApiFeed_open
        const high = obj.data_BtApiFeed_high ?? obj.dataprimary_BtApiFeed_high
        const low = obj.data_BtApiFeed_low ?? obj.dataprimary_BtApiFeed_low
        const vol = obj.data_BtApiFeed_volume ?? obj.dataprimary_BtApiFeed_volume ?? 0
        const oi = obj.data_BtApiFeed_openinterest ?? obj.dataprimary_BtApiFeed_openinterest
        let text = `O:${Number(open).toFixed(1)} H:${Number(high).toFixed(1)} L:${Number(low).toFixed(1)} C:${Number(close).toFixed(1)}`
        if (Number(vol) > 0) text += ` V:${vol}`
        if (oi != null) text += ` OI:${oi}`
        return {
          raw: line,
          text: strategyName ? `[${strategyName}] ${text}` : text,
          time,
          levelClass: 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/30',
        }
      }

      // 其他 JSON：美化输出
      const keys = ['log_time', 'datetime', 'event_time', 'event_type', 'level', 'status', 'data_name']
      const parts: string[] = []
      for (const k of keys) {
        if (obj[k] != null && obj[k] !== '') {
          parts.push(`${k}: ${JSON.stringify(obj[k])}`)
        }
      }
      const rest = Object.entries(obj)
        .filter(([k]) => !keys.includes(k) && k !== 'details')
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
      const text = parts.length > 0 ? parts.join(' | ') : rest.slice(0, 5).join(' | ')
      return {
        raw: line,
        text: text || line.slice(0, 120) + (line.length > 120 ? '...' : ''),
        time,
        levelClass: 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/30',
      }
    } catch {
      // 解析失败，按原始显示
    }
  }

  // TSV 行：简单表格式展示
  if (line.includes('\t')) {
    const cols = line.split('\t')
    return {
      raw: line,
      text: cols.map((c, i) => `[${i}]: ${c}`).join('  |  '),
      levelClass: 'border-slate-300 dark:border-slate-600',
    }
  }

  return { raw: line }
}

function formatLogTime(s: string | undefined): string {
  if (!s) return ''
  // "1970-01-01" 表示无效时间，不显示
  if (s.startsWith('1970-01-01')) return ''
  try {
    // log_time 多为 UTC (如 "2026-03-10T05:57:20.264")，补 Z 后解析再转本地
    // event_time 多为本地 (如 "2026-03-10 13:57:18")，直接解析
    let toParse = s.trim()
    // 仅对带毫秒的 ISO（log_time 格式，通常为 UTC）补 Z；event_time 带空格无毫秒，已为本地
    if (/T\d{2}:\d{2}:\d{2}\.\d+$/.test(toParse)) {
      toParse = toParse + 'Z'
    }
    toParse = toParse.replace(' ', 'T')
    const date = new Date(toParse)
    if (Number.isNaN(date.getTime())) return s.slice(0, 19)
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    const h = String(date.getHours()).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    const sec = String(date.getSeconds()).padStart(2, '0')
    return `${y}-${m}-${d} ${h}:${min}:${sec}`
  } catch {
    return s.slice(0, 19)
  }
}

function lineMatchesSearch(line: string): boolean {
  if (!searchText.value.trim()) return false
  return line.toLowerCase().includes(searchText.value.toLowerCase())
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

async function loadFiles() {
  try {
    const res = await simulationApi.listLogs(props.instanceId)
    files.value = res.files
    if (files.value.length > 0 && !selectedFile.value) {
      selectedFile.value = files.value[0].name
      await loadLog()
    }
  } catch (e: unknown) {
    error.value = (e as Error).message || '加载文件列表失败'
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
      tailLines.value ?? undefined
    )
  } catch (e: unknown) {
    error.value = (e as Error).message || '加载日志失败'
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
