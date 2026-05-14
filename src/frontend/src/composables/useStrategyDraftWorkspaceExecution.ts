import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { workspaceApi } from '@/api/workspace'
import type { KBStrategyDraft } from '@/api/kbChat'
import type { WorkspaceReportCreateRequest, WorkspaceReportResponse } from '@/types/workspace'

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
      strengths.push(`组合平均收益为 ${avgReturn}，策略具备继续研究价值。`)
    } else {
      risks.push('当前组合平均收益未体现明显正向优势，需要先确认核心信号是否有效。')
    }

    if (sharpe != null && sharpe >= 1) {
      strengths.push(`平均夏普为 ${sharpe}，风险调整后收益具备一定可用性。`)
    } else {
      risks.push('平均夏普偏低，说明收益质量仍需提升。')
    }

    if (maxDrawdown != null && maxDrawdown <= -0.15) {
      risks.push(`平均最大回撤为 ${maxDrawdown}，资金回撤压力偏大。`)
    } else if (maxDrawdown != null) {
      strengths.push(`平均最大回撤为 ${maxDrawdown}，回撤控制相对可接受。`)
    }

    if (winRate != null && winRate >= 0.55) {
      strengths.push(`平均胜率为 ${winRate}，信号命中率尚可。`)
    } else if (winRate != null) {
      risks.push(`平均胜率为 ${winRate}，需要优化入场与退出质量。`)
    }

    if (totalTrades != null && totalTrades < 5) {
      risks.push('交易次数偏少，当前样本不足以支撑稳定结论。')
    }

    suggestions.push('优先检查收益主要来自哪一类市场环境，避免只在单一行情下成立。')
    suggestions.push('围绕止损、仓位和退出规则做一轮参数敏感性分析。')
    suggestions.push(...(Array.isArray(draft.next_steps) ? draft.next_steps.slice(0, 2) : []))

    const verdict =
      avgReturn != null &&
      avgReturn > 0 &&
      sharpe != null &&
      sharpe >= 1 &&
      (maxDrawdown ?? 0) > -0.2
        ? '这版策略已经具备继续优化并扩大样本验证的价值。'
        : '这版策略更适合作为研究草案，需要先修正收益质量或回撤问题。'

    return {
      summary: `策略 ${draft.name} 已完成工作区回测汇总。完成单元 ${summary.completed_units}/${summary.total_units}，当前重点指标为平均收益 ${avgReturn ?? '-'}、平均夏普 ${sharpe ?? '-'}、平均回撤 ${maxDrawdown ?? '-'}。`,
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
        notifier.success('回测完成，报告已自动生成')
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
        notifier.warning('回测任务执行失败，未自动生成报告')
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
        notifier.warning('自动刷新回测状态失败，可稍后手动刷新')
      } else {
        notifier.error('自动刷新回测状态失败，请稍后手动刷新')
      }
    }
  }

  async function runExecution(index: number, draft: KBStrategyDraft) {
    const execution = workspaceExecutions.value[index]
    if (!execution) {
      notifier.warning('请先把策略添加到工作区')
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
      notifier.success('回测任务已提交')
    } catch {
      notifier.error('回测提交失败，请稍后重试')
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
      notifier.warning('请先把策略添加到工作区')
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
        notifier.warning('回测尚未完成，请先刷新状态或稍后再试')
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
      notifier.success('工作区报告已生成')
    } catch {
      notifier.error('生成报告失败，请稍后重试')
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
