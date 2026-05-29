import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'

import i18n from '@/i18n'
import { workspaceApi } from '@/api/workspace'
import type { KBStrategyDraft } from '@/api/kbChat'
import type { WorkspaceReportCreateRequest, WorkspaceReportResponse } from '@/types/workspace'

function t(key: string, named?: Record<string, unknown>): string {
  return named ? i18n.global.t(key, named) : i18n.global.t(key)
}

export interface DraftReportAnalysis {
  summary: string
  verdict: string
  strengths: string[]
  risks: string[]
  suggestions: string[]
}

export interface DraftWorkspaceExecutionState {
  workspaceId: string
  workspaceName: string
  unitId: string
  strategyId: string
  runStatus: string
  lastTaskId: string | null
  report: WorkspaceReportResponse | null
  analysis: DraftReportAnalysis | null
}

interface ExecutionPayload {
  workspaceId: string
  workspaceName: string
  unitId: string
  strategyId: string
  runStatus?: string
  lastTaskId?: string | null
  report?: WorkspaceReportResponse | null
  analysis?: DraftReportAnalysis | null
}

export interface StrategyDraftWorkspaceExecutionApi {
  runUnits(workspaceId: string, unitIds: string[]): Promise<{
    results: Array<{ unit_id: string; task_id: string | null; status: string }>
  }>
  getUnitsStatus(workspaceId: string): Promise<
    Array<{ id: string; run_status: string; last_task_id: string | null }>
  >
  createReport(
    workspaceId: string,
    config: WorkspaceReportCreateRequest,
  ): Promise<WorkspaceReportResponse>
}

export interface StrategyDraftWorkspaceExecutionNotifier {
  success(message: string): void
  warning(message: string): void
  error(message: string): void
}

export interface StrategyDraftWorkspaceExecutionDeps {
  api?: StrategyDraftWorkspaceExecutionApi
  notifier?: StrategyDraftWorkspaceExecutionNotifier
}

const defaultNotifier: StrategyDraftWorkspaceExecutionNotifier = {
  success(message: string) {
    ElMessage.success(message)
  },
  warning(message: string) {
    ElMessage.warning(message)
  },
  error(message: string) {
    ElMessage.error(message)
  },
}

export function useStrategyDraftWorkspaceExecution(
  deps: StrategyDraftWorkspaceExecutionDeps = {},
) {
  const api = deps.api ?? workspaceApi
  const notifier = deps.notifier ?? defaultNotifier
  const workspaceExecutions = ref<Record<number, DraftWorkspaceExecutionState>>({})
  const runningBacktestIndex = ref<number | null>(null)
  const refreshingStatusIndex = ref<number | null>(null)
  const generatingReportIndex = ref<number | null>(null)
  const executionPollTimers = new Map<number, number>()

  function clearExecutionPolling(index: number) {
    const timer = executionPollTimers.get(index)
    if (timer !== undefined) {
      window.clearTimeout(timer)
      executionPollTimers.delete(index)
    }
  }

  function clearAllExecutionPolling() {
    executionPollTimers.forEach(timer => window.clearTimeout(timer))
    executionPollTimers.clear()
  }

  function buildReportConfigFromDraft(draft: KBStrategyDraft): WorkspaceReportCreateRequest {
    return {
      calc_method: draft.backtest_defaults.calc_method as 'simple' | 'compound',
      annual_days: draft.backtest_defaults.annual_days,
      weight_mode: draft.backtest_defaults.weight_mode as 'equal' | 'custom',
    }
  }

  function buildReportAnalysis(
    report: WorkspaceReportResponse,
    draft: KBStrategyDraft,
  ): DraftReportAnalysis {
    const summary = report.summary
    const avgReturn = summary.avg_total_return
    const sharpe = summary.avg_sharpe_ratio
    const maxDrawdown = summary.avg_max_drawdown
    const winRate = summary.avg_win_rate
    const totalTrades = summary.total_trades

    const strengths: string[] = []
    const risks: string[] = []
    const suggestions: string[] = []

    if (avgReturn != null && avgReturn > 0) {
      strengths.push(t('draftExec.analysisHasReturn', { value: avgReturn }))
    } else {
      risks.push(t('draftExec.analysisNoReturn'))
    }

    if (sharpe != null && sharpe >= 1) {
      strengths.push(t('draftExec.analysisHasSharpe', { value: sharpe }))
    } else {
      risks.push(t('draftExec.analysisNoSharpe'))
    }

    if (maxDrawdown != null && maxDrawdown <= -0.15) {
      risks.push(t('draftExec.analysisHighDrawdown', { value: maxDrawdown }))
    } else if (maxDrawdown != null) {
      strengths.push(t('draftExec.analysisOkDrawdown', { value: maxDrawdown }))
    }

    if (winRate != null && winRate >= 0.55) {
      strengths.push(t('draftExec.analysisHighWinRate', { value: winRate }))
    } else if (winRate != null) {
      risks.push(t('draftExec.analysisLowWinRate', { value: winRate }))
    }

    if (totalTrades != null && totalTrades < 5) {
      risks.push(t('draftExec.analysisFewTrades'))
    }

    suggestions.push(t('draftExec.suggestionMarketRegime'))
    suggestions.push(t('draftExec.suggestionParamSensitivity'))
    suggestions.push(...(Array.isArray(draft.next_steps) ? draft.next_steps.slice(0, 2) : []))

    const verdict =
      avgReturn != null &&
      avgReturn > 0 &&
      sharpe != null &&
      sharpe >= 1 &&
      (maxDrawdown ?? 0) > -0.2
        ? t('draftExec.verdictWorthOptimizing')
        : t('draftExec.verdictNeedsFix')

    const dash = t('draftExec.placeholderDash')
    return {
      summary: t('draftExec.summaryTpl', {
        name: draft.name,
        completed: summary.completed_units,
        total: summary.total_units,
        avgReturn: avgReturn ?? dash,
        sharpe: sharpe ?? dash,
        maxDrawdown: maxDrawdown ?? dash,
      }),
      verdict,
      strengths,
      risks: [...(Array.isArray(draft.risk_points) ? draft.risk_points.slice(0, 2) : []), ...risks],
      suggestions,
    }
  }

  function persistWorkspaceExecution(index: number, payload: ExecutionPayload) {
    workspaceExecutions.value = {
      ...workspaceExecutions.value,
      [index]: {
        workspaceId: payload.workspaceId,
        workspaceName: payload.workspaceName,
        unitId: payload.unitId,
        strategyId: payload.strategyId,
        runStatus: payload.runStatus ?? 'idle',
        lastTaskId: payload.lastTaskId ?? null,
        report: payload.report ?? null,
        analysis: payload.analysis ?? null,
      },
    }
  }

  function recordAddedExecution(index: number, payload: ExecutionPayload) {
    persistWorkspaceExecution(index, {
      ...payload,
      report: null,
      analysis: null,
    })
  }

  function recordBacktestExecution(index: number, payload: ExecutionPayload, draft: KBStrategyDraft) {
    persistWorkspaceExecution(index, {
      ...payload,
      analysis: payload.report ? buildReportAnalysis(payload.report, draft) : null,
    })
    if (payload.runStatus === 'running' || payload.runStatus === 'queued') {
      scheduleExecutionPolling(index, draft)
    }
  }

  function scheduleExecutionPolling(index: number, draft: KBStrategyDraft, delay = 3000) {
    clearExecutionPolling(index)
    const timer = window.setTimeout(() => {
      void refreshExecutionAndMaybeReport(index, draft, true)
    }, delay)
    executionPollTimers.set(index, timer)
  }

  async function refreshExecutionAndMaybeReport(index: number, draft: KBStrategyDraft, silent = false) {
    const execution = workspaceExecutions.value[index]
    if (!execution) {
      clearExecutionPolling(index)
      return
    }

    try {
      const statuses = await api.getUnitsStatus(execution.workspaceId)
      const status = statuses.find(item => item.id === execution.unitId)
      if (!status) {
        clearExecutionPolling(index)
        return
      }

      if (status.run_status === 'completed') {
        const report = await api.createReport(
          execution.workspaceId,
          buildReportConfigFromDraft(draft),
        )
        persistWorkspaceExecution(index, {
          ...execution,
          runStatus: status.run_status,
          lastTaskId: status.last_task_id,
          report,
          analysis: buildReportAnalysis(report, draft),
        })
        clearExecutionPolling(index)
        notifier.success(t('draftExec.msgRunCompleted'))
        return
      }

      persistWorkspaceExecution(index, {
        ...execution,
        runStatus: status.run_status,
        lastTaskId: status.last_task_id,
        report: execution.report,
        analysis: execution.analysis,
      })

      if (status.run_status === 'running' || status.run_status === 'queued') {
        scheduleExecutionPolling(index, draft)
        return
      }

      clearExecutionPolling(index)
      if (!silent && status.run_status === 'failed') {
        notifier.warning(t('draftExec.msgRunFailed'))
      }
    } catch {
      clearExecutionPolling(index)
      const currentExecution = workspaceExecutions.value[index]
      if (currentExecution) {
        persistWorkspaceExecution(index, {
          ...currentExecution,
          runStatus: currentExecution.runStatus === 'running'
            ? 'status_unknown'
            : currentExecution.runStatus,
        })
      }
      if (silent) {
        notifier.warning(t('draftExec.msgRefreshFailedSilent'))
      } else {
        notifier.error(t('draftExec.msgRefreshFailedActive'))
      }
    }
  }

  async function runExecution(index: number, draft: KBStrategyDraft) {
    const execution = workspaceExecutions.value[index]
    if (!execution) {
      notifier.warning(t('draftExec.msgAddToWorkspaceFirst'))
      return
    }
    runningBacktestIndex.value = index
    try {
      const response = await api.runUnits(execution.workspaceId, [execution.unitId])
      const runResult = response.results[0]
      recordBacktestExecution(
        index,
        {
          ...execution,
          runStatus: runResult?.status ?? 'failed',
          lastTaskId: runResult?.task_id ?? null,
          report: null,
        },
        draft,
      )
      notifier.success(t('draftExec.msgRunSubmitted'))
    } catch {
      notifier.error(t('draftExec.msgRunSubmitFailed'))
    } finally {
      runningBacktestIndex.value = null
    }
  }

  async function refreshExecution(index: number, draft: KBStrategyDraft) {
    refreshingStatusIndex.value = index
    try {
      await refreshExecutionAndMaybeReport(index, draft)
    } finally {
      refreshingStatusIndex.value = null
    }
  }

  async function generateReport(index: number, draft: KBStrategyDraft) {
    const execution = workspaceExecutions.value[index]
    if (!execution) {
      notifier.warning(t('draftExec.msgAddToWorkspaceFirst'))
      return
    }
    generatingReportIndex.value = index
    try {
      const statuses = await api.getUnitsStatus(execution.workspaceId)
      const status = statuses.find(item => item.id === execution.unitId)
      if (!status || status.run_status !== 'completed') {
        persistWorkspaceExecution(index, {
          ...execution,
          runStatus: status?.run_status ?? execution.runStatus,
          lastTaskId: status?.last_task_id ?? execution.lastTaskId,
          report: execution.report,
          analysis: execution.analysis,
        })
        notifier.warning(t('draftExec.msgRunNotComplete'))
        return
      }
      const report = await api.createReport(
        execution.workspaceId,
        buildReportConfigFromDraft(draft),
      )
      persistWorkspaceExecution(index, {
        ...execution,
        runStatus: status.run_status,
        lastTaskId: status.last_task_id,
        report,
        analysis: buildReportAnalysis(report, draft),
      })
      notifier.success(t('draftExec.msgReportGenerated'))
    } catch {
      notifier.error(t('draftExec.msgReportFailed'))
    } finally {
      generatingReportIndex.value = null
    }
  }

  function resetExecutions() {
    clearAllExecutionPolling()
    workspaceExecutions.value = {}
    runningBacktestIndex.value = null
    refreshingStatusIndex.value = null
    generatingReportIndex.value = null
  }

  onBeforeUnmount(() => {
    clearAllExecutionPolling()
  })

  return {
    workspaceExecutions,
    runningBacktestIndex,
    refreshingStatusIndex,
    generatingReportIndex,
    buildReportConfigFromDraft,
    recordAddedExecution,
    recordBacktestExecution,
    runExecution,
    refreshExecution,
    generateReport,
    resetExecutions,
  }
}
