/** State, side effects, and actions for the strategy management page. */

import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '@/stores/strategy'
import { marketDataApi } from '@/api/marketData'
import { strategyApi } from '@/api/strategy'
import { stripStrategyMeta } from '@/constants/strategy'
import type { ParamSpec, Strategy, StrategyTemplate } from '@/types'
import type {
  AIStrategyLiveReadinessItem,
  AIStrategyLiveHandoffApprovalRequest,
  AIStrategyLiveHandoffPackage,
  AIStrategyLiveTradingPrepare,
  AIStrategyGateGap,
  AIStrategyIterationProgress,
  AIStrategyOutOfSampleValidation,
  AIStrategyPaperReviewLock,
  AIStrategyPaperMonitoringRule,
  AIStrategyPaperTradingRuleEvaluation,
  AIStrategyPaperTradingStart,
  AIStrategyPaperTradingReview,
  AIStrategyPipelineSummary,
  AIStrategyPipelineStep,
  AIStrategyPromotionAuditItem,
  AIStrategyQualityGateEvaluation,
  AIStrategyResearchConfigProfile,
  AIStrategyResearchRunRequest,
  AIStrategyResearchRunRecord,
  AIStrategyResearchRunResponse,
  AIStrategyResearchIteration,
  AIStrategyResearchTaskResponse,
  AIStrategyResearchVersion,
  AIStrategyResearchVersionCompareResponse,
  InvestmentMandateResponse,
  ResearchPipelineEvent,
} from '@/api/strategy'
import type { DataPrecheckResponse } from '@/types/trust'
import type { Workspace, StrategyUnit, TradingSnapshot, UnitStatusResponse } from '@/types/workspace'

export function useStrategyPage() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const strategyStore = useStrategyStore()

  // ---- State ----
  const isInvestmentStrategyResearchRoute = computed(() =>
    String(route.path || '').startsWith('/investment/strategies')
  )
  const showAIResearchTab = computed(() => isInvestmentStrategyResearchRoute.value)
  const showStrategyManagementTabs = computed(() => !isInvestmentStrategyResearchRoute.value)
  const activeTab = ref(showAIResearchTab.value ? 'aiResearch' : 'gallery')
  const searchKeyword = ref('')
  const categoryFilter = ref('')

  const dialogVisible = ref(false)
  const viewDialogVisible = ref(false)
  const detailVisible = ref(false)
  const isEdit = ref(false)
  const saving = ref(false)
  const editingId = ref('')
  const currentStrategy = ref<Strategy | null>(null)

  const detailTemplate = ref<StrategyTemplate | null>(null)
  const detailTab = ref('readme')
  const readmeContent = ref('')
  const readmeLoading = ref(false)
  const aiResearchRunning = ref(false)
  const aiResearchResult = ref<AIStrategyResearchRunResponse | null>(null)
  const aiResearchRunsLoading = ref(false)
  const aiResearchRuns = ref<AIStrategyResearchRunRecord[]>([])
  const AI_RESEARCH_RUNS_AUTO_REFRESH_MS = 30_000
  let aiResearchRunsAutoRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let aiResearchRunsAutoRefreshActive = false
  const aiResearchTaskId = ref('')
  const aiResearchTaskStatus = ref('')
  const aiResearchTaskStage = ref('')
  const aiResearchTaskProgress = ref(0)
  const aiResearchTaskIteration = ref<number | null>(null)
  const aiResearchBacktestTaskId = ref('')
  const aiResearchCancelledBacktestTaskId = ref('')
  const aiResearchTaskPaperWorkspaceId = ref('')
  const aiResearchTaskPaperUnitId = ref('')
  const aiResearchTaskPaperStarted = ref(false)
  const aiResearchTaskLiveWorkspaceId = ref('')
  const aiResearchTaskLiveUnitId = ref('')
  const aiResearchTaskLivePrepared = ref(false)
  const aiResearchTaskPipeline = ref<AIStrategyPipelineSummary | null>(null)
  const aiResearchTaskRequestSnapshot = ref<Record<string, unknown> | null>(null)
  const aiResearchTaskContinuedFromRunId = ref('')
  const aiResearchTaskContinuationSource = ref('')
  const aiResearchTaskContinuationContext = ref<Record<string, unknown>>({})
  const aiResearchTaskError = ref('')
  const aiResearchTaskMessage = ref('')
  const aiResearchTaskLatestIteration = ref<Record<string, unknown> | null>(null)
  const aiResearchTaskBestIteration = ref<Record<string, unknown> | null>(null)
  const aiResearchTaskAssetSpecs = ref<Record<string, Record<string, unknown>>>({})
  const aiResearchTaskBacktestEnvironment = ref<Record<string, unknown>>({})
  const aiResearchTaskPromotionAudit = ref<AIStrategyPromotionAuditItem[]>([])
  const aiResearchCancelling = ref(false)
  const aiResearchCancelRequested = ref(false)
  const aiResearchPaperStartingRunId = ref('')
  const aiResearchPaperReviewingRunId = ref('')
  const aiResearchLiveHandoffLoadingRunId = ref('')
  const aiResearchStrategyViewingRunId = ref('')
  const aiResearchPaperReviews = reactive<Record<string, AIStrategyPaperTradingReview>>({})
  const aiResearchLiveHandoffs = reactive<Record<string, AIStrategyLiveHandoffPackage>>({})
  const aiResearchLiveHandoffApprovingRunId = ref('')
  const aiResearchLiveTradingPreparingRunId = ref('')
  const aiResearchConfigDialogVisible = ref(false)
  const aiResearchConfigProfiles = ref<AIStrategyResearchConfigProfile[]>([])
  const aiResearchConfigProfilesLoading = ref(false)
  const aiResearchConfigProfileSaving = ref(false)
  const aiResearchConfigProfileImporting = ref(false)
  const aiResearchConfigProfileDeletingId = ref('')
  const aiResearchSelectedConfigProfileId = ref('')
  const aiResearchConfigProfileName = ref('')
  const aiResearchConfigProfileDescription = ref('')
  const aiResearchConfigProfileFilePath = ref('')
  const aiResearchConfigProfileFileInput = ref<HTMLInputElement | null>(null)
  const aiResearchMandate = ref<InvestmentMandateResponse | null>(null)
  const aiResearchMandateConfirmed = ref(false)
  const aiResearchMandateLoading = ref(false)
  const aiResearchTimeline = ref<ResearchPipelineEvent[]>([])
  const aiResearchTimelineLoading = ref(false)
  const aiResearchVersions = ref<AIStrategyResearchVersion[]>([])
  const aiResearchVersionsLoading = ref(false)
  const aiResearchVersionCompare = ref<AIStrategyResearchVersionCompareResponse | null>(null)
  const aiResearchVersionCompareLoading = ref(false)
  const aiResearchSelectedVersionIds = ref<string[]>([])
  const aiResearchVersionComparisonRows = computed(() => {
    const comparison = aiResearchVersionCompare.value
    if (!comparison) return []
    const rows: Array<{
      scope: 'metric' | 'gate'
      key: string
      label: string
      left: string
      right: string
      delta: string
      operator: string
      passed: boolean | null
    }> = []
    const append = (scope: 'metric' | 'gate', payload: Record<string, unknown>) => {
      for (const [key, value] of Object.entries(payload)) {
        const item = value && typeof value === 'object' ? value as Record<string, unknown> : {}
        const passed = typeof item.passed === 'boolean' ? item.passed : null
        rows.push({
          scope,
          key,
          label: String(item.label || (scope === 'metric' ? aiResearchVersionMetricLabel(key) : key)),
          left: formatComparisonValue(item.left),
          right: formatComparisonValue(item.right),
          delta: formatComparisonValue(item.delta),
          operator: String(item.operator || '—'),
          passed,
        })
      }
    }
    append('metric', comparison.metric_deltas || {})
    append('gate', comparison.gate_deltas || {})
    return rows
  })
  const aiResearchPrecheckLoading = ref(false)
  const aiResearchPrecheckResult = ref<DataPrecheckResponse | null>(null)
  const aiResearchPrecheckError = ref('')
  const AI_RESEARCH_PRECHECK_DEBOUNCE_MS = 350
  let aiResearchPrecheckTimer: ReturnType<typeof setTimeout> | null = null
  let aiResearchPrecheckController: AbortController | null = null
  let aiResearchPrecheckSequence = 0

  const AI_RESEARCH_STAGE_LABELS: Record<string, string> = {
    queued: '排队中',
    starting: '启动中',
    running: '运行中',
    initializing: '初始化',
    workspace_ready: '工作区已就绪',
    configuration_invalid: '配置无效',
    strategy_idea: '策略构思',
    drafting: '生成策略脚本',
    draft: '策略生成',
    draft_generation_failed: '脚本生成失败',
    repairing_code: '修复策略脚本',
    backtesting: '运行回测',
    backtest_loop: '策略回测',
    backtest_failed: '回测失败',
    backtest_submission_failed: '回测提交失败',
    backtest_timeout: '回测超时',
    strategy_review: '策略审查',
    optimization_loop: '策略优化',
    improving: '改进策略',
    validating: '样本外验证',
    robustness_validation: '稳健性验证',
    robustness_failed: '稳健性失败',
    evaluating: '评估策略',
    quality_achieved: '质量达标',
    paper_trading: '模拟交易',
    paper_trading_failed: '模拟启动失败',
    paper_review: '模拟复核',
    live_candidate: '实盘候选',
    live_handoff: '实盘交接',
    live_trading_prepare: '实盘准备',
    research_iteration: '投研迭代',
    interrupted: '任务中断',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    timeout: '超时',
  }

  const AI_RESEARCH_RUN_STATUS_LABELS: Record<string, string> = {
    achieved: '已达标',
    completed: '已完成',
    failed: '未达标',
    interrupted: '任务中断',
    cancelled: '已取消',
    timeout: '超时',
    backtest_submission_failed: '回测提交失败',
    configuration_invalid: '配置无效',
  }

  const AI_RESEARCH_PAPER_REVIEW_STATUS_LABELS: Record<string, string> = {
    ready_for_live_candidate: '实盘候选',
    live_readiness_expired: '实盘候选已过期',
    monitoring: '继续观察',
    needs_research_review: '需要重新投研',
    paper_workspace_missing: '模拟工作区缺失',
    paper_unit_missing: '模拟单元缺失',
    monitoring_plan_missing: '监控计划缺失',
  }

  const AI_RESEARCH_PAPER_RULE_STATUS_LABELS: Record<string, string> = {
    passed: '已通过',
    pending: '继续观察',
    failed: '未通过',
  }

  const AI_RESEARCH_LIVE_READINESS_STATUS_LABELS: Record<string, string> = {
    passed: '已通过',
    pending: '待确认',
    pending_manual_confirmation: '待人工确认',
    skipped: '已跳过',
    expired: '已过期',
    failed: '未通过',
  }

  const AI_RESEARCH_LIVE_HANDOFF_STATUS_LABELS: Record<string, string> = {
    ready_for_approval: '可提交审批',
    blocked: '存在阻塞',
    approved_for_live: '已批准实盘',
    approval_rejected: '审批驳回',
  }

  const AI_RESEARCH_PIPELINE_STEP_STATUS_LABELS: Record<string, string> = {
    pending: '待执行',
    running: '进行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    skipped: '已跳过',
  }

  type AIResearchWorkflowMode = NonNullable<AIStrategyResearchRunRequest['workflow_mode']>

  const AI_RESEARCH_WORKFLOW_STEPS: NonNullable<AIStrategyResearchRunRequest['workflow_steps']> = [
    'ideation',
    'generation',
    'backtest',
    'review',
    'optimization',
  ]

  function todayIsoDate() {
    return new Date().toISOString().slice(0, 10)
  }

  const DEFAULT_AI_RESEARCH_START_DATE = '2020-01-01'
  const DEFAULT_AI_RESEARCH_END_DATE = todayIsoDate()
  const DEFAULT_AI_RESEARCH_MIN_PAPER_TRADING_DAYS = 7
  const PAPER_GATEWAY_CONFIG_PLACEHOLDER = '{"name":"paper_gateway","params":{}}'
  const LIVE_GATEWAY_CONFIG_PLACEHOLDER = '{"name":"ctp_live","params":{}}'

  class AIResearchConfigError extends Error {
    constructor(message: string) {
      super(message)
      this.name = 'AIResearchConfigError'
    }
  }

  const AI_RESEARCH_CONFIG_ERROR_MESSAGES = new Set([
    '模拟网关配置必须是合法 JSON',
    '模拟网关配置必须是 JSON 对象',
    '模拟网关配置包含脱敏凭据，请重新输入真实网关配置',
    '实盘网关配置必须是合法 JSON',
    '实盘网关配置必须是 JSON 对象',
    '实盘网关配置包含脱敏凭据，请重新输入真实网关配置',
  ])

  const form = reactive({
    name: '',
    description: '',
    code: '',
    category: 'custom',
  })

  const aiResearchForm = reactive({
    prompt: '',
    workflow_mode: 'auto' as AIResearchWorkflowMode,
    symbol: '000001.SZ',
    symbol_name: '',
    timeframe: '1d',
    timeframe_n: 1,
    start_date: DEFAULT_AI_RESEARCH_START_DATE,
    end_date: DEFAULT_AI_RESEARCH_END_DATE,
    knowledge_base_id: '',
    thinking_mode: false,
    target_sharpe: 1.0,
    min_total_trades: 1,
    use_max_drawdown_limit: false,
    max_drawdown_limit: 20,
    use_min_total_return: false,
    min_total_return: 0,
    use_min_annual_return: false,
    min_annual_return: 0,
    use_min_win_rate: false,
    min_win_rate: 50,
    max_iterations: 3,
    out_of_sample_validation: true,
    require_out_of_sample_validation: true,
    out_of_sample_ratio_pct: 25,
    use_min_out_of_sample_sharpe: false,
    min_out_of_sample_sharpe: 0.6,
    use_min_out_of_sample_trades: false,
    min_out_of_sample_trades: 1,
    robustness_validation: false,
    require_robustness_validation: false,
    robustness_methods: ['monte_carlo'] as string[],
    min_robustness_score: 55,
    robustness_monte_carlo_iterations: 300,
    robustness_random_seed: null as number | null,
    initial_cash: 100000,
    use_manual_commission: false,
    commission: 0.001,
    annual_days: 252,
    calc_method: 'simple',
    weight_mode: 'equal',
    group_name: '',
    backtest_timeout_seconds: 600,
    poll_interval_seconds: 2,
    research_workspace_id: '',
    seed_strategy_id: '',
    continue_from_run_id: '',
    continuation_source: '',
    start_paper_trading: true,
    min_paper_trading_days: DEFAULT_AI_RESEARCH_MIN_PAPER_TRADING_DAYS,
    paper_workspace_name: '',
    trading_workspace_id: '',
    gateway_config_json: '',
    live_workspace_name: '',
    live_trading_workspace_id: '',
    live_gateway_config_json: '',
  })

  const aiResearchHeroSteps = computed(() => [
    { key: 'idea', index: '01', label: t('strategy.aiResearchHeroStepIdea') },
    { key: 'code', index: '02', label: t('strategy.aiResearchHeroStepCode') },
    { key: 'backtest', index: '03', label: t('strategy.aiResearchHeroStepBacktest') },
    { key: 'review', index: '04', label: t('strategy.aiResearchHeroStepReview') },
    { key: 'optimize', index: '05', label: t('strategy.aiResearchHeroStepOptimize') },
  ])

  const aiResearchHeroMetrics = computed(() => [
    {
      key: 'workflow',
      label: t('strategy.aiResearchHeroWorkflow'),
      value: aiResearchForm.workflow_mode === 'auto'
        ? t('strategy.aiResearchWorkflowAuto')
        : t('strategy.aiResearchWorkflowPrompt'),
    },
    {
      key: 'target',
      label: t('strategy.aiResearchHeroTarget'),
      value: formatMetric(aiResearchForm.target_sharpe),
    },
    {
      key: 'iterations',
      label: t('strategy.aiResearchHeroIterations'),
      value: formatMetric(aiResearchForm.max_iterations, 0),
    },
    {
      key: 'validation',
      label: t('strategy.aiResearchHeroValidation'),
      value: aiResearchForm.out_of_sample_validation
        ? aiResearchForm.robustness_validation
          ? `${formatMetric(aiResearchForm.out_of_sample_ratio_pct, 0)}% / R${formatMetric(aiResearchForm.min_robustness_score, 0)}`
          : `${formatMetric(aiResearchForm.out_of_sample_ratio_pct, 0)}%`
        : t('common.disable'),
    },
  ])

  const aiResearchPrecheckTagType = computed(() => {
    if (aiResearchPrecheckError.value) return 'danger'
    const status = aiResearchPrecheckResult.value?.status
    if (status === 'pass') return 'success'
    if (status === 'failed') return 'danger'
    if (status === 'warning') return 'warning'
    return 'info'
  })

  const aiResearchPrecheckSummary = computed(() => {
    if (aiResearchPrecheckError.value) return aiResearchPrecheckError.value
    const result = aiResearchPrecheckResult.value
    if (!result) return '未预检'
    const issueCount = (result.reasons?.length || 0) + (result.warnings?.length || 0)
    const label = result.passed ? '预检通过' : '预检未通过'
    return issueCount ? `${label} · ${issueCount} 项` : label
  })

  // ---- Computed ----
  const strategies = computed(() => strategyStore.strategies)
  const templates = computed(() => strategyStore.templates)
  const loading = computed(() => strategyStore.loading)

  const filteredTemplates = computed(() => {
    let list = templates.value
    if (categoryFilter.value) {
      list = list.filter(t => t.category === categoryFilter.value)
    }
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      list = list.filter(t =>
        t.name.toLowerCase().includes(kw) ||
        t.description.toLowerCase().includes(kw) ||
        t.id.toLowerCase().includes(kw)
      )
    }
    return list
  })

  const displayedTemplates = computed(() => filteredTemplates.value)
  const aiResearchSelectedConfigProfile = computed(() =>
    aiResearchConfigProfiles.value.find(
      profile => profile.id === aiResearchSelectedConfigProfileId.value
    ) ?? null
  )
  const aiResearchSelectedProfileSummary = computed(() => {
    const profile = aiResearchSelectedConfigProfile.value
    if (!profile) return '未选择方案'
    const parts = [
      aiResearchConfigProfileValue(profile, 'symbol'),
      aiResearchConfigProfileValue(profile, 'timeframe'),
      `Sharpe ${aiResearchConfigProfileMetric(profile, 'target_sharpe')}`,
      `最多 ${aiResearchConfigProfileMetric(profile, 'max_iterations', 0)} 轮`,
    ].filter(part => part && !String(part).includes('-'))
    return parts.length ? parts.join(' · ') : profile.name
  })
  const aiResearchSelectedConfigDetails = computed(() => {
    const profile = aiResearchSelectedConfigProfile.value
    if (!profile) return []
    const config = profile.config
    const symbol = stringFromUnknown(config.symbol, '-')
    const symbolName = stringFromUnknown(config.symbol_name).trim()
    const timeframe = stringFromUnknown(config.timeframe, '-')
    const timeframeN = optionalNumber(config.timeframe_n)
    const startDate = stringFromUnknown(config.start_date, '-')
    const endDate = stringFromUnknown(config.end_date, '最新')
    const targetSharpe = aiResearchConfigProfileMetric(profile, 'target_sharpe')
    const minTrades = aiResearchConfigProfileMetric(profile, 'min_total_trades', 0)
    const oosRatio = aiResearchConfigProfileOos(profile)
    const oosSharpe = optionalBoolean(config.use_min_out_of_sample_sharpe, false)
      ? aiResearchConfigProfileMetric(profile, 'min_out_of_sample_sharpe')
      : '不限制'
    const initialCash = aiResearchConfigProfileMetric(profile, 'initial_cash', 0)
    const commission = aiResearchConfigProfileMetric(profile, 'commission', 6)
    const workflowMode = stringFromUnknown(config.workflow_mode) === 'prompt' ? '按提示执行' : '自动规划'
    return [
      {
        label: t('strategy.aiResearchSymbol'),
        value: symbolName ? `${symbol} · ${symbolName}` : symbol,
      },
      {
        label: t('strategy.aiResearchTimeframe'),
        value: timeframeN && timeframeN !== 1 ? `${timeframeN}${timeframe}` : timeframe,
      },
      {
        label: t('strategy.aiResearchPeriod'),
        value: `${startDate} 至 ${endDate}`,
      },
      {
        label: t('strategy.aiResearchQualityGates'),
        value: `Sharpe ${targetSharpe} · 交易 ${minTrades}`,
      },
      {
        label: t('strategy.aiResearchOutOfSample'),
        value: `${oosRatio} · Sharpe ${oosSharpe}`,
      },
      {
        label: t('strategy.aiResearchCapitalAndFees'),
        value: `${initialCash} · ${commission}`,
      },
      {
        label: t('strategy.aiResearchMaxIterations'),
        value: aiResearchConfigProfileMetric(profile, 'max_iterations', 0),
      },
      {
        label: t('strategy.aiResearchHeroWorkflow'),
        value: workflowMode,
      },
    ]
  })
  const aiResearchSelectedConfigPromptPreview = computed(() => {
    const profile = aiResearchSelectedConfigProfile.value
    if (!profile) return ''
    const prompt = stringFromUnknown(profile.config.prompt).trim().replace(/\n{3,}/g, '\n\n')
    if (!prompt) return ''
    return prompt.length > 900 ? `${prompt.slice(0, 900)}...` : prompt
  })
  const aiResearchVisibleRuns = computed(() => {
    const profile = aiResearchSelectedConfigProfile.value
    if (!profile) return aiResearchRuns.value
    return aiResearchRuns.value.filter(record => aiResearchRunMatchesConfigProfile(record, profile))
  })
  const aiResearchNoResultDescription = computed(() => {
    const profile = aiResearchSelectedConfigProfile.value
    if (!profile) return t('strategy.aiResearchNoResult')
    return `${profile.name} 暂无投研结果，运行该方案后会在这里显示。`
  })
  const aiResearchMandateDetails = computed(() => {
    const mandate = aiResearchMandate.value
    if (!mandate) return []
    const goal = mandate.structured_goal || {}
    const asset = mandate.asset_scope || {}
    return [
      { key: 'asset', label: t('strategy.aiResearchAsset'), value: stringFromUnknown(asset.asset_class, '-') },
      { key: 'symbol', label: t('strategy.aiResearchSymbol'), value: stringFromUnknown(asset.symbol, '-') },
      { key: 'timeframe', label: t('strategy.aiResearchTimeframe'), value: mandate.timeframe || stringFromUnknown(goal.timeframe, '-') },
      { key: 'objective', label: t('strategy.aiResearchObjective'), value: mandate.objective || stringFromUnknown(goal.objective, '-') },
      {
        key: 'risk',
        label: t('strategy.aiResearchRiskConstraints'),
        value: Object.keys(mandate.risk_constraints || {}).length
          ? Object.keys(mandate.risk_constraints).join('、')
          : '未显式约束',
      },
      {
        key: 'gates',
        label: t('strategy.aiResearchQualityGates'),
        value: mandateQualityGateSummary(mandate.quality_gates),
      },
    ]
  })
  const aiResearchCanCompareVersions = computed(() => aiResearchSelectedVersionIds.value.length === 2)
  const aiResearchVersionMetricKeys = computed(() => {
    const keys = new Set<string>()
    aiResearchVersions.value.forEach(version => {
      Object.keys(version.backtest_metrics || {}).forEach(key => {
        if (['sharpe_ratio', 'sharpe', 'total_return', 'annual_return', 'max_drawdown', 'total_trades'].includes(key)) {
          keys.add(key)
        }
      })
    })
    return [...keys]
  })
  const strategyCategoryCount = computed(() =>
    new Set(templates.value.map((template) => template.category || 'custom')).size
  )
  const strategyManagementStats = computed(() => [
    {
      key: 'templates',
      label: t('strategy.metricTemplates'),
      value: templates.value.length,
    },
    {
      key: 'owned',
      label: t('strategy.metricMyStrategies'),
      value: strategies.value.length,
    },
    {
      key: 'filtered',
      label: t('strategy.metricFiltered'),
      value: filteredTemplates.value.length,
    },
    {
      key: 'categories',
      label: t('strategy.metricCategories'),
      value: strategyCategoryCount.value,
    },
  ])

  const aiBestSharpe = computed(() => {
    const metrics = aiResearchResult.value?.best_metrics
    const raw = metrics?.sharpe_ratio ?? metrics?.sharpe ?? null
    if (typeof raw === 'number') return raw
    if (typeof raw === 'string' && raw.trim()) return Number(raw)
    const bestIteration = aiResearchResult.value?.iterations.find(
      item => item.iteration === aiResearchResult.value?.best_iteration
    )
    return bestIteration?.sharpe_ratio ?? null
  })

  const aiResearchNextActions = computed(() => aiResearchResult.value?.next_actions ?? [])
  const aiResearchBestDiagnostics = computed(() => {
    const diagnostics = aiResearchResult.value?.best_diagnostics
    if (!diagnostics) return null
    const summary = String(diagnostics.summary || '').trim()
    const failureCategories = diagnostics.failure_categories ?? []
    const strengths = diagnostics.strengths ?? []
    const weaknesses = diagnostics.weaknesses ?? []
    const improvementPlan = diagnostics.improvement_plan ?? []
    const diagnosticsPayload = diagnostics as Record<string, unknown>
    const gateGaps = gateGapListFromUnknown(diagnosticsPayload.gate_gaps).slice(0, 4)
    const generationText = strategyGenerationText(diagnosticsPayload.strategy_generation)
    const promotionReady = typeof diagnostics.promotion_ready === 'boolean'
      ? diagnostics.promotion_ready
      : null
    if (
      !summary
      && !failureCategories.length
      && !strengths.length
      && !weaknesses.length
      && !gateGaps.length
      && !improvementPlan.length
      && !generationText
      && promotionReady === null
    ) {
      return null
    }
    return {
      summary,
      failureCategories,
      strengths,
      weaknesses,
      gateGaps,
      improvementPlan,
      generationText,
      promotionReady,
    }
  })
  const aiResearchPipelineSteps = computed<AIStrategyPipelineStep[]>(() => {
    const pipeline = aiResearchResult.value?.pipeline
    if (!pipeline) return []
    if (pipeline.steps?.length) return pipeline.steps
    if (!pipeline.current_stage) return []
    return [
      {
        key: pipeline.current_stage,
        label: aiResearchStageLabel(pipeline.current_stage),
        status: pipeline.ready_for_live ? 'completed' : 'running',
        error: pipeline.paper_trading_error,
      },
    ]
  })
  const aiResearchPromotionAudit = computed<AIStrategyPromotionAuditItem[]>(() =>
    promotionAuditFromPayload(
      aiResearchResult.value?.promotion_audit
        ?? aiResearchResult.value?.run_record?.promotion_audit
    )
  )
  const aiResearchCurrentPaperFailed = computed(() => {
    const pipeline = aiResearchResult.value?.pipeline
    return Boolean(
      pipeline?.current_stage === 'paper_trading_failed'
      || pipeline?.paper_trading_error
    )
  })
  const aiResearchCurrentPaperTargetMissing = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && isPaperTradingTargetMissing(record))
  })
  const aiResearchPaperStatusText = computed(() => {
    if (aiResearchCurrentPaperFailed.value) return '模拟启动失败'
    if (aiResearchCurrentPaperTargetMissing.value) return '模拟目标丢失'
    return aiResearchResult.value?.paper_trading?.started
      || aiResearchResult.value?.run_record?.paper_trading_started
      ? t('strategy.aiResearchPaperStarted')
      : t('strategy.aiResearchPaperNotStarted')
  })
  const aiResearchTaskStageLabel = computed(() =>
    aiResearchStageLabel(aiResearchTaskStage.value || aiResearchTaskStatus.value)
  )
  const aiResearchTaskContinuationSummary = computed(() => {
    const snapshot = aiResearchTaskRequestSnapshot.value ?? {}
    const context = Object.keys(aiResearchTaskContinuationContext.value).length
      ? aiResearchTaskContinuationContext.value
      : isRecord(snapshot.continuation_context)
        ? snapshot.continuation_context
        : {}
    const source = stringFromUnknown(
      aiResearchTaskContinuationSource.value,
      stringFromUnknown(context.source)
    )
    const parentRunId = stringFromUnknown(
      aiResearchTaskContinuedFromRunId.value,
      stringFromUnknown(snapshot.continue_from_run_id, stringFromUnknown(context.run_id))
    )
    if (!source && !parentRunId) return ''
    const label = continuationSourceLabel(source)
    return parentRunId ? `${label} · 上轮 ${parentRunId}` : label
  })
  const aiResearchTaskPaperStatusText = computed(() => {
    const error = String(aiResearchTaskPipeline.value?.paper_trading_error || '').trim()
    if (error) return `模拟失败 ${error}`
    if (aiResearchTaskPaperStarted.value) return '模拟已启动'
    if (aiResearchTaskPaperWorkspaceId.value || aiResearchTaskPaperUnitId.value) return '模拟已创建'
    return ''
  })
  const aiResearchTaskLiveStatusText = computed(() => {
    const pipeline = aiResearchTaskPipeline.value
    if (aiResearchTaskLivePrepared.value || pipeline?.live_trading_prepared) return '实盘已准备'
    if (
      aiResearchTaskLiveWorkspaceId.value
      || aiResearchTaskLiveUnitId.value
      || pipeline?.live_workspace_id
      || pipeline?.live_unit_id
    ) {
      return '实盘已创建'
    }
    return ''
  })
  const aiResearchTaskPipelineSteps = computed<AIStrategyPipelineStep[]>(() => {
    const pipeline = aiResearchTaskPipeline.value
    if (!pipeline) return []
    if (pipeline.steps?.length) return pipeline.steps
    if (!pipeline.current_stage) return []
    return [
      {
        key: pipeline.current_stage,
        label: aiResearchStageLabel(pipeline.current_stage),
        status: pipeline.ready_for_live ? 'completed' : 'running',
        error: pipeline.paper_trading_error,
      },
    ]
  })
  const aiResearchTaskLatestDiagnostics = computed(() =>
    taskLatestIterationDiagnostics(aiResearchTaskLatestIteration.value)
  )
  const aiResearchTaskBestIterationDisplay = computed(() => {
    const best = aiResearchTaskBestIteration.value
    if (!best) return null
    const latest = aiResearchTaskLatestIteration.value
    if (!latest) return best
    const bestIteration = optionalNumber(best.iteration)
    const latestIteration = optionalNumber(latest.iteration)
    if (bestIteration === null || latestIteration === null) return best
    return bestIteration === latestIteration ? null : best
  })
  const aiResearchContinuationEnabled = computed(() =>
    Boolean(aiResearchForm.seed_strategy_id || aiResearchForm.continue_from_run_id)
  )
  const aiResearchContinuationLabel = computed(() => {
    return continuationSourceLabel(aiResearchForm.continuation_source || '')
  })
  const aiResearchCurrentContinuationSummary = computed(() => {
    const record = aiResearchResult.value?.run_record
    return record ? continuationSummaryForRecord(record) : ''
  })
  const canCancelAIResearchTask = computed(() =>
    aiResearchRunning.value
    && Boolean(aiResearchTaskId.value)
    && typeof (strategyApi as { cancelAIResearchTask?: unknown }).cancelAIResearchTask === 'function'
  )
  const canContinueAIResearchTask = computed(() =>
    !aiResearchRunning.value
    && Boolean(aiResearchTaskId.value)
    && ['failed', 'cancelled'].includes(String(aiResearchTaskStatus.value || '').toLowerCase())
    && Boolean(
      (
        aiResearchResult.value?.run_record
        && (
          canContinueResearchFromRunRecord(aiResearchResult.value.run_record)
          || canContinueResearchFromPaperIssue(aiResearchResult.value.run_record)
        )
      )
      || aiResearchTaskBestIteration.value
      || aiResearchTaskLatestIteration.value
    )
    && typeof (strategyApi as { continueAIResearchTask?: unknown }).continueAIResearchTask === 'function'
  )
  const canRetryAIResearchTask = computed(() =>
    !aiResearchRunning.value
    && Boolean(aiResearchTaskId.value)
    && ['failed', 'cancelled'].includes(String(aiResearchTaskStatus.value || '').toLowerCase())
    && isRecord(aiResearchTaskRequestSnapshot.value)
    && !canContinueAIResearchTask.value
  )
  const canViewBestStrategyFromCurrentResult = computed(() =>
    Boolean(
      aiResearchResult.value?.best_strategy
      || (
        aiResearchResult.value?.run_record
        && bestStrategyIdForRecord(aiResearchResult.value.run_record)
      )
    )
  )
  const canStartPaperFromCurrentResult = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && canStartPaperFromRecord(record))
  })
  const canOpenPaperFromCurrentResult = computed(() =>
    Boolean(
      !(
        aiResearchResult.value?.run_record
        && isPaperTradingTargetMissing(aiResearchResult.value.run_record)
      )
      && (
        aiResearchResult.value?.paper_trading?.started
        || (
          aiResearchResult.value?.run_record?.paper_trading_started
          && aiResearchResult.value?.run_record?.paper_workspace_id
        )
      )
    )
  )
  const canReviewPaperFromCurrentResult = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && canReviewPaperFromRecord(record))
  })
  const canContinueResearchFromCurrentPaperReview = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && canContinueResearchFromPaperReview(record))
  })
  const canContinueResearchFromCurrentPaperIssue = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && canContinueResearchFromPaperIssue(record))
  })
  const canContinueResearchFromCurrentRunRecord = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && canContinueResearchFromRunRecord(record))
  })
  const aiResearchCurrentPaperReview = computed(() => {
    const result = aiResearchResult.value
    const record = result?.run_record
    if (!result || !record) return null
    return paperReviewForRecord(record)
  })
  const aiResearchCurrentPaperReviewLock = computed(() => {
    const record = aiResearchResult.value?.run_record
    return record ? paperReviewLockForRecord(record) : null
  })
  const canBuildLiveHandoffFromCurrentResult = computed(() => {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && canBuildLiveHandoffFromRecord(record))
  })
  const aiResearchCurrentLiveHandoff = computed(() => {
    const result = aiResearchResult.value
    if (!result) return null
    return result.run_record ? liveHandoffForRecord(result.run_record) : liveHandoffForRunId(result.run_id)
  })
  const aiResearchCurrentPaperEnvironment = computed(() => {
    const result = aiResearchResult.value
    if (!result) return []
    return paperEnvironmentItems(result.paper_trading?.handoff ?? result.run_record?.paper_handoff)
  })
  const aiResearchCurrentRuntimeEnvironment = computed(() => {
    const result = aiResearchResult.value
    if (!result) return []
    return researchRuntimeItems(
      result.run_record,
      result.paper_trading?.handoff ?? result.run_record?.paper_handoff ?? null
    )
  })
  const aiResearchBestGateEvaluations = computed(
    () => aiResearchResult.value?.best_quality_gate_evaluations ?? []
  )
  const aiResearchOutOfSampleValidation = computed(() => {
    const result = aiResearchResult.value
    if (!result) return null
    const handoffValidation = outOfSampleValidationFromHandoff(result.paper_trading?.handoff)
    if (handoffValidation) return handoffValidation
    const bestIteration = result.iterations.find(item => item.iteration === result.best_iteration)
      ?? result.iterations.find(item => item.passed)
      ?? result.iterations[result.iterations.length - 1]
    return bestIteration ? iterationOutOfSampleValidation(bestIteration) : null
  })

  const paramTableData = computed(() => {
    if (!detailTemplate.value) return []
    return Object.entries(detailTemplate.value.params).map(([name, spec]: [string, ParamSpec]) => ({
      name,
      default: spec.default ?? '-',
      type: spec.type ?? '-',
      description: spec.description ?? name,
    }))
  })

  // ---- Methods ----
  async function openTemplateDetail(t: StrategyTemplate) {
    detailTemplate.value = t
    detailTab.value = 'readme'
    detailVisible.value = true
    readmeContent.value = ''
    readmeLoading.value = true
    try {
      const res = await strategyApi.getTemplateReadme(t.id)
      readmeContent.value = res.content ?? ''
    } catch {
      readmeContent.value = ''
    } finally {
      readmeLoading.value = false
    }
  }

  function goBacktest(t: StrategyTemplate) {
    detailVisible.value = false
    router.push({ path: '/backtest/legacy', query: { strategy: t.id } })
  }

  function formatMetric(value: unknown, digits = 2) {
    if (value === null || value === undefined || value === '') return '-'
    const number = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(number)) return '-'
    return number.toFixed(digits)
  }

  function formatComparisonValue(value: unknown): string {
    if (typeof value === 'string' && value.trim()) return value
    return formatMetric(value)
  }

  function gateGapListFromUnknown(value: unknown): AIStrategyGateGap[] {
    if (!Array.isArray(value)) return []
    return value
      .filter(isRecord)
      .map(item => ({
        key: stringFromUnknown(item.key),
        label: stringFromUnknown(item.label),
        actual: optionalNumber(item.actual),
        target: optionalNumber(item.target),
        direction: stringFromUnknown(item.direction),
        gap: optionalNumber(item.gap),
        gap_ratio: optionalNumber(item.gap_ratio),
        distance_to_pass: optionalNumber(item.distance_to_pass),
        score: optionalNumber(item.score),
        status: stringFromUnknown(item.status),
      }))
      .filter(item => item.key || item.label)
  }

  function gateGapText(gap: AIStrategyGateGap) {
    const label = gap.label || gap.key || '质量门槛'
    const distance = gap.distance_to_pass ?? gap.gap
    const parts = [label]
    if (distance !== null && distance !== undefined) {
      parts.push(`还差 ${formatMetric(distance)}`)
    } else if (gap.status === 'unavailable') {
      parts.push('缺少指标')
    }
    const actual = gap.actual !== null && gap.actual !== undefined
      ? `当前 ${formatMetric(gap.actual)}`
      : ''
    const target = gap.target !== null && gap.target !== undefined
      ? `目标 ${formatMetric(gap.target)}`
      : ''
    const ratio = gap.gap_ratio !== null && gap.gap_ratio !== undefined
      ? `差距 ${formatMetric(Number(gap.gap_ratio) * 100, 0)}%`
      : ''
    return [parts.join(' '), actual, target, ratio].filter(Boolean).join('，')
  }

  function formatTaskProgress(value: unknown) {
    const number = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(number) || number <= 0) return ''
    return `${Math.round(number)}%`
  }

  function taskLatestIterationLabel(iteration: Record<string, unknown>) {
    const number = taskLatestIterationMetric(iteration, 'iteration')
    return number === null ? '一轮' : `第 ${formatMetric(number, 0)} 轮`
  }

  function taskLatestIterationMetric(
    iteration: Record<string, unknown>,
    ...keys: string[]
  ) {
    for (const key of keys) {
      const value = optionalNumber(iteration[key])
      if (value !== null) return value
    }
    const metrics = iteration.metrics
    if (isRecord(metrics)) {
      for (const key of keys) {
        const value = optionalNumber(metrics[key])
        if (value !== null) return value
      }
    }
    return null
  }

  function taskLatestIterationProgress(iteration: Record<string, unknown> | null) {
    if (!iteration) return null
    const diagnostics = isRecord(iteration.diagnostics) ? iteration.diagnostics : {}
    const progress = isRecord(diagnostics.iteration_progress)
      ? diagnostics.iteration_progress
      : iteration.iteration_progress
    return isRecord(progress) ? progress as AIStrategyIterationProgress : null
  }

  function taskLatestIterationDiagnostics(iteration: Record<string, unknown> | null) {
    if (!iteration) return null
    const diagnostics = isRecord(iteration.diagnostics) ? iteration.diagnostics : {}
    const summary = stringFromUnknown(diagnostics.summary)
    const failures = uniqueTextItems([
      stringFromUnknown(iteration.failure_reason),
      ...stringArrayFromUnknown(iteration.quality_gate_failures),
      ...stringArrayFromUnknown(iteration.validation_failures),
      ...stringArrayFromUnknown(diagnostics.weaknesses),
    ]).slice(0, 4)
    const improvementPlan = uniqueTextItems([
      ...stringArrayFromUnknown(iteration.improvement_plan),
      ...stringArrayFromUnknown(diagnostics.improvement_plan),
    ]).slice(0, 4)
    const gateGaps = gateGapListFromUnknown(diagnostics.gate_gaps).slice(0, 3)
    const nextActions = uniqueTextItems(stringArrayFromUnknown(iteration.next_actions)).slice(0, 3)
    const generationText = strategyGenerationText(diagnostics.strategy_generation)
    if (
      !summary
      && !failures.length
      && !gateGaps.length
      && !improvementPlan.length
      && !nextActions.length
      && !generationText
    ) {
      return null
    }
    return {
      summary,
      failures,
      gateGaps,
      improvementPlan,
      nextActions,
      generationText,
    }
  }

  function strategyGenerationText(value: unknown) {
    if (!isRecord(value)) return ''
    const source = stringFromUnknown(value.source)
    const model = stringFromUnknown(value.model_id)
    const provider = stringFromUnknown(value.provider)
    const fallbackReason = stringFromUnknown(value.fallback_reason)
    const sourceLabel: Record<string, string> = {
      ai_initial_draft: 'AI初稿',
      ai_model: 'AI改稿',
      local_rules: '本地规则改稿',
      local_fallback: '本地回退改稿',
      local_initial_fallback: '本地初稿回退',
      local_code_repair_fallback: '本地代码修复',
      seed_strategy: '种子策略',
      continued_run_seed: '历史记录种子',
      local_seed: '本地种子',
    }
    const label = sourceLabel[source] || source || '草案来源'
    const parts = [label]
    if (model) parts.push(`模型 ${model}`)
    else if (provider && provider !== 'local') parts.push(provider)
    if (fallbackReason) parts.push(`回退 ${fallbackReason}`)
    return parts.join(' · ')
  }

  function formatDateTime(value: string | null | undefined) {
    if (!value) return '-'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleString()
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
  }

  function containsRedactedSecret(value: unknown): boolean {
    if (typeof value === 'string') return value.trim() === '***'
    if (Array.isArray(value)) return value.some(item => containsRedactedSecret(item))
    if (!isRecord(value)) return false
    return Object.values(value).some(item => containsRedactedSecret(item))
  }

  function optionalNumber(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim()) {
      const number = Number(value)
      return Number.isFinite(number) ? number : null
    }
    return null
  }

  function optionalBoolean(value: unknown, fallback = false) {
    if (typeof value === 'boolean') return value
    return fallback
  }

  function outOfSampleRatioPct(value: unknown) {
    const ratio = optionalNumber(value)
    if (ratio === null) return 25
    return ratio <= 1 ? Math.round(ratio * 100) : ratio
  }

  function outOfSampleRatioValue() {
    const ratio = Number(aiResearchForm.out_of_sample_ratio_pct || 25) / 100
    return Number(ratio.toFixed(4))
  }

  function parseResearchDate(value: string) {
    const trimmed = value.trim()
    if (!trimmed) return null
    const date = new Date(`${trimmed}T00:00:00Z`)
    return Number.isNaN(date.getTime()) ? null : date
  }

  function requiredOutOfSampleValidationError() {
    if (
      !aiResearchForm.out_of_sample_validation
      || !aiResearchForm.require_out_of_sample_validation
    ) {
      return ''
    }
    const startDate = parseResearchDate(aiResearchForm.start_date)
    const endDate = parseResearchDate(aiResearchForm.end_date)
    if (!startDate || !endDate || endDate <= startDate) {
      return '强制样本外验证需要填写合法的开始日期和结束日期'
    }
    const totalDays = Math.floor((endDate.getTime() - startDate.getTime()) / 86400000) + 1
    if (totalDays < 8) {
      return '强制样本外验证至少需要 8 天以上的回测区间'
    }
    return ''
  }

  function aiResearchPrecheckAssetType() {
    const symbol = aiResearchForm.symbol.trim().toUpperCase()
    if (isAIResearchFuturesSymbol(symbol)) return 'futures'
    if (/(USDT|USDC|PERP|SWAP|BTC|ETH)/.test(symbol)) return 'crypto'
    if (/\.(SZ|SH|BJ)$/.test(symbol) || /^\d{6}$/.test(symbol)) return 'stock'
    return undefined
  }

  async function runAIResearchDataPrecheck({ interactive = true }: { interactive?: boolean } = {}) {
    const symbol = aiResearchForm.symbol.trim()
    if (!symbol) {
      if (interactive) ElMessage.warning(t('strategy.aiResearchSymbolRequired'))
      return
    }
    const requestSequence = ++aiResearchPrecheckSequence
    aiResearchPrecheckController?.abort()
    const controller = new AbortController()
    aiResearchPrecheckController = controller
    aiResearchPrecheckLoading.value = true
    aiResearchPrecheckError.value = ''
    try {
      const result = await marketDataApi.runPrecheck({
        asset_type: aiResearchPrecheckAssetType(),
        symbol,
        timeframe: aiResearchForm.timeframe,
        start_date: aiResearchForm.start_date || null,
        end_date: aiResearchForm.end_date || null,
      }, { signal: controller.signal })
      if (requestSequence !== aiResearchPrecheckSequence) return
      aiResearchPrecheckResult.value = result
      if (interactive) {
        if (result.passed) {
          ElMessage.success(t('strategy.aiResearchPrecheckPassed'))
        } else {
          ElMessage.warning(t('strategy.aiResearchPrecheckBlocked'))
        }
      }
    } catch {
      if (requestSequence !== aiResearchPrecheckSequence || controller.signal.aborted) return
      aiResearchPrecheckResult.value = null
      aiResearchPrecheckError.value = '预检失败'
      if (interactive) ElMessage.error(t('strategy.aiResearchPrecheckFailed'))
    } finally {
      if (requestSequence === aiResearchPrecheckSequence) {
        aiResearchPrecheckLoading.value = false
      }
    }
  }

  function scheduleAIResearchDataPrecheck() {
    if (aiResearchPrecheckTimer !== null) clearTimeout(aiResearchPrecheckTimer)
    if (!aiResearchForm.symbol.trim()) return
    aiResearchPrecheckTimer = setTimeout(() => {
      aiResearchPrecheckTimer = null
      void runAIResearchDataPrecheck({ interactive: false })
    }, AI_RESEARCH_PRECHECK_DEBOUNCE_MS)
  }

  function aiResearchSymbolLabel() {
    const symbol = aiResearchForm.symbol.trim() || '待研究标的'
    const symbolName = aiResearchForm.symbol_name.trim()
    return symbolName ? `${symbolName}（${symbol}）` : symbol
  }

  const AI_RESEARCH_FUTURES_PREFIXES = [
    'IF', 'IC', 'IH', 'IM', 'T', 'TF', 'TL', 'TS',
    'AU', 'AG', 'CU', 'AL', 'ZN', 'PB', 'NI', 'SN', 'AO', 'RB', 'HC', 'SS',
    'BU', 'RU', 'BR', 'FU', 'SP', 'WR',
    'SC', 'LU', 'NR', 'BC', 'EC',
    'A', 'B', 'C', 'CS', 'EB', 'EG', 'I', 'J', 'JD', 'JM', 'L', 'LH',
    'M', 'P', 'PG', 'PP', 'RR', 'V', 'Y',
    'SA', 'FG', 'MA', 'TA', 'SR', 'CF', 'OI', 'RM', 'AP', 'CJ', 'CY',
    'PF', 'PK', 'SF', 'SM', 'UR', 'WH', 'ZC',
    'SI', 'LC',
  ].sort((left, right) => right.length - left.length)

  function isAIResearchFuturesSymbol(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return false
    if (/\.(CFE|CFFEX|SHFE|INE|DCE|CZCE|GFEX)$/.test(normalized)) return true
    return AI_RESEARCH_FUTURES_PREFIXES.some(prefix => {
      if (!normalized.startsWith(prefix)) return false
      const suffix = normalized.slice(prefix.length)
      if (/\d/.test(suffix)) return true
      return !suffix && prefix.length >= 2
    })
  }

  function aiResearchAssetConstraintLine() {
    const symbol = aiResearchForm.symbol.trim().toUpperCase()
    if (isAIResearchFuturesSymbol(symbol)) {
      return '按期货/合约资产处理，必须使用交易所或本地资产规格中的合约乘数、保证金、杠杆、最小变动价位和真实手续费估算仓位与风险。'
    }
    if (/(USDT|USDC|PERP|SWAP|BTC|ETH)/.test(symbol)) {
      return '按数字资产或永续合约处理，必须显式考虑资金费率、杠杆、滑点、交易费率和保证金约束。'
    }
    if (/\.(SZ|SH|BJ)$/.test(symbol)) {
      return '按股票资产处理，必须控制单票仓位、换手率、手续费和不可成交假设，避免过度交易。'
    }
    return '必须从交易所或本地资产规格读取手续费、合约乘数、保证金、价格精度和最小下单量，并在仓位 sizing 中使用这些约束。'
  }

  function aiResearchQualityGateLines() {
    const lines = [
      `目标 Sharpe 不低于 ${formatMetric(aiResearchForm.target_sharpe)}。`,
      `至少产生 ${formatMetric(aiResearchForm.min_total_trades, 0)} 笔有效交易，避免只靠少数交易达标。`,
    ]
    if (aiResearchForm.use_max_drawdown_limit) {
      lines.push(`最大回撤控制在 ${formatMetric(aiResearchForm.max_drawdown_limit, 0)}% 以内。`)
    }
    if (aiResearchForm.use_min_total_return) {
      lines.push(`总收益率不低于 ${formatMetric(aiResearchForm.min_total_return, 0)}%。`)
    }
    if (aiResearchForm.use_min_annual_return) {
      lines.push(`年化收益率不低于 ${formatMetric(aiResearchForm.min_annual_return, 0)}%。`)
    }
    if (aiResearchForm.use_min_win_rate) {
      lines.push(`胜率不低于 ${formatMetric(aiResearchForm.min_win_rate, 0)}%。`)
    }
    return lines
  }

  function aiResearchValidationLines() {
    const lines = [
      `回测区间：${aiResearchForm.start_date || '可用历史数据起点'} 至 ${aiResearchForm.end_date || '最新可得数据'}。`,
      `运行口径：年化天数 ${formatMetric(aiResearchForm.annual_days, 0)}，收益计算 ${aiResearchForm.calc_method}，组合权重 ${aiResearchForm.weight_mode}。`,
    ]
    if (aiResearchForm.out_of_sample_validation) {
      const requirements = [
        `保留 ${formatMetric(aiResearchForm.out_of_sample_ratio_pct, 0)}% 数据做样本外验证`,
      ]
      if (aiResearchForm.require_out_of_sample_validation) {
        requirements.push('达标后必须通过样本外验证才能进入模拟交易')
      }
      if (aiResearchForm.use_min_out_of_sample_sharpe) {
        requirements.push(`样本外 Sharpe 不低于 ${formatMetric(aiResearchForm.min_out_of_sample_sharpe)}`)
      }
      if (aiResearchForm.use_min_out_of_sample_trades) {
        requirements.push(`样本外交易数不少于 ${formatMetric(aiResearchForm.min_out_of_sample_trades, 0)}`)
      }
      lines.push(`${requirements.join('，')}。`)
    } else {
      lines.push('暂不启用样本外验证，但策略说明中必须提示过拟合风险。')
    }
    if (aiResearchForm.robustness_validation) {
      const methods = aiResearchForm.robustness_methods.length
        ? aiResearchForm.robustness_methods.join('、')
        : 'monte_carlo'
      const requirements = [
        `方法 ${methods}`,
        `稳健性得分不低于 ${formatMetric(aiResearchForm.min_robustness_score)}`,
      ]
      if (aiResearchForm.require_robustness_validation) {
        requirements.push('达标后必须通过稳健性验证才能进入模拟交易')
      }
      lines.push(`晋级前完成稳健性验证，${requirements.join('，')}。`)
    } else {
      lines.push('暂不启用稳健性验证，策略说明中必须显式提示参数敏感性和过拟合风险。')
    }
    if (aiResearchForm.start_paper_trading) {
      lines.push(
        `质量门槛达成后进入模拟交易，至少观察 ${formatMetric(aiResearchForm.min_paper_trading_days, 0)} 天，重点复核真实手续费、滑点、估值置信度、回撤和滚动 Sharpe。`
      )
    } else {
      lines.push('本轮只完成研究和回测，不自动启动模拟交易。')
    }
    return lines
  }

  function buildGeneratedAIResearchPrompt() {
    const signalFamilies = '趋势跟随、均值回归、波动率过滤、突破确认和风险预算'
    const workflowModeLine = aiResearchForm.workflow_mode === 'prompt'
      ? '模式：按用户提示执行指定投研流水线。'
      : '模式：自动规划并执行完整投研流水线。'
    return [
      `请为 ${aiResearchSymbolLabel()} 生成一套 ${aiResearchForm.timeframe} 级别的可执行 Backtrader 策略，并自动迭代回测直到达到质量门槛。`,
      '',
      '专业流水线：',
      workflowModeLine,
      '1. 策略构思：比较候选信号家族，明确入场、出场、仓位和风控假设。',
      '2. 策略生成：生成完整可运行的 Backtrader Strategy 脚本，next 方法必须包含真实 self.buy/self.sell/self.close 或 order_target_* 调用，不能留 pass、TODO 或伪代码。',
      '3. 策略回测：自动提交回测并记录 Sharpe、收益、回撤、交易次数和质量门槛差距。',
      '4. 策略审查：审查回测结果、失败原因、过拟合风险和实盘可执行性。',
      '5. 策略优化：根据审查意见继续优化代码、参数和风控，必要时进入下一轮回测。',
      '',
      '研究方向：',
      `1. 先比较 ${signalFamilies} 等候选逻辑，再选择最适合该标的的可执行方案。`,
      '2. 策略必须包含明确的入场、出场、止损/止盈、仓位 sizing 和异常行情保护。',
      `3. ${aiResearchAssetConstraintLine()}`,
      '',
      '质量门槛：',
      ...aiResearchQualityGateLines().map((line, index) => `${index + 1}. ${line}`),
      '',
      '验证与晋级：',
      ...aiResearchValidationLines().map((line, index) => `${index + 1}. ${line}`),
      '',
      '输出要求：生成完整可运行的 Backtrader Strategy 脚本，参数默认值要便于自动改稿；每轮改进都应解释为什么可能改善 Sharpe、回撤、交易次数或实盘可执行性。',
    ].join('\n')
  }

  function generateAIResearchPrompt() {
    aiResearchForm.prompt = buildGeneratedAIResearchPrompt()
    clearAIResearchMandate()
    ElMessage.success(t('strategy.aiResearchPromptGenerated'))
  }

  function aiResearchMandateQualityGatesFromForm(): Record<string, unknown> {
    return {
      target_sharpe: aiResearchForm.target_sharpe,
      min_total_trades: aiResearchForm.min_total_trades,
      max_drawdown_limit: aiResearchForm.use_max_drawdown_limit
        ? aiResearchForm.max_drawdown_limit
        : null,
      min_total_return: aiResearchForm.use_min_total_return
        ? aiResearchForm.min_total_return
        : null,
      min_annual_return: aiResearchForm.use_min_annual_return
        ? aiResearchForm.min_annual_return
        : null,
      min_win_rate: aiResearchForm.use_min_win_rate ? aiResearchForm.min_win_rate : null,
      out_of_sample_validation: aiResearchForm.out_of_sample_validation,
      require_out_of_sample_validation: aiResearchForm.require_out_of_sample_validation,
      out_of_sample_ratio: outOfSampleRatioValue(),
      min_out_of_sample_sharpe:
        aiResearchForm.out_of_sample_validation && aiResearchForm.use_min_out_of_sample_sharpe
          ? aiResearchForm.min_out_of_sample_sharpe
          : null,
      min_out_of_sample_trades:
        aiResearchForm.out_of_sample_validation && aiResearchForm.use_min_out_of_sample_trades
          ? aiResearchForm.min_out_of_sample_trades
          : null,
      robustness_validation: aiResearchForm.robustness_validation,
      require_robustness_validation: aiResearchForm.require_robustness_validation,
      robustness_methods: aiResearchForm.robustness_methods,
      min_robustness_score: aiResearchForm.min_robustness_score,
      robustness_monte_carlo_iterations: aiResearchForm.robustness_monte_carlo_iterations,
      robustness_random_seed: aiResearchForm.robustness_random_seed,
    }
  }

  function aiResearchMandateInputPrompt(input?: { prompt: string; symbol: string } | null) {
    return input?.prompt || aiResearchForm.prompt.trim() || buildGeneratedAIResearchPrompt()
  }

  function aiResearchMandatePayload(input?: { prompt: string; symbol: string } | null) {
    const prompt = aiResearchMandateInputPrompt(input)
    return {
      raw_prompt: prompt,
      symbol: input?.symbol || aiResearchForm.symbol.trim() || null,
      symbol_name: aiResearchForm.symbol_name.trim() || null,
      timeframe: aiResearchForm.timeframe || null,
      risk_constraints: {
        max_drawdown_limit: aiResearchForm.use_max_drawdown_limit
          ? aiResearchForm.max_drawdown_limit
          : null,
        min_win_rate: aiResearchForm.use_min_win_rate ? aiResearchForm.min_win_rate : null,
        out_of_sample_validation: aiResearchForm.out_of_sample_validation,
      },
      trading_constraints: {
        initial_cash: aiResearchForm.initial_cash,
        annual_days: aiResearchForm.annual_days,
        calc_method: aiResearchForm.calc_method,
        weight_mode: aiResearchForm.weight_mode,
        start_paper_trading: aiResearchForm.start_paper_trading,
      },
      quality_gates: aiResearchMandateQualityGatesFromForm(),
    }
  }

  async function parseAIResearchMandate(input?: { prompt: string; symbol: string } | null) {
    aiResearchMandateLoading.value = true
    try {
      aiResearchMandate.value = await strategyApi.createAIResearchMandate(
        aiResearchMandatePayload(input)
      )
      aiResearchMandateConfirmed.value = false
      ElMessage.success(t('strategy.aiResearchMandateStructured'))
      return aiResearchMandate.value
    } catch {
      ElMessage.error(t('strategy.aiResearchMandateStructureFailed'))
      return null
    } finally {
      aiResearchMandateLoading.value = false
    }
  }

  function confirmAIResearchMandate() {
    if (!aiResearchMandate.value) return
    aiResearchMandateConfirmed.value = true
    ElMessage.success(t('strategy.aiResearchMandateConfirmed'))
  }

  function clearAIResearchMandate() {
    aiResearchMandate.value = null
    aiResearchMandateConfirmed.value = false
  }

  async function loadAIResearchMandate(mandateId: string | null | undefined) {
    const id = stringFromUnknown(mandateId)
    if (!id) {
      clearAIResearchMandate()
      return
    }
    try {
      aiResearchMandate.value = await strategyApi.getAIResearchMandate(id)
      aiResearchMandateConfirmed.value = true
    } catch {
      aiResearchMandate.value = null
      aiResearchMandateConfirmed.value = false
    }
  }

  async function ensureAIResearchMandateConfirmed(input: { prompt: string; symbol: string }) {
    if (
      aiResearchMandate.value
      && aiResearchMandateConfirmed.value
      && aiResearchMandateMatchesInput(aiResearchMandate.value, input)
    ) {
      return aiResearchMandate.value
    }
    await parseAIResearchMandate(input)
    ElMessage.warning(t('strategy.aiResearchMandateConfirmationRequired'))
    return null
  }

  function aiResearchMandateMatchesInput(
    mandate: InvestmentMandateResponse,
    input: { prompt: string; symbol: string }
  ) {
    const prompt = aiResearchMandateInputPrompt(input).trim()
    const symbol = input.symbol.trim().toUpperCase()
    const mandateSymbol = stringFromUnknown(mandate.asset_scope.symbol).trim().toUpperCase()
    const mandateTimeframe = stringFromUnknown(mandate.timeframe || mandate.structured_goal.timeframe)
    return (
      mandate.raw_prompt.trim() === prompt
      && (!mandateSymbol || mandateSymbol === symbol)
      && (!mandateTimeframe || mandateTimeframe === aiResearchForm.timeframe)
    )
  }

  function mandateQualityGateSummary(gates: Record<string, unknown>) {
    const parts = [
      `Sharpe ${formatMetric(gates.target_sharpe)}`,
      `交易 ${formatMetric(gates.min_total_trades, 0)}`,
    ]
    if (gates.max_drawdown_limit !== null && gates.max_drawdown_limit !== undefined) {
      parts.push(`回撤 ${formatMetric(gates.max_drawdown_limit)}`)
    }
    if (gates.min_win_rate !== null && gates.min_win_rate !== undefined) {
      parts.push(`胜率 ${formatMetric(gates.min_win_rate)}`)
    }
    return parts.join(' · ')
  }

  type AIResearchConfigProfileApi = typeof strategyApi & {
    listAIResearchConfigProfiles?: typeof strategyApi.listAIResearchConfigProfiles
    createAIResearchConfigProfile?: typeof strategyApi.createAIResearchConfigProfile
    updateAIResearchConfigProfile?: typeof strategyApi.updateAIResearchConfigProfile
    deleteAIResearchConfigProfile?: typeof strategyApi.deleteAIResearchConfigProfile
    importAIResearchConfigProfileYaml?: typeof strategyApi.importAIResearchConfigProfileYaml
  }

  function aiResearchConfigProfileApi(): AIResearchConfigProfileApi {
    return strategyApi as AIResearchConfigProfileApi
  }

  function hasConfigKey(config: Record<string, unknown>, key: string) {
    return Object.prototype.hasOwnProperty.call(config, key)
  }

  function configStringValue(config: Record<string, unknown>, key: string, fallback = '') {
    if (!hasConfigKey(config, key)) return fallback
    const value = config[key]
    return typeof value === 'string' ? value.trim() : fallback
  }

  function snapshotAIResearchConfigForm(): Record<string, unknown> {
    return {
      ...JSON.parse(JSON.stringify(aiResearchForm)),
      seed_strategy_id: '',
      continue_from_run_id: '',
      continuation_source: '',
    }
  }

  function formatAIResearchConfigJson(value: unknown) {
    return isRecord(value) && Object.keys(value).length ? JSON.stringify(value) : ''
  }

  function applyAIResearchConfigToForm(config: Record<string, unknown>) {
    aiResearchForm.prompt = stringFromUnknown(config.prompt)
    aiResearchForm.workflow_mode = config.workflow_mode === 'prompt' ? 'prompt' : 'auto'
    aiResearchForm.symbol = stringFromUnknown(config.symbol, aiResearchForm.symbol)
    aiResearchForm.symbol_name = stringFromUnknown(config.symbol_name)
    aiResearchForm.timeframe = stringFromUnknown(config.timeframe, aiResearchForm.timeframe)
    aiResearchForm.timeframe_n = optionalNumber(config.timeframe_n) ?? aiResearchForm.timeframe_n
    aiResearchForm.start_date = configStringValue(config, 'start_date', aiResearchForm.start_date)
    aiResearchForm.end_date = configStringValue(config, 'end_date', aiResearchForm.end_date)
    aiResearchForm.knowledge_base_id = stringFromUnknown(config.knowledge_base_id)
    aiResearchForm.thinking_mode = optionalBoolean(config.thinking_mode, aiResearchForm.thinking_mode)
    aiResearchForm.target_sharpe = optionalNumber(config.target_sharpe) ?? aiResearchForm.target_sharpe
    aiResearchForm.min_total_trades =
      optionalNumber(config.min_total_trades) ?? aiResearchForm.min_total_trades

    const maxDrawdownLimit = optionalNumber(config.max_drawdown_limit)
    aiResearchForm.use_max_drawdown_limit = optionalBoolean(
      config.use_max_drawdown_limit,
      maxDrawdownLimit !== null
    )
    aiResearchForm.max_drawdown_limit = maxDrawdownLimit ?? aiResearchForm.max_drawdown_limit
    const minTotalReturn = optionalNumber(config.min_total_return)
    aiResearchForm.use_min_total_return = optionalBoolean(
      config.use_min_total_return,
      minTotalReturn !== null
    )
    aiResearchForm.min_total_return = minTotalReturn ?? aiResearchForm.min_total_return
    const minAnnualReturn = optionalNumber(config.min_annual_return)
    aiResearchForm.use_min_annual_return = optionalBoolean(
      config.use_min_annual_return,
      minAnnualReturn !== null
    )
    aiResearchForm.min_annual_return = minAnnualReturn ?? aiResearchForm.min_annual_return
    const minWinRate = optionalNumber(config.min_win_rate)
    aiResearchForm.use_min_win_rate = optionalBoolean(
      config.use_min_win_rate,
      minWinRate !== null
    )
    aiResearchForm.min_win_rate = minWinRate ?? aiResearchForm.min_win_rate

    aiResearchForm.max_iterations = optionalNumber(config.max_iterations) ?? aiResearchForm.max_iterations
    aiResearchForm.out_of_sample_validation = optionalBoolean(
      config.out_of_sample_validation,
      aiResearchForm.out_of_sample_validation
    )
    aiResearchForm.require_out_of_sample_validation = optionalBoolean(
      config.require_out_of_sample_validation,
      aiResearchForm.require_out_of_sample_validation
    )
    aiResearchForm.out_of_sample_ratio_pct =
      optionalNumber(config.out_of_sample_ratio_pct)
      ?? outOfSampleRatioPct(config.out_of_sample_ratio)
    const minOutOfSampleSharpe = optionalNumber(config.min_out_of_sample_sharpe)
    aiResearchForm.use_min_out_of_sample_sharpe = optionalBoolean(
      config.use_min_out_of_sample_sharpe,
      minOutOfSampleSharpe !== null
    )
    aiResearchForm.min_out_of_sample_sharpe =
      minOutOfSampleSharpe ?? aiResearchForm.min_out_of_sample_sharpe
    const minOutOfSampleTrades = optionalNumber(config.min_out_of_sample_trades)
    aiResearchForm.use_min_out_of_sample_trades = optionalBoolean(
      config.use_min_out_of_sample_trades,
      minOutOfSampleTrades !== null
    )
    aiResearchForm.min_out_of_sample_trades =
      minOutOfSampleTrades ?? aiResearchForm.min_out_of_sample_trades

    aiResearchForm.robustness_validation = optionalBoolean(
      config.robustness_validation,
      aiResearchForm.robustness_validation
    )
    aiResearchForm.require_robustness_validation = optionalBoolean(
      config.require_robustness_validation,
      aiResearchForm.require_robustness_validation
    )
    const robustnessMethods = stringArrayFromUnknown(config.robustness_methods)
    aiResearchForm.robustness_methods = robustnessMethods.length
      ? robustnessMethods
      : aiResearchForm.robustness_methods
    aiResearchForm.min_robustness_score =
      optionalNumber(config.min_robustness_score) ?? aiResearchForm.min_robustness_score
    aiResearchForm.robustness_monte_carlo_iterations =
      optionalNumber(config.robustness_monte_carlo_iterations)
      ?? aiResearchForm.robustness_monte_carlo_iterations
    aiResearchForm.robustness_random_seed =
      optionalNumber(config.robustness_random_seed)

    aiResearchForm.initial_cash = optionalNumber(config.initial_cash) ?? aiResearchForm.initial_cash
    aiResearchForm.use_manual_commission = optionalBoolean(
      config.use_manual_commission,
      hasConfigKey(config, 'commission')
    )
    aiResearchForm.commission = optionalNumber(config.commission) ?? aiResearchForm.commission
    aiResearchForm.annual_days = optionalNumber(config.annual_days) ?? aiResearchForm.annual_days
    aiResearchForm.calc_method = stringFromUnknown(config.calc_method, aiResearchForm.calc_method)
    aiResearchForm.weight_mode = stringFromUnknown(config.weight_mode, aiResearchForm.weight_mode)
    aiResearchForm.group_name = stringFromUnknown(config.group_name)
    aiResearchForm.backtest_timeout_seconds =
      optionalNumber(config.backtest_timeout_seconds) ?? aiResearchForm.backtest_timeout_seconds
    aiResearchForm.poll_interval_seconds =
      optionalNumber(config.poll_interval_seconds) ?? aiResearchForm.poll_interval_seconds
    aiResearchForm.research_workspace_id = stringFromUnknown(config.research_workspace_id)
    aiResearchForm.seed_strategy_id = stringFromUnknown(config.seed_strategy_id)
    aiResearchForm.continue_from_run_id = stringFromUnknown(config.continue_from_run_id)
    aiResearchForm.continuation_source = stringFromUnknown(config.continuation_source)
    aiResearchForm.start_paper_trading = optionalBoolean(
      config.start_paper_trading,
      aiResearchForm.start_paper_trading
    )
    aiResearchForm.min_paper_trading_days =
      optionalNumber(config.min_paper_trading_days) ?? aiResearchForm.min_paper_trading_days
    aiResearchForm.paper_workspace_name = stringFromUnknown(config.paper_workspace_name)
    aiResearchForm.trading_workspace_id = stringFromUnknown(config.trading_workspace_id)
    aiResearchForm.gateway_config_json =
      stringFromUnknown(config.gateway_config_json) || formatAIResearchConfigJson(config.gateway_config)
    aiResearchForm.live_workspace_name = stringFromUnknown(config.live_workspace_name)
    aiResearchForm.live_trading_workspace_id = stringFromUnknown(config.live_trading_workspace_id)
    aiResearchForm.live_gateway_config_json =
      stringFromUnknown(config.live_gateway_config_json)
      || formatAIResearchConfigJson(config.live_gateway_config)
  }

  function upsertAIResearchConfigProfile(profile: AIStrategyResearchConfigProfile) {
    const index = aiResearchConfigProfiles.value.findIndex(item => item.id === profile.id)
    if (index < 0) {
      aiResearchConfigProfiles.value = [...aiResearchConfigProfiles.value, profile].sort(
        (left, right) => left.name.localeCompare(right.name)
      )
      return
    }
    aiResearchConfigProfiles.value = aiResearchConfigProfiles.value.map(item =>
      item.id === profile.id ? profile : item
    )
  }

  function setAIResearchConfigProfileEditor(profile: AIStrategyResearchConfigProfile | null) {
    aiResearchSelectedConfigProfileId.value = profile?.id ?? ''
    aiResearchConfigProfileName.value = profile?.name ?? ''
    aiResearchConfigProfileDescription.value = profile?.description ?? ''
  }

  function ensureAIResearchVisiblePrompt() {
    if (aiResearchForm.prompt.trim()) return
    aiResearchForm.prompt = buildGeneratedAIResearchPrompt()
  }

  function applyAIResearchConfigProfile(
    profile: AIStrategyResearchConfigProfile,
    options: { notify?: boolean; syncResult?: boolean } = {}
  ) {
    setAIResearchConfigProfileEditor(profile)
    applyAIResearchConfigToForm(profile.config)
    ensureAIResearchVisiblePrompt()
    clearAIResearchMandate()
    if (options.syncResult ?? true) {
      syncAIResearchDisplayedOutputWithSelectedProfile()
    }
    if (options.notify ?? true) ElMessage.success(t('strategy.aiResearchConfigLoaded', { name: profile.name }))
  }

  function openAIResearchConfigDialog() {
    aiResearchConfigDialogVisible.value = true
  }

  function selectAIResearchConfigProfile(profileId: string | number | boolean | undefined) {
    const selectedId = String(profileId || '')
    const profile = aiResearchConfigProfiles.value.find(item => item.id === selectedId)
    if (!profile) return
    applyAIResearchConfigProfile(profile)
  }

  function clearAIResearchDisplayedOutput() {
    aiResearchResult.value = null
    clearAIResearchArtifacts()
    clearAIResearchMandate()
    resetAIResearchTaskState()
    aiResearchForm.seed_strategy_id = ''
    aiResearchForm.continue_from_run_id = ''
    aiResearchForm.continuation_source = ''
  }

  function currentAIResearchResultMatchesConfigProfile(profile: AIStrategyResearchConfigProfile) {
    const record = aiResearchResult.value?.run_record
    return Boolean(record && aiResearchRunMatchesConfigProfile(record, profile))
  }

  function aiResearchConfigProfileForRunRecord(record: AIStrategyResearchRunRecord) {
    return aiResearchConfigProfiles.value.find(profile =>
      aiResearchRunMatchesConfigProfile(record, profile)
    ) ?? null
  }

  function setAIResearchConfigProfileFromRunRecord(record: AIStrategyResearchRunRecord) {
    const profile = aiResearchConfigProfileForRunRecord(record)
    if (profile) setAIResearchConfigProfileEditor(profile)
  }

  function syncAIResearchDisplayedOutputWithSelectedProfile() {
    const profile = aiResearchSelectedConfigProfile.value
    if (!profile || aiResearchRunning.value) return
    if (currentAIResearchResultMatchesConfigProfile(profile)) return
    const matchedRun = aiResearchRuns.value.find(record =>
      aiResearchRunMatchesConfigProfile(record, profile)
    )
    if (matchedRun) {
      selectAIResearchRunRecord(matchedRun, { keepSelectedProfile: true })
    } else {
      clearAIResearchDisplayedOutput()
    }
  }

  function aiResearchRunMatchesConfigProfile(
    record: AIStrategyResearchRunRecord,
    profile: AIStrategyResearchConfigProfile
  ) {
    const config = profile.config || {}
    const symbol = stringFromUnknown(config.symbol).trim().toUpperCase()
    const timeframe = stringFromUnknown(config.timeframe).trim().toLowerCase()
    const timeframeN = optionalNumber(config.timeframe_n)
    if (symbol && record.symbol.trim().toUpperCase() !== symbol) return false
    if (timeframe && record.timeframe.trim().toLowerCase() !== timeframe) return false
    if (timeframeN !== null && Number(record.timeframe_n || 1) !== timeframeN) return false
    return Boolean(symbol || timeframe || timeframeN !== null)
  }

  function aiResearchConfigProfileValue(profile: AIStrategyResearchConfigProfile, key: string) {
    return stringFromUnknown(profile.config[key], '-')
  }

  function aiResearchConfigProfileMetric(
    profile: AIStrategyResearchConfigProfile,
    key: string,
    digits = 2
  ) {
    const value = optionalNumber(profile.config[key])
    return value === null ? '-' : formatMetric(value, digits)
  }

  function aiResearchConfigProfileOos(profile: AIStrategyResearchConfigProfile) {
    if (!optionalBoolean(profile.config.out_of_sample_validation, false)) return '关闭'
    const ratioPct = optionalNumber(profile.config.out_of_sample_ratio_pct)
      ?? outOfSampleRatioPct(profile.config.out_of_sample_ratio)
    return `${formatMetric(ratioPct, 0)}%`
  }

  async function loadAIResearchConfigProfiles(options: { showError?: boolean } = {}) {
    const api = aiResearchConfigProfileApi()
    if (typeof api.listAIResearchConfigProfiles !== 'function') return
    if (aiResearchConfigProfilesLoading.value) return
    aiResearchConfigProfilesLoading.value = true
    try {
      const response = await api.listAIResearchConfigProfiles()
      aiResearchConfigProfiles.value = response.items
      aiResearchConfigProfileFilePath.value = response.file_path
      const selected = aiResearchSelectedConfigProfile.value
      if (selected) applyAIResearchConfigProfile(selected, { notify: false })
      if (!selected && response.items[0]) {
        applyAIResearchConfigProfile(response.items[0], { notify: false })
      }
    } catch {
      if (options.showError) ElMessage.error(t('strategy.aiResearchConfigLoadFailed'))
    } finally {
      aiResearchConfigProfilesLoading.value = false
    }
  }

  async function createAIResearchConfigProfile() {
    const api = aiResearchConfigProfileApi()
    if (typeof api.createAIResearchConfigProfile !== 'function') return
    const name = aiResearchConfigProfileName.value.trim()
    if (!name) {
      ElMessage.warning(t('strategy.aiResearchConfigNameRequired'))
      return
    }
    aiResearchConfigProfileSaving.value = true
    try {
      const profile = await api.createAIResearchConfigProfile({
        name,
        description: aiResearchConfigProfileDescription.value.trim(),
        config: snapshotAIResearchConfigForm(),
      })
      upsertAIResearchConfigProfile(profile)
      setAIResearchConfigProfileEditor(profile)
      ElMessage.success(t('strategy.aiResearchConfigCreated'))
    } catch {
      ElMessage.error(t('strategy.aiResearchConfigCreateFailed'))
    } finally {
      aiResearchConfigProfileSaving.value = false
    }
  }

  async function saveAIResearchConfigProfile(profileId = aiResearchSelectedConfigProfileId.value) {
    const api = aiResearchConfigProfileApi()
    if (typeof api.updateAIResearchConfigProfile !== 'function') return
    const profile = aiResearchConfigProfiles.value.find(item => item.id === profileId)
    if (!profile) {
      ElMessage.warning(t('strategy.aiResearchConfigSelectionRequired'))
      return
    }
    const isEditingSelected = profile.id === aiResearchSelectedConfigProfileId.value
    const name = isEditingSelected
      ? aiResearchConfigProfileName.value.trim() || profile.name
      : profile.name
    const description = isEditingSelected
      ? aiResearchConfigProfileDescription.value.trim()
      : profile.description
    aiResearchConfigProfileSaving.value = true
    try {
      const updated = await api.updateAIResearchConfigProfile(profile.id, {
        name,
        description,
        config: snapshotAIResearchConfigForm(),
      })
      upsertAIResearchConfigProfile(updated)
      setAIResearchConfigProfileEditor(updated)
      ElMessage.success(t('strategy.aiResearchConfigSaved'))
    } catch {
      ElMessage.error(t('strategy.aiResearchConfigSaveFailed'))
    } finally {
      aiResearchConfigProfileSaving.value = false
    }
  }

  async function deleteAIResearchConfigProfile(profile: AIStrategyResearchConfigProfile) {
    const api = aiResearchConfigProfileApi()
    if (typeof api.deleteAIResearchConfigProfile !== 'function') return
    try {
      await ElMessageBox.confirm(t('strategy.aiResearchDeleteConfigConfirm', { name: profile.name }),
        t('strategy.aiResearchDeleteConfigTitle'), { type: 'warning' })
    } catch {
      return
    }
    aiResearchConfigProfileDeletingId.value = profile.id
    try {
      await api.deleteAIResearchConfigProfile(profile.id)
      aiResearchConfigProfiles.value = aiResearchConfigProfiles.value.filter(
        item => item.id !== profile.id
      )
      if (aiResearchSelectedConfigProfileId.value === profile.id) {
        setAIResearchConfigProfileEditor(null)
      }
      ElMessage.success(t('strategy.aiResearchConfigDeleted'))
    } catch {
      ElMessage.error(t('strategy.aiResearchConfigDeleteFailed'))
    } finally {
      aiResearchConfigProfileDeletingId.value = ''
    }
  }

  function triggerAIResearchConfigProfileImport() {
    aiResearchConfigProfileFileInput.value?.click()
  }

  function readSelectedAIResearchConfigFile(file: File) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(reader.error ?? new Error('读取 YAML 文件失败'))
      reader.readAsText(file)
    })
  }

  async function importAIResearchConfigProfileFile(event: Event) {
    const api = aiResearchConfigProfileApi()
    if (typeof api.importAIResearchConfigProfileYaml !== 'function') return
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file) return
    aiResearchConfigProfileImporting.value = true
    try {
      const rawYaml = await readSelectedAIResearchConfigFile(file)
      const fallbackName = file.name.replace(/\.(ya?ml)$/i, '')
      const response = await api.importAIResearchConfigProfileYaml({
        raw_yaml: rawYaml,
        name: fallbackName,
      })
      aiResearchConfigProfileFilePath.value = response.file_path
      response.items.forEach(upsertAIResearchConfigProfile)
      if (response.items[0]) applyAIResearchConfigProfile(response.items[0])
      ElMessage.success(t('strategy.aiResearchConfigsImported', { count: response.total }))
    } catch {
      ElMessage.error(t('strategy.aiResearchConfigImportFailed'))
    } finally {
      aiResearchConfigProfileImporting.value = false
    }
  }

  function validationWindowFromUnknown(value: unknown): Record<string, string> | null {
    if (!isRecord(value)) return null
    const entries = Object.entries(value)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    return entries.length ? Object.fromEntries(entries) : null
  }

  function outOfSampleValidationFromHandoff(
    handoff: Record<string, unknown> | null | undefined
  ): AIStrategyOutOfSampleValidation | null {
    if (!isRecord(handoff)) return null
    const payload = handoff.out_of_sample_validation
    if (!isRecord(payload)) return null
    return {
      status: typeof payload.status === 'string' ? payload.status : null,
      window: validationWindowFromUnknown(payload.window),
      metrics: isRecord(payload.metrics) ? payload.metrics : {},
      gate_evaluations: Array.isArray(payload.gate_evaluations)
        ? payload.gate_evaluations as AIStrategyQualityGateEvaluation[]
        : [],
      failures: Array.isArray(payload.failures)
        ? payload.failures.filter((item): item is string => typeof item === 'string')
        : [],
      failure_reason: typeof payload.failure_reason === 'string' ? payload.failure_reason : null,
    }
  }

  type PaperEnvironmentItem = {
    key: string
    label: string
    value: string
  }

  function hasResearchRuntimeEnvironment(record: AIStrategyResearchRunRecord) {
    return researchRuntimeItems(record).length > 0
  }

  function researchRuntimeItems(
    record: AIStrategyResearchRunRecord | null | undefined,
    handoff?: Record<string, unknown> | null
  ): PaperEnvironmentItem[] {
    const environment = runtimeEnvironmentPayload(record, handoff)
    const specs = runtimeAssetSpecsPayload(record, handoff)
    return runtimeItemsFromPayloads(environment, specs)
  }

  function runtimeItemsFromPayloads(
    environment: Record<string, unknown>,
    assetSpecs: Record<string, unknown>,
    requestSnapshot?: Record<string, unknown> | null
  ): PaperEnvironmentItem[] {
    const items = environmentItemsFromPayload(environment)
    const existing = new Set(items.map(item => item.key))
    const appendItem = (item: PaperEnvironmentItem) => {
      if (existing.has(item.key) || !item.value) return
      items.push(item)
      existing.add(item.key)
    }
    for (const item of gatewayRuntimeItemsFromSnapshot(requestSnapshot)) {
      appendItem(item)
    }
    const asset = firstRuntimeAssetSpecFromPayload(assetSpecs)
    if (!asset) return items

    if (!existing.has('asset_symbol')) {
      items.unshift({ key: 'asset_symbol', label: t('strategy.aiResearchAsset'), value: asset.symbol })
      existing.add('asset_symbol')
    }
    const appendSpecNumber = (key: string, label: string, digits = 2) => {
      if (existing.has(key)) return
      const value = asset.spec[key]
      if (value === undefined || value === null || value === '') return
      items.push({ key, label, value: formatMetric(value, digits) })
      existing.add(key)
    }
    const appendSpecText = (key: string, label: string) => {
      if (existing.has(key)) return
      const value = asset.spec[key]
      if (value === undefined || value === null || value === '') return
      items.push({ key, label, value: String(value) })
      existing.add(key)
    }
    appendSpecNumber('multiplier', '合约乘数', 2)
    appendSpecNumber('margin', '保证金', 4)
    appendSpecNumber('margin_rate', '保证金率', 4)
    appendSpecNumber('leverage', '杠杆', 2)
    appendSpecNumber('max_leverage', '最大杠杆', 2)
    appendSpecNumber('commission', '手续费', 6)
    appendSpecNumber('commission_rate', '手续费率', 6)
    if (!items.some(item => item.label === '资产来源')) appendSpecText('asset_spec_source', '资产来源')
    if (!items.some(item => item.label === '资产来源')) appendSpecText('source', '资产来源')
    if (!items.some(item => item.label === '费用来源')) appendSpecText('fee_source', '费用来源')
    return items.slice(0, 10)
  }

  function gatewayRuntimeItemsFromSnapshot(
    requestSnapshot?: Record<string, unknown> | null
  ): PaperEnvironmentItem[] {
    if (!isRecord(requestSnapshot) || !isRecord(requestSnapshot.gateway_config)) return []
    const gatewayConfig = requestSnapshot.gateway_config
    const params = isRecord(gatewayConfig.params) ? gatewayConfig.params : {}
    const gatewayParams = isRecord(params.gateway) ? params.gateway : {}
    const ctpParams = isRecord(params.ctp) ? params.ctp : {}
    const ibParams = isRecord(params.ib) ? params.ib : {}
    const mt5Params = isRecord(params.mt5) ? params.mt5 : {}
    const text = (...values: unknown[]) => {
      for (const value of values) {
        if (typeof value === 'number' && Number.isFinite(value)) return String(value)
        const parsed = stringFromUnknown(value)
        if (parsed) return parsed
      }
      return ''
    }
    const items: PaperEnvironmentItem[] = []
    const appendText = (key: string, label: string, value: string) => {
      if (!value) return
      items.push({ key, label, value })
    }
    appendText(
      'gateway_name',
      '网关',
      text(
        gatewayConfig.name,
        gatewayConfig.preset_id,
        params.name,
        params.preset_id,
        gatewayParams.provider
      )
    )
    appendText(
      'gateway_exchange',
      '交易所',
      text(
        gatewayConfig.exchange,
        gatewayConfig.exchange_id,
        gatewayConfig.exchange_type,
        params.exchange,
        params.exchange_id,
        params.exchange_type,
        gatewayParams.exchange,
        gatewayParams.exchange_id,
        gatewayParams.exchange_type
      )
    )
    appendText(
      'gateway_mode',
      '模式',
      text(
        gatewayConfig.mode,
        gatewayConfig.trading_mode,
        params.mode,
        params.trading_mode,
        gatewayParams.mode,
        gatewayParams.trading_mode
      )
    )
    appendText(
      'gateway_broker',
      '经纪商',
      text(
        gatewayConfig.broker_id,
        params.broker_id,
        ctpParams.broker_id,
        ibParams.broker_id,
        mt5Params.broker_id,
        gatewayParams.broker_id
      )
    )
    return items
  }

  function hasPaperEnvironment(handoff: Record<string, unknown> | null | undefined) {
    return paperEnvironmentItems(handoff).length > 0
  }

  function paperEnvironmentItems(
    handoff: Record<string, unknown> | null | undefined
  ): PaperEnvironmentItem[] {
    if (!isRecord(handoff) || !isRecord(handoff.backtest_environment)) return []
    return environmentItemsFromPayload(handoff.backtest_environment)
  }

  function environmentItemsFromPayload(environment: Record<string, unknown>): PaperEnvironmentItem[] {
    const items: PaperEnvironmentItem[] = []
    const appendNumber = (key: string, label: string, digits = 2) => {
      const value = environment[key]
      if (value === undefined || value === null || value === '') return
      items.push({ key, label, value: formatMetric(value, digits) })
    }
    const appendText = (key: string, label: string) => {
      const value = environment[key]
      if (value === undefined || value === null || value === '') return
      items.push({ key, label, value: String(value) })
    }
    const startDate = environment.start_date
    const endDate = environment.end_date
    if (startDate || endDate) {
      items.push({
        key: 'date_range',
        label: t('strategy.aiResearchPeriod'),
        value: `${startDate || '-'} 至 ${endDate || '-'}`,
      })
    }
    appendNumber('initial_cash', '初始资金', 2)
    appendNumber('commission', '手续费', 6)
    appendNumber('multiplier', '合约乘数', 2)
    appendNumber('margin', '保证金', 4)
    appendNumber('annual_days', '年化天数', 0)
    appendText('calc_method', '收益')
    appendText('weight_mode', '权重')
    appendText('asset_spec_source', '资产来源')
    return items
  }

  function runtimeEnvironmentPayload(
    record: AIStrategyResearchRunRecord | null | undefined,
    handoff?: Record<string, unknown> | null
  ): Record<string, unknown> {
    const environment: Record<string, unknown> = {}
    const merge = (source: unknown) => {
      if (isRecord(source)) Object.assign(environment, source)
    }
    merge(record?.backtest_environment)
    merge(handoff?.backtest_environment)
    if (handoff !== undefined && isRecord(record?.paper_handoff)) {
      merge(record.paper_handoff.backtest_environment)
    }
    return environment
  }

  function firstRuntimeAssetSpecFromPayload(
    specs: Record<string, unknown>
  ): { symbol: string; spec: Record<string, unknown> } | null {
    for (const [symbol, spec] of Object.entries(specs)) {
      if (!isRecord(spec)) continue
      return { symbol, spec }
    }
    return null
  }

  function iterationOutOfSampleValidation(
    item: AIStrategyResearchRunResponse['iterations'][number]
  ): AIStrategyOutOfSampleValidation | null {
    const hasWindow = Boolean(item.validation_window)
    const hasMetrics = Boolean(Object.keys(item.validation_metrics || {}).length)
    const hasGates = Boolean((item.validation_gate_evaluations || []).length)
    const hasFailures = Boolean((item.validation_failures || []).length)
    if (!item.validation_status && !hasWindow && !hasMetrics && !hasGates && !hasFailures) {
      return null
    }
    return {
      status: item.validation_status ?? null,
      window: item.validation_window ?? null,
      metrics: item.validation_metrics ?? {},
      gate_evaluations: item.validation_gate_evaluations ?? [],
      failures: item.validation_failures ?? [],
      failure_reason: item.validation_failure_reason ?? null,
    }
  }

  function formatBacktestPercent(value: unknown, { absolute = false } = {}) {
    const number = optionalNumber(value)
    if (number === null) return ''
    return `${formatMetric(absolute ? Math.abs(number) : number)}%`
  }

  function researchIterationBacktestSummary(
    item: AIStrategyResearchRunResponse['iterations'][number]
  ) {
    const metrics = isRecord(item.metrics) ? item.metrics : {}
    const rows: { key: string; label: string; value: string }[] = []
    const appendMetric = (
      key: string,
      label: string,
      keys: string[],
      formatter: (value: unknown) => string = value => formatMetric(value)
    ) => {
      const value = keys
        .map(metricKey => metrics[metricKey])
        .find(metricValue => optionalNumber(metricValue) !== null)
      if (value === undefined || value === null || value === '') return
      const formatted = formatter(value)
      if (!formatted || formatted === '-') return
      rows.push({ key, label, value: formatted })
    }
    const runStatus = stringFromUnknown(item.unit_status?.run_status, item.run_result.status)
    if (runStatus) rows.push({ key: 'run_status', label: t('common.status'), value: runStatus })
    if (item.run_result.task_id) {
      rows.push({ key: 'task_id', label: t('strategy.aiResearchTask'), value: item.run_result.task_id })
    }
    appendMetric('total_return', '总收益', ['total_return', 'return'], value =>
      formatBacktestPercent(value)
    )
    appendMetric('annual_return', '年化', ['annual_return', 'annualized_return'], value =>
      formatBacktestPercent(value)
    )
    appendMetric('max_drawdown', '最大回撤', ['max_drawdown', 'max_drawdown_rate'], value =>
      formatBacktestPercent(value, { absolute: true })
    )
    appendMetric('win_rate', '胜率', ['win_rate'], value => formatBacktestPercent(value))
    appendMetric('net_profit', '净利润', ['net_profit', 'total_pnl', 'pnl'])
    appendMetric('final_value', '最终权益', ['final_value', 'portfolio_value'])
    appendMetric('trading_cost', '交易成本', ['trading_cost', 'commission'])
    if (item.unit_status?.bar_count) {
      rows.push({ key: 'bar_count', label: t('strategy.aiResearchKline'), value: formatMetric(item.unit_status.bar_count, 0) })
    }
    return rows
  }

  function formatOutOfSampleWindow(window: Record<string, string> | null | undefined) {
    if (!window) return ''
    const trainStart = window.train_start
    const trainEnd = window.train_end
    const validationStart = window.validation_start
    const validationEnd = window.validation_end
    if (!trainStart || !trainEnd || !validationStart || !validationEnd) return ''
    return `训练 ${trainStart} - ${trainEnd}；样本外 ${validationStart} - ${validationEnd}`
  }

  function outOfSampleTagType(status: string | null | undefined) {
    if (status === 'passed') return 'success'
    if (status === 'failed') return 'danger'
    if (status === 'skipped') return 'info'
    return 'warning'
  }

  function outOfSampleStatusLabel(status: string | null | undefined) {
    const normalized = String(status || '').trim()
    const labels: Record<string, string> = {
      passed: '已通过',
      failed: '未通过',
      skipped: '已跳过',
      not_required: '无需验证',
      pending: '待验证',
      running: '验证中',
    }
    return labels[normalized] ?? aiResearchStageLabel(normalized || 'not_required')
  }

  function recordOutOfSampleSummary(record: AIStrategyResearchRunRecord) {
    const handoffValidation = outOfSampleValidationFromHandoff(record.paper_handoff)
    if (handoffValidation?.status) return `样本外 ${outOfSampleStatusLabel(handoffValidation.status)}`
    const gates = record.quality_gates || {}
    if (optionalBoolean(gates.out_of_sample_validation, false)) {
      return `样本外 ${formatMetric(outOfSampleRatioPct(gates.out_of_sample_ratio), 0)}%`
    }
    return ''
  }

  function strategyIdFromIterationPayload(payload: Record<string, unknown>) {
    const strategySnapshot = iterationStrategyPayload(payload)
    return stringFromUnknown(strategySnapshot.id ?? payload.strategy_id, '').trim()
  }

  function iterationPayloadHasStrategy(payload: Record<string, unknown>) {
    const strategySnapshot = iterationStrategyPayload(payload)
    return Boolean(
      strategyIdFromIterationPayload(payload)
      || stringFromUnknown(strategySnapshot.code, '')
      || stringFromUnknown(payload.strategy_code, '')
      || stringFromUnknown(payload.code, '')
    )
  }

  function iterationPayloadRank(payload: Record<string, unknown>) {
    const metrics = isRecord(payload.metrics) ? payload.metrics : {}
    return [
      optionalBoolean(payload.passed, false) ? 1 : 0,
      optionalNumber(payload.quality_score) ?? 0,
      optionalNumber(payload.sharpe_ratio)
        ?? optionalNumber(metrics.sharpe_ratio)
        ?? optionalNumber(metrics.sharpe)
        ?? optionalNumber(metrics.sharpeRatio)
        ?? 0,
      optionalNumber(payload.total_trades)
        ?? optionalNumber(metrics.total_trades)
        ?? optionalNumber(metrics.totalTrades)
        ?? optionalNumber(metrics.trades)
        ?? 0,
      -(optionalNumber(payload.iteration) ?? 0),
    ]
  }

  function compareIterationPayloads(
    candidate: Record<string, unknown>,
    current: Record<string, unknown>
  ) {
    const candidateRank = iterationPayloadRank(candidate)
    const currentRank = iterationPayloadRank(current)
    for (let index = 0; index < candidateRank.length; index += 1) {
      const delta = candidateRank[index] - currentRank[index]
      if (delta !== 0) return delta
    }
    return 0
  }

  function bestIterationPayloadForRecord(record: AIStrategyResearchRunRecord) {
    const iterations = (record.iterations || []).filter(isRecord)
    if (!iterations.length) return null
    const bestIteration = optionalNumber(record.best_iteration)
    if (bestIteration !== null) {
      const matched = iterations.find(
        payload => optionalNumber(payload.iteration) === bestIteration
      )
      if (matched) return matched
    }
    const candidates = iterations.filter(iterationPayloadHasStrategy)
    const pool = candidates.length ? candidates : iterations
    return pool.reduce(
      (best, payload) => (compareIterationPayloads(payload, best) > 0 ? payload : best),
      pool[0]
    )
  }

  function bestStrategyIdForRecord(record: AIStrategyResearchRunRecord) {
    const direct = stringFromUnknown(record.best_strategy_id, '').trim()
    if (direct) return direct
    const payload = bestIterationPayloadForRecord(record)
    if (!payload) return ''
    const payloadStrategyId = strategyIdFromIterationPayload(payload)
    if (payloadStrategyId) return payloadStrategyId
    return iterationPayloadHasStrategy(payload) ? fallbackSnapshotStrategyId(record) : ''
  }

  function fallbackSnapshotStrategyId(record: AIStrategyResearchRunRecord) {
    return `${record.run_id}-strategy`
  }

  function gatewayConfigJsonFromRunRecord(record: AIStrategyResearchRunRecord) {
    const payload = bestIterationPayloadForRecord(record)
    const snapshot = payload && isRecord(payload.unit_snapshot) ? payload.unit_snapshot : {}
    const handoff = isRecord(record.paper_handoff) ? record.paper_handoff : {}
    const candidates = [snapshot.gateway_config, handoff.gateway_config]
    const gatewayConfig = candidates.find(
      item => isRecord(item) && Object.keys(item).length > 0 && !containsRedactedSecret(item)
    )
    return isRecord(gatewayConfig) ? JSON.stringify(gatewayConfig) : ''
  }

  function gatewayConfigJsonFromTaskSnapshot(snapshot: Record<string, unknown>) {
    const gatewayConfig = snapshot.gateway_config
    if (!isRecord(gatewayConfig) || containsRedactedSecret(gatewayConfig)) return ''
    return JSON.stringify(gatewayConfig)
  }

  function liveGatewayConfigJsonFromRunRecord(record: AIStrategyResearchRunRecord) {
    const handoffPayload = record.live_handoff?.handoff
    const gatewayConfig = isRecord(handoffPayload?.gateway_config)
      ? handoffPayload.gateway_config
      : null
    if (!isRecord(gatewayConfig) || containsRedactedSecret(gatewayConfig)) return ''
    return JSON.stringify(gatewayConfig)
  }

  function bestStrategyFromRunRecord(record: AIStrategyResearchRunRecord): Strategy | null {
    const payload = bestIterationPayloadForRecord(record)
    if (!payload) return null
    const fallbackIteration = Math.max(
      Math.trunc(
        optionalNumber(payload.iteration)
        ?? optionalNumber(record.best_iteration)
        ?? record.iteration_count
        ?? 1
      ),
      1
    )
    return strategyFromIterationRecord(record, payload, fallbackIteration)
  }

  function aiResearchRunNeedsAutoRefresh(record: AIStrategyResearchRunRecord) {
    if (!record.paper_trading_started || isLiveTradingPreparedForRecord(record)) return false
    if (isPaperTradingStartFailure(record) || isPaperTradingTargetMissing(record)) return false
    if (liveHandoffLocksPaperActions(record)) return false
    const handoffStatus = liveHandoffStatusForRecord(record)
    if (handoffStatus === 'blocked') return false
    return true
  }

  function shouldAutoRefreshAIResearchRuns() {
    return (
      aiResearchRunsAutoRefreshActive
      && activeTab.value === 'aiResearch'
      && !aiResearchRunsLoading.value
      && !aiResearchRunning.value
      && aiResearchRuns.value.some(aiResearchRunNeedsAutoRefresh)
    )
  }

  function clearAIResearchRunsAutoRefresh() {
    if (!aiResearchRunsAutoRefreshTimer) return
    clearTimeout(aiResearchRunsAutoRefreshTimer)
    aiResearchRunsAutoRefreshTimer = null
  }

  function unrefTimer(timer: ReturnType<typeof setTimeout>) {
    if (typeof timer !== 'object' || timer === null || !('unref' in timer)) return
    const maybeUnref = (timer as { unref?: () => void }).unref
    if (typeof maybeUnref === 'function') maybeUnref.call(timer)
  }

  function scheduleAIResearchRunsAutoRefresh() {
    clearAIResearchRunsAutoRefresh()
    if (!shouldAutoRefreshAIResearchRuns()) return
    const timer = setTimeout(() => {
      aiResearchRunsAutoRefreshTimer = null
      void refreshAIResearchRunsSilently()
    }, AI_RESEARCH_RUNS_AUTO_REFRESH_MS)
    aiResearchRunsAutoRefreshTimer = timer
    unrefTimer(timer)
  }

  async function refreshAIResearchRunsSilently() {
    if (!shouldAutoRefreshAIResearchRuns()) return
    try {
      await loadAIResearchRuns({ showLoading: false })
    } catch {
      scheduleAIResearchRunsAutoRefresh()
    }
  }

  async function loadAIResearchRuns(options: { showLoading?: boolean } = {}) {
    if (aiResearchRunsLoading.value) {
      scheduleAIResearchRunsAutoRefresh()
      return
    }
    const showLoading = options.showLoading ?? true
    if (showLoading) aiResearchRunsLoading.value = true
    try {
      const response = await strategyApi.listAIResearchRuns(undefined, 50)
      aiResearchRuns.value = response.items
      response.items.forEach(hydrateLiveHandoffFromRunRecord)
      syncAIResearchDisplayedOutputWithSelectedProfile()
    } finally {
      if (showLoading) aiResearchRunsLoading.value = false
      scheduleAIResearchRunsAutoRefresh()
    }
  }

  function upsertAIResearchRunRecord(record: AIStrategyResearchRunRecord) {
    hydrateLiveHandoffFromRunRecord(record)
    aiResearchRuns.value = [
      record,
      ...aiResearchRuns.value.filter(item => item.run_id !== record.run_id),
    ].slice(0, 50)
    scheduleAIResearchRunsAutoRefresh()
  }

  function hydrateLiveHandoffFromRunRecord(record: AIStrategyResearchRunRecord) {
    const handoff = record.live_handoff
    if (handoff?.run_id === record.run_id) {
      aiResearchLiveHandoffs[record.run_id] = handoff
      return
    }
    const status = String(record.paper_review_status || '').trim()
    if (status && status !== 'ready_for_live_candidate') {
      delete aiResearchLiveHandoffs[record.run_id]
    }
  }

  async function refreshAIResearchRunRecord(
    runId: string,
    researchWorkspaceId?: string | null
  ) {
    let record: AIStrategyResearchRunRecord | null = null
    try {
      record = await strategyApi.getAIResearchRun(runId, researchWorkspaceId || undefined)
    } catch {
      const response = await strategyApi.listAIResearchRuns(researchWorkspaceId || undefined, 20)
      record = response.items.find(item => item.run_id === runId) ?? null
    }
    if (!record) return null
    upsertAIResearchRunRecord(record)
    applyResearchRunRecordToCurrentResult(record)
    if (aiResearchResult.value?.run_id === record.run_id) {
      void loadAIResearchRunArtifacts(record)
    }
    return record
  }

  function clearAIResearchArtifacts() {
    aiResearchTimeline.value = []
    aiResearchVersions.value = []
    aiResearchVersionCompare.value = null
    aiResearchSelectedVersionIds.value = []
  }

  async function loadAIResearchRunArtifacts(record: AIStrategyResearchRunRecord) {
    await Promise.allSettled([
      loadAIResearchTimeline(record),
      loadAIResearchVersions(record),
      loadAIResearchMandate(record.mandate_id),
    ])
  }

  async function loadAIResearchTimeline(record: AIStrategyResearchRunRecord) {
    aiResearchTimelineLoading.value = true
    try {
      const response = await strategyApi.getAIResearchTimeline(
        record.run_id,
        record.research_workspace_id
      )
      aiResearchTimeline.value = response.items
    } finally {
      aiResearchTimelineLoading.value = false
    }
  }

  async function loadAIResearchVersions(record: AIStrategyResearchRunRecord) {
    aiResearchVersionsLoading.value = true
    try {
      const response = await strategyApi.listAIResearchVersions(
        record.run_id,
        record.research_workspace_id
      )
      aiResearchVersions.value = response.items
      aiResearchSelectedVersionIds.value = response.items.slice(-2).map(item => item.id)
      aiResearchVersionCompare.value = null
    } finally {
      aiResearchVersionsLoading.value = false
    }
  }

  async function compareSelectedAIResearchVersions() {
    if (!aiResearchCanCompareVersions.value) return
    const [leftId, rightId] = aiResearchSelectedVersionIds.value
    aiResearchVersionCompareLoading.value = true
    try {
      aiResearchVersionCompare.value = await strategyApi.compareAIResearchVersions(leftId, rightId)
    } catch {
      ElMessage.error(t('strategy.aiResearchVersionCompareFailed'))
    } finally {
      aiResearchVersionCompareLoading.value = false
    }
  }

  function aiResearchEventTagType(status?: string | null) {
    const normalized = stringFromUnknown(status)
    if (normalized === 'completed' || normalized === 'submitted') return 'success'
    if (normalized === 'failed') return 'danger'
    if (normalized === 'started' || normalized === 'running') return 'warning'
    return 'info'
  }

  function aiResearchVersionStatusTagType(status?: string | null) {
    const normalized = stringFromUnknown(status)
    if (normalized === 'passed') return 'success'
    if (normalized === 'failed') return 'warning'
    return 'info'
  }

  function aiResearchVersionMetric(version: AIStrategyResearchVersion, key: string) {
    return formatMetric(version.backtest_metrics?.[key])
  }

  function aiResearchVersionMetricLabel(key: string) {
    const labels: Record<string, string> = {
      sharpe_ratio: 'Sharpe',
      sharpe: 'Sharpe',
      total_return: '总收益',
      annual_return: '年化收益',
      max_drawdown: '最大回撤',
      total_trades: '交易次数',
    }
    return labels[key] ?? key
  }

  function aiResearchRequestSnapshotFromRunRecord(record: AIStrategyResearchRunRecord) {
    const gates = record.quality_gates || {}
    return {
      prompt: record.prompt,
      workflow_mode: record.workflow_mode ?? 'auto',
      workflow_steps: record.workflow_steps ?? [...AI_RESEARCH_WORKFLOW_STEPS],
      symbol: record.symbol,
      symbol_name: record.symbol_name || '',
      timeframe: record.timeframe || '1d',
      timeframe_n: record.timeframe_n || 1,
      start_date: record.start_date ?? null,
      end_date: record.end_date ?? null,
      target_sharpe: record.target_sharpe,
      min_total_trades: record.min_total_trades,
      max_drawdown_limit: gates.max_drawdown_limit,
      min_total_return: gates.min_total_return,
      min_annual_return: gates.min_annual_return,
      min_win_rate: gates.min_win_rate,
      max_iterations: record.max_iterations,
      out_of_sample_validation: optionalBoolean(gates.out_of_sample_validation, true),
      require_out_of_sample_validation: optionalBoolean(
        gates.require_out_of_sample_validation,
        false
      ),
      out_of_sample_ratio: optionalNumber(gates.out_of_sample_ratio) ?? 0.25,
      min_out_of_sample_sharpe: gates.min_out_of_sample_sharpe,
      min_out_of_sample_trades: gates.min_out_of_sample_trades,
      robustness_validation: optionalBoolean(gates.robustness_validation, true),
      require_robustness_validation: optionalBoolean(
        gates.require_robustness_validation,
        true
      ),
      robustness_methods: stringArrayFromUnknown(gates.robustness_methods).length
        ? stringArrayFromUnknown(gates.robustness_methods)
        : ['monte_carlo'],
      min_robustness_score: optionalNumber(gates.min_robustness_score) ?? 55,
      robustness_monte_carlo_iterations:
        optionalNumber(gates.robustness_monte_carlo_iterations) ?? 300,
      robustness_random_seed: optionalNumber(gates.robustness_random_seed),
      backtest_timeout_seconds: record.backtest_timeout_seconds,
      poll_interval_seconds: record.poll_interval_seconds,
      initial_cash: record.initial_cash,
      commission: record.commission,
      annual_days: record.annual_days,
      calc_method: record.calc_method,
      weight_mode: record.weight_mode,
      research_workspace_id: record.research_workspace_id,
      mandate_id: record.mandate_id,
      seed_strategy_id: record.seed_strategy_id,
      continue_from_run_id: record.continued_from_run_id,
      start_paper_trading: record.paper_trading_started,
      min_paper_trading_days:
        optionalNumber(gates.min_paper_trading_days) ?? DEFAULT_AI_RESEARCH_MIN_PAPER_TRADING_DAYS,
      paper_workspace_name: record.paper_workspace_name,
      group_name: record.group_name,
      knowledge_base_id: record.knowledge_base_id,
      thinking_mode: Boolean(record.thinking_mode),
      continuation_context: record.continuation_context ?? {},
    } as AIStrategyResearchRunRequest & Record<string, unknown>
  }

  function aiResearchTaskFromRunRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyResearchTaskResponse {
    const iterations = (record.iterations || []).filter(isRecord)
    const bestIterationPayload =
      iterations.find(item => optionalNumber(item.iteration) === record.best_iteration)
      ?? null
    const latestIteration = iterations[iterations.length - 1] ?? bestIterationPayload
    return {
      task_id: `run-${record.run_id}`,
      status: 'completed',
      submitted_at: record.started_at,
      started_at: record.started_at,
      completed_at: record.completed_at,
      run_id: record.run_id,
      research_workspace_id: record.research_workspace_id,
      mandate_id: record.mandate_id,
      request_snapshot: aiResearchRequestSnapshotFromRunRecord(record),
      continued_from_run_id: record.continued_from_run_id,
      continuation_source: record.continuation_source,
      continuation_context: record.continuation_context ?? {},
      current_stage: record.pipeline?.current_stage || record.status || 'completed',
      progress: optionalNumber(record.pipeline?.progress) ?? 100,
      current_iteration: record.best_iteration ?? record.iteration_count ?? null,
      iteration_count: record.iteration_count,
      max_iterations: record.max_iterations,
      latest_iteration: latestIteration,
      best_iteration_payload: bestIterationPayload,
      run_status: record.status,
      achieved: record.achieved,
      target_sharpe: record.target_sharpe,
      best_iteration: record.best_iteration,
      best_sharpe: record.best_sharpe,
      best_quality_score: record.best_quality_score,
      best_quality_gate_evaluations: record.best_quality_gate_evaluations ?? [],
      best_diagnostics: record.best_diagnostics,
      best_metrics: record.best_metrics,
      best_strategy_id: record.best_strategy_id,
      best_strategy_name: record.best_strategy_name,
      asset_specs: record.asset_specs,
      backtest_environment: record.backtest_environment,
      paper_workspace_id: record.paper_workspace_id,
      paper_workspace_name: record.paper_workspace_name,
      paper_unit_id: record.paper_unit_id,
      paper_trading_started: record.paper_trading_started,
      paper_monitoring_plan: record.paper_monitoring_plan,
      paper_handoff: record.paper_handoff,
      paper_review_status: record.paper_review_status,
      paper_review_ready_for_live: record.paper_review_ready_for_live,
      paper_reviewed_at: record.paper_reviewed_at,
      paper_review_evaluations: record.paper_review_evaluations,
      paper_review_next_actions: record.paper_review_next_actions,
      live_readiness_checklist: record.live_readiness_checklist,
      live_readiness_expires_at: record.live_readiness_expires_at,
      live_handoff: record.live_handoff,
      live_handoff_approval: record.live_handoff_approval,
      live_workspace_id: record.live_workspace_id,
      live_workspace_name: record.live_workspace_name,
      live_unit_id: record.live_unit_id,
      live_trading_prepared: record.live_trading_prepared,
      live_trading_prepared_at: record.live_trading_prepared_at,
      pipeline: record.pipeline,
      promotion_audit: record.promotion_audit,
      next_actions: record.next_actions,
      message: 'AI research result restored from run history',
    }
  }

  function selectAIResearchRunRecord(
    record: AIStrategyResearchRunRecord,
    options: { keepSelectedProfile?: boolean } = {}
  ) {
    const selectedProfileId = aiResearchSelectedConfigProfileId.value
    hydrateLiveHandoffFromRunRecord(record)
    aiResearchResult.value = researchResultFromRunRecord(record)
    useAIResearchRecord(record)
    resetAIResearchTaskState()
    applyAIResearchTaskStatus(aiResearchTaskFromRunRecord(record))
    if (options.keepSelectedProfile) {
      aiResearchSelectedConfigProfileId.value = selectedProfileId
    } else {
      setAIResearchConfigProfileFromRunRecord(record)
    }
    void loadAIResearchRunArtifacts(record)
  }

  function useAIResearchRecord(record: AIStrategyResearchRunRecord) {
    const gates = record.quality_gates || {}
    aiResearchForm.prompt = record.prompt
    aiResearchForm.workflow_mode = record.workflow_mode === 'prompt' ? 'prompt' : 'auto'
    aiResearchForm.symbol = record.symbol
    aiResearchForm.symbol_name = record.symbol_name || ''
    aiResearchForm.timeframe = record.timeframe || '1d'
    aiResearchForm.timeframe_n = record.timeframe_n || 1
    aiResearchForm.start_date = record.start_date || ''
    aiResearchForm.end_date = record.end_date || ''
    if (typeof record.initial_cash === 'number') {
      aiResearchForm.initial_cash = record.initial_cash
    }
    if (typeof record.commission === 'number') {
      aiResearchForm.commission = record.commission
      aiResearchForm.use_manual_commission = researchRecordUsesManualCommission(record)
    } else {
      aiResearchForm.use_manual_commission = false
    }
    aiResearchForm.annual_days = record.annual_days || 252
    aiResearchForm.calc_method = record.calc_method || 'simple'
    aiResearchForm.weight_mode = record.weight_mode || 'equal'
    aiResearchForm.group_name = record.group_name || record.best_strategy_name || ''
    aiResearchForm.knowledge_base_id = record.knowledge_base_id || ''
    aiResearchForm.thinking_mode = Boolean(record.thinking_mode)
    aiResearchForm.paper_workspace_name = record.paper_workspace_name || ''
    aiResearchForm.trading_workspace_id = record.paper_workspace_id || ''
    aiResearchForm.gateway_config_json = gatewayConfigJsonFromRunRecord(record)
    aiResearchForm.live_workspace_name = record.live_workspace_name || ''
    aiResearchForm.live_trading_workspace_id = record.live_workspace_id || ''
    aiResearchForm.live_gateway_config_json = liveGatewayConfigJsonFromRunRecord(record)
    aiResearchForm.target_sharpe = record.target_sharpe
    aiResearchForm.min_total_trades = record.min_total_trades
    aiResearchForm.use_max_drawdown_limit = typeof gates.max_drawdown_limit === 'number'
    aiResearchForm.max_drawdown_limit = Number(gates.max_drawdown_limit ?? 20)
    aiResearchForm.use_min_total_return = typeof gates.min_total_return === 'number'
    aiResearchForm.min_total_return = Number(gates.min_total_return ?? 0)
    aiResearchForm.use_min_annual_return = typeof gates.min_annual_return === 'number'
    aiResearchForm.min_annual_return = Number(gates.min_annual_return ?? 0)
    aiResearchForm.use_min_win_rate = typeof gates.min_win_rate === 'number'
    aiResearchForm.min_win_rate = Number(gates.min_win_rate ?? 50)
    aiResearchForm.max_iterations = record.max_iterations || 3
    if (typeof record.backtest_timeout_seconds === 'number') {
      aiResearchForm.backtest_timeout_seconds = record.backtest_timeout_seconds
    }
    if (typeof record.poll_interval_seconds === 'number') {
      aiResearchForm.poll_interval_seconds = record.poll_interval_seconds
    }
    aiResearchForm.out_of_sample_validation = optionalBoolean(gates.out_of_sample_validation, true)
    aiResearchForm.require_out_of_sample_validation = optionalBoolean(
      gates.require_out_of_sample_validation,
      false
    )
    aiResearchForm.out_of_sample_ratio_pct = outOfSampleRatioPct(gates.out_of_sample_ratio)
    aiResearchForm.use_min_out_of_sample_sharpe =
      optionalNumber(gates.min_out_of_sample_sharpe) !== null
    aiResearchForm.min_out_of_sample_sharpe = Number(gates.min_out_of_sample_sharpe ?? 0.6)
    aiResearchForm.use_min_out_of_sample_trades =
      optionalNumber(gates.min_out_of_sample_trades) !== null
    aiResearchForm.min_out_of_sample_trades = Number(gates.min_out_of_sample_trades ?? 1)
    aiResearchForm.robustness_validation = optionalBoolean(gates.robustness_validation, true)
    aiResearchForm.require_robustness_validation = optionalBoolean(
      gates.require_robustness_validation,
      true
    )
    const robustnessMethods = stringArrayFromUnknown(gates.robustness_methods)
    aiResearchForm.robustness_methods = robustnessMethods.length ? robustnessMethods : ['monte_carlo']
    aiResearchForm.min_robustness_score = Number(gates.min_robustness_score ?? 55)
    aiResearchForm.robustness_monte_carlo_iterations = Number(
      gates.robustness_monte_carlo_iterations ?? 300
    )
    aiResearchForm.robustness_random_seed = optionalNumber(gates.robustness_random_seed)
    aiResearchForm.min_paper_trading_days = Math.max(
      0,
      Number(gates.min_paper_trading_days ?? aiResearchForm.min_paper_trading_days)
    )
    aiResearchForm.research_workspace_id = record.research_workspace_id || ''
    const bestStrategyId = bestStrategyIdForRecord(record)
    aiResearchForm.seed_strategy_id = bestStrategyId
    aiResearchForm.continue_from_run_id = bestStrategyId ? record.run_id : ''
    aiResearchForm.continuation_source = continuationSourceForRecord(record)
  }

  function syncAIResearchFormFromResult(result: AIStrategyResearchRunResponse | null | undefined) {
    const record = result?.run_record
    if (record) useAIResearchRecord(record)
  }

  function researchRecordUsesManualCommission(record: AIStrategyResearchRunRecord) {
    const environment = record.backtest_environment
    if (!isRecord(environment)) return false
    return String(environment.commission_source || '').trim() === 'user_override'
  }

  function resolvedAIResearchTaskBacktestEnvironment(
    task: AIStrategyResearchTaskResponse,
    snapshot: Record<string, unknown>
  ) {
    if (isRecord(task.backtest_environment)) return task.backtest_environment
    if (isRecord(snapshot.backtest_environment)) return snapshot.backtest_environment
    return null
  }

  function aiResearchTaskExplicitFields(task: AIStrategyResearchTaskResponse) {
    return Array.isArray(task.request_explicit_fields)
      ? task.request_explicit_fields.map(item => String(item).trim()).filter(Boolean)
      : []
  }

  function aiResearchTaskUsesManualCommission(
    task: AIStrategyResearchTaskResponse,
    snapshot: Record<string, unknown>
  ) {
    const environment = resolvedAIResearchTaskBacktestEnvironment(task, snapshot)
    if (environment) {
      const source = String(environment.commission_source || '').trim()
      if (source) return source === 'user_override'
    }
    const explicitFields = aiResearchTaskExplicitFields(task)
    if (explicitFields.length) return explicitFields.includes('commission')
    return optionalNumber(snapshot.commission) !== null
  }

  function aiResearchTaskRestoredCommission(
    task: AIStrategyResearchTaskResponse,
    snapshot: Record<string, unknown>
  ) {
    const environment = resolvedAIResearchTaskBacktestEnvironment(task, snapshot)
    const environmentCommission = environment ? optionalNumber(environment.commission) : null
    return environmentCommission ?? optionalNumber(snapshot.commission)
  }

  function enabledQualityGate(enabled: boolean, value: number) {
    return enabled ? value : null
  }

  function researchIterationNextActions(item: AIStrategyResearchRunResponse['iterations'][number]) {
    const nextActions = item.next_actions ?? []
    const improvementPlan = item.improvement_plan ?? item.diagnostics?.improvement_plan ?? []
    return [...new Set([...nextActions, ...improvementPlan])]
  }

  function iterationProgress(item: AIStrategyResearchIteration) {
    const progress = item.diagnostics?.iteration_progress
    return isRecord(progress) ? progress as AIStrategyIterationProgress : null
  }

  function iterationProgressLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    const labels: Record<string, string> = {
      baseline: '基准',
      improved: '改善',
      regressed: '退化',
      stalled: '停滞',
    }
    return labels[normalized] ?? aiResearchStageLabel(normalized || 'baseline')
  }

  function iterationProgressTagType(status?: string | null) {
    const normalized = String(status || '').trim()
    if (normalized === 'improved') return 'success'
    if (normalized === 'regressed') return 'danger'
    if (normalized === 'stalled') return 'warning'
    return 'info'
  }

  function iterationProgressDeltaText(
    progress: AIStrategyIterationProgress | null,
    key: 'sharpe_delta' | 'quality_score_delta'
  ) {
    const value = optionalNumber(progress?.[key])
    if (value === null) return ''
    const sign = value > 0 ? '+' : ''
    return `${sign}${formatMetric(value)}`
  }

  function canStartPaperFromRecord(record: AIStrategyResearchRunRecord) {
    return Boolean(
      record.achieved
      && bestStrategyIdForRecord(record)
      && (!record.paper_trading_started || isPaperTradingTargetMissing(record))
    )
  }

  function canReviewPaperFromRecord(record: AIStrategyResearchRunRecord) {
    return Boolean(
      record.paper_trading_started
      && record.paper_workspace_id
      && record.paper_unit_id
      && !isPaperTradingTargetMissing(record)
      && !liveHandoffLocksPaperActions(record)
    )
  }

  function canBuildLiveHandoffFromRecord(record: AIStrategyResearchRunRecord) {
    const review = paperReviewForRecord(record)
    return Boolean(
      record.paper_trading_started
      && review?.ready_for_live
      && review.status === 'ready_for_live_candidate'
      && !liveHandoffLocksPaperActions(record)
    )
  }

  function liveHandoffForRunId(runId: string): AIStrategyLiveHandoffPackage | null {
    return aiResearchLiveHandoffs[runId] ?? null
  }

  function liveHandoffForRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyLiveHandoffPackage | null {
    return liveHandoffForRunId(record.run_id) ?? record.live_handoff ?? null
  }

  function liveHandoffStatusForRecord(record: AIStrategyResearchRunRecord) {
    const handoff = liveHandoffForRecord(record)
    return String(handoff?.status || record.pipeline?.live_handoff_status || '').trim()
  }

  function liveHandoffLocksPaperActions(record: AIStrategyResearchRunRecord) {
    const status = liveHandoffStatusForRecord(record)
    return Boolean(
      isLiveTradingPreparedForRecord(record)
      || record.live_handoff_approval
      || ['ready_for_approval', 'approved_for_live', 'approval_rejected'].includes(status)
    )
  }

  function canApproveLiveHandoff(handoff: AIStrategyLiveHandoffPackage | null | undefined) {
    return Boolean(
      handoff
      && handoff.ready_for_live
      && handoff.status === 'ready_for_approval'
      && !handoff.approval
      && !handoff.approval_status
    )
  }

  function canPrepareLiveTradingFromRecord(record: AIStrategyResearchRunRecord) {
    const handoff = liveHandoffForRecord(record)
    return Boolean(
      handoff
      && handoff.ready_for_live
      && handoff.status === 'approved_for_live'
      && handoff.approval?.approved
      && !isLiveTradingPreparedForRecord(record)
    )
  }

  function liveHandoffApprovalLabel(handoff: AIStrategyLiveHandoffPackage | null | undefined) {
    const approval = handoff?.approval
    if (!approval) return ''
    if (approval.approved) return '已批准'
    if (approval.decision === 'rejected') return '已驳回'
    return approval.decision || ''
  }

  function liveTradingPrepareSummary(record: AIStrategyResearchRunRecord | null | undefined) {
    if (!record) return ''
    const unitId = record.live_unit_id || record.pipeline?.live_unit_id || '实盘单元'
    const preparedAt = record.live_trading_prepared_at
      || record.pipeline?.live_trading_prepared_at
      || liveTradingPreparedAtFromPipeline(record.pipeline)
    const lockText = record.pipeline?.live_unit_locked === false ? '待确认锁定' : '默认锁定'
    return `${unitId} 已准备，${lockText}${preparedAt ? `，${formatDateTime(preparedAt)}` : ''}`
  }

  function isLiveTradingPreparedForRecord(record: AIStrategyResearchRunRecord | null | undefined) {
    return Boolean(
      record?.live_trading_prepared
      || record?.pipeline?.live_trading_prepared
      || record?.pipeline?.current_stage === 'live_trading_prepare'
    )
  }

  function liveTradingPreparedAtFromPipeline(
    pipeline: AIStrategyPipelineSummary | null | undefined
  ) {
    const step = [...(pipeline?.steps ?? [])]
      .reverse()
      .find(item => item.key === 'live_trading_prepare')
    return stringFromUnknown(step?.prepared_at)
  }

  function isPaperTradingTargetMissing(record: AIStrategyResearchRunRecord) {
    const status = String(record.paper_review_status || '').trim()
    return Boolean(
      ['paper_workspace_missing', 'paper_unit_missing'].includes(status)
      || (
        record.paper_trading_started
        && (!record.paper_workspace_id || !record.paper_unit_id)
      )
    )
  }

  function paperStartButtonLabel(record: AIStrategyResearchRunRecord) {
    if (isPaperTradingTargetMissing(record)) return '重启模拟'
    if (isPaperTradingStartFailure(record)) return '重试模拟'
    return '启动模拟'
  }

  function canContinueResearchFromPaperReview(record: AIStrategyResearchRunRecord) {
    return canContinueResearchFromPaperIssue(record)
  }

  function canContinueResearchFromPaperIssue(record: AIStrategyResearchRunRecord) {
    const source = continuationSourceForRecord(record)
    return Boolean(
      bestStrategyIdForRecord(record) &&
      (
        source === 'paper_review'
        || source === 'paper_trading_failed'
        || source === 'live_handoff_rejected'
      )
    )
  }

  function canContinueResearchFromRunRecord(record: AIStrategyResearchRunRecord) {
    return Boolean(
      bestStrategyIdForRecord(record)
      && !record.achieved
      && (
        record.iteration_count > 0
        || (record.iterations ?? []).length > 0
        || record.status === 'backtest_submission_failed'
        || record.status === 'cancelled'
        || record.status === 'interrupted'
        || record.pipeline?.current_stage === 'backtest_failed'
        || record.pipeline?.current_stage === 'cancelled'
        || record.pipeline?.current_stage === 'interrupted'
      )
    )
  }

  function continuationSourceForRecord(record: AIStrategyResearchRunRecord) {
    if (isLiveHandoffRejected(record)) return 'live_handoff_rejected'
    if (
      ['needs_research_review', 'live_readiness_expired'].includes(
        String(record.paper_review_status || '')
      )
      && !record.paper_review_ready_for_live
    ) {
      return 'paper_review'
    }
    if (isPaperTradingStartFailure(record)) return 'paper_trading_failed'
    if (
      canContinueResearchFromRunRecord(record)
      && (record.status === 'cancelled' || record.pipeline?.current_stage === 'cancelled')
    ) {
      return 'research_cancelled'
    }
    if (
      canContinueResearchFromRunRecord(record)
      && (record.status === 'interrupted' || record.pipeline?.current_stage === 'interrupted')
    ) {
      return 'research_interrupted'
    }
    if (canContinueResearchFromRunRecord(record)) return 'research_failure'
    return ''
  }

  function continuationSourceLabel(source?: string | null) {
    if (source === 'paper_review') return '从模拟复核反馈继续'
    if (source === 'paper_trading_failed') return '从模拟启动失败继续'
    if (source === 'live_handoff_rejected') return '从实盘交接驳回继续'
    if (source === 'research_cancelled') return '从已取消任务继续'
    if (source === 'research_interrupted') return '从中断任务继续'
    if (source === 'research_failure') return '从未达标结果继续'
    return '从历史最佳策略继续'
  }

  function continuationSummaryForRecord(record: AIStrategyResearchRunRecord) {
    const context = isRecord(record.continuation_context) ? record.continuation_context : {}
    const source = stringFromUnknown(record.continuation_source, stringFromUnknown(context.source))
    const parentRunId = stringFromUnknown(record.continued_from_run_id, stringFromUnknown(context.run_id))
    if (!source && !parentRunId) return ''
    const label = continuationSourceLabel(source)
    return parentRunId ? `${label} · 上轮 ${parentRunId}` : label
  }

  function aiResearchContinuationRecord(runId: string) {
    const currentRecord = aiResearchResult.value?.run_record
    if (currentRecord?.run_id === runId) return currentRecord
    return aiResearchRuns.value.find(record => record.run_id === runId) ?? null
  }

  function aiResearchContinuationContext(): Record<string, unknown> | undefined {
    const runId = aiResearchForm.continue_from_run_id.trim()
    const source = aiResearchForm.continuation_source.trim()
    if (!runId || !source) return undefined

    const record = aiResearchContinuationRecord(runId)
    const context: Record<string, unknown> = { source, run_id: runId }
    if (!record) return context

    const failures = continuationQualityGateFailures(record, source)
    if (failures.length) context.quality_gate_failures = failures
    if (isRecord(record.best_metrics)) context.metrics = { ...record.best_metrics }
    if (record.next_actions?.length) context.next_actions = [...record.next_actions]
    if (record.pipeline) context.pipeline = { ...record.pipeline }
    if (record.asset_specs) context.asset_specs = { ...record.asset_specs }
    if (record.backtest_environment) context.backtest_environment = { ...record.backtest_environment }
    if (record.best_diagnostics) context.diagnostics = { ...record.best_diagnostics }

    if (source === 'paper_review') {
      context.paper_review_status = record.paper_review_status
      context.paper_reviewed_at = record.paper_reviewed_at
      const evaluations = [...(record.paper_review_evaluations ?? [])].map(item => ({ ...item }))
      if (evaluations.length) context.paper_review_evaluations = evaluations
      if (record.paper_review_next_actions?.length) {
        context.paper_review_next_actions = [...record.paper_review_next_actions]
      }
    } else if (source === 'paper_trading_failed') {
      context.paper_trading_error = stringFromUnknown(record.pipeline?.paper_trading_error)
    } else if (source === 'live_handoff_rejected') {
      const handoff = liveHandoffForRecord(record) ?? record.live_handoff
      context.live_handoff_status = liveHandoffStatusForRecord(record) || 'approval_rejected'
      if (handoff) context.live_handoff = { ...handoff }
      if (record.live_handoff_approval) {
        context.live_handoff_approval = { ...record.live_handoff_approval }
      }
      if (record.live_readiness_checklist?.length) {
        context.live_readiness_checklist = record.live_readiness_checklist.map(item => ({ ...item }))
      }
      if (record.paper_review_evaluations?.length) {
        context.paper_review_evaluations = record.paper_review_evaluations.map(item => ({ ...item }))
      }
      context.paper_review_status = record.paper_review_status
      context.paper_reviewed_at = record.paper_reviewed_at
    } else {
      const iteration = continuationIterationPayload(record)
      if (iteration?.failure_reason) {
        context.failure_reason = stringFromUnknown(iteration.failure_reason)
      }
      if (iteration?.quality_gate_failures) {
        context.previous_quality_gate_failures = stringListFromUnknown(
          iteration.quality_gate_failures
        )
      }
    }

    return context
  }

  function continuationQualityGateFailures(
    record: AIStrategyResearchRunRecord,
    source: string
  ) {
    const failures = new Set<string>()
    if (source === 'paper_review') {
      const failedEvaluations = (record.paper_review_evaluations ?? []).filter(
        item => String(item.status || '') === 'failed' || item.passed === false
      )
      failedEvaluations.forEach(item => {
        const failure = paperReviewFailureText(item)
        if (failure) failures.add(failure)
      })
      if (!failures.size && record.paper_review_status === 'live_readiness_expired') {
        failures.add('实盘候选复核已过期，需要重新复核模拟交易指标后再进入实盘审批。')
      }
      for (const item of record.paper_review_next_actions ?? []) {
        if (item.trim()) failures.add(item.trim())
      }
    } else if (source === 'paper_trading_failed') {
      const error = stringFromUnknown(record.pipeline?.paper_trading_error)
      failures.add(error ? `模拟交易启动失败：${error}` : '模拟交易启动失败。')
    } else if (source === 'live_handoff_rejected') {
      failures.add('实盘交接审批被驳回，需要处理审批意见后重新投研并重新进入模拟复核。')
      const comment = stringFromUnknown(record.live_handoff_approval?.comment)
      if (comment) failures.add(`实盘交接驳回意见：${comment}`)
      for (const item of record.next_actions ?? []) {
        if (item.trim()) failures.add(item.trim())
      }
    } else {
      const iteration = continuationIterationPayload(record)
      stringListFromUnknown(iteration?.quality_gate_failures).forEach(item => failures.add(item))
      const reason = stringFromUnknown(iteration?.failure_reason)
      if (reason) failures.add(reason)
      for (const item of record.next_actions ?? []) {
        if (item.trim()) failures.add(item.trim())
      }
    }
    return [...failures]
  }

  function paperReviewFailureText(item: AIStrategyPaperTradingRuleEvaluation) {
    const label = stringFromUnknown(item.label, stringFromUnknown(item.key, '模拟交易复核'))
    const actual = optionalNumber(item.actual)
    const threshold = optionalNumber(item.threshold)
    const actualText = actual === null ? '' : `实际 ${formatMetric(actual)}`
    const thresholdText = threshold === null ? '' : `阈值 ${formatMetric(threshold)}`
    const action = stringFromUnknown(item.action)
    const parts = [actualText, thresholdText].filter(Boolean).join('，')
    return `${label}未通过${parts ? `（${parts}）` : ''}${action ? `，${action}` : ''}`
  }

  function continuationIterationPayload(record: AIStrategyResearchRunRecord) {
    const iterations = record.iterations.filter(isRecord)
    if (!iterations.length) return null
    const bestIteration = optionalNumber(record.best_iteration)
    if (bestIteration !== null) {
      const bestPayload = iterations.find(item => optionalNumber(item.iteration) === bestIteration)
      if (bestPayload) return bestPayload
    }
    return iterations[iterations.length - 1]
  }

  function stringListFromUnknown(value: unknown) {
    if (!Array.isArray(value)) return []
    return value.map(item => stringFromUnknown(item)).filter(Boolean)
  }

  function isLiveHandoffRejected(record: AIStrategyResearchRunRecord) {
    const handoff = liveHandoffForRecord(record) ?? record.live_handoff
    const approval = handoff?.approval ?? record.live_handoff_approval
    return Boolean(
      approval?.decision === 'rejected'
      || handoff?.approval_status === 'rejected'
      || handoff?.status === 'approval_rejected'
      || record.pipeline?.live_handoff_status === 'approval_rejected'
    )
  }

  function isPaperTradingStartFailure(record: AIStrategyResearchRunRecord) {
    return Boolean(
      record.pipeline?.current_stage === 'paper_trading_failed'
      || record.pipeline?.paper_trading_error
    )
  }

  function pipelineStage(record: AIStrategyResearchRunRecord) {
    if (record.live_trading_prepared || record.pipeline?.current_stage === 'live_trading_prepare') {
      return 'live_trading_prepare'
    }
    if (record.live_handoff || record.pipeline?.current_stage === 'live_handoff') return 'live_handoff'
    if (record.paper_review_ready_for_live) return 'live_candidate'
    if (record.paper_review_status) return 'paper_review'
    if (record.paper_trading_started) return 'paper_trading'
    if (record.pipeline?.current_stage) return record.pipeline.current_stage
    if (record.achieved) return 'quality_achieved'
    if (record.status === 'timeout') return 'backtest_timeout'
    if (record.status === 'cancelled') return 'cancelled'
    return record.iteration_count > 0 ? 'research_iteration' : ''
  }

  function pipelineStageLabel(record: AIStrategyResearchRunRecord) {
    return aiResearchStageLabel(pipelineStage(record))
  }

  function aiResearchRunStatusLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_RUN_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
  }

  function paperReviewStatusLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_PAPER_REVIEW_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
  }

  function paperReviewRuleStatusLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_PAPER_RULE_STATUS_LABELS[normalized] ?? liveReadinessStatusLabel(normalized)
  }

  function paperReviewRuleGapText(rule: AIStrategyPaperTradingRuleEvaluation) {
    const distance = optionalNumber(rule.distance_to_pass ?? rule.gap)
    if (distance !== null && distance > 0) {
      return `差距 ${formatMetric(distance)}`
    }
    const margin = optionalNumber(rule.margin)
    if (margin !== null && margin > 0) {
      return `余量 ${formatMetric(margin)}`
    }
    return ''
  }

  function paperReviewDispositionLabel(review: AIStrategyPaperTradingReview | null | undefined) {
    const status = String(review?.status || '').trim()
    if (review?.ready_for_live) return '实盘候选'
    if (status === 'live_readiness_expired') return '重新复核'
    if (status === 'needs_research_review') return '需要重新投研'
    if (['paper_workspace_missing', 'paper_unit_missing', 'monitoring_plan_missing'].includes(status)) {
      return '检查模拟'
    }
    if (status === 'monitoring') return '继续观察'
    return '待处理'
  }

  function liveReadinessStatusLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_LIVE_READINESS_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
  }

  function liveHandoffStatusLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_LIVE_HANDOFF_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
  }

  function pipelineStepStatusLabel(status?: string | null) {
    const normalized = String(status || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_PIPELINE_STEP_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
  }

  function pipelineStepTagType(status?: string | null) {
    const normalized = String(status || '').trim()
    if (normalized === 'completed') return 'success'
    if (normalized === 'failed') return 'danger'
    if (normalized === 'running') return 'warning'
    return 'info'
  }

  function pipelineStepIterationText(step: AIStrategyPipelineStep) {
    const count = typeof step.iteration_count === 'number' ? step.iteration_count : null
    const max = typeof step.max_iterations === 'number' ? step.max_iterations : null
    if (count === null && max === null) return ''
    if (count !== null && max !== null) return `${count}/${max} 轮`
    if (count !== null) return `${count} 轮`
    return `最多 ${max} 轮`
  }

  function pipelineStepDetailText(
    step: AIStrategyPipelineStep,
    pipeline?: AIStrategyPipelineSummary | null
  ) {
    const details: string[] = []
    const iteration = pipelineStepIterationText(step)
    if (iteration) details.push(iteration)
    if (step.key === 'validation' && step.validation_status) {
      details.push(`样本外 ${outOfSampleStatusLabel(step.validation_status)}`)
    }
    if (step.review_status) details.push(`复核 ${paperReviewStatusLabel(step.review_status)}`)
    if (step.key === 'live_handoff') {
      const handoffStatus = stringFromUnknown(pipeline?.live_handoff_status)
      if (handoffStatus) details.push(`交接 ${liveHandoffStatusLabel(handoffStatus)}`)
      const blockerCount = optionalNumber(pipeline?.live_handoff_blocker_count)
      if (blockerCount !== null && blockerCount > 0) details.push(`${formatMetric(blockerCount, 0)} 项阻塞`)
    }
    return details.join(' ')
  }

  function aiResearchStageLabel(stage?: string | null) {
    const normalized = String(stage || '').trim()
    if (!normalized) return ''
    return AI_RESEARCH_STAGE_LABELS[normalized] ?? normalized.replace(/_/g, ' ')
  }

  function liveReadinessChecklistForReview(
    review: AIStrategyPaperTradingReview | null | undefined
  ): AIStrategyLiveReadinessItem[] {
    if (!review) return []
    if (review.live_readiness_checklist?.length) return review.live_readiness_checklist
    return liveReadinessChecklistFromPayload(review.pipeline?.live_readiness_checklist)
  }

  function liveReadinessChecklistForRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyLiveReadinessItem[] {
    if (record.live_readiness_checklist?.length) return record.live_readiness_checklist
    const pipelineChecklist = liveReadinessChecklistFromPayload(
      record.pipeline?.live_readiness_checklist
    )
    if (pipelineChecklist.length) return pipelineChecklist
    if (isRecord(record.paper_handoff)) {
      return liveReadinessChecklistFromPayload(record.paper_handoff.live_readiness_checklist)
    }
    return []
  }

  function liveReadinessExpiresAtForRecord(record: AIStrategyResearchRunRecord): string | null {
    if (record.live_readiness_expires_at) return record.live_readiness_expires_at
    if (typeof record.pipeline?.live_readiness_expires_at === 'string') {
      return record.pipeline.live_readiness_expires_at
    }
    if (isRecord(record.paper_handoff) && typeof record.paper_handoff.live_readiness_expires_at === 'string') {
      return record.paper_handoff.live_readiness_expires_at
    }
    return null
  }

  function paperReviewLockFromPayload(payload: unknown): AIStrategyPaperReviewLock | null {
    if (!isRecord(payload)) return null
    if (!payload.status && !payload.paper_unit_id && !payload.stop_results) return null
    return {
      ...payload,
      failed_rules: arrayFromUnknown<AIStrategyPaperTradingRuleEvaluation>(payload.failed_rules),
      stop_results: arrayFromUnknown<Record<string, unknown>>(payload.stop_results),
      next_actions: stringArrayFromUnknown(payload.next_actions),
    } as AIStrategyPaperReviewLock
  }

  function paperReviewLockForRecord(
    record: AIStrategyResearchRunRecord | null | undefined
  ): AIStrategyPaperReviewLock | null {
    if (!record) return null
    return paperReviewLockFromPayload(record.pipeline?.paper_review_lock)
      ?? paperReviewLockFromPayload(
        isRecord(record.paper_handoff) ? record.paper_handoff.paper_review_lock : null
      )
  }

  function paperReviewLockSummary(lock: AIStrategyPaperReviewLock | null | undefined) {
    if (!lock) return ''
    const unitId = stringFromUnknown(lock.paper_unit_id, '模拟单元')
    const status = paperReviewStatusLabel(lock.status)
    return `${unitId} ${status || '复核未通过'}，已自动停止并锁定`
  }

  function paperReviewLockStopResultText(lock: AIStrategyPaperReviewLock | null | undefined) {
    const results = lock?.stop_results ?? []
    if (!results.length) return ''
    return results
      .map(item => {
        const unitId = stringFromUnknown(item.unit_id, stringFromUnknown(lock?.paper_unit_id, '模拟单元'))
        if (item.cancelled === true) return `${unitId} 已取消`
        const status = stringFromUnknown(item.status)
        if (status) return `${unitId} ${status}`
        return unitId
      })
      .join('；')
  }

  function liveReadinessChecklistFromPayload(payload: unknown): AIStrategyLiveReadinessItem[] {
    if (!Array.isArray(payload)) return []
    return payload.filter(isRecord).map((item, index) => ({
      key: String(item.key || `item-${index}`),
      label: String(item.label || item.key || `检查项 ${index + 1}`),
      status: String(item.status || 'pending'),
      evidence: String(item.evidence || ''),
      action: String(item.action || ''),
      details: isRecord(item.details) ? item.details : undefined,
    }))
  }

  function promotionAuditFromPayload(payload: unknown): AIStrategyPromotionAuditItem[] {
    if (!Array.isArray(payload)) return []
    return payload.filter(isRecord).map((item, index) => ({
      key: String(item.key || `audit-${index}`),
      label: String(item.label || item.key || `审计项 ${index + 1}`),
      status: String(item.status || 'pending'),
      evidence: String(item.evidence || ''),
      action: String(item.action || ''),
      details: isRecord(item.details) ? item.details : undefined,
    }))
  }

  function clearAIResearchContinuation() {
    aiResearchForm.research_workspace_id = ''
    aiResearchForm.seed_strategy_id = ''
    aiResearchForm.continue_from_run_id = ''
    aiResearchForm.continuation_source = ''
  }

  function paperHandoffRunRecordAssetSpecs(
    record: AIStrategyResearchRunRecord,
    handoff: Record<string, unknown>
  ): Record<string, Record<string, unknown>> | undefined {
    const specs: Record<string, Record<string, unknown>> = {}
    const merge = (source: unknown) => {
      if (!isRecord(source)) return
      for (const [symbol, spec] of Object.entries(source)) {
        if (isRecord(spec)) specs[symbol] = { ...spec }
      }
    }
    merge(record.asset_specs)
    merge(handoff.asset_specs)
    return Object.keys(specs).length ? specs : record.asset_specs
  }

  function paperHandoffRunRecordBacktestEnvironment(
    record: AIStrategyResearchRunRecord,
    handoff: Record<string, unknown>
  ): Record<string, unknown> | undefined {
    const environment: Record<string, unknown> = {}
    if (isRecord(record.backtest_environment)) Object.assign(environment, record.backtest_environment)
    if (isRecord(handoff.backtest_environment)) Object.assign(environment, handoff.backtest_environment)
    return Object.keys(environment).length ? environment : record.backtest_environment
  }

  function paperStartedRunRecord(
    record: AIStrategyResearchRunRecord,
    paper: AIStrategyPaperTradingStart
  ): AIStrategyResearchRunRecord {
    const handoff = isRecord(paper.handoff) ? paper.handoff : {}
    return {
      ...record,
      asset_specs: paperHandoffRunRecordAssetSpecs(record, handoff),
      backtest_environment: paperHandoffRunRecordBacktestEnvironment(record, handoff),
      paper_trading_started: paper.started,
      paper_workspace_id: paper.workspace.id,
      paper_workspace_name: paper.workspace.name,
      paper_unit_id: paper.unit.id,
      paper_handoff: handoff,
      paper_monitoring_plan:
        paperMonitoringPlanFromHandoff(handoff) ?? record.paper_monitoring_plan,
      paper_review_status: null,
      paper_review_ready_for_live: false,
      paper_reviewed_at: null,
      paper_review_evaluations: [],
      paper_review_next_actions: [],
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      pipeline: paperStartedPipeline(record),
      next_actions: [
        '模拟交易已启动，正在等待后端同步模拟复核状态。',
        '如果同步暂不可用，可稍后手动复核模拟交易监控指标。',
      ],
    }
  }

  function paperStartedPipeline(record: AIStrategyResearchRunRecord) {
    return {
      current_stage: 'paper_trading',
      status: record.status,
      progress: 80,
      ready_for_live: false,
      paper_trading_error: null,
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      workflow_mode: record.workflow_mode ?? 'auto',
      workflow_steps: record.workflow_steps ?? [...AI_RESEARCH_WORKFLOW_STEPS],
      steps: [
        { key: 'strategy_idea', label: t('strategy.aiResearchHeroStepIdea'), status: 'completed' },
        { key: 'draft', label: t('strategy.aiResearchStageDraft'), status: 'completed' },
        {
          key: 'backtest_loop',
          label: t('strategy.aiResearchHeroStepBacktest'),
          status: record.iteration_count > 0 ? 'completed' : 'pending',
          iteration_count: record.iteration_count,
          max_iterations: record.max_iterations,
        },
        {
          key: 'strategy_review',
          label: t('strategy.aiResearchStageReview'),
          status: record.iteration_count > 0 ? 'completed' : 'pending',
          iteration_count: record.iteration_count,
        },
        {
          key: 'optimization_loop',
          label: t('strategy.aiResearchStageOptimization'),
          status: record.iteration_count > 1 ? 'completed' : record.achieved ? 'skipped' : 'running',
          iteration_count: record.iteration_count,
          max_iterations: record.max_iterations,
        },
        {
          key: 'quality_gate',
          label: t('strategy.aiResearchQualityGates'),
          status: record.achieved ? 'completed' : 'running',
        },
        {
          key: 'paper_trading',
          label: t('strategy.aiResearchPaperStatus'),
          status: 'completed',
          error: null,
        },
        {
          key: 'paper_review',
          label: t('strategy.aiResearchPaperReview'),
          status: 'pending',
          review_status: null,
        },
      ],
    }
  }

  function paperTradingStartError(paper: AIStrategyPaperTradingStart) {
    const status = String(paper.run_result?.status || '').trim()
    if (status) return `Paper trading run finished with status ${status}`
    return 'Paper trading run did not return a runnable task'
  }

  function paperStartFailedRunRecord(
    record: AIStrategyResearchRunRecord,
    paper: AIStrategyPaperTradingStart
  ): AIStrategyResearchRunRecord {
    const error = paperTradingStartError(paper)
    const previousSteps = record.pipeline?.steps ?? []
    const steps = previousSteps.some(step => step.key === 'paper_trading')
      ? previousSteps.map(step =>
          step.key === 'paper_trading'
            ? { ...step, status: 'failed', error }
            : step
        )
      : [
          ...previousSteps,
          {
            key: 'paper_trading',
            label: t('strategy.aiResearchPaperStatus'),
            status: 'failed',
            error,
          },
        ]
    return {
      ...paperStartedRunRecord(record, paper),
      paper_trading_started: false,
      paper_review_status: null,
      paper_review_ready_for_live: false,
      paper_reviewed_at: null,
      paper_review_evaluations: [],
      paper_review_next_actions: [],
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      pipeline: {
        current_stage: 'paper_trading_failed',
        status: record.status,
        progress: record.pipeline?.progress ?? 92,
        ready_for_live: false,
        paper_trading_error: error,
        live_readiness_checklist: [],
        live_readiness_expires_at: null,
        steps,
      },
      next_actions: [
        `模拟交易启动错误：${error}`,
        '检查交易工作区、网关配置、策略脚本依赖和资产参数后可重试模拟。',
        '如果启动问题来自策略脚本或交易环境假设，可从该记录继续投研。',
      ],
    }
  }

  function applyPaperStartToCurrentResult(
    runId: string,
    paper: AIStrategyPaperTradingStart,
    runRecord: AIStrategyResearchRunRecord
  ) {
    const current = aiResearchResult.value
    if (!current || current.run_id !== runId) return
    aiResearchResult.value = {
      ...current,
      paper_trading: paper,
      paper_monitoring_plan:
        paperMonitoringPlanFromHandoff(paper.handoff) ?? current.paper_monitoring_plan,
      pipeline: runRecord.pipeline ?? current.pipeline,
      promotion_audit: runRecord.promotion_audit ?? current.promotion_audit,
      next_actions: runRecord.next_actions ?? current.next_actions,
      run_record: runRecord,
    }
  }

  function applyResearchRunRecordToCurrentResult(runRecord: AIStrategyResearchRunRecord) {
    const current = aiResearchResult.value
    if (!current || current.run_id !== runRecord.run_id) return
    hydrateLiveHandoffFromRunRecord(runRecord)
    const restored = researchResultFromRunRecord(runRecord)
    const keepLocalFailedPaper = Boolean(
      !restored.paper_trading
      && isPaperTradingStartFailure(runRecord)
      && current.paper_trading?.started === false
    )
    aiResearchResult.value = {
      ...current,
      ...restored,
      research_workspace: current.research_workspace ?? restored.research_workspace,
      iterations: restored.iterations.length ? restored.iterations : current.iterations,
      best_strategy: current.best_strategy ?? restored.best_strategy,
      paper_trading: restored.paper_trading ?? (keepLocalFailedPaper ? current.paper_trading : null),
      message: current.message,
    }
  }

  function workspaceFromResearchRunRecord(record: AIStrategyResearchRunRecord): Workspace {
    return {
      id: record.research_workspace_id,
      user_id: '',
      name: `AI投研 - ${record.symbol}`,
      description: null,
      workspace_type: 'research',
      settings: { ai_research: { runs: [record] } },
      trading_config: {},
      unit_count: 0,
      completed_count: record.iteration_count,
      status: 'completed',
      created_at: record.started_at,
      updated_at: record.completed_at,
    }
  }

  function researchResultFromRunRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyResearchRunResponse {
    const iterations = researchIterationsFromRunRecord(record)
    const snapshotBestStrategy = bestStrategyFromRunRecord(record)
    return {
      run_id: record.run_id,
      status: record.status,
      achieved: record.achieved,
      target_sharpe: record.target_sharpe,
      started_at: record.started_at,
      completed_at: record.completed_at,
      best_iteration: record.best_iteration,
      best_quality_score: record.best_quality_score,
      best_quality_gate_evaluations: record.best_quality_gate_evaluations ?? [],
      best_diagnostics: record.best_diagnostics ?? {},
      best_metrics: record.best_metrics ?? {},
      research_workspace: workspaceFromResearchRunRecord(record),
      iterations,
      best_strategy: snapshotBestStrategy?.code?.trim() ? snapshotBestStrategy : null,
      paper_trading: paperTradingFromRunRecord(record),
      paper_monitoring_plan: record.paper_monitoring_plan ?? [],
      pipeline: record.pipeline,
      promotion_audit: promotionAuditFromPayload(record.promotion_audit),
      run_record: record,
      next_actions: record.next_actions ?? [],
      message: 'AI research result restored from run history',
    }
  }

  function researchResultFromTaskSummary(
    task: AIStrategyResearchTaskResponse
  ): AIStrategyResearchRunResponse | null {
    if (!task.run_id || !task.research_workspace_id) return null
    const request: Record<string, unknown> = isRecord(task.request_snapshot)
      ? task.request_snapshot
      : {}
    const latestIteration = isRecord(task.latest_iteration) ? task.latest_iteration : null
    const bestIterationPayload = isRecord(task.best_iteration_payload)
      ? task.best_iteration_payload
      : null
    const taskIterations: Record<string, unknown>[] = []
    const appendTaskIteration = (payload: Record<string, unknown> | null) => {
      if (!payload) return
      const iteration = optionalNumber(payload.iteration)
      if (
        iteration !== null
        && taskIterations.some(item => optionalNumber(item.iteration) === iteration)
      ) {
        return
      }
      taskIterations.push(payload)
    }
    appendTaskIteration(bestIterationPayload)
    appendTaskIteration(latestIteration)
    const bestMetrics = isRecord(task.best_metrics) ? task.best_metrics : {}
    const bestSharpe = optionalNumber(task.best_sharpe)
      ?? optionalNumber(bestMetrics.sharpe_ratio)
      ?? optionalNumber(bestMetrics.sharpe)
      ?? optionalNumber(latestIteration?.sharpe_ratio)
      ?? optionalNumber(latestIteration?.sharpe)
      ?? 0
    const bestIteration = optionalNumber(task.best_iteration)
      ?? optionalNumber(bestIterationPayload?.iteration)
      ?? optionalNumber(latestIteration?.iteration)
      ?? optionalNumber(task.current_iteration)
      ?? null
    const achieved = optionalBoolean(
      task.achieved,
      Boolean(task.paper_trading_started && String(task.status || '').toLowerCase() === 'completed')
    )
    const runStatus = String(
      task.current_stage === 'interrupted'
        ? 'interrupted'
        : task.run_status || (achieved ? 'achieved' : task.status || 'completed')
    )
    const targetSharpe = optionalNumber(task.target_sharpe) ?? optionalNumber(request.target_sharpe) ?? 0
    const paperHandoff = isRecord(task.paper_handoff) ? task.paper_handoff : {}
    const bestDiagnostics = isRecord(task.best_diagnostics) ? task.best_diagnostics : {}
    const assetSpecs = isRecord(task.asset_specs) && Object.keys(task.asset_specs).length
      ? task.asset_specs as Record<string, Record<string, unknown>>
      : isRecord(paperHandoff.asset_specs)
        ? paperHandoff.asset_specs as Record<string, Record<string, unknown>>
        : {}
    const backtestEnvironment = isRecord(task.backtest_environment)
      && Object.keys(task.backtest_environment).length
      ? task.backtest_environment
      : isRecord(paperHandoff.backtest_environment)
        ? paperHandoff.backtest_environment
        : {}
    const taskPipeline = task.pipeline ?? {
      current_stage: task.current_stage || 'completed',
      status: task.run_status || task.status || 'completed',
      progress: task.progress ?? 100,
      ready_for_live: Boolean(task.paper_review_ready_for_live),
      steps: [],
    }
    const liveWorkspaceId = task.live_workspace_id ?? taskPipeline.live_workspace_id ?? null
    const liveWorkspaceName = task.live_workspace_name ?? null
    const liveUnitId = task.live_unit_id ?? taskPipeline.live_unit_id ?? null
    const liveTradingPrepared = Boolean(
      task.live_trading_prepared
      || taskPipeline.live_trading_prepared
      || taskPipeline.current_stage === 'live_trading_prepare'
    )
    const liveTradingPreparedAt = task.live_trading_prepared_at
      ?? taskPipeline.live_trading_prepared_at
      ?? liveTradingPreparedAtFromPipeline(taskPipeline)
      ?? null
    const taskContinuationContext = isRecord(task.continuation_context)
      ? { ...task.continuation_context }
      : {}
    const requestContinuationContext = isRecord(request.continuation_context)
      ? { ...request.continuation_context }
      : {}
    const continuationContext = Object.keys(taskContinuationContext).length
      ? taskContinuationContext
      : requestContinuationContext
    const record: AIStrategyResearchRunRecord = {
      run_id: task.run_id,
      prompt: stringFromUnknown(request.prompt),
      symbol: stringFromUnknown(request.symbol),
      symbol_name: stringFromUnknown(request.symbol_name, stringFromUnknown(request.symbol)),
      timeframe: stringFromUnknown(request.timeframe, '1d'),
      timeframe_n: optionalNumber(request.timeframe_n) ?? 1,
      start_date: stringFromUnknown(request.start_date) || null,
      end_date: stringFromUnknown(request.end_date) || null,
      initial_cash:
        optionalNumber(backtestEnvironment.initial_cash)
        ?? optionalNumber(request.initial_cash)
        ?? undefined,
      commission:
        optionalNumber(backtestEnvironment.commission)
        ?? optionalNumber(request.commission)
        ?? undefined,
      annual_days:
        optionalNumber(backtestEnvironment.annual_days)
        ?? optionalNumber(request.annual_days)
        ?? undefined,
      calc_method:
        stringFromUnknown(backtestEnvironment.calc_method, stringFromUnknown(request.calc_method))
        || undefined,
      weight_mode:
        stringFromUnknown(backtestEnvironment.weight_mode, stringFromUnknown(request.weight_mode))
        || undefined,
      group_name: stringFromUnknown(request.group_name) || undefined,
      asset_specs: assetSpecs,
      backtest_environment: backtestEnvironment,
      status: runStatus,
      achieved,
      target_sharpe: targetSharpe,
      quality_gates: {
        target_sharpe: targetSharpe,
        min_total_trades: optionalNumber(request.min_total_trades) ?? 0,
        max_drawdown_limit: optionalNumber(request.max_drawdown_limit),
        min_total_return: optionalNumber(request.min_total_return),
        min_annual_return: optionalNumber(request.min_annual_return),
        min_win_rate: optionalNumber(request.min_win_rate),
        out_of_sample_validation: optionalBoolean(request.out_of_sample_validation, true),
        require_out_of_sample_validation: optionalBoolean(
          request.require_out_of_sample_validation,
          false
        ),
        out_of_sample_ratio: optionalNumber(request.out_of_sample_ratio) ?? 0.25,
        min_out_of_sample_sharpe: optionalNumber(request.min_out_of_sample_sharpe),
        min_out_of_sample_trades: optionalNumber(request.min_out_of_sample_trades),
        robustness_validation: optionalBoolean(request.robustness_validation, true),
        require_robustness_validation: optionalBoolean(
          request.require_robustness_validation,
          true
        ),
        robustness_methods: request.robustness_methods ?? ['monte_carlo'],
        min_robustness_score: optionalNumber(request.min_robustness_score) ?? 55,
        robustness_monte_carlo_iterations:
          optionalNumber(request.robustness_monte_carlo_iterations) ?? 300,
        robustness_random_seed: optionalNumber(request.robustness_random_seed),
        min_paper_trading_days:
          optionalNumber(request.min_paper_trading_days) ?? DEFAULT_AI_RESEARCH_MIN_PAPER_TRADING_DAYS,
      },
      min_total_trades: optionalNumber(request.min_total_trades) ?? 0,
      max_iterations: optionalNumber(task.max_iterations) ?? optionalNumber(request.max_iterations) ?? 0,
      iteration_count: Math.max(
        optionalNumber(task.iteration_count) ?? 0,
        taskIterations.length,
        latestIteration ? 1 : 0
      ),
      best_iteration: bestIteration,
      best_sharpe: bestSharpe,
      best_quality_score: optionalNumber(task.best_quality_score) ?? 0,
      best_quality_gate_evaluations: task.best_quality_gate_evaluations ?? [],
      best_diagnostics: bestDiagnostics,
      best_metrics: bestMetrics,
      best_strategy_id: task.best_strategy_id ?? null,
      best_strategy_name: task.best_strategy_name ?? null,
      research_workspace_id: task.research_workspace_id,
      mandate_id: (task.mandate_id ?? stringFromUnknown(request.mandate_id)) || null,
      seed_strategy_id: stringFromUnknown(request.seed_strategy_id) || null,
      continued_from_run_id: stringFromUnknown(
        task.continued_from_run_id,
        stringFromUnknown(request.continue_from_run_id)
      ) || null,
      continuation_source: stringFromUnknown(
        task.continuation_source,
        stringFromUnknown(continuationContext.source)
      ) || null,
      continuation_context: continuationContext,
      paper_workspace_id: task.paper_workspace_id ?? null,
      paper_workspace_name: stringFromUnknown(
        task.paper_workspace_name,
        stringFromUnknown(paperHandoff.paper_workspace_name, stringFromUnknown(request.paper_workspace_name))
      ) || null,
      paper_unit_id: task.paper_unit_id ?? null,
      paper_trading_started: Boolean(task.paper_trading_started),
      paper_monitoring_plan: task.paper_monitoring_plan ?? [],
      paper_handoff: paperHandoff,
      paper_review_status: task.paper_review_status ?? null,
      paper_review_ready_for_live: Boolean(task.paper_review_ready_for_live),
      paper_reviewed_at: task.paper_reviewed_at ?? null,
      paper_review_evaluations: task.paper_review_evaluations ?? [],
      paper_review_next_actions: task.paper_review_next_actions ?? [],
      live_readiness_checklist: task.live_readiness_checklist ?? [],
      live_readiness_expires_at: task.live_readiness_expires_at ?? null,
      live_handoff: task.live_handoff ?? null,
      live_handoff_approval: task.live_handoff_approval ?? null,
      live_workspace_id: liveWorkspaceId,
      live_workspace_name: liveWorkspaceName,
      live_unit_id: liveUnitId,
      live_trading_prepared: liveTradingPrepared,
      live_trading_prepared_at: liveTradingPreparedAt,
      pipeline: taskPipeline,
      promotion_audit: promotionAuditFromPayload(task.promotion_audit),
      next_actions: task.next_actions ?? [],
      started_at: task.started_at ?? task.submitted_at,
      completed_at: task.completed_at ?? task.started_at ?? task.submitted_at,
      iterations: taskIterations,
    }
    hydrateLiveHandoffFromRunRecord(record)
    return {
      ...researchResultFromRunRecord(record),
      message: 'AI research result restored from task summary',
    }
  }

  function researchIterationsFromRunRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyResearchIteration[] {
    return (record.iterations || [])
      .filter(isRecord)
      .map((payload, index) => researchIterationFromRunRecord(record, payload, index + 1))
  }

  function researchIterationFromRunRecord(
    record: AIStrategyResearchRunRecord,
    payload: Record<string, unknown>,
    fallbackIteration: number
  ): AIStrategyResearchIteration {
    const iteration = Math.max(Math.trunc(optionalNumber(payload.iteration) ?? fallbackIteration), 1)
    const metrics = isRecord(payload.metrics) ? payload.metrics : {}
    const strategy = strategyFromIterationRecord(record, payload, iteration)
    const unit = unitFromIterationRecord(record, payload, strategy, metrics)
    const runResult = iterationRunResultPayload(payload)
    const runStatus = stringFromUnknown(
      payload.run_status ?? runResult.status ?? unit.run_status,
      'completed'
    )
    const taskId = nullableString(payload.task_id)
      ?? nullableString(runResult.task_id)
      ?? unit.last_task_id
    return {
      iteration,
      strategy,
      unit,
      run_result: {
        unit_id: unit.id,
        task_id: taskId,
        status: runStatus,
      },
      unit_status: unitStatusFromIterationRecord(unit, payload, runStatus, taskId, metrics),
      metrics,
      sharpe_ratio: optionalNumber(payload.sharpe_ratio) ?? metricFromPayload(metrics, 'sharpe_ratio', 'sharpe') ?? 0,
      total_trades: optionalNumber(payload.total_trades) ?? metricFromPayload(metrics, 'total_trades', 'trades') ?? 0,
      validation_status: nullableString(payload.validation_status),
      validation_window: validationWindowFromUnknown(payload.validation_window),
      validation_metrics: isRecord(payload.validation_metrics) ? payload.validation_metrics : {},
      validation_gate_evaluations: arrayFromUnknown<AIStrategyQualityGateEvaluation>(
        payload.validation_gate_evaluations
      ),
      validation_failures: stringArrayFromUnknown(payload.validation_failures),
      validation_failure_reason: nullableString(payload.validation_failure_reason),
      quality_score: optionalNumber(payload.quality_score) ?? record.best_quality_score ?? 0,
      quality_gate_evaluations: arrayFromUnknown<AIStrategyQualityGateEvaluation>(
        payload.quality_gate_evaluations
      ),
      passed: Boolean(payload.passed),
      failure_reason: nullableString(payload.failure_reason),
      quality_gate_failures: stringArrayFromUnknown(payload.quality_gate_failures),
      diagnostics: isRecord(payload.diagnostics)
        ? payload.diagnostics as AIStrategyResearchIteration['diagnostics']
        : {},
      improvement_plan: stringArrayFromUnknown(payload.improvement_plan),
      improvement_notes: stringArrayFromUnknown(payload.improvement_notes),
      next_actions: stringArrayFromUnknown(payload.next_actions),
    }
  }

  function strategyFromIterationRecord(
    record: AIStrategyResearchRunRecord,
    payload: Record<string, unknown>,
    iteration: number
  ): Strategy {
    const snapshot = iterationUnitPayload(payload)
    const strategySnapshot = iterationStrategyPayload(payload)
    const strategyId = stringFromUnknown(
      strategySnapshot.id ?? payload.strategy_id,
      record.best_strategy_id || fallbackSnapshotStrategyId(record)
    )
    const strategyName = stringFromUnknown(
      strategySnapshot.name ?? payload.strategy_name,
      record.best_strategy_name || `AI策略 第${iteration}轮`
    )
    const diagnostics = isRecord(payload.diagnostics) ? payload.diagnostics : {}
    return {
      id: strategyId,
      user_id: '',
      name: strategyName,
      description: stringFromUnknown(strategySnapshot.description, stringFromUnknown(diagnostics.summary, record.prompt)),
      code: stringFromUnknown(strategySnapshot.code, stringFromUnknown(payload.strategy_code, stringFromUnknown(payload.code, ''))),
      params: isRecord(strategySnapshot.params)
        ? strategySnapshot.params as Strategy['params']
        : isRecord(snapshot.params) ? snapshot.params as Strategy['params'] : {},
      category: stringFromUnknown(strategySnapshot.category, stringFromUnknown(snapshot.category, 'custom')),
      created_at: stringFromUnknown(strategySnapshot.created_at, record.started_at),
      updated_at: stringFromUnknown(strategySnapshot.updated_at, record.completed_at),
    }
  }

  function paperTradingFromRunRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyPaperTradingStart | null {
    if (!record.paper_trading_started || !record.paper_workspace_id || !record.paper_unit_id) {
      return null
    }
    const handoff = isRecord(record.paper_handoff) ? record.paper_handoff : {}
    const paperUnit = paperUnitFromRunRecord(record, handoff)
    const runStatus = paperUnit.run_status
    const taskId = paperUnit.last_task_id
    return {
      workspace: paperWorkspaceFromRunRecord(record),
      unit: paperUnit,
      run_result: {
        unit_id: paperUnit.id,
        task_id: taskId,
        status: runStatus,
      },
      started: Boolean(record.paper_trading_started),
      handoff,
    }
  }

  function paperUnitFromRunRecord(
    record: AIStrategyResearchRunRecord,
    handoff: Record<string, unknown>
  ): StrategyUnit {
    const payload = bestIterationPayloadForRecord(record)
    if (!payload) return fallbackPaperUnitFromRunRecord(record, handoff)
    const iteration = Math.max(
      Math.trunc(optionalNumber(payload.iteration) ?? record.best_iteration ?? 1),
      1
    )
    const metrics = isRecord(payload.metrics) ? payload.metrics : record.best_metrics ?? {}
    const strategy = strategyFromIterationRecord(record, payload, iteration)
    const researchUnit = unitFromIterationRecord(record, payload, strategy, metrics)
    const runStatus = paperRunStatusFromHandoff(handoff, 'running')
    const taskId = nullableString(handoff.paper_task_id) ?? researchUnit.last_task_id
    return {
      ...researchUnit,
      id: record.paper_unit_id || researchUnit.id,
      workspace_id: record.paper_workspace_id || researchUnit.workspace_id,
      trading_mode: 'paper',
      data_config: {
        ...researchUnit.data_config,
        ai_research_run_id: record.run_id,
        ai_research_workspace_id: record.research_workspace_id,
      },
      unit_settings: {
        ...researchUnit.unit_settings,
        ai_research_handoff: handoff,
      },
      run_status: runStatus,
      last_task_id: taskId,
      gateway_config: Object.keys(researchUnit.gateway_config || {}).length
        ? researchUnit.gateway_config
        : isRecord(handoff.gateway_config)
          ? handoff.gateway_config as StrategyUnit['gateway_config']
          : {},
      updated_at: record.completed_at,
    }
  }

  function paperWorkspaceFromRunRecord(record: AIStrategyResearchRunRecord): Workspace {
    return {
      id: record.paper_workspace_id || '',
      user_id: '',
      name: record.paper_workspace_name || `AI模拟 - ${record.symbol}`,
      description: null,
      workspace_type: 'trading',
      settings: {
        ai_research_handoff: {
          last_handoff: isRecord(record.paper_handoff) ? record.paper_handoff : {},
        },
      },
      trading_config: {},
      unit_count: record.paper_unit_id ? 1 : 0,
      completed_count: 0,
      status: 'running',
      created_at: record.completed_at,
      updated_at: record.completed_at,
    }
  }

  function fallbackPaperUnitFromRunRecord(
    record: AIStrategyResearchRunRecord,
    handoff: Record<string, unknown>
  ): StrategyUnit {
    const assetSpecs = runtimeAssetSpecsPayload(record, handoff)
    const environment = runtimeEnvironmentPayload(record, handoff)
    const dataConfig: Record<string, unknown> = {
      symbol: record.symbol,
      ai_research_run_id: record.run_id,
      ai_research_workspace_id: record.research_workspace_id,
    }
    if (Object.keys(assetSpecs).length) dataConfig.asset_specs = assetSpecs
    if (Object.keys(environment).length) dataConfig.backtest_environment = environment
    const unitSettings: Record<string, unknown> = {
      ...environment,
      ai_research_handoff: handoff,
    }
    if (Object.keys(assetSpecs).length) unitSettings.asset_specs = assetSpecs
    return {
      id: record.paper_unit_id || `${record.run_id}-paper-unit`,
      workspace_id: record.paper_workspace_id || '',
      group_name: record.group_name || record.best_strategy_name || 'AI策略',
      strategy_id: record.best_strategy_id || null,
      strategy_name: record.best_strategy_name || 'AI策略',
      symbol: record.symbol,
      symbol_name: record.symbol_name || record.symbol,
      timeframe: record.timeframe,
      timeframe_n: record.timeframe_n,
      category: 'custom',
      sort_order: 0,
      data_config: dataConfig,
      unit_settings: unitSettings,
      params: {},
      optimization_config: {},
      trading_mode: 'paper',
      gateway_config: isRecord(handoff.gateway_config)
        ? handoff.gateway_config as StrategyUnit['gateway_config']
        : {},
      lock_trading: false,
      lock_running: false,
      trading_instance_id: null,
      trading_snapshot: emptyTradingSnapshot('paper'),
      run_status: paperRunStatusFromHandoff(handoff, 'running'),
      run_count: 1,
      last_run_time: null,
      last_task_id: nullableString(handoff.paper_task_id),
      last_optimization_task_id: null,
      bar_count: null,
      metrics_snapshot: record.best_metrics ?? {},
      created_at: record.started_at,
      updated_at: record.completed_at,
    }
  }

  function runtimeAssetSpecsPayload(
    record: AIStrategyResearchRunRecord | null | undefined,
    handoff?: Record<string, unknown> | null
  ) {
    const specs: Record<string, unknown> = {}
    const merge = (source: unknown) => {
      if (!isRecord(source)) return
      for (const [symbol, spec] of Object.entries(source)) {
        if (isRecord(spec)) specs[symbol] = spec
      }
    }
    merge(record?.asset_specs)
    merge(handoff?.asset_specs)
    if (handoff !== undefined && isRecord(record?.paper_handoff)) {
      merge(record.paper_handoff.asset_specs)
    }
    return specs
  }

  function paperRunStatusFromHandoff(
    handoff: Record<string, unknown>,
    fallback: StrategyUnit['run_status']
  ): StrategyUnit['run_status'] {
    const status = stringFromUnknown(handoff.paper_run_status, fallback)
    return ['idle', 'queued', 'running', 'completed', 'failed', 'cancelled', 'timeout'].includes(status)
      ? status as StrategyUnit['run_status']
      : fallback
  }

  function unitFromIterationRecord(
    record: AIStrategyResearchRunRecord,
    payload: Record<string, unknown>,
    strategy: Strategy,
    metrics: Record<string, unknown>
  ): StrategyUnit {
    const snapshot = iterationUnitPayload(payload)
    const runResult = iterationRunResultPayload(payload)
    const runStatus = stringFromUnknown(
      payload.run_status ?? runResult.status ?? snapshot.run_status,
      'completed'
    ) as StrategyUnit['run_status']
    const taskId = nullableString(payload.task_id)
      ?? nullableString(runResult.task_id)
      ?? nullableString(snapshot.last_task_id)
    return {
      id: stringFromUnknown(
        payload.unit_id ?? runResult.unit_id,
        stringFromUnknown(snapshot.id, `${record.run_id}-unit`)
      ),
      workspace_id: stringFromUnknown(snapshot.workspace_id, record.research_workspace_id),
      group_name: stringFromUnknown(snapshot.group_name, strategy.name),
      strategy_id: strategy.id,
      strategy_name: strategy.name,
      symbol: stringFromUnknown(snapshot.symbol, record.symbol),
      symbol_name: stringFromUnknown(snapshot.symbol_name, record.symbol_name || record.symbol),
      timeframe: stringFromUnknown(snapshot.timeframe, record.timeframe),
      timeframe_n: optionalNumber(snapshot.timeframe_n) ?? record.timeframe_n,
      category: stringFromUnknown(snapshot.category, strategy.category),
      sort_order: 0,
      data_config: isRecord(snapshot.data_config) ? snapshot.data_config : {},
      unit_settings: isRecord(snapshot.unit_settings) ? snapshot.unit_settings : {},
      params: isRecord(snapshot.params) ? snapshot.params : {},
      optimization_config: isRecord(snapshot.optimization_config) ? snapshot.optimization_config : {},
      trading_mode: unitTradingMode(snapshot),
      gateway_config: isRecord(snapshot.gateway_config)
        ? snapshot.gateway_config as StrategyUnit['gateway_config']
        : {},
      lock_trading: Boolean(snapshot.lock_trading),
      lock_running: Boolean(snapshot.lock_running),
      trading_instance_id: nullableString(snapshot.trading_instance_id),
      trading_snapshot: emptyTradingSnapshot(unitTradingMode(snapshot)),
      run_status: runStatus,
      run_count: optionalNumber(snapshot.run_count) ?? 1,
      last_run_time: optionalNumber(snapshot.last_run_time),
      last_task_id: taskId,
      last_optimization_task_id: nullableString(snapshot.last_optimization_task_id),
      bar_count: optionalNumber(snapshot.bar_count),
      metrics_snapshot: metrics,
      created_at: record.started_at,
      updated_at: record.completed_at,
    }
  }

  function iterationStrategyPayload(payload: Record<string, unknown>) {
    if (isRecord(payload.strategy_snapshot) && Object.keys(payload.strategy_snapshot).length) {
      return payload.strategy_snapshot
    }
    return isRecord(payload.strategy) ? payload.strategy : {}
  }

  function iterationUnitPayload(payload: Record<string, unknown>) {
    if (isRecord(payload.unit_snapshot) && Object.keys(payload.unit_snapshot).length) {
      return payload.unit_snapshot
    }
    return isRecord(payload.unit) ? payload.unit : {}
  }

  function iterationRunResultPayload(payload: Record<string, unknown>) {
    return isRecord(payload.run_result) ? payload.run_result : {}
  }

  function iterationUnitStatusPayload(payload: Record<string, unknown>) {
    return isRecord(payload.unit_status) ? payload.unit_status : {}
  }

  function unitStatusFromIterationRecord(
    unit: StrategyUnit,
    payload: Record<string, unknown>,
    runStatus: string,
    taskId: string | null,
    metrics: Record<string, unknown>
  ): UnitStatusResponse {
    const status = iterationUnitStatusPayload(payload)
    const statusRunStatus = stringFromUnknown(status.run_status, runStatus)
    const statusTaskId = nullableString(status.last_task_id) ?? taskId
    const statusMetrics = isRecord(status.metrics_snapshot) ? status.metrics_snapshot : metrics
    const tradingSnapshot = isRecord(status.trading_snapshot)
      ? {
          ...emptyTradingSnapshot(unit.trading_mode),
          ...status.trading_snapshot,
        } as TradingSnapshot
      : emptyTradingSnapshot(unit.trading_mode)
    return {
      id: stringFromUnknown(status.id, unit.id),
      run_status: statusRunStatus as UnitStatusResponse['run_status'],
      last_task_id: statusTaskId,
      metrics_snapshot: statusMetrics,
      run_progress: optionalNumber(status.run_progress),
      run_message: nullableString(status.run_message),
      run_count: optionalNumber(status.run_count) ?? unit.run_count,
      last_run_time: optionalNumber(status.last_run_time) ?? unit.last_run_time,
      bar_count: optionalNumber(status.bar_count) ?? unit.bar_count,
      trading_instance_id: nullableString(status.trading_instance_id) ?? unit.trading_instance_id,
      trading_snapshot: tradingSnapshot,
      trading_mode: stringFromUnknown(status.trading_mode, unit.trading_mode) as UnitStatusResponse['trading_mode'],
      lock_trading: optionalBoolean(status.lock_trading, unit.lock_trading),
      lock_running: optionalBoolean(status.lock_running, unit.lock_running),
      opt_status: nullableString(status.opt_status),
      opt_total: optionalNumber(status.opt_total),
      opt_completed: optionalNumber(status.opt_completed),
      opt_progress: optionalNumber(status.opt_progress),
      opt_elapsed_time: optionalNumber(status.opt_elapsed_time),
      opt_remaining_time: optionalNumber(status.opt_remaining_time),
    }
  }

  function metricFromPayload(payload: Record<string, unknown>, ...keys: string[]) {
    for (const key of keys) {
      const value = optionalNumber(payload[key])
      if (value !== null) return value
    }
    return null
  }

  function unitTradingMode(snapshot: Record<string, unknown>) {
    return stringFromUnknown(snapshot.trading_mode, 'paper') as StrategyUnit['trading_mode']
  }

  function emptyTradingSnapshot(mode: StrategyUnit['trading_mode']): TradingSnapshot {
    return {
      instance_id: null,
      instance_status: 'idle',
      mode,
      error: null,
      started_at: null,
      stopped_at: null,
      gateway_summary: null,
      long_position: 0,
      short_position: 0,
      today_pnl: null,
      position_pnl: null,
      latest_price: null,
      change_pct: null,
      long_market_value: null,
      short_market_value: null,
      leverage: null,
      cumulative_pnl: null,
      max_drawdown_rate: null,
      trading_day: null,
      updated_at: null,
      detail_route: null,
      positions: [],
      trades: [],
    }
  }

  function stringFromUnknown(value: unknown, fallback = '') {
    const text = typeof value === 'string' ? value.trim() : ''
    return text || fallback
  }

  function routeQueryText(value: unknown) {
    if (Array.isArray(value)) return stringFromUnknown(value[0])
    return stringFromUnknown(value)
  }

  function aiResearchRouteRunId() {
    return (
      routeQueryText(route.query.ai_research_run_id)
      || routeQueryText(route.query.research_run_id)
      || routeQueryText(route.query.run_id)
    )
  }

  function aiResearchRouteWorkspaceId() {
    return (
      routeQueryText(route.query.research_workspace_id)
      || routeQueryText(route.query.workspace_id)
    )
  }

  function applyAIResearchRoutePrefill() {
    const prompt = routeQueryText(route.query.prompt)
      || routeQueryText(route.query.strategy_prompt)
    const symbol = routeQueryText(route.query.symbol)
    const symbolName = routeQueryText(route.query.symbol_name)
      || routeQueryText(route.query.symbolName)
    const timeframe = routeQueryText(route.query.timeframe)
    const knowledgeBaseId = routeQueryText(route.query.knowledge_base_id)
      || routeQueryText(route.query.kbId)

    if (!prompt && !symbol && !symbolName && !timeframe && !knowledgeBaseId) return false

    activeTab.value = 'aiResearch'
    if (prompt) {
      aiResearchForm.prompt = prompt
      aiResearchForm.workflow_mode = 'prompt'
    }
    if (symbol) aiResearchForm.symbol = symbol
    if (symbolName) aiResearchForm.symbol_name = symbolName
    if (timeframe) aiResearchForm.timeframe = timeframe
    if (knowledgeBaseId) aiResearchForm.knowledge_base_id = knowledgeBaseId
    return true
  }

  function nullableString(value: unknown) {
    const text = typeof value === 'string' ? value.trim() : ''
    return text || null
  }

  function stringArrayFromUnknown(value: unknown) {
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      : []
  }

  function uniqueTextItems(items: unknown[]) {
    return [...new Set(
      items
        .map(item => stringFromUnknown(item))
        .filter(Boolean)
    )]
  }

  function arrayFromUnknown<T>(value: unknown): T[] {
    return Array.isArray(value) ? value.filter(isRecord) as T[] : []
  }

  async function restoreAIResearchResultFromTask(
    task: AIStrategyResearchTaskResponse
  ): Promise<AIStrategyResearchRunResponse | null> {
    if (!task.run_id) return null
    try {
      let record: AIStrategyResearchRunRecord | null = null
      try {
        record = await strategyApi.getAIResearchRun(
          task.run_id,
          task.research_workspace_id || undefined
        )
      } catch {
        const response = await strategyApi.listAIResearchRuns(
          task.research_workspace_id || undefined,
          100
        )
        record = response.items.find(item => item.run_id === task.run_id) ?? null
      }
      if (!record) return researchResultFromTaskSummary(task)
      upsertAIResearchRunRecord(record)
      return researchResultFromRunRecord(record)
    } catch {
      return researchResultFromTaskSummary(task)
    }
  }

  async function restoreAIResearchRunFromRoute() {
    const runId = aiResearchRouteRunId()
    if (!runId) return false
    try {
      const record = await refreshAIResearchRunRecord(runId, aiResearchRouteWorkspaceId())
      if (!record) return false
      selectAIResearchRunRecord(record)
      activeTab.value = 'aiResearch'
      return true
    } catch {
      return false
    }
  }

  function reviewedRunRecord(
    record: AIStrategyResearchRunRecord,
    review: AIStrategyPaperTradingReview
  ): AIStrategyResearchRunRecord {
    const liveReadinessChecklist = liveReadinessChecklistForReview(review)
    const paperHandoff: Record<string, unknown> = { ...(record.paper_handoff ?? {}) }
    if (liveReadinessChecklist.length) {
      paperHandoff.live_readiness_checklist = liveReadinessChecklist
    } else {
      delete paperHandoff.live_readiness_checklist
    }
    if (review.live_readiness_expires_at) {
      paperHandoff.live_readiness_expires_at = review.live_readiness_expires_at
    } else {
      delete paperHandoff.live_readiness_expires_at
    }
    const reviewLock = paperReviewLockFromPayload(review.pipeline?.paper_review_lock)
    if (reviewLock) {
      paperHandoff.paper_review_lock = reviewLock
    } else {
      delete paperHandoff.paper_review_lock
    }
    return {
      ...record,
      paper_review_status: review.status,
      paper_review_ready_for_live: review.ready_for_live,
      paper_reviewed_at: review.reviewed_at ?? record.paper_reviewed_at,
      paper_review_evaluations: review.evaluations,
      paper_review_next_actions: review.next_actions,
      live_readiness_checklist: liveReadinessChecklist,
      live_readiness_expires_at: review.live_readiness_expires_at ?? null,
      paper_handoff: paperHandoff,
      pipeline: review.pipeline ?? record.pipeline,
      next_actions: review.next_actions,
    }
  }

  function paperReviewForRecord(
    record: AIStrategyResearchRunRecord
  ): AIStrategyPaperTradingReview | null {
    const review = aiResearchPaperReviews[record.run_id]
    if (review) return review
    if (!record.paper_review_status) return null
    return {
      run_id: record.run_id,
      research_workspace_id: record.research_workspace_id,
      paper_workspace_id: record.paper_workspace_id,
      paper_unit_id: record.paper_unit_id,
      paper_trading_started: record.paper_trading_started,
      monitoring_plan: record.paper_monitoring_plan ?? [],
      evaluations: record.paper_review_evaluations ?? [],
      ready_for_live: Boolean(record.paper_review_ready_for_live),
      status: record.paper_review_status,
      reviewed_at: record.paper_reviewed_at,
      live_readiness_checklist: liveReadinessChecklistForRecord(record),
      live_readiness_expires_at: liveReadinessExpiresAtForRecord(record),
      pipeline: record.pipeline,
      next_actions: record.paper_review_next_actions ?? [],
    } satisfies AIStrategyPaperTradingReview
  }

  function applyPaperReviewToCurrentResult(
    runId: string,
    runRecord: AIStrategyResearchRunRecord
  ) {
    const current = aiResearchResult.value
    if (!current || current.run_id !== runId) return
    aiResearchResult.value = {
      ...current,
      run_record: runRecord,
      pipeline: runRecord.pipeline ?? current.pipeline,
      next_actions: runRecord.next_actions ?? current.next_actions,
    }
  }

  async function startPaperFromResearchRecord(record: AIStrategyResearchRunRecord) {
    aiResearchPaperStartingRunId.value = record.run_id
    try {
      const paper = await strategyApi.startAIResearchPaperTrading(
        record.run_id,
        aiResearchPaperStartRequest(record)
      )
      const responseRecord = paper.run_record ?? null
      if (!paper.started) {
        const failedRecord = responseRecord ?? paperStartFailedRunRecord(record, paper)
        upsertAIResearchRunRecord(failedRecord)
        applyPaperStartToCurrentResult(record.run_id, paper, failedRecord)
        try {
          await refreshAIResearchRunRecord(record.run_id, record.research_workspace_id)
        } catch {
          // Keep the local failed start state visible even if history refresh fails.
        }
        ElMessage.error(t('strategy.aiResearchPaperStartFailed'))
        return
      }
      const updatedRecord = responseRecord ?? paperStartedRunRecord(record, paper)
      upsertAIResearchRunRecord(updatedRecord)
      applyPaperStartToCurrentResult(record.run_id, paper, updatedRecord)
      try {
        await refreshAIResearchRunRecord(record.run_id, record.research_workspace_id)
      } catch {
        // Keep the local started state visible even if history refresh fails.
      }
      ElMessage.success(t('strategy.aiResearchPaperStartedSuccess'))
    } catch (error) {
      if (notifyAIResearchConfigError(error)) return
      try {
        await refreshAIResearchRunRecord(record.run_id, record.research_workspace_id)
      } catch {
        // Keep the original start failure visible even if history refresh fails.
      }
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchPaperStartingRunId.value = ''
    }
  }

  async function startPaperFromCurrentResult() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await startPaperFromResearchRecord(record)
  }

  async function viewBestStrategyFromCurrentResult() {
    const result = aiResearchResult.value
    if (!result) return
    if (result.best_strategy) {
      viewStrategy(result.best_strategy)
      return
    }
    const record = result.run_record
    if (!record) return
    await viewStrategyFromResearchRecord(record)
  }

  async function viewResearchIterationStrategy(item: AIStrategyResearchIteration) {
    if (item.strategy.code.trim()) {
      viewStrategy(item.strategy)
      return
    }
    if (!item.strategy.id) return
    aiResearchStrategyViewingRunId.value = aiResearchResult.value?.run_id || item.strategy.id
    try {
      const strategy = await strategyApi.get(item.strategy.id)
      viewStrategy(strategy)
    } catch {
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchStrategyViewingRunId.value = ''
    }
  }

  async function viewStrategyFromResearchRecord(record: AIStrategyResearchRunRecord) {
    const snapshotStrategy = bestStrategyFromRunRecord(record)
    if (snapshotStrategy?.code?.trim()) {
      viewStrategy(snapshotStrategy)
      return
    }
    const strategyId = bestStrategyIdForRecord(record)
    if (!strategyId) return
    aiResearchStrategyViewingRunId.value = record.run_id
    try {
      const strategy = await strategyApi.get(strategyId)
      viewStrategy(strategy)
    } catch {
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchStrategyViewingRunId.value = ''
    }
  }

  function viewAIResearchVersionCode(version: AIStrategyResearchVersion) {
    viewStrategy({
      id: version.strategy_id || version.id,
      user_id: '',
      name: version.strategy_name || version.version_name,
      description: version.change_summary || version.ai_rationale || '',
      code: version.code,
      params: {},
      category: 'custom',
      created_at: version.created_at,
      updated_at: version.updated_at,
    })
  }

  function paperMonitoringPlanFromHandoff(
    handoff: Record<string, unknown> | null | undefined
  ): AIStrategyPaperMonitoringRule[] | undefined {
    const plan = handoff?.paper_monitoring_plan
    return Array.isArray(plan) ? (plan as AIStrategyPaperMonitoringRule[]) : undefined
  }

  async function reviewPaperFromResearchRecord(record: AIStrategyResearchRunRecord) {
    aiResearchPaperReviewingRunId.value = record.run_id
    try {
      const review = await strategyApi.reviewAIResearchPaperTrading(
        record.run_id,
        record.research_workspace_id
      )
      aiResearchPaperReviews[record.run_id] = review
      delete aiResearchLiveHandoffs[record.run_id]
      let updatedRecord = reviewedRunRecord(record, review)
      if (review.live_handoff) {
        aiResearchLiveHandoffs[record.run_id] = review.live_handoff
        updatedRecord = liveHandoffRunRecord(updatedRecord, review.live_handoff)
      }
      upsertAIResearchRunRecord(updatedRecord)
      applyPaperReviewToCurrentResult(record.run_id, updatedRecord)
      ElMessage.success(review.ready_for_live ? t('strategy.aiResearchPaperReadyForLive') : t('strategy.aiResearchPaperReviewUpdated'))
      if (review.live_handoff) {
        ElMessage.success(review.live_handoff.ready_for_live ? t('strategy.aiResearchLiveHandoffGenerated') : t('strategy.aiResearchLiveHandoffBlocked'))
      } else if (review.ready_for_live) {
        await buildLiveHandoffFromResearchRecord(updatedRecord)
      }
    } catch {
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchPaperReviewingRunId.value = ''
    }
  }

  async function reviewPaperFromCurrentResult() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await reviewPaperFromResearchRecord(record)
  }

  async function buildLiveHandoffFromCurrentResult() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await buildLiveHandoffFromResearchRecord(record)
  }

  async function approveCurrentLiveHandoff(decision: 'approved' | 'rejected') {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await approveLiveHandoffFromResearchRecord(record, decision)
  }

  async function prepareLiveTradingFromCurrentResult() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await prepareLiveTradingFromResearchRecord(record)
  }

  async function buildLiveHandoffFromResearchRecord(record: AIStrategyResearchRunRecord) {
    aiResearchLiveHandoffLoadingRunId.value = record.run_id
    try {
      const handoff = await strategyApi.buildAIResearchLiveHandoff(
        record.run_id,
        record.research_workspace_id
      )
      aiResearchLiveHandoffs[record.run_id] = handoff
      const updatedRecord = liveHandoffRunRecord(record, handoff)
      upsertAIResearchRunRecord(updatedRecord)
      applyResearchRunRecordToCurrentResult(updatedRecord)
      ElMessage.success(handoff.ready_for_live ? t('strategy.aiResearchLiveHandoffGenerated') : t('strategy.aiResearchLiveHandoffBlocked'))
    } catch {
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchLiveHandoffLoadingRunId.value = ''
    }
  }

  async function approveLiveHandoffFromResearchRecord(
    record: AIStrategyResearchRunRecord,
    decision: 'approved' | 'rejected'
  ) {
    const handoff = liveHandoffForRecord(record)
    if (!handoff || !canApproveLiveHandoff(handoff)) return
    const confirmMessage = decision === 'approved'
      ? t('strategy.aiResearchApproveLiveHandoffConfirm')
      : t('strategy.aiResearchRejectLiveHandoffConfirm')
    try {
      await ElMessageBox.confirm(confirmMessage, t('strategy.aiResearchLiveHandoffApproval'), {
        type: decision === 'approved' ? 'success' : 'warning',
      })
    } catch {
      return
    }

    aiResearchLiveHandoffApprovingRunId.value = `${record.run_id}:${decision}`
    const payload: AIStrategyLiveHandoffApprovalRequest = decision === 'approved'
      ? {
          decision,
          approver: 'web',
          comment: '前端人工审批通过',
          account_confirmed: true,
          risk_limit_confirmed: true,
          deployment_window: '人工审批通过后执行',
        }
      : {
          decision,
          approver: 'web',
          comment: '前端人工驳回',
          account_confirmed: false,
          risk_limit_confirmed: false,
        }
    try {
      const updatedHandoff = await strategyApi.approveAIResearchLiveHandoff(
        record.run_id,
        payload,
        record.research_workspace_id
      )
      aiResearchLiveHandoffs[record.run_id] = updatedHandoff
      const updatedRecord = liveHandoffRunRecord(record, updatedHandoff)
      upsertAIResearchRunRecord(updatedRecord)
      applyResearchRunRecordToCurrentResult(updatedRecord)
      ElMessage.success(decision === 'approved' ? t('strategy.aiResearchLiveHandoffApproved') : t('strategy.aiResearchLiveHandoffRejected'))
    } catch {
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchLiveHandoffApprovingRunId.value = ''
    }
  }

  async function prepareLiveTradingFromResearchRecord(record: AIStrategyResearchRunRecord) {
    if (!canPrepareLiveTradingFromRecord(record)) return
    aiResearchLiveTradingPreparingRunId.value = record.run_id
    try {
      const prepared = await strategyApi.prepareAIResearchLiveTrading(
        record.run_id,
        aiResearchLivePrepareRequest(record),
        record.research_workspace_id
      )
      const updatedRecord = liveTradingPreparedRunRecord(record, prepared)
      upsertAIResearchRunRecord(updatedRecord)
      applyResearchRunRecordToCurrentResult(updatedRecord)
      ElMessage.success(t('strategy.aiResearchLiveUnitPrepared'))
    } catch (error) {
      if (notifyAIResearchConfigError(error)) return
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchLiveTradingPreparingRunId.value = ''
    }
  }

  function liveHandoffRunRecord(
    record: AIStrategyResearchRunRecord,
    handoff: AIStrategyLiveHandoffPackage
  ): AIStrategyResearchRunRecord {
    const approval = handoff.approval ?? record.live_handoff_approval ?? null
    const recordPipeline = record.pipeline ?? null
    const handoffPipeline = handoff.pipeline ?? null
    return {
      ...record,
      live_handoff: handoff,
      live_handoff_approval: approval,
      pipeline: {
        ...(recordPipeline ?? {}),
        ...(handoffPipeline ?? {}),
        current_stage: handoffPipeline?.current_stage ?? recordPipeline?.current_stage ?? 'live_candidate',
        status: handoffPipeline?.status ?? recordPipeline?.status ?? record.status,
        progress: handoffPipeline?.progress ?? recordPipeline?.progress ?? (handoff.ready_for_live ? 100 : 90),
        ready_for_live: handoffPipeline?.ready_for_live ?? recordPipeline?.ready_for_live ?? handoff.ready_for_live,
        steps: handoffPipeline?.steps ?? recordPipeline?.steps ?? [],
        live_handoff_status: handoff.status,
        live_handoff_generated_at: handoff.generated_at,
        live_handoff_ready_for_live: handoff.ready_for_live,
        live_handoff_approval_required: handoff.approval_required,
        live_handoff_blocker_count: handoff.deployment_blockers.length,
        live_handoff_approval_status: approval?.decision
          ?? handoffPipeline?.live_handoff_approval_status
          ?? recordPipeline?.live_handoff_approval_status,
        live_handoff_approved: approval?.approved
          ?? handoffPipeline?.live_handoff_approved
          ?? recordPipeline?.live_handoff_approved,
        live_handoff_approved_at: approval?.approved
          ? approval.decided_at
          : handoffPipeline?.live_handoff_approved_at ?? recordPipeline?.live_handoff_approved_at,
        live_handoff_rejected_at: approval && !approval.approved
          ? approval.decided_at
          : handoffPipeline?.live_handoff_rejected_at ?? recordPipeline?.live_handoff_rejected_at,
      },
      next_actions: handoff.next_actions?.length ? handoff.next_actions : record.next_actions,
    }
  }

  function liveTradingPreparedRunRecord(
    record: AIStrategyResearchRunRecord,
    prepared: AIStrategyLiveTradingPrepare
  ): AIStrategyResearchRunRecord {
    const handoff = isRecord(prepared.handoff) ? prepared.handoff : {}
    const preparedAt = stringFromUnknown(
      handoff.live_trading_prepared_at,
      new Date().toISOString()
    )
    const previousSteps = record.pipeline?.steps ?? []
    const nextSteps = upsertPipelineStep(
      upsertPipelineStep(previousSteps, {
        key: 'live_handoff',
        label: t('strategy.aiResearchLiveHandoff'),
        status: 'completed',
      }),
      {
        key: 'live_trading_prepare',
        label: t('strategy.aiResearchLivePreparation'),
        status: 'completed',
        live_trading_prepared: prepared.prepared,
        live_workspace_id: prepared.workspace.id,
        live_unit_id: prepared.unit.id,
        live_unit_locked: Boolean(prepared.unit.lock_trading || prepared.unit.lock_running),
        prepared_at: preparedAt,
      }
    )
    const liveHandoff = record.live_handoff
      ? {
          ...record.live_handoff,
          handoff: {
            ...(record.live_handoff.handoff ?? {}),
            live_trading_prepare: handoff,
          },
          next_actions: prepared.next_actions,
        }
      : record.live_handoff
    return {
      ...record,
      live_handoff: liveHandoff,
      live_workspace_id: prepared.workspace.id,
      live_workspace_name: prepared.workspace.name,
      live_unit_id: prepared.unit.id,
      live_trading_prepared: prepared.prepared,
      live_trading_prepared_at: preparedAt,
      pipeline: {
        ...(record.pipeline ?? {}),
        current_stage: 'live_trading_prepare',
        status: record.pipeline?.status ?? record.live_handoff?.status ?? record.status,
        progress: record.pipeline?.progress ?? 100,
        ready_for_live: record.pipeline?.ready_for_live ?? true,
        live_trading_prepared: prepared.prepared,
        live_trading_prepared_at: preparedAt,
        live_workspace_id: prepared.workspace.id,
        live_unit_id: prepared.unit.id,
        live_unit_locked: Boolean(prepared.unit.lock_trading || prepared.unit.lock_running),
        steps: nextSteps,
      },
      next_actions: prepared.next_actions?.length ? prepared.next_actions : record.next_actions,
    }
  }

  function upsertPipelineStep(
    steps: AIStrategyPipelineStep[],
    nextStep: AIStrategyPipelineStep
  ): AIStrategyPipelineStep[] {
    const index = steps.findIndex(step => step.key === nextStep.key)
    if (index < 0) return [...steps, nextStep]
    return steps.map((step, currentIndex) =>
      currentIndex === index ? { ...step, ...nextStep } : step
    )
  }

  async function continueResearchFromCurrentPaperReview() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await continueResearchFromRecord(record)
  }

  async function continueResearchFromCurrentRunRecord() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    await continueResearchFromRecord(record)
  }

  async function continueResearchFromPaperReview(record: AIStrategyResearchRunRecord) {
    await continueResearchFromRecord(record)
  }

  async function continueResearchFromRecord(record: AIStrategyResearchRunRecord) {
    useAIResearchRecord(record)
    if (record.mandate_id) {
      await loadAIResearchMandate(record.mandate_id)
    }
    prepareContinuationPromotion(record)
    const continueRun = (strategyApi as typeof strategyApi & {
      continueAIResearchRun?: typeof strategyApi.continueAIResearchRun
      getAIResearchTask?: typeof strategyApi.getAIResearchTask
    }).continueAIResearchRun
    if (typeof continueRun !== 'function') {
      await runAIResearchLoop()
      return
    }
    await continueAIResearchFromRunRecord(record, continueRun)
  }

  function prepareContinuationPromotion(record: AIStrategyResearchRunRecord) {
    const source = continuationSourceForRecord(record)
    if (source) {
      aiResearchForm.start_paper_trading = true
    }
  }

  function buildAIResearchRequest(prompt: string, symbol: string): AIStrategyResearchRunRequest {
    const paperWorkspaceName = aiResearchPaperWorkspaceName()
    const gatewayConfig = parseAIResearchGatewayConfig()
    const request: AIStrategyResearchRunRequest = {
      prompt,
      workflow_mode: aiResearchForm.workflow_mode === 'prompt' ? 'prompt' : 'auto',
      workflow_steps: [...AI_RESEARCH_WORKFLOW_STEPS],
      symbol,
      symbol_name: aiResearchForm.symbol_name.trim(),
      timeframe: aiResearchForm.timeframe,
      timeframe_n: aiResearchForm.timeframe_n,
      start_date: aiResearchForm.start_date || null,
      end_date: aiResearchForm.end_date || null,
      target_sharpe: aiResearchForm.target_sharpe,
      min_total_trades: aiResearchForm.min_total_trades,
      max_drawdown_limit: enabledQualityGate(
        aiResearchForm.use_max_drawdown_limit,
        aiResearchForm.max_drawdown_limit
      ),
      min_total_return: enabledQualityGate(
        aiResearchForm.use_min_total_return,
        aiResearchForm.min_total_return
      ),
      min_annual_return: enabledQualityGate(
        aiResearchForm.use_min_annual_return,
        aiResearchForm.min_annual_return
      ),
      min_win_rate: enabledQualityGate(
        aiResearchForm.use_min_win_rate,
        aiResearchForm.min_win_rate
      ),
      max_iterations: aiResearchForm.max_iterations,
      out_of_sample_validation: aiResearchForm.out_of_sample_validation,
      require_out_of_sample_validation: Boolean(
        aiResearchForm.out_of_sample_validation
          && aiResearchForm.require_out_of_sample_validation
      ),
      out_of_sample_ratio: outOfSampleRatioValue(),
      min_out_of_sample_sharpe: aiResearchForm.out_of_sample_validation
        ? enabledQualityGate(
            aiResearchForm.use_min_out_of_sample_sharpe,
            aiResearchForm.min_out_of_sample_sharpe
          )
        : null,
      min_out_of_sample_trades: aiResearchForm.out_of_sample_validation
        ? enabledQualityGate(
            aiResearchForm.use_min_out_of_sample_trades,
            aiResearchForm.min_out_of_sample_trades
          )
        : null,
      robustness_validation: aiResearchForm.robustness_validation,
      require_robustness_validation: Boolean(
        aiResearchForm.robustness_validation
          && aiResearchForm.require_robustness_validation
      ),
      robustness_methods: aiResearchForm.robustness_validation
        ? [...aiResearchForm.robustness_methods]
        : [],
      min_robustness_score: aiResearchForm.min_robustness_score,
      robustness_monte_carlo_iterations: aiResearchForm.robustness_monte_carlo_iterations,
      robustness_random_seed: aiResearchForm.robustness_random_seed,
      initial_cash: aiResearchForm.initial_cash,
      annual_days: aiResearchForm.annual_days,
      calc_method: aiResearchForm.calc_method,
      weight_mode: aiResearchForm.weight_mode,
      research_workspace_id: aiResearchForm.research_workspace_id || null,
      mandate_id: aiResearchMandateConfirmed.value ? aiResearchMandate.value?.id ?? null : null,
      seed_strategy_id: aiResearchForm.seed_strategy_id || null,
      continue_from_run_id: aiResearchForm.continue_from_run_id || null,
      start_paper_trading: aiResearchForm.start_paper_trading,
      min_paper_trading_days: Math.max(0, aiResearchForm.min_paper_trading_days),
      trading_workspace_id: aiResearchForm.trading_workspace_id.trim() || null,
      paper_workspace_name: aiResearchForm.start_paper_trading
        ? paperWorkspaceName
        : null,
      backtest_timeout_seconds: aiResearchForm.backtest_timeout_seconds,
      poll_interval_seconds: aiResearchForm.poll_interval_seconds,
      group_name: aiResearchForm.group_name.trim() || null,
      knowledge_base_id: aiResearchForm.knowledge_base_id.trim() || null,
      thinking_mode: aiResearchForm.thinking_mode,
    }
    if (aiResearchForm.use_manual_commission) {
      request.commission = aiResearchForm.commission
    }
    const continuationContext = aiResearchContinuationContext()
    if (continuationContext) {
      request.continuation_context = continuationContext
    }
    if (gatewayConfig) {
      request.gateway_config = gatewayConfig
    }
    return request
  }

  function aiResearchPaperWorkspaceName() {
    return aiResearchForm.paper_workspace_name.trim() || null
  }

  function parseAIResearchGatewayConfig() {
    return parseGatewayConfigJson(
      aiResearchForm.gateway_config_json,
      '模拟网关配置必须是合法 JSON',
      '模拟网关配置必须是 JSON 对象',
      '模拟网关配置包含脱敏凭据，请重新输入真实网关配置'
    )
  }

  function parseAIResearchLiveGatewayConfig() {
    return parseGatewayConfigJson(
      aiResearchForm.live_gateway_config_json,
      '实盘网关配置必须是合法 JSON',
      '实盘网关配置必须是 JSON 对象',
      '实盘网关配置包含脱敏凭据，请重新输入真实网关配置'
    )
  }

  function parseGatewayConfigJson(
    rawValue: string,
    parseErrorMessage: string,
    objectErrorMessage: string,
    redactedErrorMessage: string
  ): Record<string, unknown> | undefined {
    const raw = rawValue.trim()
    if (!raw) return undefined
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      throw new AIResearchConfigError(parseErrorMessage)
    }
    if (!isRecord(parsed) || Array.isArray(parsed)) {
      throw new AIResearchConfigError(objectErrorMessage)
    }
    if (containsRedactedSecret(parsed)) {
      throw new AIResearchConfigError(redactedErrorMessage)
    }
    return parsed
  }

  function notifyAIResearchConfigError(error: unknown) {
    const message = error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : ''
    if (!AI_RESEARCH_CONFIG_ERROR_MESSAGES.has(message)) return false
    ElMessage.warning(message)
    return true
  }

  function aiResearchPaperStartRequest(record: AIStrategyResearchRunRecord) {
    const gatewayConfig = parseAIResearchGatewayConfig()
    const request = {
      research_workspace_id: record.research_workspace_id,
    } as {
      research_workspace_id: string
      trading_workspace_id?: string
      paper_workspace_name?: string
      gateway_config?: Record<string, unknown>
    }
    const tradingWorkspaceId = aiResearchForm.trading_workspace_id.trim()
    if (tradingWorkspaceId) {
      request.trading_workspace_id = tradingWorkspaceId
    }
    const paperWorkspaceName = aiResearchPaperWorkspaceName()
      || record.paper_workspace_name?.trim()
      || null
    if (paperWorkspaceName) {
      request.paper_workspace_name = paperWorkspaceName
    }
    if (gatewayConfig) {
      request.gateway_config = gatewayConfig
    }
    return request
  }

  function aiResearchLivePrepareRequest(record: AIStrategyResearchRunRecord) {
    const gatewayConfig = parseAIResearchLiveGatewayConfig()
    const request = {
      research_workspace_id: record.research_workspace_id,
    } as {
      research_workspace_id: string
      trading_workspace_id?: string
      live_workspace_name?: string
      gateway_config?: Record<string, unknown>
    }
    const liveWorkspaceId = aiResearchForm.live_trading_workspace_id.trim()
    if (liveWorkspaceId) {
      request.trading_workspace_id = liveWorkspaceId
    }
    const liveWorkspaceName = aiResearchForm.live_workspace_name.trim()
    if (liveWorkspaceName) {
      request.live_workspace_name = liveWorkspaceName
    }
    if (gatewayConfig) {
      request.gateway_config = gatewayConfig
    }
    return request
  }

  function isAIResearchTaskTerminal(task: AIStrategyResearchTaskResponse) {
    return ['completed', 'failed', 'cancelled'].includes(String(task.status || '').toLowerCase())
  }

  function isAIResearchTaskCancelled(task: AIStrategyResearchTaskResponse) {
    return String(task.status || '').toLowerCase() === 'cancelled'
  }

  function isRestorableAIResearchTask(task: AIStrategyResearchTaskResponse) {
    return isAIResearchTaskTerminal(task) && Boolean(task.result || task.run_id)
  }

  function sleep(ms: number) {
    return new Promise(resolve => window.setTimeout(resolve, ms))
  }

  const AI_RESEARCH_TASK_POLL_INTERVAL_MS = 1500
  const AI_RESEARCH_TASK_MIN_TIMEOUT_MS = 10 * 60 * 1000
  const AI_RESEARCH_TASK_MAX_TIMEOUT_MS = 8 * 60 * 60 * 1000

  function boundedNumber(value: unknown, fallback: number, min: number, max: number) {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return fallback
    return Math.min(Math.max(parsed, min), max)
  }

  function aiResearchTaskPollTimeoutMs(
    payload?: AIStrategyResearchRunRequest,
    task?: AIStrategyResearchTaskResponse
  ) {
    const snapshot: Record<string, unknown> = isRecord(task?.request_snapshot)
      ? task.request_snapshot
      : {}
    const maxIterations = boundedNumber(
      payload?.max_iterations
        ?? task?.max_iterations
        ?? snapshot.max_iterations
        ?? aiResearchForm.max_iterations,
      3,
      1,
      8
    )
    const backtestTimeoutSeconds = boundedNumber(
      payload?.backtest_timeout_seconds ?? snapshot.backtest_timeout_seconds,
      600,
      1,
      3600
    )
    const outOfSampleValidation = payload?.out_of_sample_validation ?? snapshot.out_of_sample_validation
    const robustnessValidation = payload?.robustness_validation ?? snapshot.robustness_validation ?? false
    const validationFactor = 1
      + (outOfSampleValidation === false ? 0 : 1)
      + (robustnessValidation === false ? 0 : 1)
    const estimatedSeconds = maxIterations * validationFactor * backtestTimeoutSeconds + 240
    return boundedNumber(
      estimatedSeconds * 1000,
      AI_RESEARCH_TASK_MIN_TIMEOUT_MS,
      AI_RESEARCH_TASK_MIN_TIMEOUT_MS,
      AI_RESEARCH_TASK_MAX_TIMEOUT_MS
    )
  }

  function applyAIResearchTaskStatus(task: AIStrategyResearchTaskResponse) {
    const pipeline = task.pipeline ?? null
    const sameTask = aiResearchTaskId.value === task.task_id
    const hasTaskKey = (key: string) => Object.prototype.hasOwnProperty.call(task, key)
    aiResearchTaskId.value = task.task_id
    aiResearchTaskStatus.value = task.status
    aiResearchTaskStage.value = task.current_stage || task.status
    aiResearchTaskProgress.value = Number(task.progress || 0)
    aiResearchTaskIteration.value = task.current_iteration ?? task.iteration_count ?? null
    aiResearchBacktestTaskId.value = task.current_backtest_task_id || ''
    aiResearchCancelledBacktestTaskId.value = task.cancelled_backtest_task_id || ''
    aiResearchTaskPaperWorkspaceId.value = task.paper_workspace_id || ''
    aiResearchTaskPaperUnitId.value = task.paper_unit_id || ''
    aiResearchTaskPaperStarted.value = Boolean(task.paper_trading_started)
    aiResearchTaskLiveWorkspaceId.value = task.live_workspace_id || pipeline?.live_workspace_id || ''
    aiResearchTaskLiveUnitId.value = task.live_unit_id || pipeline?.live_unit_id || ''
    aiResearchTaskLivePrepared.value = Boolean(
      task.live_trading_prepared || pipeline?.live_trading_prepared
    )
    aiResearchTaskPipeline.value = pipeline
    if (hasTaskKey('continued_from_run_id') || !sameTask) {
      aiResearchTaskContinuedFromRunId.value = stringFromUnknown(task.continued_from_run_id)
    }
    if (hasTaskKey('continuation_source') || !sameTask) {
      aiResearchTaskContinuationSource.value = stringFromUnknown(task.continuation_source)
    }
    if (hasTaskKey('continuation_context') || !sameTask) {
      aiResearchTaskContinuationContext.value = isRecord(task.continuation_context)
        ? { ...task.continuation_context }
        : {}
    }
    if (isRecord(task.request_snapshot)) {
      aiResearchTaskRequestSnapshot.value = task.request_snapshot
    } else if (hasTaskKey('request_snapshot') || !sameTask) {
      aiResearchTaskRequestSnapshot.value = {}
    }
    if (hasTaskKey('asset_specs') || !sameTask) {
      aiResearchTaskAssetSpecs.value = isRecord(task.asset_specs)
        ? task.asset_specs as Record<string, Record<string, unknown>>
        : {}
    }
    if (hasTaskKey('backtest_environment') || !sameTask) {
      aiResearchTaskBacktestEnvironment.value = isRecord(task.backtest_environment)
        ? task.backtest_environment
        : {}
    }
    if (hasTaskKey('promotion_audit') || !sameTask) {
      aiResearchTaskPromotionAudit.value = promotionAuditFromPayload(task.promotion_audit)
    }
    aiResearchTaskError.value = aiResearchTaskFailureMessage(task)
    aiResearchTaskMessage.value = String(task.message || '').trim()
    aiResearchTaskLatestIteration.value = task.latest_iteration ?? null
    if (hasTaskKey('best_iteration_payload') || !sameTask) {
      aiResearchTaskBestIteration.value = isRecord(task.best_iteration_payload)
        ? task.best_iteration_payload
        : null
    }
  }

  function applyAIResearchTaskSnapshotToForm(task: AIStrategyResearchTaskResponse) {
    const snapshot = isRecord(task.request_snapshot) ? task.request_snapshot : null
    if (!snapshot) return
    const environment = resolvedAIResearchTaskBacktestEnvironment(task, snapshot)
    const prompt = stringFromUnknown(snapshot.prompt)
    const symbol = stringFromUnknown(snapshot.symbol)
    const symbolName = stringFromUnknown(snapshot.symbol_name)
    const timeframe = stringFromUnknown(snapshot.timeframe)
    const startDate = stringFromUnknown(snapshot.start_date)
    const endDate = stringFromUnknown(snapshot.end_date)
    if (prompt) aiResearchForm.prompt = prompt
    aiResearchForm.workflow_mode = snapshot.workflow_mode === 'prompt' ? 'prompt' : 'auto'
    if (symbol) aiResearchForm.symbol = symbol
    if (symbolName || snapshot.symbol_name !== undefined) aiResearchForm.symbol_name = symbolName
    if (timeframe) aiResearchForm.timeframe = timeframe
    aiResearchForm.timeframe_n = optionalNumber(snapshot.timeframe_n) ?? aiResearchForm.timeframe_n
    aiResearchForm.start_date = startDate
    aiResearchForm.end_date = endDate
    aiResearchForm.knowledge_base_id = stringFromUnknown(snapshot.knowledge_base_id)
    aiResearchForm.thinking_mode = optionalBoolean(snapshot.thinking_mode, false)
    aiResearchForm.target_sharpe = optionalNumber(snapshot.target_sharpe) ?? aiResearchForm.target_sharpe
    aiResearchForm.min_total_trades =
      optionalNumber(snapshot.min_total_trades) ?? aiResearchForm.min_total_trades
    aiResearchForm.max_iterations = optionalNumber(snapshot.max_iterations) ?? aiResearchForm.max_iterations
    aiResearchForm.initial_cash =
      (environment ? optionalNumber(environment.initial_cash) : null)
      ?? optionalNumber(snapshot.initial_cash)
      ?? aiResearchForm.initial_cash
    const commission = aiResearchTaskRestoredCommission(task, snapshot)
    if (commission !== null) {
      aiResearchForm.commission = commission
      aiResearchForm.use_manual_commission = aiResearchTaskUsesManualCommission(task, snapshot)
    } else {
      aiResearchForm.use_manual_commission = false
    }
    aiResearchForm.annual_days =
      (environment ? optionalNumber(environment.annual_days) : null)
      ?? optionalNumber(snapshot.annual_days)
      ?? aiResearchForm.annual_days
    aiResearchForm.calc_method = environment
      ? stringFromUnknown(environment.calc_method, stringFromUnknown(snapshot.calc_method, aiResearchForm.calc_method))
      : stringFromUnknown(snapshot.calc_method, aiResearchForm.calc_method)
    aiResearchForm.weight_mode = environment
      ? stringFromUnknown(environment.weight_mode, stringFromUnknown(snapshot.weight_mode, aiResearchForm.weight_mode))
      : stringFromUnknown(snapshot.weight_mode, aiResearchForm.weight_mode)
    aiResearchForm.group_name = stringFromUnknown(snapshot.group_name)
    aiResearchForm.backtest_timeout_seconds =
      optionalNumber(snapshot.backtest_timeout_seconds) ?? aiResearchForm.backtest_timeout_seconds
    aiResearchForm.poll_interval_seconds =
      optionalNumber(snapshot.poll_interval_seconds) ?? aiResearchForm.poll_interval_seconds
    aiResearchForm.research_workspace_id = stringFromUnknown(snapshot.research_workspace_id)
    aiResearchForm.trading_workspace_id = stringFromUnknown(snapshot.trading_workspace_id)
    aiResearchForm.seed_strategy_id = stringFromUnknown(snapshot.seed_strategy_id)
    const taskContinuationContext = isRecord(task.continuation_context)
      ? task.continuation_context
      : null
    const snapshotContinuationContext = isRecord(snapshot.continuation_context)
      ? snapshot.continuation_context
      : null
    const continuationContext = taskContinuationContext ?? snapshotContinuationContext
    const continuationRunId = continuationContext
      ? stringFromUnknown(continuationContext.run_id)
      : ''
    const continuationSource = continuationContext
      ? stringFromUnknown(continuationContext.source)
      : ''
    aiResearchForm.continue_from_run_id =
      stringFromUnknown(task.continued_from_run_id, stringFromUnknown(snapshot.continue_from_run_id))
      || continuationRunId
    aiResearchForm.continuation_source =
      stringFromUnknown(task.continuation_source, continuationSource)
    aiResearchForm.start_paper_trading = optionalBoolean(snapshot.start_paper_trading, true)
    aiResearchForm.paper_workspace_name = stringFromUnknown(snapshot.paper_workspace_name)
    if (snapshot.gateway_config !== undefined) {
      aiResearchForm.gateway_config_json = gatewayConfigJsonFromTaskSnapshot(snapshot)
    }
    const maxDrawdownLimit = optionalNumber(snapshot.max_drawdown_limit)
    aiResearchForm.use_max_drawdown_limit = maxDrawdownLimit !== null
    aiResearchForm.max_drawdown_limit = maxDrawdownLimit ?? aiResearchForm.max_drawdown_limit
    const minTotalReturn = optionalNumber(snapshot.min_total_return)
    aiResearchForm.use_min_total_return = minTotalReturn !== null
    aiResearchForm.min_total_return = minTotalReturn ?? aiResearchForm.min_total_return
    const minAnnualReturn = optionalNumber(snapshot.min_annual_return)
    aiResearchForm.use_min_annual_return = minAnnualReturn !== null
    aiResearchForm.min_annual_return = minAnnualReturn ?? aiResearchForm.min_annual_return
    const minWinRate = optionalNumber(snapshot.min_win_rate)
    aiResearchForm.use_min_win_rate = minWinRate !== null
    aiResearchForm.min_win_rate = minWinRate ?? aiResearchForm.min_win_rate
    aiResearchForm.out_of_sample_validation =
      optionalBoolean(snapshot.out_of_sample_validation, aiResearchForm.out_of_sample_validation)
    aiResearchForm.require_out_of_sample_validation = optionalBoolean(
      snapshot.require_out_of_sample_validation,
      false
    )
    const outOfSampleRatio = optionalNumber(snapshot.out_of_sample_ratio)
    if (outOfSampleRatio !== null) aiResearchForm.out_of_sample_ratio_pct = outOfSampleRatio * 100
    const minOutOfSampleSharpe = optionalNumber(snapshot.min_out_of_sample_sharpe)
    aiResearchForm.use_min_out_of_sample_sharpe = minOutOfSampleSharpe !== null
    aiResearchForm.min_out_of_sample_sharpe =
      minOutOfSampleSharpe ?? aiResearchForm.min_out_of_sample_sharpe
    const minOutOfSampleTrades = optionalNumber(snapshot.min_out_of_sample_trades)
    aiResearchForm.use_min_out_of_sample_trades = minOutOfSampleTrades !== null
    aiResearchForm.min_out_of_sample_trades =
      minOutOfSampleTrades ?? aiResearchForm.min_out_of_sample_trades
    aiResearchForm.robustness_validation =
      optionalBoolean(snapshot.robustness_validation, aiResearchForm.robustness_validation)
    aiResearchForm.require_robustness_validation = optionalBoolean(
      snapshot.require_robustness_validation,
      aiResearchForm.require_robustness_validation
    )
    const robustnessMethods = stringArrayFromUnknown(snapshot.robustness_methods)
    aiResearchForm.robustness_methods = robustnessMethods.length
      ? robustnessMethods
      : aiResearchForm.robustness_methods
    aiResearchForm.min_robustness_score =
      optionalNumber(snapshot.min_robustness_score) ?? aiResearchForm.min_robustness_score
    aiResearchForm.robustness_monte_carlo_iterations =
      optionalNumber(snapshot.robustness_monte_carlo_iterations)
      ?? aiResearchForm.robustness_monte_carlo_iterations
    aiResearchForm.robustness_random_seed = optionalNumber(snapshot.robustness_random_seed)
    const minPaperTradingDays = optionalNumber(snapshot.min_paper_trading_days)
    if (minPaperTradingDays !== null) {
      aiResearchForm.min_paper_trading_days = Math.max(0, minPaperTradingDays)
    }
  }

  function aiResearchTaskFailureMessage(task: AIStrategyResearchTaskResponse) {
    if (isAIResearchTaskCancelled(task)) return ''
    if (String(task.status || '').toLowerCase() !== 'failed') return ''
    return String(task.error || task.message || 'AI research task failed').trim()
  }

  function aiResearchErrorMessage(error: unknown) {
    if (error instanceof Error && error.message.trim()) return error.message.trim()
    const message = String(error || '').trim()
    return message || t('strategy.aiResearchRunFailed')
  }

  function isAIResearchResultPaperStartFailure(result: AIStrategyResearchRunResponse) {
    const pipeline = result.pipeline ?? result.run_record?.pipeline
    return Boolean(
      pipeline?.current_stage === 'paper_trading_failed'
      || pipeline?.paper_trading_error
      || result.run_record?.pipeline?.current_stage === 'paper_trading_failed'
      || result.run_record?.pipeline?.paper_trading_error
    )
  }

  function notifyAIResearchResult(result: AIStrategyResearchRunResponse) {
    const status = String(result.status || '').toLowerCase()
    if (status === 'cancelled') {
      if (!aiResearchCancelRequested.value) {
        ElMessage.success(t('strategy.aiResearchTaskCancelled'))
      }
      return
    }
    if (isAIResearchResultPaperStartFailure(result)) {
      ElMessage.error(t('strategy.aiResearchPaperStartFailed'))
      return
    }
    if (result.achieved || status === 'achieved') {
      ElMessage.success(t('strategy.aiResearchRunSuccess'))
      return
    }
    if (status === 'timeout' || result.pipeline?.current_stage === 'backtest_timeout') {
      ElMessage.warning(t('strategy.aiResearchBacktestTimedOut'))
      return
    }
    if (status === 'interrupted' || result.pipeline?.current_stage === 'interrupted') {
      ElMessage.warning(t('strategy.aiResearchTaskInterrupted'))
      return
    }
    if (status === 'configuration_invalid' || result.pipeline?.current_stage === 'configuration_invalid') {
      const message = String(result.message || result.next_actions?.[0] || '').trim()
      ElMessage.warning(message ? t('strategy.aiResearchConfigInvalidDetail', { message }) : t('strategy.aiResearchConfigInvalid'))
      return
    }
    ElMessage.warning(t('strategy.aiResearchTargetNotMet'))
  }

  function resetAIResearchTaskState() {
    aiResearchTaskId.value = ''
    aiResearchTaskStatus.value = ''
    aiResearchTaskStage.value = ''
    aiResearchTaskProgress.value = 0
    aiResearchTaskIteration.value = null
    aiResearchBacktestTaskId.value = ''
    aiResearchCancelledBacktestTaskId.value = ''
    aiResearchTaskPaperWorkspaceId.value = ''
    aiResearchTaskPaperUnitId.value = ''
    aiResearchTaskPaperStarted.value = false
    aiResearchTaskLiveWorkspaceId.value = ''
    aiResearchTaskLiveUnitId.value = ''
    aiResearchTaskLivePrepared.value = false
    aiResearchTaskPipeline.value = null
    aiResearchTaskRequestSnapshot.value = null
    aiResearchTaskContinuedFromRunId.value = ''
    aiResearchTaskContinuationSource.value = ''
    aiResearchTaskContinuationContext.value = {}
    aiResearchTaskError.value = ''
    aiResearchTaskMessage.value = ''
    aiResearchTaskLatestIteration.value = null
    aiResearchTaskAssetSpecs.value = {}
    aiResearchTaskBacktestEnvironment.value = {}
    aiResearchTaskPromotionAudit.value = []
  }

  function aiResearchRunnableInput() {
    let prompt = aiResearchForm.prompt.trim()
    const promptRequired = aiResearchForm.workflow_mode === 'prompt'
    const shouldUseServerGeneratedPrompt = !prompt && !promptRequired
    const symbol = aiResearchForm.symbol.trim()
    if (!symbol) {
      ElMessage.warning(t('strategy.aiResearchSymbolRequired'))
      return null
    }
    if (!prompt && promptRequired) {
      ElMessage.warning(t('strategy.aiResearchPromptOrAutoRequired'))
      return null
    }
    if (shouldUseServerGeneratedPrompt) {
      aiResearchForm.prompt = buildGeneratedAIResearchPrompt()
      prompt = ''
    }
    const outOfSampleError = requiredOutOfSampleValidationError()
    if (outOfSampleError) {
      ElMessage.warning(outOfSampleError)
      return null
    }
    return { prompt, symbol, shouldUseServerGeneratedPrompt }
  }

  function applyCanonicalAIResearchPrompt(
    result: AIStrategyResearchRunResponse,
    shouldUseServerGeneratedPrompt: boolean
  ) {
    if (!shouldUseServerGeneratedPrompt) return
    const canonicalPrompt = stringFromUnknown(result.run_record?.prompt)
    if (canonicalPrompt) aiResearchForm.prompt = canonicalPrompt
  }

  async function applyCompletedAIResearchResult(result: AIStrategyResearchRunResponse) {
    aiResearchResult.value = result
    if (result.run_record) {
      setAIResearchConfigProfileFromRunRecord(result.run_record)
      upsertAIResearchRunRecord(result.run_record)
      await loadAIResearchRunArtifacts(result.run_record)
    } else {
      await loadAIResearchRuns()
    }
    notifyAIResearchResult(result)
  }

  function handleAIResearchRunError(error: unknown) {
    if (
      error instanceof Error
      && error.message === 'AI_RESEARCH_CANCELLED'
      && aiResearchCancelRequested.value
    ) {
      aiResearchTaskError.value = ''
      return true
    }
    if (notifyAIResearchConfigError(error)) {
      aiResearchTaskError.value = ''
      return true
    }
    aiResearchTaskError.value = aiResearchErrorMessage(error)
    ElMessage.error(t('strategy.aiResearchRunFailed'))
    return true
  }

  async function runAIResearchRequest(
    payload: AIStrategyResearchRunRequest
  ): Promise<AIStrategyResearchRunResponse> {
    const apiWithTasks = strategyApi as typeof strategyApi & {
      submitAIResearchTask?: typeof strategyApi.submitAIResearchTask
      getAIResearchTask?: typeof strategyApi.getAIResearchTask
    }
    if (
      typeof apiWithTasks.submitAIResearchTask !== 'function'
      || typeof apiWithTasks.getAIResearchTask !== 'function'
    ) {
      return strategyApi.runAIResearchLoop(payload)
    }

    const task = await apiWithTasks.submitAIResearchTask(payload)
    return pollAIResearchTask(task, aiResearchTaskPollTimeoutMs(payload, task))
  }

  async function continueAIResearchFromRunRecord(
    record: AIStrategyResearchRunRecord,
    continueRun: NonNullable<typeof strategyApi.continueAIResearchRun>
  ) {
    const input = aiResearchRunnableInput()
    if (!input) return
    const mandate = await ensureAIResearchMandateConfirmed(input)
    if (!mandate) return

    aiResearchRunning.value = true
    resetAIResearchTaskState()
    aiResearchCancelRequested.value = false
    try {
      const request = buildAIResearchRequest(input.prompt, input.symbol)
      const overrides: Partial<AIStrategyResearchRunRequest> & Record<string, unknown> = {
        ...request,
      }
      delete overrides.continue_from_run_id
      delete overrides.seed_strategy_id
      delete overrides.continuation_context
      const task = await continueRun(
        record.run_id,
        { overrides },
        record.research_workspace_id
      )
      const result = await pollAIResearchTask(
        task,
        aiResearchTaskPollTimeoutMs(request, task)
      )
      applyCanonicalAIResearchPrompt(result, input.shouldUseServerGeneratedPrompt)
      await applyCompletedAIResearchResult(result)
    } catch (error) {
      handleAIResearchRunError(error)
    } finally {
      aiResearchRunning.value = false
      scheduleAIResearchRunsAutoRefresh()
    }
  }

  async function pollAIResearchTask(
    task: AIStrategyResearchTaskResponse,
    timeoutMs = aiResearchTaskPollTimeoutMs(undefined, task)
  ): Promise<AIStrategyResearchRunResponse> {
    const apiWithTasks = strategyApi as typeof strategyApi & {
      getAIResearchTask?: typeof strategyApi.getAIResearchTask
    }
    applyAIResearchTaskStatus(task)
    const deadline = Date.now() + timeoutMs
    const maxPolls = Math.max(
      240,
      Math.ceil(timeoutMs / AI_RESEARCH_TASK_POLL_INTERVAL_MS) + 2
    )
    for (let attempt = 0; attempt < maxPolls; attempt += 1) {
      if (task.status === 'completed') {
        if (task.result) return task.result
        const restoredResult = await restoreAIResearchResultFromTask(task)
        if (restoredResult) return restoredResult
        throw new Error('AI research task completed without a result')
      }
      if (isAIResearchTaskCancelled(task)) {
        const restoredResult = await restoreAIResearchResultFromTask(task)
        if (restoredResult) return restoredResult
        throw new Error('AI_RESEARCH_CANCELLED')
      }
      if (isAIResearchTaskTerminal(task)) {
        const restoredResult = await restoreAIResearchResultFromTask(task)
        if (restoredResult) return restoredResult
        throw new Error(task.error || task.message || 'AI research task failed')
      }
      if (Date.now() > deadline) {
        break
      }
      if (typeof apiWithTasks.getAIResearchTask !== 'function') {
        throw new Error('AI research task polling is unavailable')
      }
      task = await apiWithTasks.getAIResearchTask(task.task_id)
      applyAIResearchTaskStatus(task)
      if (!isAIResearchTaskTerminal(task)) {
        await sleep(AI_RESEARCH_TASK_POLL_INTERVAL_MS)
      }
    }
    throw new Error(`AI research task polling timed out after ${Math.round(timeoutMs / 1000)}s`)
  }

  async function restoreActiveAIResearchTask() {
    const apiWithTasks = strategyApi as typeof strategyApi & {
      listAIResearchTasks?: typeof strategyApi.listAIResearchTasks
    }
    if (aiResearchRunning.value || typeof apiWithTasks.listAIResearchTasks !== 'function') return
    try {
      const response = await apiWithTasks.listAIResearchTasks(true, 5)
      const task = response.items.find(item => !isAIResearchTaskTerminal(item))
      if (task) {
        aiResearchRunning.value = true
        applyAIResearchTaskSnapshotToForm(task)
        aiResearchResult.value = await pollAIResearchTask(task)
      } else {
        if (aiResearchResult.value) return
        const recentResponse = await apiWithTasks.listAIResearchTasks(false, 5)
        const restoredTask = recentResponse.items.find(isRestorableAIResearchTask)
        if (!restoredTask) return
        applyAIResearchTaskSnapshotToForm(restoredTask)
        applyAIResearchTaskStatus(restoredTask)
        aiResearchResult.value = restoredTask.result ?? await restoreAIResearchResultFromTask(restoredTask)
      }
      if (!aiResearchResult.value) return
      syncAIResearchFormFromResult(aiResearchResult.value)
      if (aiResearchResult.value.run_record) {
        setAIResearchConfigProfileFromRunRecord(aiResearchResult.value.run_record)
        upsertAIResearchRunRecord(aiResearchResult.value.run_record)
      } else {
        await loadAIResearchRuns()
      }
      notifyAIResearchResult(aiResearchResult.value)
    } catch (error) {
      aiResearchTaskError.value = aiResearchErrorMessage(error)
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchRunning.value = false
      scheduleAIResearchRunsAutoRefresh()
    }
  }

  async function cancelAIResearchTask() {
    const taskId = aiResearchTaskId.value
    const cancelTask = (strategyApi as { cancelAIResearchTask?: (taskId: string) => Promise<AIStrategyResearchTaskResponse> }).cancelAIResearchTask
    if (!taskId || typeof cancelTask !== 'function') return
    aiResearchCancelling.value = true
    aiResearchCancelRequested.value = true
    try {
      const task = await cancelTask(taskId)
      applyAIResearchTaskStatus(task)
      aiResearchTaskError.value = ''
      aiResearchRunning.value = false
      if (task.run_id) {
        try {
          const record = await refreshAIResearchRunRecord(task.run_id, task.research_workspace_id)
          if (record) {
            aiResearchResult.value = researchResultFromRunRecord(record)
          }
        } catch {
          await loadAIResearchRuns()
        }
      }
      ElMessage.success(
        task.child_cancelled && task.cancelled_backtest_task_id
          ? 'AI投研任务已取消，当前回测任务已同步取消'
          : 'AI投研任务已取消'
      )
    } catch {
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchCancelling.value = false
    }
  }

  async function continueAIResearchFromTaskSnapshot() {
    const taskId = aiResearchTaskId.value
    const continueTask = (strategyApi as {
      continueAIResearchTask?: (
        taskId: string,
        data: { overrides?: Partial<AIStrategyResearchRunRequest> & Record<string, unknown> }
      ) => Promise<AIStrategyResearchTaskResponse>
    }).continueAIResearchTask
    if (!taskId || typeof continueTask !== 'function' || aiResearchRunning.value) return
    let prompt = aiResearchForm.prompt.trim()
    const shouldUseServerGeneratedPrompt = !prompt
    const symbol = aiResearchForm.symbol.trim()
    if (!symbol) {
      ElMessage.warning(t('strategy.aiResearchSymbolRequired'))
      return
    }
    if (shouldUseServerGeneratedPrompt) {
      aiResearchForm.prompt = buildGeneratedAIResearchPrompt()
      prompt = ''
    }
    const outOfSampleError = requiredOutOfSampleValidationError()
    if (outOfSampleError) {
      ElMessage.warning(outOfSampleError)
      return
    }
    const mandate = await ensureAIResearchMandateConfirmed({ prompt, symbol })
    if (!mandate) return

    aiResearchRunning.value = true
    aiResearchCancelRequested.value = false
    aiResearchTaskError.value = ''
    try {
      const request = buildAIResearchRequest(prompt, symbol)
      const overrides: Partial<AIStrategyResearchRunRequest> & Record<string, unknown> = { ...request }
      const task = await continueTask(taskId, { overrides })
      aiResearchResult.value = await pollAIResearchTask(
        task,
        aiResearchTaskPollTimeoutMs(request, task)
      )
      if (shouldUseServerGeneratedPrompt) {
        const canonicalPrompt = stringFromUnknown(aiResearchResult.value.run_record?.prompt)
        if (canonicalPrompt) aiResearchForm.prompt = canonicalPrompt
      }
      if (aiResearchResult.value.run_record) {
        setAIResearchConfigProfileFromRunRecord(aiResearchResult.value.run_record)
        upsertAIResearchRunRecord(aiResearchResult.value.run_record)
      } else {
        await loadAIResearchRuns()
      }
      notifyAIResearchResult(aiResearchResult.value)
    } catch (error) {
      if (
        error instanceof Error
        && error.message === 'AI_RESEARCH_CANCELLED'
        && aiResearchCancelRequested.value
      ) {
        aiResearchTaskError.value = ''
        return
      }
      if (notifyAIResearchConfigError(error)) {
        aiResearchTaskError.value = ''
        return
      }
      aiResearchTaskError.value = aiResearchErrorMessage(error)
      ElMessage.error(t('strategy.aiResearchRunFailed'))
    } finally {
      aiResearchRunning.value = false
      scheduleAIResearchRunsAutoRefresh()
    }
  }

  async function retryAIResearchFromTaskSnapshot() {
    if (!canRetryAIResearchTask.value || aiResearchRunning.value) return
    clearAIResearchContinuation()
    await runAIResearchLoop()
  }

  async function runAIResearchLoop() {
    const input = aiResearchRunnableInput()
    if (!input) return
    const mandate = await ensureAIResearchMandateConfirmed(input)
    if (!mandate) return

    aiResearchRunning.value = true
    resetAIResearchTaskState()
    aiResearchCancelRequested.value = false
    try {
      const result = await runAIResearchRequest(
        buildAIResearchRequest(input.prompt, input.symbol)
      )
      applyCanonicalAIResearchPrompt(result, input.shouldUseServerGeneratedPrompt)
      await applyCompletedAIResearchResult(result)
    } catch (error) {
      handleAIResearchRunError(error)
    } finally {
      aiResearchRunning.value = false
      scheduleAIResearchRunsAutoRefresh()
    }
  }

  function openResearchWorkspace() {
    const workspaceId = aiResearchResult.value?.research_workspace.id
    if (!workspaceId) return
    router.push({ name: 'ResearchWorkspaceDetail', params: { id: workspaceId } })
  }

  function openPaperWorkspace() {
    const workspaceId = aiResearchResult.value?.paper_trading?.workspace.id
      || aiResearchResult.value?.run_record?.paper_workspace_id
    if (!workspaceId) return
    router.push({ name: 'TradingWorkspaceDetail', params: { id: workspaceId } })
  }

  function openLiveWorkspaceFromCurrentResult() {
    const record = aiResearchResult.value?.run_record
    if (!record) return
    openLiveWorkspaceFromRecord(record)
  }

  function openLiveWorkspaceFromRecord(record: AIStrategyResearchRunRecord) {
    const workspaceId = record.live_workspace_id || record.pipeline?.live_workspace_id
    if (!workspaceId) return
    router.push({ name: 'TradingWorkspaceDetail', params: { id: workspaceId } })
  }

  function showCreateDialog() {
    isEdit.value = false
    editingId.value = ''
    Object.assign(form, { name: '', description: '', code: '', category: 'custom' })
    dialogVisible.value = true
  }

  function editStrategy(strategy: Strategy) {
    isEdit.value = true
    editingId.value = strategy.id
    Object.assign(form, {
      name: strategy.name,
      description: strategy.description || '',
      code: strategy.code,
      category: strategy.category,
    })
    dialogVisible.value = true
  }

  function viewStrategy(strategy: Strategy) {
    currentStrategy.value = strategy
    viewDialogVisible.value = true
  }

  function useTemplate(template: StrategyTemplate) {
    detailVisible.value = false
    isEdit.value = false
    editingId.value = ''
    Object.assign(form, {
      name: template.name + ` (${t('strategy.typeCopy')})`,
      description: stripStrategyMeta(template.description),
      code: template.code,
      category: template.category,
    })
    activeTab.value = 'my'
    dialogVisible.value = true
  }

  function updateStrategyForm(nextForm: typeof form) {
    Object.assign(form, nextForm)
  }

  async function saveStrategy() {
    if (!form.name || !form.code) {
      ElMessage.warning(t('strategy.warnNameOrCodeEmpty'))
      return
    }
    saving.value = true
    try {
      if (isEdit.value) {
        await strategyStore.updateStrategy(editingId.value, form)
        ElMessage.success(t('strategy.updated'))
      } else {
        await strategyStore.createStrategy(form)
        ElMessage.success(t('strategy.created'))
      }
      dialogVisible.value = false
    } finally {
      saving.value = false
    }
  }

  async function deleteStrategy(id: string) {
    await ElMessageBox.confirm(t('strategy.confirmDeleteText'), t('strategy.confirmDeleteTitle'), { type: 'warning' })
    await strategyStore.deleteStrategy(id)
    ElMessage.success(t('strategy.deleted'))
  }

  onMounted(async () => {
    aiResearchRunsAutoRefreshActive = true
    try {
      const initialLoads: Array<Promise<unknown>> = [
        strategyStore.fetchStrategies(),
        strategyStore.fetchTemplates(),
      ]
      if (showAIResearchTab.value) {
        initialLoads.push(loadAIResearchRuns())
        initialLoads.push(loadAIResearchConfigProfiles())
      }
      await Promise.all(initialLoads)
      if (showAIResearchTab.value) {
        const restoredFromRoute = await restoreAIResearchRunFromRoute()
        const prefilledFromRoute = !restoredFromRoute && applyAIResearchRoutePrefill()
        if (!restoredFromRoute && !prefilledFromRoute) {
          void restoreActiveAIResearchTask()
        }
      }
    } catch {
      ElMessage.error(t('strategy.loadFailed'))
    }
  })

  watch(activeTab, tab => {
    if (!showAIResearchTab.value && tab === 'aiResearch') {
      activeTab.value = 'gallery'
      return
    }
    if (!showStrategyManagementTabs.value && tab !== 'aiResearch') {
      activeTab.value = 'aiResearch'
      return
    }
    if (tab === 'aiResearch') {
      scheduleAIResearchRunsAutoRefresh()
    } else {
      clearAIResearchRunsAutoRefresh()
    }
  })

  watch(showAIResearchTab, visible => {
    if (visible && activeTab.value !== 'aiResearch') {
      activeTab.value = 'aiResearch'
      void loadAIResearchConfigProfiles()
      return
    }
    if (visible) {
      void loadAIResearchConfigProfiles()
    }
    if (!visible && activeTab.value === 'aiResearch') {
      activeTab.value = 'gallery'
    }
  }, { immediate: true })

  watch(
    () => [
      aiResearchForm.symbol,
      aiResearchForm.timeframe,
      aiResearchForm.start_date,
      aiResearchForm.end_date,
    ],
    () => {
      aiResearchPrecheckResult.value = null
      aiResearchPrecheckError.value = ''
      scheduleAIResearchDataPrecheck()
    },
  )

  onUnmounted(() => {
    aiResearchRunsAutoRefreshActive = false
    clearAIResearchRunsAutoRefresh()
    if (aiResearchPrecheckTimer !== null) clearTimeout(aiResearchPrecheckTimer)
    aiResearchPrecheckController?.abort()
  })

  return {
    t,
    route,
    router,
    strategyStore,
    isInvestmentStrategyResearchRoute,
    showAIResearchTab,
    showStrategyManagementTabs,
    activeTab,
    searchKeyword,
    categoryFilter,
    dialogVisible,
    viewDialogVisible,
    detailVisible,
    isEdit,
    saving,
    editingId,
    currentStrategy,
    detailTemplate,
    detailTab,
    readmeContent,
    readmeLoading,
    aiResearchRunning,
    aiResearchResult,
    aiResearchRunsLoading,
    aiResearchRuns,
    AI_RESEARCH_RUNS_AUTO_REFRESH_MS,
    aiResearchRunsAutoRefreshTimer,
    aiResearchRunsAutoRefreshActive,
    aiResearchTaskId,
    aiResearchTaskStatus,
    aiResearchTaskStage,
    aiResearchTaskProgress,
    aiResearchTaskIteration,
    aiResearchBacktestTaskId,
    aiResearchCancelledBacktestTaskId,
    aiResearchTaskPaperWorkspaceId,
    aiResearchTaskPaperUnitId,
    aiResearchTaskPaperStarted,
    aiResearchTaskLiveWorkspaceId,
    aiResearchTaskLiveUnitId,
    aiResearchTaskLivePrepared,
    aiResearchTaskPipeline,
    aiResearchTaskRequestSnapshot,
    aiResearchTaskContinuedFromRunId,
    aiResearchTaskContinuationSource,
    aiResearchTaskContinuationContext,
    aiResearchTaskError,
    aiResearchTaskMessage,
    aiResearchTaskLatestIteration,
    aiResearchTaskBestIteration,
    aiResearchTaskAssetSpecs,
    aiResearchTaskBacktestEnvironment,
    aiResearchTaskPromotionAudit,
    aiResearchCancelling,
    aiResearchCancelRequested,
    aiResearchPaperStartingRunId,
    aiResearchPaperReviewingRunId,
    aiResearchLiveHandoffLoadingRunId,
    aiResearchStrategyViewingRunId,
    aiResearchPaperReviews,
    aiResearchLiveHandoffs,
    aiResearchLiveHandoffApprovingRunId,
    aiResearchLiveTradingPreparingRunId,
    aiResearchConfigDialogVisible,
    aiResearchConfigProfiles,
    aiResearchConfigProfilesLoading,
    aiResearchConfigProfileSaving,
    aiResearchConfigProfileImporting,
    aiResearchConfigProfileDeletingId,
    aiResearchSelectedConfigProfileId,
    aiResearchConfigProfileName,
    aiResearchConfigProfileDescription,
    aiResearchConfigProfileFilePath,
    aiResearchConfigProfileFileInput,
    aiResearchMandate,
    aiResearchMandateConfirmed,
    aiResearchMandateLoading,
    aiResearchTimeline,
    aiResearchTimelineLoading,
    aiResearchVersions,
    aiResearchVersionsLoading,
    aiResearchVersionCompare,
    aiResearchVersionCompareLoading,
    aiResearchSelectedVersionIds,
    aiResearchVersionComparisonRows,
    aiResearchPrecheckLoading,
    aiResearchPrecheckResult,
    aiResearchPrecheckError,
    AI_RESEARCH_STAGE_LABELS,
    AI_RESEARCH_RUN_STATUS_LABELS,
    AI_RESEARCH_PAPER_REVIEW_STATUS_LABELS,
    AI_RESEARCH_PAPER_RULE_STATUS_LABELS,
    AI_RESEARCH_LIVE_READINESS_STATUS_LABELS,
    AI_RESEARCH_LIVE_HANDOFF_STATUS_LABELS,
    AI_RESEARCH_PIPELINE_STEP_STATUS_LABELS,
    AI_RESEARCH_WORKFLOW_STEPS,
    todayIsoDate,
    DEFAULT_AI_RESEARCH_START_DATE,
    DEFAULT_AI_RESEARCH_END_DATE,
    DEFAULT_AI_RESEARCH_MIN_PAPER_TRADING_DAYS,
    PAPER_GATEWAY_CONFIG_PLACEHOLDER,
    LIVE_GATEWAY_CONFIG_PLACEHOLDER,
    AI_RESEARCH_CONFIG_ERROR_MESSAGES,
    form,
    aiResearchForm,
    aiResearchHeroSteps,
    aiResearchHeroMetrics,
    aiResearchPrecheckTagType,
    aiResearchPrecheckSummary,
    strategies,
    templates,
    loading,
    filteredTemplates,
    displayedTemplates,
    aiResearchSelectedConfigProfile,
    aiResearchSelectedProfileSummary,
    aiResearchSelectedConfigDetails,
    aiResearchSelectedConfigPromptPreview,
    aiResearchVisibleRuns,
    aiResearchNoResultDescription,
    aiResearchMandateDetails,
    aiResearchCanCompareVersions,
    aiResearchVersionMetricKeys,
    strategyCategoryCount,
    strategyManagementStats,
    aiBestSharpe,
    aiResearchNextActions,
    aiResearchBestDiagnostics,
    aiResearchPipelineSteps,
    aiResearchPromotionAudit,
    aiResearchCurrentPaperFailed,
    aiResearchCurrentPaperTargetMissing,
    aiResearchPaperStatusText,
    aiResearchTaskStageLabel,
    aiResearchTaskContinuationSummary,
    aiResearchTaskPaperStatusText,
    aiResearchTaskLiveStatusText,
    aiResearchTaskPipelineSteps,
    aiResearchTaskLatestDiagnostics,
    aiResearchTaskBestIterationDisplay,
    aiResearchContinuationEnabled,
    aiResearchContinuationLabel,
    aiResearchCurrentContinuationSummary,
    canCancelAIResearchTask,
    canContinueAIResearchTask,
    canRetryAIResearchTask,
    canViewBestStrategyFromCurrentResult,
    canStartPaperFromCurrentResult,
    canOpenPaperFromCurrentResult,
    canReviewPaperFromCurrentResult,
    canContinueResearchFromCurrentPaperReview,
    canContinueResearchFromCurrentPaperIssue,
    canContinueResearchFromCurrentRunRecord,
    aiResearchCurrentPaperReview,
    aiResearchCurrentPaperReviewLock,
    canBuildLiveHandoffFromCurrentResult,
    aiResearchCurrentLiveHandoff,
    aiResearchCurrentPaperEnvironment,
    aiResearchCurrentRuntimeEnvironment,
    aiResearchBestGateEvaluations,
    aiResearchOutOfSampleValidation,
    paramTableData,
    openTemplateDetail,
    goBacktest,
    formatMetric,
    gateGapListFromUnknown,
    gateGapText,
    formatTaskProgress,
    taskLatestIterationLabel,
    taskLatestIterationMetric,
    taskLatestIterationProgress,
    taskLatestIterationDiagnostics,
    strategyGenerationText,
    formatDateTime,
    isRecord,
    containsRedactedSecret,
    optionalNumber,
    optionalBoolean,
    outOfSampleRatioPct,
    outOfSampleRatioValue,
    parseResearchDate,
    requiredOutOfSampleValidationError,
    aiResearchPrecheckAssetType,
    runAIResearchDataPrecheck,
    scheduleAIResearchDataPrecheck,
    aiResearchSymbolLabel,
    AI_RESEARCH_FUTURES_PREFIXES,
    isAIResearchFuturesSymbol,
    aiResearchAssetConstraintLine,
    aiResearchQualityGateLines,
    aiResearchValidationLines,
    buildGeneratedAIResearchPrompt,
    generateAIResearchPrompt,
    aiResearchMandateQualityGatesFromForm,
    aiResearchMandateInputPrompt,
    aiResearchMandatePayload,
    parseAIResearchMandate,
    confirmAIResearchMandate,
    clearAIResearchMandate,
    loadAIResearchMandate,
    ensureAIResearchMandateConfirmed,
    aiResearchMandateMatchesInput,
    mandateQualityGateSummary,
    aiResearchConfigProfileApi,
    hasConfigKey,
    configStringValue,
    snapshotAIResearchConfigForm,
    formatAIResearchConfigJson,
    applyAIResearchConfigToForm,
    upsertAIResearchConfigProfile,
    setAIResearchConfigProfileEditor,
    ensureAIResearchVisiblePrompt,
    applyAIResearchConfigProfile,
    openAIResearchConfigDialog,
    selectAIResearchConfigProfile,
    clearAIResearchDisplayedOutput,
    currentAIResearchResultMatchesConfigProfile,
    aiResearchConfigProfileForRunRecord,
    setAIResearchConfigProfileFromRunRecord,
    syncAIResearchDisplayedOutputWithSelectedProfile,
    aiResearchRunMatchesConfigProfile,
    aiResearchConfigProfileValue,
    aiResearchConfigProfileMetric,
    aiResearchConfigProfileOos,
    loadAIResearchConfigProfiles,
    createAIResearchConfigProfile,
    saveAIResearchConfigProfile,
    deleteAIResearchConfigProfile,
    triggerAIResearchConfigProfileImport,
    readSelectedAIResearchConfigFile,
    importAIResearchConfigProfileFile,
    validationWindowFromUnknown,
    outOfSampleValidationFromHandoff,
    hasResearchRuntimeEnvironment,
    researchRuntimeItems,
    runtimeItemsFromPayloads,
    gatewayRuntimeItemsFromSnapshot,
    hasPaperEnvironment,
    paperEnvironmentItems,
    environmentItemsFromPayload,
    runtimeEnvironmentPayload,
    firstRuntimeAssetSpecFromPayload,
    iterationOutOfSampleValidation,
    formatBacktestPercent,
    researchIterationBacktestSummary,
    formatOutOfSampleWindow,
    outOfSampleTagType,
    outOfSampleStatusLabel,
    recordOutOfSampleSummary,
    strategyIdFromIterationPayload,
    iterationPayloadHasStrategy,
    iterationPayloadRank,
    compareIterationPayloads,
    bestIterationPayloadForRecord,
    bestStrategyIdForRecord,
    fallbackSnapshotStrategyId,
    gatewayConfigJsonFromRunRecord,
    gatewayConfigJsonFromTaskSnapshot,
    liveGatewayConfigJsonFromRunRecord,
    bestStrategyFromRunRecord,
    aiResearchRunNeedsAutoRefresh,
    shouldAutoRefreshAIResearchRuns,
    clearAIResearchRunsAutoRefresh,
    unrefTimer,
    scheduleAIResearchRunsAutoRefresh,
    refreshAIResearchRunsSilently,
    loadAIResearchRuns,
    upsertAIResearchRunRecord,
    hydrateLiveHandoffFromRunRecord,
    refreshAIResearchRunRecord,
    clearAIResearchArtifacts,
    loadAIResearchRunArtifacts,
    loadAIResearchTimeline,
    loadAIResearchVersions,
    compareSelectedAIResearchVersions,
    aiResearchEventTagType,
    aiResearchVersionStatusTagType,
    aiResearchVersionMetric,
    aiResearchVersionMetricLabel,
    aiResearchRequestSnapshotFromRunRecord,
    aiResearchTaskFromRunRecord,
    selectAIResearchRunRecord,
    useAIResearchRecord,
    syncAIResearchFormFromResult,
    researchRecordUsesManualCommission,
    resolvedAIResearchTaskBacktestEnvironment,
    aiResearchTaskExplicitFields,
    aiResearchTaskUsesManualCommission,
    aiResearchTaskRestoredCommission,
    enabledQualityGate,
    researchIterationNextActions,
    iterationProgress,
    iterationProgressLabel,
    iterationProgressTagType,
    iterationProgressDeltaText,
    canStartPaperFromRecord,
    canReviewPaperFromRecord,
    canBuildLiveHandoffFromRecord,
    liveHandoffForRunId,
    liveHandoffForRecord,
    liveHandoffStatusForRecord,
    liveHandoffLocksPaperActions,
    canApproveLiveHandoff,
    canPrepareLiveTradingFromRecord,
    liveHandoffApprovalLabel,
    liveTradingPrepareSummary,
    isLiveTradingPreparedForRecord,
    liveTradingPreparedAtFromPipeline,
    isPaperTradingTargetMissing,
    paperStartButtonLabel,
    canContinueResearchFromPaperReview,
    canContinueResearchFromPaperIssue,
    canContinueResearchFromRunRecord,
    continuationSourceForRecord,
    continuationSourceLabel,
    continuationSummaryForRecord,
    aiResearchContinuationRecord,
    aiResearchContinuationContext,
    continuationQualityGateFailures,
    paperReviewFailureText,
    continuationIterationPayload,
    stringListFromUnknown,
    isLiveHandoffRejected,
    isPaperTradingStartFailure,
    pipelineStage,
    pipelineStageLabel,
    aiResearchRunStatusLabel,
    paperReviewStatusLabel,
    paperReviewRuleStatusLabel,
    paperReviewRuleGapText,
    paperReviewDispositionLabel,
    liveReadinessStatusLabel,
    liveHandoffStatusLabel,
    pipelineStepStatusLabel,
    pipelineStepTagType,
    pipelineStepIterationText,
    pipelineStepDetailText,
    aiResearchStageLabel,
    liveReadinessChecklistForReview,
    liveReadinessChecklistForRecord,
    liveReadinessExpiresAtForRecord,
    paperReviewLockFromPayload,
    paperReviewLockForRecord,
    paperReviewLockSummary,
    paperReviewLockStopResultText,
    liveReadinessChecklistFromPayload,
    promotionAuditFromPayload,
    clearAIResearchContinuation,
    paperHandoffRunRecordAssetSpecs,
    paperHandoffRunRecordBacktestEnvironment,
    paperStartedRunRecord,
    paperStartedPipeline,
    paperTradingStartError,
    paperStartFailedRunRecord,
    applyPaperStartToCurrentResult,
    applyResearchRunRecordToCurrentResult,
    workspaceFromResearchRunRecord,
    researchResultFromRunRecord,
    researchResultFromTaskSummary,
    researchIterationsFromRunRecord,
    researchIterationFromRunRecord,
    strategyFromIterationRecord,
    paperTradingFromRunRecord,
    paperUnitFromRunRecord,
    paperWorkspaceFromRunRecord,
    fallbackPaperUnitFromRunRecord,
    runtimeAssetSpecsPayload,
    paperRunStatusFromHandoff,
    unitFromIterationRecord,
    iterationStrategyPayload,
    iterationUnitPayload,
    iterationRunResultPayload,
    iterationUnitStatusPayload,
    unitStatusFromIterationRecord,
    metricFromPayload,
    unitTradingMode,
    emptyTradingSnapshot,
    stringFromUnknown,
    routeQueryText,
    aiResearchRouteRunId,
    aiResearchRouteWorkspaceId,
    applyAIResearchRoutePrefill,
    nullableString,
    stringArrayFromUnknown,
    uniqueTextItems,
    arrayFromUnknown,
    restoreAIResearchResultFromTask,
    restoreAIResearchRunFromRoute,
    reviewedRunRecord,
    paperReviewForRecord,
    applyPaperReviewToCurrentResult,
    startPaperFromResearchRecord,
    startPaperFromCurrentResult,
    viewBestStrategyFromCurrentResult,
    viewResearchIterationStrategy,
    viewStrategyFromResearchRecord,
    viewAIResearchVersionCode,
    paperMonitoringPlanFromHandoff,
    reviewPaperFromResearchRecord,
    reviewPaperFromCurrentResult,
    buildLiveHandoffFromCurrentResult,
    approveCurrentLiveHandoff,
    prepareLiveTradingFromCurrentResult,
    buildLiveHandoffFromResearchRecord,
    approveLiveHandoffFromResearchRecord,
    prepareLiveTradingFromResearchRecord,
    liveHandoffRunRecord,
    liveTradingPreparedRunRecord,
    upsertPipelineStep,
    continueResearchFromCurrentPaperReview,
    continueResearchFromCurrentRunRecord,
    continueResearchFromPaperReview,
    continueResearchFromRecord,
    prepareContinuationPromotion,
    buildAIResearchRequest,
    aiResearchPaperWorkspaceName,
    parseAIResearchGatewayConfig,
    parseAIResearchLiveGatewayConfig,
    parseGatewayConfigJson,
    notifyAIResearchConfigError,
    aiResearchPaperStartRequest,
    aiResearchLivePrepareRequest,
    isAIResearchTaskTerminal,
    isAIResearchTaskCancelled,
    isRestorableAIResearchTask,
    sleep,
    AI_RESEARCH_TASK_POLL_INTERVAL_MS,
    AI_RESEARCH_TASK_MIN_TIMEOUT_MS,
    AI_RESEARCH_TASK_MAX_TIMEOUT_MS,
    boundedNumber,
    aiResearchTaskPollTimeoutMs,
    applyAIResearchTaskStatus,
    applyAIResearchTaskSnapshotToForm,
    aiResearchTaskFailureMessage,
    aiResearchErrorMessage,
    isAIResearchResultPaperStartFailure,
    notifyAIResearchResult,
    resetAIResearchTaskState,
    aiResearchRunnableInput,
    applyCanonicalAIResearchPrompt,
    applyCompletedAIResearchResult,
    handleAIResearchRunError,
    runAIResearchRequest,
    continueAIResearchFromRunRecord,
    pollAIResearchTask,
    restoreActiveAIResearchTask,
    cancelAIResearchTask,
    continueAIResearchFromTaskSnapshot,
    retryAIResearchFromTaskSnapshot,
    runAIResearchLoop,
    openResearchWorkspace,
    openPaperWorkspace,
    openLiveWorkspaceFromCurrentResult,
    openLiveWorkspaceFromRecord,
    showCreateDialog,
    editStrategy,
    viewStrategy,
    useTemplate,
    updateStrategyForm,
    saveStrategy,
    deleteStrategy,
  }
}
