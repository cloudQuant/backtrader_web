<template>
  <section class="strategy-draft">
    <div class="draft-head">
      <div>
        <div class="draft-title">
          {{ draft.name }}
        </div>
        <div class="draft-meta">
          {{ draft.category || t('aiChat.uncategorized') }}
          / {{ t('aiChat.paramCount', { n: getDraftParamCount(draft) }) }}
          <span v-if="draft.suggested_timeframe">
            / {{ draft.suggested_timeframe }}
          </span>
        </div>
      </div>
      <div class="draft-actions">
        <el-button
          type="primary"
          size="small"
          :disabled="saving || saved || Boolean(draftIssue)"
          @click="emit('save')"
        >
          <el-icon aria-hidden="true"><Document /></el-icon>
          {{ saved ? t('aiChat.savedToCenter') : saving ? t('aiChat.saving') : t('aiChat.saveAsStrategy') }}
        </el-button>
        <el-button
          size="small"
          :disabled="added || Boolean(draftIssue)"
          @click="emit('addToWorkspace')"
        >
          <el-icon aria-hidden="true"><Aim /></el-icon>
          {{ added ? t('aiChat.addedToWorkspace') : t('aiChat.addToWorkspace') }}
        </el-button>
        <el-button
          v-if="execution"
          size="small"
          :disabled="runningBacktest || Boolean(draftIssue)"
          @click="emit('runBacktest')"
        >
          <el-icon aria-hidden="true"><Promotion /></el-icon>
          {{ runningBacktest ? t('aiChat.backtestSubmitting') : t('aiChat.runOneClickBacktest') }}
        </el-button>
        <el-button
          v-if="execution"
          size="small"
          :disabled="refreshingStatus"
          @click="emit('refreshExecution')"
        >
          <el-icon aria-hidden="true"><Refresh /></el-icon>
          {{ refreshingStatus ? t('aiChat.refreshing') : t('aiChat.refreshStatus') }}
        </el-button>
        <el-button
          v-if="execution"
          size="small"
          :disabled="generatingReport || Boolean(draftIssue)"
          @click="emit('generateReport')"
        >
          <el-icon aria-hidden="true"><DataAnalysis /></el-icon>
          {{ generatingReport ? t('aiChat.generatingReport') : t('aiChat.generateReport') }}
        </el-button>
        <el-button
          size="small"
          @click="emit('copyCode')"
        >
          <el-icon aria-hidden="true"><CopyDocument /></el-icon>
          {{ t('aiChat.copyCode') }}
        </el-button>
      </div>
    </div>

    <p
      v-if="draft.rationale"
      class="draft-rationale"
    >
      {{ draft.rationale }}
    </p>

    <p
      v-if="draftIssue"
      class="draft-warning"
    >
      {{ draftIssue }}
    </p>

    <div class="draft-stats">
      <span>{{ t('aiChat.dataSourcePrefix') }} {{ getDraftDataSourceType(draft) }}</span>
      <span>{{ t('aiChat.timeframePrefix') }} {{ getDraftTimeframe(draft) }}</span>
      <span>{{ t('aiChat.cashPrefix') }} {{ getDraftInitialCash(draft) }}</span>
      <span>{{ t('aiChat.commissionPrefix') }} {{ getDraftCommission(draft) }}</span>
    </div>

    <div
      v-if="getDraftAssumptions(draft).length"
      class="draft-list"
    >
      <div class="draft-list-title">
        <el-icon aria-hidden="true"><CircleCheck /></el-icon>
        {{ t('aiChat.keyAssumptions') }}
      </div>
      <div
        v-for="item in getDraftAssumptions(draft)"
        :key="item"
      >
        {{ item }}
      </div>
    </div>

    <div
      v-if="getDraftRiskPoints(draft).length"
      class="draft-list warning"
    >
      <div class="draft-list-title">
        <el-icon aria-hidden="true"><Warning /></el-icon>
        {{ t('aiChat.riskNotes') }}
      </div>
      <div
        v-for="item in getDraftRiskPoints(draft)"
        :key="item"
      >
        {{ item }}
      </div>
    </div>

    <div
      v-if="execution"
      class="execution-box"
    >
      <div class="execution-title">
        {{ t('aiChat.workspaceExecState') }}
      </div>
      <div>{{ t('aiChat.workspaceLabelInline') }}: {{ execution.workspaceName }}</div>
      <div>{{ t('aiChat.unitIdLabel') }}: {{ execution.unitId }}</div>
      <div>{{ t('aiChat.runStatusLabel') }}: {{ execution.runStatus || t('aiChat.notRunning') }}</div>
      <div v-if="execution.lastTaskId">
        {{ t('aiChat.taskIdLabel') }}: {{ execution.lastTaskId }}
      </div>
      <div
        v-if="execution.report"
        class="report-box"
      >
        <div class="execution-title">
          {{ t('aiChat.latestReportSummary') }}
        </div>
        <div>
          {{ t('aiChat.completedUnits') }}:
          {{ execution.report?.summary.completed_units }}
          / {{ execution.report?.summary.total_units }}
        </div>
        <div>{{ t('aiChat.avgReturn') }}: {{ execution.report?.summary.avg_total_return ?? '-' }}</div>
        <div>{{ t('aiChat.avgSharpe') }}: {{ execution.report?.summary.avg_sharpe_ratio ?? '-' }}</div>
        <div>{{ t('aiChat.avgDrawdown') }}: {{ execution.report?.summary.avg_max_drawdown ?? '-' }}</div>
      </div>
      <div
        v-if="execution.analysis"
        class="analysis-box"
      >
        <div class="execution-title">
          {{ t('aiChat.aiReviewSuggestions') }}
        </div>
        <div>{{ execution.analysis?.summary }}</div>
        <div class="mt-2 font-medium">
          {{ execution.analysis?.verdict }}
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Aim,
  CircleCheck,
  CopyDocument,
  DataAnalysis,
  Document,
  Promotion,
  Refresh,
  Warning,
} from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import type { KBStrategyDraft } from '@/api/kbChat'
import type { DraftWorkspaceExecutionState } from '@/composables/useStrategyDraftWorkspaceExecution'
import {
  getDraftAssumptions,
  getDraftCommission,
  getDraftDataSourceType,
  getDraftInitialCash,
  getDraftParamCount,
  getDraftRiskPoints,
  getDraftTimeframe,
  getStrategyDraftIssue,
} from '@/composables/useAIChatRendering'

const { t } = useI18n()

const props = defineProps<{
  draft: KBStrategyDraft
  saving: boolean
  saved: boolean
  added: boolean
  runningBacktest: boolean
  refreshingStatus: boolean
  generatingReport: boolean
  execution?: DraftWorkspaceExecutionState
}>()

const emit = defineEmits<{
  save: []
  addToWorkspace: []
  runBacktest: []
  refreshExecution: []
  generateReport: []
  copyCode: []
}>()

const draftIssue = computed(() => getStrategyDraftIssue(props.draft))
</script>

<style scoped lang="scss">
.strategy-draft,
.execution-box {
  margin-top: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 12px;
}

.strategy-draft {
  border-color: color-mix(in srgb, var(--success-color) 44%, var(--border-color) 56%);
  background: color-mix(in srgb, var(--bg-color) 84%, var(--success-color) 16%);
}

.draft-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.draft-title {
  font-weight: 700;
  color: var(--success-text-strong);
}

.draft-meta,
.draft-rationale,
.draft-list,
.execution-box {
  margin-top: 6px;
  color: var(--success-text-color);
  font-size: 12px;
  line-height: 1.6;
}

.draft-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.draft-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.draft-stats span {
  border: 1px solid color-mix(in srgb, var(--success-color) 36%, var(--border-color) 64%);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 8px;
  color: var(--success-text-strong);
  font-size: 12px;
}

.draft-list {
  border: 1px solid color-mix(in srgb, var(--success-color) 36%, var(--border-color) 64%);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 9px;
}

.draft-list.warning {
  border-color: color-mix(in srgb, var(--warning-color) 44%, var(--border-color) 56%);
  background: color-mix(in srgb, var(--bg-color) 84%, var(--warning-color) 16%);
  color: var(--warning-text-color);
}

.draft-warning {
  margin-top: 8px;
  border: 1px solid color-mix(in srgb, var(--warning-color) 44%, var(--border-color) 56%);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 84%, var(--warning-color) 16%);
  padding: 8px 10px;
  color: var(--warning-text-color);
  font-size: 12px;
  line-height: 1.6;
}

.draft-list-title,
.execution-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
  font-weight: 700;
}

.report-box,
.analysis-box {
  margin-top: 10px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 38%, var(--border-color) 62%);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 84%, var(--primary-color) 16%);
  padding: 10px;
  color: var(--text-color-primary);
}
</style>
