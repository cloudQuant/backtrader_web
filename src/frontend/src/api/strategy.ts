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
  AIStrategyResearchObjectiveOptimizeRequest,
  AIStrategyResearchObjectiveOptimizeResponse,
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
import type {
  AiResearchApprovalContext,
  AiResearchApprovalDecisionCreate,
  AiResearchApprovalDecisionReceipt,
  AiResearchApprovalRequestCreate,
  AiResearchApprovalRequestReceipt,
  AiResearchV2Candidate,
  AiResearchV2CandidateFreezeRequest,
  AiResearchV2DataPrecheck,
  AiResearchV2DataPrecheckRequest,
  AiResearchV2Dataset,
  AiResearchV2DatasetCreateRequest,
  AiResearchV2Epoch,
  AiResearchV2EpochCreateRequest,
  AiResearchV2Hypothesis,
  AiResearchV2HoldoutCommand,
  AiResearchV2RunSubmission,
  AiResearchV2RunSubmitRequest,
  AiResearchV2Task,
  AiResearchV2TaskEventPage,
  AiResearchV2TaskPage,
  AiResearchV2Workbench,
} from '@/types/aiResearchV2'
import {
  projectAiResearchApprovalContext,
  projectAiResearchApprovalDecision,
  projectAiResearchApprovalRequest,
} from '@/types/aiResearchV2'

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
  AIStrategyResearchObjectiveOptimizeRequest,
  AIStrategyResearchObjectiveOptimizeResponse,
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

  async createTrustedAIResearchHypothesis(
    payload: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Hypothesis> {
    return api.post<AiResearchV2Hypothesis, { payload: Record<string, unknown> }>(
      '/strategy/ai-research/v2/hypotheses',
      { payload },
      { signal },
    )
  },

  async confirmTrustedAIResearchHypothesis(
    hypothesisId: string,
    requestHash: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Hypothesis> {
    return api.post<AiResearchV2Hypothesis, { request_hash: string }>(
      `/strategy/ai-research/v2/hypotheses/${hypothesisId}/confirm`,
      { request_hash: requestHash },
      { signal },
    )
  },

  async createTrustedAIResearchDataset(
    data: AiResearchV2DatasetCreateRequest,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Dataset> {
    return api.post<AiResearchV2Dataset, AiResearchV2DatasetCreateRequest>(
      '/strategy/ai-research/v2/datasets',
      data,
      { signal },
    )
  },

  async createTrustedAIResearchEpoch(
    data: AiResearchV2EpochCreateRequest,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Epoch> {
    return api.post<AiResearchV2Epoch, AiResearchV2EpochCreateRequest>(
      '/strategy/ai-research/v2/epochs',
      data,
      { signal },
    )
  },

  async createTrustedAIResearchDataPrecheck(
    data: AiResearchV2DataPrecheckRequest,
    signal?: AbortSignal,
  ): Promise<AiResearchV2DataPrecheck> {
    return api.post<AiResearchV2DataPrecheck, AiResearchV2DataPrecheckRequest>(
      '/strategy/ai-research/v2/data-prechecks',
      data,
      { signal },
    )
  },

  async submitTrustedAIResearchRun(
    data: AiResearchV2RunSubmitRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2RunSubmission> {
    return api.post<AiResearchV2RunSubmission, AiResearchV2RunSubmitRequest>(
      '/strategy/ai-research/v2/runs',
      data,
      { headers: { 'Idempotency-Key': idempotencyKey }, signal },
    )
  },

  async getTrustedAIResearchWorkbench(
    runId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Workbench> {
    return api.get<AiResearchV2Workbench>(`/strategy/ai-research/v2/runs/${runId}`, { signal })
  },

  async freezeTrustedAIResearchCandidate(
    candidateId: string,
    data: AiResearchV2CandidateFreezeRequest,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Candidate> {
    return api.post<AiResearchV2Candidate, AiResearchV2CandidateFreezeRequest>(
      `/strategy/ai-research/v2/candidates/${candidateId}/freeze`,
      data,
      { signal },
    )
  },

  async requestTrustedAIResearchHoldout(
    candidateId: string,
    expectedHash: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2HoldoutCommand> {
    return api.post<AiResearchV2HoldoutCommand, { expected_candidate_hash: string }>(
      `/strategy/ai-research/v2/candidates/${candidateId}/holdout-evaluation`,
      { expected_candidate_hash: expectedHash },
      { headers: { 'Idempotency-Key': idempotencyKey }, signal },
    )
  },

  async getTrustedAIResearchHoldout(
    commandId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2HoldoutCommand> {
    return api.get<AiResearchV2HoldoutCommand>(
      `/strategy/ai-research/v2/holdout-evaluations/${commandId}`,
      { signal },
    )
  },

  async getTrustedAIResearchApprovalContext(
    runId: string,
    candidateId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchApprovalContext> {
    const response = await api.get<unknown>(
      `/strategy/ai-research/v2/runs/${runId}/candidates/${candidateId}/approval-context`,
      { signal, suppressErrorToast: true },
    )
    const context = projectAiResearchApprovalContext(response)
    if (context === null) throw new Error('RESEARCH_APPROVAL_CONTEXT_INVALID')
    return context
  },

  async requestTrustedAIResearchApproval(
    runId: string,
    candidateId: string,
    data: AiResearchApprovalRequestCreate,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchApprovalRequestReceipt> {
    const request: AiResearchApprovalRequestCreate = {
      gate_input_evidence_hash: data.gate_input_evidence_hash,
      evidence_package_hash: data.evidence_package_hash,
    }
    const response = await api.post<unknown, AiResearchApprovalRequestCreate>(
      `/strategy/ai-research/v2/runs/${runId}/candidates/${candidateId}/approval-requests`,
      request,
      { headers: { 'Idempotency-Key': idempotencyKey }, signal, suppressErrorToast: true },
    )
    const receipt = projectAiResearchApprovalRequest(response)
    if (receipt === null) throw new Error('RESEARCH_APPROVAL_REQUEST_INVALID')
    return receipt
  },

  async decideTrustedAIResearchApproval(
    runId: string,
    candidateId: string,
    data: AiResearchApprovalDecisionCreate,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchApprovalDecisionReceipt> {
    const request: AiResearchApprovalDecisionCreate = {
      approval_request_id: data.approval_request_id,
      decision: data.decision,
      reason: data.reason,
      gate_input_evidence_hash: data.gate_input_evidence_hash,
      evidence_package_hash: data.evidence_package_hash,
      challenge_responses: { ...data.challenge_responses },
      residual_risk_acknowledgement: data.residual_risk_acknowledgement,
    }
    const response = await api.post<unknown, AiResearchApprovalDecisionCreate>(
      `/strategy/ai-research/v2/runs/${runId}/candidates/${candidateId}/approval-decisions`,
      request,
      { headers: { 'Idempotency-Key': idempotencyKey }, signal, suppressErrorToast: true },
    )
    const receipt = projectAiResearchApprovalDecision(response)
    if (receipt === null) throw new Error('RESEARCH_APPROVAL_DECISION_INVALID')
    return receipt
  },

  async listTrustedAIResearchTasks(
    cursor?: string | null,
    limit = 50,
    signal?: AbortSignal,
  ): Promise<AiResearchV2TaskPage> {
    return api.get<AiResearchV2TaskPage>('/strategy/ai-research/v2/tasks', {
      params: { cursor: cursor ?? undefined, limit },
      signal,
    })
  },

  async getTrustedAIResearchTask(
    taskId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Task> {
    return api.get<AiResearchV2Task>(`/strategy/ai-research/v2/tasks/${taskId}`, { signal })
  },

  async listTrustedAIResearchTaskEvents(
    taskId: string,
    cursor?: string | null,
    limit = 50,
    signal?: AbortSignal,
  ): Promise<AiResearchV2TaskEventPage> {
    return api.get<AiResearchV2TaskEventPage>(`/strategy/ai-research/v2/tasks/${taskId}/events`, {
      params: { cursor: cursor ?? undefined, limit },
      signal,
    })
  },

  async cancelTrustedAIResearchTask(
    taskId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Task> {
    return api.post<AiResearchV2Task, undefined>(
      `/strategy/ai-research/v2/tasks/${taskId}/cancel`,
      undefined,
      { signal },
    )
  },

  async optimizeAIResearchObjective(
    data: AIStrategyResearchObjectiveOptimizeRequest
  ): Promise<AIStrategyResearchObjectiveOptimizeResponse> {
    return api.post<
      AIStrategyResearchObjectiveOptimizeResponse,
      AIStrategyResearchObjectiveOptimizeRequest
    >('/strategy/ai-research/objectives/optimize', data)
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
