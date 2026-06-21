<template>
  <section class="stock-task-card">
    <div class="task-head">
      <div>
        <div class="task-title">
          {{ displayTask.symbol }} {{ t('aiChat.stockAnalysisTask') }}
        </div>
        <div class="task-meta">
          {{ t('aiChat.taskStatusLabel') }}: {{ displayTask.status }}
          <span v-if="displayTask.current_step">/ {{ displayTask.current_step }}</span>
        </div>
      </div>
      <el-tag
        size="small"
        :type="statusTagType"
      >
        {{ displayTask.progress }}%
      </el-tag>
    </div>

    <el-progress
      :percentage="displayTask.progress"
      :stroke-width="8"
    />

    <p
      v-if="displayTask.message || displayTask.error_message"
      class="task-message"
    >
      {{ displayTask.error_message || displayTask.message }}
    </p>

    <div
      v-if="canCancel || canRetry"
      class="task-actions"
    >
      <el-button
        v-if="canRetry"
        size="small"
        type="primary"
        :loading="retrying"
        @click="retryTask"
      >
        {{ t('aiChat.stockRetryTask') }}
      </el-button>
      <el-button
        v-if="canCancel"
        size="small"
        :loading="cancelling"
        @click="cancelTask"
      >
        {{ t('aiChat.stockCancelTask') }}
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import type { KBStockAnalysisReport, KBStockAnalysisTask } from '@/api/kbChat'
import {
  stockAnalysisApi,
  type StockAnalysisResult,
  type StockAnalysisTask,
} from '@/api/stockAnalysis'
import {
  isStockAnalysisTerminalStatus,
  useStockAnalysisTask,
} from '@/composables/useStockAnalysisTask'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  task: KBStockAnalysisTask
  autoPoll?: boolean
}>(), {
  autoPoll: true,
})

const emit = defineEmits<{
  taskUpdated: [task: StockAnalysisTask]
  resultLoaded: [report: KBStockAnalysisReport]
}>()

const {
  task: polledTask,
  result,
  startPolling,
  stopPolling,
} = useStockAnalysisTask(props.task.task_id)
const cancelling = ref(false)
const retrying = ref(false)

type DisplayStockTask = KBStockAnalysisTask & { error_message?: string | null }

const displayTask = computed<DisplayStockTask>(() => {
  const nextTask = polledTask.value
  if (!nextTask) return props.task
  return {
    task_id: nextTask.task_id,
    symbol: nextTask.symbol,
    status: nextTask.status,
    progress: nextTask.progress,
    current_step: nextTask.current_step,
    message: nextTask.message,
    error_message: nextTask.error_message,
  }
})

const statusTagType = computed(() => {
  if (displayTask.value.status === 'completed') return 'success'
  if (displayTask.value.status === 'failed' || displayTask.value.status === 'cancelled') return 'danger'
  return 'warning'
})

const canCancel = computed(() => !isStockAnalysisTerminalStatus(displayTask.value.status))
const canRetry = computed(() => displayTask.value.status === 'failed')

function buildReportCard(taskResult: StockAnalysisResult): KBStockAnalysisReport | null {
  const report = taskResult.report
  if (!report || typeof report !== 'object') return null
  const meta = (report.meta ?? {}) as Record<string, unknown>
  const decision = (report.decision ?? {}) as Record<string, unknown>
  const summary = typeof report.executive_summary === 'string'
    ? report.executive_summary
    : ''
  return {
    report_id: taskResult.report_id ?? '',
    symbol: String(meta.symbol ?? displayTask.value.symbol),
    summary,
    decision_label: String(decision.label ?? '持有'),
    risk_level: String(decision.risk_level ?? '中等'),
    confidence_score: typeof decision.confidence_score === 'number'
      ? decision.confidence_score
      : null,
    export_formats: ['markdown', 'html', 'docx', 'pdf'],
  }
}

async function cancelTask() {
  cancelling.value = true
  try {
    const cancelledTask = await stockAnalysisApi.cancelTask(props.task.task_id)
    polledTask.value = cancelledTask
    stopPolling()
    emit('taskUpdated', cancelledTask)
    ElMessage.success(t('aiChat.stockTaskCancelled'))
  } catch {
    ElMessage.error(t('aiChat.stockCancelTaskFailed'))
  } finally {
    cancelling.value = false
  }
}

async function retryTask() {
  retrying.value = true
  try {
    const retriedTask = await stockAnalysisApi.retryTask(props.task.task_id)
    polledTask.value = retriedTask
    emit('taskUpdated', retriedTask)
    ElMessage.success(t('aiChat.stockTaskRetried'))
  } catch {
    ElMessage.error(t('aiChat.stockRetryTaskFailed'))
  } finally {
    retrying.value = false
  }
}

watch(polledTask, (nextTask) => {
  if (nextTask) {
    emit('taskUpdated', nextTask)
  }
})

watch(result, (nextResult) => {
  if (!nextResult) return
  const reportCard = buildReportCard(nextResult)
  if (reportCard?.report_id) {
    emit('resultLoaded', reportCard)
  }
})

onMounted(() => {
  if (props.autoPoll && !isStockAnalysisTerminalStatus(props.task.status)) {
    startPolling()
    return
  }
  stopPolling()
})
</script>

<style scoped lang="scss">
.stock-task-card {
  margin-top: 12px;
  border: 1px solid var(--info-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--info-surface);
  padding: 12px;
}

.task-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.task-title {
  font-weight: 700;
  color: var(--info-text-strong);
}

.task-meta,
.task-message {
  margin-top: 6px;
  color: var(--info-text-color);
  font-size: 13px;
  line-height: 1.65;
}

.task-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}
</style>
