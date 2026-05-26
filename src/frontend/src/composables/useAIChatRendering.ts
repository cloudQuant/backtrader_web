import type { KBAssistantMode, KBCitation, KBReasonCode, KBStrategyDraft } from '@/api/kbChat'

export const assistantModeOptions: Array<{ value: KBAssistantMode; label: string }> = [
  { value: 'knowledge_qa', label: '知识问答' },
  { value: 'strategy_idea', label: '策略构思' },
  { value: 'backtrader_strategy', label: 'Backtrader策略生成' },
  { value: 'strategy_review', label: '策略审查' },
  { value: 'trading_execution', label: '交易执行' },
]

export interface QuickTool {
  icon: string
  title: string
  description: string
  prompt: string
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

export const assistantModeMetaMap: Record<KBAssistantMode, AssistantModeMeta> = {
  knowledge_qa: {
    label: '知识问答',
    emptyTitle: '从知识库开始提问',
    emptyDescription: '选择知识库后输入问题，回答会优先引用已经保存的文档内容。',
    inputHint: '输入问题，AI 将结合知识库回答',
    inputPlaceholder: '请输入问题... (Enter 发送，Shift+Enter 换行)',
    suggestedPrompts: [
      '这个知识库主要包含哪些内容？',
      '总结当前知识库的核心主题',
      '有哪些值得重点阅读的文档？',
    ],
    quickTools: [
      {
        icon: 'summary',
        title: '总结知识库',
        description: '快速生成核心主题摘要',
        prompt: '请总结这个知识库的核心主题与重点文档。',
      },
      {
        icon: 'docs',
        title: '提取关键文档',
        description: '找出最值得优先阅读的内容',
        prompt: '请列出这个知识库中最值得优先阅读的文档，并说明原因。',
      },
      {
        icon: 'path',
        title: '生成阅读路径',
        description: '给出推荐阅读顺序',
        prompt: '请为我生成这个知识库的推荐阅读路径。',
      },
    ],
  },
  strategy_idea: {
    label: '策略构思',
    emptyTitle: '拆解策略想法',
    emptyDescription: '把一句策略设想拆成信号、风控、数据需求和回测验证步骤。',
    inputHint: '输入一句话策略想法，AI 将生成结构化研究方案',
    inputPlaceholder: '例如：我想做一个基于均线突破和成交量放大的日线趋势策略',
    suggestedPrompts: [
      '把“均线突破 + 放量确认”的想法扩展成完整研究方案',
      '帮我设计一个适合 A 股日线回测的低频趋势策略',
      '把“回撤后反弹买入”整理成可验证的量化假设',
    ],
    quickTools: [
      {
        icon: 'expand',
        title: '一句话扩展',
        description: '把模糊策略想法拆成研究任务',
        prompt: '请把下面这句自然语言策略想法扩展成结构化研究方案：',
      },
      {
        icon: 'test',
        title: '生成回测计划',
        description: '补充样本区间、指标和验证步骤',
        prompt: '请基于这个策略想法生成详细的回测计划与验证步骤：',
      },
      {
        icon: 'risk',
        title: '补风控框架',
        description: '为策略添加仓位和止损框架',
        prompt: '请为这个策略补充仓位控制、止损止盈和风险暴露约束：',
      },
    ],
  },
  backtrader_strategy: {
    label: 'Backtrader策略生成',
    emptyTitle: '生成策略实现草案',
    emptyDescription: '输入自然语言策略需求，生成可保存、可加入工作区的 Backtrader 草稿。',
    inputHint: '输入自然语言需求，AI 将生成 Backtrader 策略草案',
    inputPlaceholder: '例如：帮我生成一个 RSI 超卖反弹 + ATR 止损的 Backtrader 策略骨架',
    suggestedPrompts: [
      '请生成一个“双均线 + ATR 止损”的 Backtrader 策略代码骨架',
      '请把“突破20日高点买入，跌破10日低点卖出”转成 Backtrader 策略',
      '请生成一个适合期货分钟级别的布林带均值回归策略草案',
    ],
    quickTools: [
      {
        icon: 'code',
        title: '生成代码骨架',
        description: '输出 Backtrader 类与关键参数',
        prompt: '请把下面的自然语言策略需求生成 Backtrader 策略代码骨架：',
      },
      {
        icon: 'platform',
        title: '生成接入建议',
        description: '补充平台参数与运行建议',
        prompt: '请为这个 Backtrader 策略补充在 Backtrader Web 中的接入建议：',
      },
      {
        icon: 'params',
        title: '生成参数表',
        description: '提炼可优化参数与默认值',
        prompt: '请为这个策略生成参数表、默认值以及建议优化区间：',
      },
    ],
  },
  strategy_review: {
    label: '策略审查',
    emptyTitle: '审查策略质量',
    emptyDescription: '粘贴策略描述或代码片段，从逻辑、风控、数据和回测偏差角度审查。',
    inputHint: '输入策略描述或代码，AI 将执行结构化审查',
    inputPlaceholder: '例如：请审查这个动量策略的风控设计是否充分...',
    suggestedPrompts: [
      '请审查一个“动量轮动 + 每周调仓”策略的主要风险',
      '请从回测偏差角度审查“财报因子选股”策略',
      '请检查这个趋势策略是否存在过拟合和数据窥探风险',
    ],
    quickTools: [
      {
        icon: 'logic',
        title: '审查策略逻辑',
        description: '识别核心假设和漏洞',
        prompt: '请从策略逻辑、风险和可执行性角度审查下面的策略：',
      },
      {
        icon: 'bias',
        title: '审查回测偏差',
        description: '检查未来函数、幸存者偏差等问题',
        prompt: '请重点审查下面策略是否存在未来函数、数据泄露或样本偏差：',
      },
      {
        icon: 'next',
        title: '给出优化顺序',
        description: '生成下一步修改建议',
        prompt: '请为这个策略生成按优先级排序的优化建议与验证顺序：',
      },
    ],
  },
  trading_execution: {
    label: '交易执行',
    emptyTitle: '自然语言交易',
    emptyDescription: '用自然语言描述交易意图，AI 自动解析并执行。支持期货、加密货币等多品种。',
    inputHint: '描述您的交易意图',
    inputPlaceholder: '例如：买入1手螺纹钢主力合约 / 帮我在币安买入0.1个BTC / 查看当前持仓',
    suggestedPrompts: [
      '买入1手螺纹钢主力合约',
      '帮我在币安买入0.1个BTC',
      '以3500限价卖出2手铁矿石',
      '查看当前持仓',
      '平掉所有螺纹钢仓位',
    ],
    quickTools: [
      {
        icon: 'trade',
        title: '快速下单',
        description: '用自然语言描述交易',
        prompt: '买入',
      },
      {
        icon: 'position',
        title: '查看持仓',
        description: '查询当前持仓状态',
        prompt: '查看我当前的持仓情况',
      },
      {
        icon: 'close',
        title: '平仓',
        description: '平掉指定品种仓位',
        prompt: '平掉所有',
      },
    ],
  },
}


export function formatDate(value?: string | null): string {
  if (!value) return '未知时间'
  return value.replace('T', ' ').slice(0, 16)
}

export function retrievalProfileLabel(profile?: string | null): string {
  if (profile === 'precision') return '高精度引用'
  if (profile === 'exploration') return '探索式阅读'
  return '量化研究平衡'
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
  return draft?.data_source?.type || '未设置'
}

export function getDraftTimeframe(draft?: KBStrategyDraft | null): string {
  return draft?.data_source?.timeframe || draft?.suggested_timeframe || '未设置'
}

export function getDraftInitialCash(draft?: KBStrategyDraft | null): number | string {
  return typeof draft?.backtest_defaults?.initial_cash === 'number'
    ? draft.backtest_defaults.initial_cash
    : '未设置'
}

export function getDraftCommission(draft?: KBStrategyDraft | null): number | string {
  return typeof draft?.backtest_defaults?.commission === 'number'
    ? draft.backtest_defaults.commission
    : '未设置'
}

export function getStrategyDraftIssue(draft?: KBStrategyDraft | null): string | null {
  if (!draft) return '当前回答未包含策略草稿'
  if (!draft.name?.trim()) return '策略草稿缺少名称，暂不能保存或执行'
  if (!draft.code?.trim()) return '策略草稿缺少 Backtrader 代码，暂不能保存或执行'
  if (!isPlainRecord(draft.params)) return '策略草稿参数格式异常，暂不能保存或执行'
  if (!draft.category?.trim()) return '策略草稿缺少策略分类，暂不能保存或执行'
  if (!draft.data_source || !draft.data_source.timeframe) {
    return '策略草稿缺少数据源周期，暂不能添加到工作区'
  }
  if (
    !draft.backtest_defaults
      || typeof draft.backtest_defaults.initial_cash !== 'number'
      || typeof draft.backtest_defaults.commission !== 'number'
  ) {
    return '策略草稿缺少回测默认参数，暂不能执行'
  }
  if (!draft.execution_plan || typeof draft.execution_plan.run_parallel !== 'boolean') {
    return '策略草稿缺少执行计划，暂不能添加到工作区'
  }
  return null
}

export function getDiagnosticTitle(reasonCode?: KBReasonCode | null): string {
  if (reasonCode === 'no_context_found') return '未找到相关上下文'
  if (reasonCode === 'ai_not_configured') return 'AI 模型未配置'
  if (reasonCode === 'ai_provider_failed') return 'AI 模型调用失败'
  return 'AI 助手诊断'
}

export function getCitationTitle(citation: KBCitation): string {
  const title = citation.document_title?.trim()
  return title || '未命名文档'
}

export function getCitationKey(citation: KBCitation, index: number): string {
  return citation.chunk_id || `${citation.document_id || 'missing-doc'}-${citation.chunk_index ?? index}`
}

export function getCitationChunkIndex(citation: KBCitation): number | string {
  return typeof citation.chunk_index === 'number' ? citation.chunk_index : '未知'
}

export function getCitationSimilarity(citation: KBCitation): number {
  const similarity = typeof citation.similarity === 'number' ? citation.similarity : 0
  return Math.round(Math.max(0, Math.min(1, similarity)) * 100)
}
