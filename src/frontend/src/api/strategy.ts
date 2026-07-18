import api from './index'
import type {
  Strategy,
  StrategyCreate,
  StrategyListResponse,
  StrategyTemplate,
  StrategyConfig,
  StrategyType,
} from '@/types'
import type {
  StrategyCopilotDraftRequest,
  StrategyCopilotDraftResponse,
  StrategyCopilotWorkspaceAddRequest,
  StrategyCopilotWorkspaceAddResponse,
  StrategyCopilotBacktestRequest,
  StrategyCopilotBacktestResponse,
  AIStrategyResearchRunRequest,
  InvestmentMandateCreateRequest,
  InvestmentMandateResponse,
  AIStrategyResearchConfigProfile,
  AIStrategyResearchConfigProfileListResponse,
  AIStrategyResearchConfigProfileCreateRequest,
  AIStrategyResearchConfigProfileUpdateRequest,
  AIStrategyResearchConfigProfileImportRequest,
  AIStrategyResearchConfigProfileImportResponse,
  AIStrategyPaperTradingStart,
  AIStrategyPaperTradingStartRequest,
  AIStrategyResearchRunRecord,
  AIStrategyResearchRunListResponse,
  AIStrategyResearchRunResponse,
  AIStrategyResearchTaskResponse,
  ResearchTimelineResponse,
  AIStrategyResearchVersion,
  AIStrategyResearchVersionListResponse,
  AIStrategyResearchVersionCompareResponse,
  AIStrategyResearchTaskListResponse,
  AIStrategyResearchTaskContinueRequest,
  AIStrategyResearchRunContinueRequest,
  AIStrategyPaperTradingReview,
  AIStrategyLiveHandoffApprovalRequest,
  AIStrategyLiveHandoffPackage,
  AIStrategyLiveTradingPrepareRequest,
  AIStrategyLiveTradingPrepare,
  StrategyScoreRequest,
  StrategyScoreResponse,
  StrategyOverfittingAnalysisRequest,
  StrategyOverfittingTaskSubmission,
  StrategyOverfittingTaskResult,
  StrategyExplainRequest,
  StrategyExplanation,
} from '@/types/strategy'

export type {
  StrategyCopilotDataSource,
  StrategyCopilotBacktestDefaults,
  StrategyCopilotExecutionPlan,
  StrategyCopilotDraft,
  StrategyCopilotDraftRequest,
  StrategyCopilotDraftResponse,
  StrategyCopilotWorkspaceAddRequest,
  StrategyCopilotWorkspaceAddResponse,
  StrategyCopilotBacktestRequest,
  StrategyCopilotRunResult,
  StrategyCopilotBacktestResponse,
  AIStrategyResearchRunRequest,
  InvestmentMandateCreateRequest,
  InvestmentMandateResponse,
  AIStrategyResearchConfigProfile,
  AIStrategyResearchConfigProfileListResponse,
  AIStrategyResearchConfigProfileCreateRequest,
  AIStrategyResearchConfigProfileUpdateRequest,
  AIStrategyResearchConfigProfileImportRequest,
  AIStrategyResearchConfigProfileImportResponse,
  AIStrategyQualityGateEvaluation,
  AIStrategyGateGap,
  AIStrategyResearchDiagnostics,
  AIStrategyIterationProgress,
  AIStrategyPaperMonitoringRule,
  AIStrategyPaperTradingRuleEvaluation,
  AIStrategyResearchIteration,
  AIStrategyOutOfSampleValidation,
  AIStrategyPaperTradingStart,
  AIStrategyPaperTradingStartRequest,
  AIStrategyLiveReadinessItem,
  AIStrategyPromotionAuditItem,
  AIStrategyResearchRunRecord,
  AIStrategyResearchRunListResponse,
  AIStrategyResearchRunResponse,
  AIStrategyResearchTaskResponse,
  ResearchPipelineEvent,
  ResearchTimelineResponse,
  AIStrategyResearchVersion,
  AIStrategyResearchVersionListResponse,
  AIStrategyResearchVersionCompareResponse,
  AIStrategyResearchTaskListResponse,
  AIStrategyResearchTaskContinueRequest,
  AIStrategyResearchRunContinueRequest,
  AIStrategyPaperTradingReview,
  AIStrategyPaperReviewLock,
  AIStrategyLiveHandoffApprovalRequest,
  AIStrategyLiveHandoffApprovalRecord,
  AIStrategyLiveHandoffPackage,
  AIStrategyLiveTradingPrepareRequest,
  AIStrategyLiveTradingPrepare,
  AIStrategyPipelineStep,
  AIStrategyPipelineSummary,
  StrategyScoreDimension,
  StrategyScoreRequest,
  StrategyScoreResponse,
  StrategyOverfittingMethod,
  StrategyOverfittingRiskLevel,
  StrategyOverfittingAnalysisRequest,
  StrategyOverfittingMethodResult,
  StrategyOverfittingTaskSubmission,
  StrategyOverfittingTaskResult,
  StrategyIndicator,
  StrategySignal,
  StrategyRiskControl,
  StrategyParamInfo,
  StrategyStructure,
  StrategyExplainRequest,
  StrategyExplanation,
} from '@/types/strategy'

export const strategyApi = {
  async create(data: StrategyCreate): Promise<Strategy> {
    return api.post<Strategy, StrategyCreate>('/strategy/', data)
  },

  async generateCopilotDraft(data: StrategyCopilotDraftRequest): Promise<StrategyCopilotDraftResponse> {
    return api.post<StrategyCopilotDraftResponse, StrategyCopilotDraftRequest>('/strategy/copilot/draft', data)
  },

  async addCopilotDraftToWorkspace(
    workspaceId: string,
    data: StrategyCopilotWorkspaceAddRequest
  ): Promise<StrategyCopilotWorkspaceAddResponse> {
    return api.post<StrategyCopilotWorkspaceAddResponse, StrategyCopilotWorkspaceAddRequest>(
      `/strategy/copilot/workspaces/${workspaceId}/units`,
      data
    )
  },

  async backtestCopilotDraft(
    workspaceId: string,
    data: StrategyCopilotBacktestRequest
  ): Promise<StrategyCopilotBacktestResponse> {
    return api.post<StrategyCopilotBacktestResponse, StrategyCopilotBacktestRequest>(
      `/strategy/copilot/workspaces/${workspaceId}/backtest`,
      data
    )
  },

  async listAIResearchConfigProfiles(): Promise<AIStrategyResearchConfigProfileListResponse> {
    return api.get<AIStrategyResearchConfigProfileListResponse>(
      '/strategy/ai-research/config-profiles'
    )
  },

  async createAIResearchConfigProfile(
    data: AIStrategyResearchConfigProfileCreateRequest
  ): Promise<AIStrategyResearchConfigProfile> {
    return api.post<
      AIStrategyResearchConfigProfile,
      AIStrategyResearchConfigProfileCreateRequest
    >('/strategy/ai-research/config-profiles', data)
  },

  async updateAIResearchConfigProfile(
    profileId: string,
    data: AIStrategyResearchConfigProfileUpdateRequest
  ): Promise<AIStrategyResearchConfigProfile> {
    return api.put<
      AIStrategyResearchConfigProfile,
      AIStrategyResearchConfigProfileUpdateRequest
    >(`/strategy/ai-research/config-profiles/${profileId}`, data)
  },

  async deleteAIResearchConfigProfile(profileId: string): Promise<void> {
    return api.delete<void>(`/strategy/ai-research/config-profiles/${profileId}`)
  },

  async importAIResearchConfigProfileYaml(
    data: AIStrategyResearchConfigProfileImportRequest
  ): Promise<AIStrategyResearchConfigProfileImportResponse> {
    return api.post<
      AIStrategyResearchConfigProfileImportResponse,
      AIStrategyResearchConfigProfileImportRequest
    >('/strategy/ai-research/config-profiles/import', data)
  },

  async runAIResearchLoop(
    data: AIStrategyResearchRunRequest
  ): Promise<AIStrategyResearchRunResponse> {
    return api.post<AIStrategyResearchRunResponse, AIStrategyResearchRunRequest>(
      '/strategy/ai-research/run',
      data
    )
  },

  async createAIResearchMandate(
    data: InvestmentMandateCreateRequest
  ): Promise<InvestmentMandateResponse> {
    return api.post<InvestmentMandateResponse, InvestmentMandateCreateRequest>(
      '/strategy/ai-research/mandates',
      data
    )
  },

  async getAIResearchMandate(mandateId: string): Promise<InvestmentMandateResponse> {
    return api.get<InvestmentMandateResponse>(`/strategy/ai-research/mandates/${mandateId}`)
  },

  async submitAIResearchTask(
    data: AIStrategyResearchRunRequest
  ): Promise<AIStrategyResearchTaskResponse> {
    return api.post<AIStrategyResearchTaskResponse, AIStrategyResearchRunRequest>(
      '/strategy/ai-research/tasks',
      data
    )
  },

  async getAIResearchTask(taskId: string): Promise<AIStrategyResearchTaskResponse> {
    return api.get<AIStrategyResearchTaskResponse>(`/strategy/ai-research/tasks/${taskId}`)
  },

  async listAIResearchTasks(activeOnly = false, limit = 20): Promise<AIStrategyResearchTaskListResponse> {
    return api.get<AIStrategyResearchTaskListResponse>('/strategy/ai-research/tasks', {
      params: { active_only: activeOnly, limit },
    })
  },

  async cancelAIResearchTask(taskId: string): Promise<AIStrategyResearchTaskResponse> {
    return api.post<AIStrategyResearchTaskResponse, undefined>(
      `/strategy/ai-research/tasks/${taskId}/cancel`,
      undefined
    )
  },

  async continueAIResearchTask(
    taskId: string,
    data: AIStrategyResearchTaskContinueRequest = {}
  ): Promise<AIStrategyResearchTaskResponse> {
    return api.post<AIStrategyResearchTaskResponse, AIStrategyResearchTaskContinueRequest>(
      `/strategy/ai-research/tasks/${taskId}/continue`,
      data
    )
  },

  async continueAIResearchRun(
    runId: string,
    data: AIStrategyResearchRunContinueRequest = {},
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyResearchTaskResponse> {
    return api.post<AIStrategyResearchTaskResponse, AIStrategyResearchRunContinueRequest>(
      `/strategy/ai-research/runs/${runId}/continue`,
      data,
      { params: { research_workspace_id: researchWorkspaceId || undefined } }
    )
  },

  async listAIResearchRuns(
    researchWorkspaceId?: string | null,
    limit = 20
  ): Promise<AIStrategyResearchRunListResponse> {
    return api.get<AIStrategyResearchRunListResponse>('/strategy/ai-research/runs', {
      params: { research_workspace_id: researchWorkspaceId || undefined, limit },
    })
  },

  async getAIResearchRun(
    runId: string,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyResearchRunRecord> {
    return api.get<AIStrategyResearchRunRecord>(`/strategy/ai-research/runs/${runId}`, {
      params: { research_workspace_id: researchWorkspaceId || undefined },
    })
  },

  async getAIResearchTimeline(
    runId: string,
    researchWorkspaceId?: string | null
  ): Promise<ResearchTimelineResponse> {
    return api.get<ResearchTimelineResponse>(`/strategy/ai-research/runs/${runId}/timeline`, {
      params: { research_workspace_id: researchWorkspaceId || undefined },
    })
  },

  async listAIResearchVersions(
    runId: string,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyResearchVersionListResponse> {
    return api.get<AIStrategyResearchVersionListResponse>(
      `/strategy/ai-research/runs/${runId}/versions`,
      { params: { research_workspace_id: researchWorkspaceId || undefined } }
    )
  },

  async getAIResearchVersion(versionId: string): Promise<AIStrategyResearchVersion> {
    return api.get<AIStrategyResearchVersion>(`/strategy/ai-research/versions/${versionId}`)
  },

  async compareAIResearchVersions(
    leftId: string,
    rightId: string
  ): Promise<AIStrategyResearchVersionCompareResponse> {
    return api.get<AIStrategyResearchVersionCompareResponse>(
      `/strategy/ai-research/versions/${leftId}/compare/${rightId}`
    )
  },

  async startAIResearchPaperTrading(
    runId: string,
    data: AIStrategyPaperTradingStartRequest
  ): Promise<AIStrategyPaperTradingStart> {
    return api.post<AIStrategyPaperTradingStart, AIStrategyPaperTradingStartRequest>(
      `/strategy/ai-research/runs/${runId}/paper-trading`,
      data
    )
  },

  async reviewAIResearchPaperTrading(
    runId: string,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyPaperTradingReview> {
    return api.get<AIStrategyPaperTradingReview>(
      `/strategy/ai-research/runs/${runId}/paper-trading/review`,
      {
        params: { research_workspace_id: researchWorkspaceId || undefined },
      }
    )
  },

  async buildAIResearchLiveHandoff(
    runId: string,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyLiveHandoffPackage> {
    return api.get<AIStrategyLiveHandoffPackage>(
      `/strategy/ai-research/runs/${runId}/live-handoff`,
      {
        params: { research_workspace_id: researchWorkspaceId || undefined },
      }
    )
  },

  async approveAIResearchLiveHandoff(
    runId: string,
    data: AIStrategyLiveHandoffApprovalRequest,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyLiveHandoffPackage> {
    return api.post<AIStrategyLiveHandoffPackage, AIStrategyLiveHandoffApprovalRequest>(
      `/strategy/ai-research/runs/${runId}/live-handoff/approval`,
      data,
      {
        params: { research_workspace_id: researchWorkspaceId || undefined },
      }
    )
  },

  async prepareAIResearchLiveTrading(
    runId: string,
    data: AIStrategyLiveTradingPrepareRequest,
    researchWorkspaceId?: string | null
  ): Promise<AIStrategyLiveTradingPrepare> {
    return api.post<AIStrategyLiveTradingPrepare, AIStrategyLiveTradingPrepareRequest>(
      `/strategy/ai-research/runs/${runId}/live-trading/prepare`,
      data,
      {
        params: {
          research_workspace_id: researchWorkspaceId || data.research_workspace_id || undefined,
        },
      }
    )
  },

  async createScore(data: StrategyScoreRequest): Promise<StrategyScoreResponse> {
    return api.post<StrategyScoreResponse, StrategyScoreRequest>('/strategy/score', data)
  },

  async getScore(backtestId: string): Promise<StrategyScoreResponse> {
    return api.get<StrategyScoreResponse>(`/strategy/score/${backtestId}`)
  },

  async createOverfittingTask(
    backtestId: string,
    data: StrategyOverfittingAnalysisRequest
  ): Promise<StrategyOverfittingTaskSubmission> {
    return api.post<StrategyOverfittingTaskSubmission, StrategyOverfittingAnalysisRequest>(
      `/strategy/overfitting/${backtestId}`,
      data,
    )
  },

  async getOverfittingTask(taskId: string): Promise<StrategyOverfittingTaskResult> {
    return api.get<StrategyOverfittingTaskResult>(`/strategy/overfitting/task/${taskId}`)
  },

  async explainStrategy(data: StrategyExplainRequest): Promise<StrategyExplanation> {
    return api.post<StrategyExplanation, StrategyExplainRequest>('/strategy/explain', data)
  },

  async getCachedExplanation(codeHash: string): Promise<StrategyExplanation> {
    return api.get<StrategyExplanation>(`/strategy/explain/cached/${codeHash}`)
  },

  async get(id: string): Promise<Strategy> {
    return api.get<Strategy>(`/strategy/${id}`)
  },

  async update(id: string, data: Partial<StrategyCreate>): Promise<Strategy> {
    return api.put<Strategy, Partial<StrategyCreate>>(`/strategy/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    return api.delete<void>(`/strategy/${id}`)
  },

  async list(limit = 20, offset = 0, category?: string): Promise<StrategyListResponse> {
    return api.get<StrategyListResponse>('/strategy/', { params: { limit, offset, category } })
  },

  async getTemplates(strategyType?: StrategyType): Promise<{ templates: StrategyTemplate[]; total: number }> {
    return api.get<{ templates: StrategyTemplate[]; total: number }>('/strategy/templates', {
      params: { strategy_type: strategyType },
    })
  },

  async getTemplateDetail(id: string): Promise<StrategyTemplate> {
    return api.get<StrategyTemplate>(`/strategy/templates/${id}`)
  },

  async getTemplateReadme(id: string): Promise<{ template_id: string; content: string }> {
    return api.get<{ template_id: string; content: string }>(`/strategy/templates/${id}/readme`)
  },

  async getTemplateConfig(id: string): Promise<StrategyConfig> {
    return api.get<StrategyConfig>(`/strategy/templates/${id}/config`)
  },
}
