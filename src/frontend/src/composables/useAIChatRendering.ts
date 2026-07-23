import { computed, type ComputedRef } from 'vue'
import i18n from '@/i18n'
import type { KBAssistantMode, KBCitation, KBReasonCode, KBStrategyDraft } from '@/api/kbChat'

// Top-level helper to access translations from a non-component module.
// Wrap in a function so the i18n instance's locale ref is consulted at call time
// (vue-i18n's t() is reactive when the locale ref changes).
function t(key: string): string {
  return i18n.global.t(key)
}

export interface QuickTool {
  icon: string
  title: string
  description: string
  prompt: string
  assistantMode?: KBAssistantMode
}

export interface AssistantModeMeta {
  label: string
  emptyTitle: string
  emptyDescription: string
  inputHint: string
  inputPlaceholder: string
  suggestedPrompts: string[]
  quickTools: QuickTool[]
}

// Reactive computed list — locale changes update labels automatically.
export const assistantModeOptions: ComputedRef<Array<{ value: KBAssistantMode; label: string }>> = computed(() => [
  { value: 'knowledge_qa', label: t('aiChat.modeKnowledgeQA') },
])

// Reactive computed map — locale changes update labels automatically.
export const assistantModeMetaMap: ComputedRef<Record<KBAssistantMode, AssistantModeMeta>> = computed(() => ({
  knowledge_qa: {
    label: t('aiChat.modeKnowledgeQA'),
    emptyTitle: t('aiChat.kqaEmptyTitle'),
    emptyDescription: t('aiChat.kqaEmptyDesc'),
    inputHint: t('aiChat.kqaInputHint'),
    inputPlaceholder: t('aiChat.kqaInputPh'),
    suggestedPrompts: [
      t('aiChat.kqaPrompt1'),
      t('aiChat.kqaPrompt2'),
      t('aiChat.kqaPrompt3'),
    ],
    quickTools: [
      {
        icon: 'summary',
        title: t('aiChat.kqaToolSummaryTitle'),
        description: t('aiChat.kqaToolSummaryDesc'),
        prompt: t('aiChat.kqaToolSummaryPrompt'),
      },
      {
        icon: 'docs',
        title: t('aiChat.kqaToolDocsTitle'),
        description: t('aiChat.kqaToolDocsDesc'),
        prompt: t('aiChat.kqaToolDocsPrompt'),
      },
      {
        icon: 'path',
        title: t('aiChat.kqaToolPathTitle'),
        description: t('aiChat.kqaToolPathDesc'),
        prompt: t('aiChat.kqaToolPathPrompt'),
      },
    ],
  },
  strategy_idea: {
    label: t('aiChat.modeStrategyResearch'),
    emptyTitle: t('aiChat.sresearchEmptyTitle'),
    emptyDescription: t('aiChat.sresearchEmptyDesc'),
    inputHint: t('aiChat.sresearchInputHint'),
    inputPlaceholder: t('aiChat.sresearchInputPh'),
    suggestedPrompts: [
      t('aiChat.sideaPrompt1'),
      t('aiChat.sideaPrompt2'),
      t('aiChat.sideaPrompt3'),
    ],
    quickTools: [
      {
        icon: 'expand',
        title: t('aiChat.sideaToolExpandTitle'),
        description: t('aiChat.sideaToolExpandDesc'),
        prompt: t('aiChat.sideaToolExpandPrompt'),
        assistantMode: 'strategy_idea',
      },
      {
        icon: 'code',
        title: t('aiChat.btToolCodeTitle'),
        description: t('aiChat.btToolCodeDesc'),
        prompt: t('aiChat.btToolCodePrompt'),
        assistantMode: 'backtrader_strategy',
      },
      {
        icon: 'logic',
        title: t('aiChat.reviewToolLogicTitle'),
        description: t('aiChat.reviewToolLogicDesc'),
        prompt: t('aiChat.reviewToolLogicPrompt'),
        assistantMode: 'strategy_review',
      },
    ],
  },
  backtrader_strategy: {
    label: t('aiChat.modeBacktraderStrategy'),
    emptyTitle: t('aiChat.btEmptyTitle'),
    emptyDescription: t('aiChat.btEmptyDesc'),
    inputHint: t('aiChat.btInputHint'),
    inputPlaceholder: t('aiChat.btInputPh'),
    suggestedPrompts: [
      t('aiChat.btPrompt1'),
      t('aiChat.btPrompt2'),
      t('aiChat.btPrompt3'),
    ],
    quickTools: [
      {
        icon: 'code',
        title: t('aiChat.btToolCodeTitle'),
        description: t('aiChat.btToolCodeDesc'),
        prompt: t('aiChat.btToolCodePrompt'),
      },
      {
        icon: 'platform',
        title: t('aiChat.btToolPlatformTitle'),
        description: t('aiChat.btToolPlatformDesc'),
        prompt: t('aiChat.btToolPlatformPrompt'),
      },
      {
        icon: 'params',
        title: t('aiChat.btToolParamsTitle'),
        description: t('aiChat.btToolParamsDesc'),
        prompt: t('aiChat.btToolParamsPrompt'),
      },
    ],
  },
  strategy_review: {
    label: t('aiChat.modeStrategyReview'),
    emptyTitle: t('aiChat.reviewEmptyTitle'),
    emptyDescription: t('aiChat.reviewEmptyDesc'),
    inputHint: t('aiChat.reviewInputHint'),
    inputPlaceholder: t('aiChat.reviewInputPh'),
    suggestedPrompts: [
      t('aiChat.reviewPrompt1'),
      t('aiChat.reviewPrompt2'),
      t('aiChat.reviewPrompt3'),
    ],
    quickTools: [
      {
        icon: 'logic',
        title: t('aiChat.reviewToolLogicTitle'),
        description: t('aiChat.reviewToolLogicDesc'),
        prompt: t('aiChat.reviewToolLogicPrompt'),
      },
      {
        icon: 'bias',
        title: t('aiChat.reviewToolBiasTitle'),
        description: t('aiChat.reviewToolBiasDesc'),
        prompt: t('aiChat.reviewToolBiasPrompt'),
      },
      {
        icon: 'next',
        title: t('aiChat.reviewToolNextTitle'),
        description: t('aiChat.reviewToolNextDesc'),
        prompt: t('aiChat.reviewToolNextPrompt'),
      },
    ],
  },
  trading_execution: {
    label: t('aiChat.modeTradingExecution'),
    emptyTitle: t('aiChat.tradeEmptyTitle'),
    emptyDescription: t('aiChat.tradeEmptyDesc'),
    inputHint: t('aiChat.tradeInputHint'),
    inputPlaceholder: t('aiChat.tradeInputPh'),
    suggestedPrompts: [
      t('aiChat.tradePrompt1'),
      t('aiChat.tradePrompt2'),
      t('aiChat.tradePrompt3'),
      t('aiChat.tradePrompt4'),
      t('aiChat.tradePrompt5'),
    ],
    quickTools: [
      {
        icon: 'trade',
        title: t('aiChat.tradeToolTradeTitle'),
        description: t('aiChat.tradeToolTradeDesc'),
        prompt: t('aiChat.tradeToolTradePrompt'),
      },
      {
        icon: 'position',
        title: t('aiChat.tradeToolPositionTitle'),
        description: t('aiChat.tradeToolPositionDesc'),
        prompt: t('aiChat.tradeToolPositionPrompt'),
      },
      {
        icon: 'close',
        title: t('aiChat.tradeToolCloseTitle'),
        description: t('aiChat.tradeToolCloseDesc'),
        prompt: t('aiChat.tradeToolClosePrompt'),
      },
    ],
  },
  stock_analysis: {
    label: t('aiChat.modeStockAnalysis'),
    emptyTitle: t('aiChat.stockEmptyTitle'),
    emptyDescription: t('aiChat.stockEmptyDesc'),
    inputHint: t('aiChat.stockInputHint'),
    inputPlaceholder: t('aiChat.stockInputPh'),
    suggestedPrompts: [
      t('aiChat.stockPrompt1'),
      t('aiChat.stockPrompt2'),
      t('aiChat.stockPrompt3'),
    ],
    quickTools: [
      {
        icon: 'stock',
        title: t('aiChat.stockToolSingleTitle'),
        description: t('aiChat.stockToolSingleDesc'),
        prompt: t('aiChat.stockToolSinglePrompt'),
      },
      {
        icon: 'risk',
        title: t('aiChat.stockToolRiskTitle'),
        description: t('aiChat.stockToolRiskDesc'),
        prompt: t('aiChat.stockToolRiskPrompt'),
      },
      {
        icon: 'summary',
        title: t('aiChat.stockToolReportTitle'),
        description: t('aiChat.stockToolReportDesc'),
        prompt: t('aiChat.stockToolReportPrompt'),
      },
    ],
  },
}))


export function formatDate(value?: string | null): string {
  if (!value) return t('aiChat.msgUnknownTime')
  return value.replace('T', ' ').slice(0, 16)
}

export function retrievalProfileLabel(profile?: string | null): string {
  if (profile === 'precision') return t('kb.profilePrecision')
  if (profile === 'exploration') return t('kb.profileExploration')
  return t('aiChat.profileBalance')
}

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function getDraftParamCount(draft?: KBStrategyDraft | null): number {
  return isPlainRecord(draft?.params) ? Object.keys(draft.params).length : 0
}

export function getDraftAssumptions(draft?: KBStrategyDraft | null): string[] {
  return Array.isArray(draft?.assumptions) ? draft.assumptions : []
}

export function getDraftRiskPoints(draft?: KBStrategyDraft | null): string[] {
  return Array.isArray(draft?.risk_points) ? draft.risk_points : []
}

export function getDraftDataSourceType(draft?: KBStrategyDraft | null): string {
  return draft?.data_source?.type || t('aiChat.notSet')
}

export function getDraftTimeframe(draft?: KBStrategyDraft | null): string {
  return draft?.data_source?.timeframe || draft?.suggested_timeframe || t('aiChat.notSet')
}

export function getDraftInitialCash(draft?: KBStrategyDraft | null): number | string {
  return typeof draft?.backtest_defaults?.initial_cash === 'number'
    ? draft.backtest_defaults.initial_cash
    : t('aiChat.notSet')
}

export function getDraftCommission(draft?: KBStrategyDraft | null): number | string {
  return typeof draft?.backtest_defaults?.commission === 'number'
    ? draft.backtest_defaults.commission
    : t('aiChat.notSet')
}

export function getStrategyDraftIssue(draft?: KBStrategyDraft | null): string | null {
  if (!draft) return t('aiChat.draftIssueNoCard')
  if (!draft.name?.trim()) return t('aiChat.draftIssueNoName')
  if (!draft.code?.trim()) return t('aiChat.draftIssueNoCode')
  const code = draft.code.trim()
  const hasStrategyClass = /class\s+\w+\s*\([^)]*bt\.Strategy[^)]*\)\s*:/.test(code)
  const hasInit = /def\s+__init__\s*\(/.test(code)
  const hasNext = /def\s+next\s*\(/.test(code)
  const hasTradeAction = /\bself\.(buy|sell|close|order_target_percent|order_target_size|order_target_value|buy_bracket|sell_bracket)\s*\(/.test(code)
  const codeWithoutComments = code
    .split('\n')
    .map(line => line.replace(/#.*$/, ''))
    .join('\n')
  const hasPlaceholder = (
    /^\s*pass\s*$/m.test(codeWithoutComments)
    || /TODO|NotImplemented|待实现|省略|\.{3}|…/.test(code)
  )
  if (!hasStrategyClass || !hasInit || !hasNext || !hasTradeAction || hasPlaceholder) {
    return t('aiChat.draftIssueIncompleteCode')
  }
  if (!isPlainRecord(draft.params)) return t('aiChat.draftIssueBadParams')
  if (!draft.category?.trim()) return t('aiChat.draftIssueNoCategory')
  if (!draft.data_source || !draft.data_source.timeframe) {
    return t('aiChat.draftIssueNoTimeframe')
  }
  if (
    !draft.backtest_defaults
      || typeof draft.backtest_defaults.initial_cash !== 'number'
      || typeof draft.backtest_defaults.commission !== 'number'
  ) {
    return t('aiChat.draftIssueNoBacktestDefaults')
  }
  if (!draft.execution_plan || typeof draft.execution_plan.run_parallel !== 'boolean') {
    return t('aiChat.draftIssueNoExecPlan')
  }
  return null
}

export function getDiagnosticTitle(reasonCode?: KBReasonCode | null): string {
  if (reasonCode === 'no_context_found') return t('aiChat.diagNoContext')
  if (reasonCode === 'knowledge_base_overview') return t('aiChat.diagKnowledgeBaseOverview')
  if (reasonCode === 'ai_not_configured') return t('aiChat.diagAINotConfigured')
  if (reasonCode === 'ai_provider_failed') return t('aiChat.diagAIProviderFailed')
  return t('aiChat.diagDefault')
}

export function getCitationTitle(citation: KBCitation): string {
  const title = citation.document_title?.trim()
  return title || t('aiChat.citationUnnamedDoc')
}

export function getCitationKey(citation: KBCitation, index: number): string {
  return citation.chunk_id || `${citation.document_id || 'missing-doc'}-${citation.chunk_index ?? index}`
}

export function getCitationChunkIndex(citation: KBCitation): number | string {
  return typeof citation.chunk_index === 'number' ? citation.chunk_index : t('aiChat.citationChunkUnknown')
}

export function getCitationSimilarity(citation: KBCitation): number {
  const similarity = typeof citation.similarity === 'number' ? citation.similarity : 0
  return Math.round(Math.max(0, Math.min(1, similarity)) * 100)
}
