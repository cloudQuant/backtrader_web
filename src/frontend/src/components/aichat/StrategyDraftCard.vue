<template>
  <section class="strategy-draft">
    <div class="draft-head">
      <div>
        <div class="draft-title">
          {{ draft.name }}
        </div>
        <div class="draft-meta">
          {{ draft.category || '未分类' }}
          / {{ getDraftParamCount(draft) }} 个参数
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
          <el-icon><Document /></el-icon>
          {{ saved ? '已保存到策略中心' : saving ? '保存中...' : '保存为策略' }}
        </el-button>
        <el-button
          size="small"
          :disabled="added || Boolean(draftIssue)"
          @click="emit('addToWorkspace')"
        >
          <el-icon><Aim /></el-icon>
          {{ added ? '已添加到工作区' : '添加到工作区' }}
        </el-button>
        <el-button
          v-if="execution"
          size="small"
          :disabled="runningBacktest || Boolean(draftIssue)"
          @click="emit('runBacktest')"
        >
          <el-icon><Promotion /></el-icon>
          {{ runningBacktest ? '回测提交中...' : '一键回测' }}
        </el-button>
        <el-button
          v-if="execution"
          size="small"
          :disabled="refreshingStatus"
          @click="emit('refreshExecution')"
        >
          <el-icon><Refresh /></el-icon>
          {{ refreshingStatus ? '刷新中...' : '刷新状态' }}
        </el-button>
        <el-button
          v-if="execution"
          size="small"
          :disabled="generatingReport || Boolean(draftIssue)"
          @click="emit('generateReport')"
        >
          <el-icon><DataAnalysis /></el-icon>
          {{ generatingReport ? '生成中...' : '生成报告' }}
        </el-button>
        <el-button
          size="small"
          @click="emit('copyCode')"
        >
          <el-icon><CopyDocument /></el-icon>
          复制代码
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
      <span>数据源 {{ getDraftDataSourceType(draft) }}</span>
      <span>周期 {{ getDraftTimeframe(draft) }}</span>
      <span>资金 {{ getDraftInitialCash(draft) }}</span>
      <span>手续费 {{ getDraftCommission(draft) }}</span>
    </div>

    <div
      v-if="getDraftAssumptions(draft).length"
      class="draft-list"
    >
      <div class="draft-list-title">
        <el-icon><CircleCheck /></el-icon>
        关键假设
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
        <el-icon><Warning /></el-icon>
        风险提示
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
        工作区执行状态
      </div>
      <div>工作区：{{ execution.workspaceName }}</div>
      <div>单元ID：{{ execution.unitId }}</div>
      <div>回测状态：{{ execution.runStatus || '未运行' }}</div>
      <div v-if="execution.lastTaskId">
        任务ID：{{ execution.lastTaskId }}
      </div>
      <div
        v-if="execution.report"
        class="report-box"
      >
        <div class="execution-title">
          最新报告摘要
        </div>
        <div>
          完成单元：
          {{ execution.report?.summary.completed_units }}
          / {{ execution.report?.summary.total_units }}
        </div>
        <div>平均收益：{{ execution.report?.summary.avg_total_return ?? '-' }}</div>
        <div>平均夏普：{{ execution.report?.summary.avg_sharpe_ratio ?? '-' }}</div>
        <div>平均回撤：{{ execution.report?.summary.avg_max_drawdown ?? '-' }}</div>
      </div>
      <div
        v-if="execution.analysis"
        class="analysis-box"
      >
        <div class="execution-title">
          AI复盘建议
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
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  padding: 12px;
}

.strategy-draft {
  border-color: var(--success-border-color);
  background: var(--success-surface);
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
  border: 1px solid var(--success-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  padding: 8px;
  color: var(--success-text-strong);
  font-size: 12px;
}

.draft-list {
  border: 1px solid var(--success-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--bg-color-card);
  padding: 9px;
}

.draft-list.warning {
  border-color: var(--warning-border-color);
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

.draft-warning {
  margin-top: 8px;
  border: 1px solid var(--warning-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--warning-surface);
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
  border: 1px solid var(--info-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--info-surface);
  padding: 10px;
  color: var(--info-text-color);
}
</style>
