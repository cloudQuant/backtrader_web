<template>
  <section class="stock-analysis-card">
    <div class="stock-head">
      <div>
        <div class="stock-title">
          {{ report.symbol }} {{ t('aiChat.stockAnalysisReport') }}
        </div>
        <div class="stock-meta">
          {{ t('aiChat.stockDecision') }}: {{ report.decision_label }}
          / {{ t('aiChat.stockRiskLevel') }}: {{ report.risk_level }}
          <span v-if="typeof report.confidence_score === 'number'">
            / {{ t('aiChat.stockConfidence') }}: {{ Math.round(report.confidence_score * 100) }}%
          </span>
        </div>
      </div>
      <el-tag
        size="small"
        type="success"
      >
        {{ t('aiChat.stockCompat') }}
      </el-tag>
    </div>

    <p class="stock-summary">
      {{ report.summary }}
    </p>

    <div
      v-if="task"
      class="stock-task"
    >
      <span>{{ t('aiChat.taskStatusLabel') }}: {{ task.status }}</span>
      <el-progress
        :percentage="task.progress"
        :stroke-width="8"
      />
      <small>{{ task.message || task.current_step }}</small>
    </div>

    <div class="stock-actions">
      <el-button
        size="small"
        @click="emit('continueStrategyIdea', buildStrategyIdeaPrompt())"
      >
        <el-icon><MagicStick /></el-icon>
        {{ t('aiChat.stockContinueStrategyIdea') }}
      </el-button>
      <el-button
        size="small"
        @click="emit('continueBacktraderStrategy', buildBacktraderPrompt())"
      >
        <el-icon><Cpu /></el-icon>
        {{ t('aiChat.stockContinueBacktrader') }}
      </el-button>
      <el-button
        v-if="knowledgeBaseId"
        size="small"
        type="primary"
        :loading="saving"
        @click="saveToKnowledgeBase"
      >
        <el-icon><Collection /></el-icon>
        {{ t('aiChat.stockSaveToKb') }}
      </el-button>
      <el-button
        size="small"
        :loading="loadingWorkspaces"
        @click="openWorkspaceDialog"
      >
        <el-icon><FolderOpened /></el-icon>
        {{ t('aiChat.stockSaveToWorkspace') }}
      </el-button>
      <el-button
        v-for="format in report.export_formats"
        :key="format"
        size="small"
        :loading="exporting === format"
        @click="download(format)"
      >
        <el-icon><Download /></el-icon>
        {{ format.toUpperCase() }}
      </el-button>
    </div>

    <el-dialog
      v-model="workspaceDialogVisible"
      :title="t('aiChat.stockWorkspaceDialogTitle')"
      width="420px"
    >
      <div class="workspace-save-form">
        <label>
          <span>{{ t('aiChat.stockSelectWorkspace') }}</span>
          <el-select
            v-model="selectedWorkspaceId"
            class="w-full"
            :placeholder="t('aiChat.stockSelectWorkspace')"
          >
            <el-option
              v-for="workspace in workspaces"
              :key="workspace.id"
              :label="workspace.name"
              :value="workspace.id"
            />
          </el-select>
        </label>
        <label>
          <span>{{ t('aiChat.stockWorkspaceTitle') }}</span>
          <el-input
            v-model="workspaceTitle"
            :placeholder="defaultReportTitle()"
          />
        </label>
        <p
          v-if="workspaces.length === 0"
          class="workspace-empty"
        >
          {{ t('aiChat.stockNoWorkspace') }}
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="workspaceDialogVisible = false">
            {{ t('aiChat.cancel') }}
          </el-button>
          <el-button
            type="primary"
            :loading="savingWorkspace"
            :disabled="!selectedWorkspaceId"
            @click="saveToWorkspace"
          >
            {{ t('aiChat.confirmAdd') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Collection, Cpu, Download, FolderOpened, MagicStick } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import { stockAnalysisApi, type StockAnalysisExportFormat } from '@/api/stockAnalysis'
import { workspaceApi } from '@/api/workspace'
import type { KBStockAnalysisReport, KBStockAnalysisTask } from '@/api/kbChat'
import type { Workspace } from '@/types/workspace'

const { t } = useI18n()

const props = defineProps<{
  task?: KBStockAnalysisTask | null
  report: KBStockAnalysisReport
  knowledgeBaseId?: string | null
}>()

const emit = defineEmits<{
  continueStrategyIdea: [prompt: string]
  continueBacktraderStrategy: [prompt: string]
}>()

const exporting = ref<StockAnalysisExportFormat | null>(null)
const saving = ref(false)
const loadingWorkspaces = ref(false)
const savingWorkspace = ref(false)
const workspaceDialogVisible = ref(false)
const workspaces = ref<Workspace[]>([])
const selectedWorkspaceId = ref('')
const workspaceTitle = ref('')

function defaultReportTitle(): string {
  return `${props.report.symbol} ${t('aiChat.stockAnalysisReport')}`
}

function buildReportContext(): string {
  const confidence = typeof props.report.confidence_score === 'number'
    ? `，置信度 ${Math.round(props.report.confidence_score * 100)}%`
    : ''
  return `${props.report.symbol} 股票分析报告，倾向：${props.report.decision_label}，风险等级：${props.report.risk_level}${confidence}。报告摘要：${props.report.summary}`
}

function buildStrategyIdeaPrompt(): string {
  return `基于 ${buildReportContext()}。请生成一个可验证的量化策略构思，包含交易假设、入场条件、出场条件、仓位与止损风控、所需数据、回测验证步骤和主要风险。`
}

function buildBacktraderPrompt(): string {
  return `基于 ${buildReportContext()}。请生成一个 Backtrader 策略草案，包含策略名称、适用周期、核心指标、参数表、完整策略代码、默认回测参数、接入 AI for Investor 研究工作区的建议，以及需要进一步验证的风险点。`
}

async function download(format: StockAnalysisExportFormat) {
  exporting.value = format
  try {
    const payload = await stockAnalysisApi.exportReport(props.report.report_id, format)
    const blob = payload instanceof Blob ? payload : new Blob([payload])
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.report.symbol}_stock_analysis.${format === 'markdown' ? 'md' : format}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success(t('aiChat.stockExportStarted'))
  } catch {
    ElMessage.error(t('aiChat.stockExportFailed'))
  } finally {
    exporting.value = null
  }
}

async function saveToKnowledgeBase() {
  if (!props.knowledgeBaseId) return
  saving.value = true
  try {
    await stockAnalysisApi.saveToKnowledgeBase(
      props.report.report_id,
      props.knowledgeBaseId,
      `${props.report.symbol} ${t('aiChat.stockAnalysisReport')}`,
    )
    ElMessage.success(t('aiChat.stockSavedToKb'))
  } catch {
    ElMessage.error(t('aiChat.stockSaveToKbFailed'))
  } finally {
    saving.value = false
  }
}

async function openWorkspaceDialog() {
  loadingWorkspaces.value = true
  try {
    const payload = await workspaceApi.list(0, 100, 'research')
    workspaces.value = payload.items
    selectedWorkspaceId.value = payload.items[0]?.id ?? ''
    workspaceTitle.value = workspaceTitle.value || defaultReportTitle()
    workspaceDialogVisible.value = true
    if (payload.items.length === 0) {
      ElMessage.warning(t('aiChat.stockNoWorkspace'))
    }
  } catch {
    ElMessage.error(t('aiChat.stockLoadWorkspaceFailed'))
  } finally {
    loadingWorkspaces.value = false
  }
}

async function saveToWorkspace() {
  if (!selectedWorkspaceId.value) {
    ElMessage.warning(t('aiChat.stockSelectWorkspace'))
    return
  }
  savingWorkspace.value = true
  try {
    await stockAnalysisApi.saveToWorkspace(
      props.report.report_id,
      selectedWorkspaceId.value,
      workspaceTitle.value || defaultReportTitle(),
    )
    ElMessage.success(t('aiChat.stockSavedToWorkspace'))
    workspaceDialogVisible.value = false
  } catch {
    ElMessage.error(t('aiChat.stockSaveToWorkspaceFailed'))
  } finally {
    savingWorkspace.value = false
  }
}
</script>

<style scoped lang="scss">
.stock-analysis-card {
  margin-top: 12px;
  border: 1px solid var(--info-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--info-surface);
  padding: 12px;
}

.stock-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.stock-title {
  font-weight: 700;
  color: var(--info-text-strong);
}

.stock-meta,
.stock-summary,
.stock-task {
  margin-top: 6px;
  color: var(--info-text-color);
  font-size: 13px;
  line-height: 1.65;
}

.stock-task {
  display: grid;
  gap: 6px;
}

.stock-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.workspace-save-form {
  display: grid;
  gap: 12px;
}

.workspace-save-form label {
  display: grid;
  gap: 6px;
  color: var(--info-text-color);
  font-size: 13px;
}

.workspace-empty {
  margin: 0;
  color: var(--el-color-warning);
  font-size: 13px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
