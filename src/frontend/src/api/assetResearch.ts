import api from './index'

export type AssetResearchAssetType = 'bond' | 'fund' | 'futures' | 'option' | 'fx' | 'crypto'
export type AssetResearchTaskStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'
export type AssetResearchRecommendation = 'BUY' | 'SELL' | 'HOLD' | 'AVOID'
export type AssetResearchActionability = 'ACTIONABLE' | 'RESEARCH_ONLY' | 'INSUFFICIENT_DATA' | 'REGION_RESTRICTED'

export interface AssetResearchCapability {
  asset_type: AssetResearchAssetType
  source_capability_enabled?: boolean
  instrument_catalog_ready?: boolean
  research_enabled: boolean
  availability_reason?: string | null
  short_open_research_allowed: boolean
  reason_codes: string[]
}

export interface AssetResearchCapabilities {
  capability_version: string
  execution_disabled: true
  asset_types: AssetResearchCapability[]
}

export interface InstrumentIdentity {
  asset_type: AssetResearchAssetType
  identity_level: 'ASSET' | 'PRODUCT' | 'CONTRACT' | 'SERIES'
  canonical_id: string
  display_symbol: string
  name: string
  venue?: string | null
  currency?: string | null
  timezone: string
  identifier_type: string
  identifier_value: string
  product_type?: string | null
  metadata_version: string
  details: Record<string, unknown>
}

export interface InstrumentSearchCandidate {
  asset_type: AssetResearchAssetType
  identity_level?: InstrumentIdentity['identity_level']
  symbol: string
  name: string
  market?: string
  canonical_id?: string
  metadata_version?: string
  asset_research_identity?: InstrumentIdentity
}

export interface InstrumentSearchResponse {
  asset_type: AssetResearchAssetType
  items: InstrumentSearchCandidate[]
}

export interface AssetResearchDecision {
  asset_type: AssetResearchAssetType
  market_view: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'INDETERMINATE'
  normalized_direction: 'LONG' | 'SHORT' | 'NEUTRAL' | 'INDETERMINATE'
  position_context: 'FLAT' | 'LONG' | 'SHORT' | 'UNKNOWN'
  horizon_code: string
  quality_status: 'ELIGIBLE' | 'DEGRADED' | 'REJECTED'
  recommendation: AssetResearchRecommendation
  actionability: AssetResearchActionability
  trade_intent: 'OPEN' | 'ADD' | 'REDUCE' | 'CLOSE' | 'KEEP' | 'NONE'
  confidence?: number | null
  reason_codes: string[]
  invalidation_conditions?: string[]
  asset_details?: Record<string, unknown> | null
  execution_disabled: true
}

export interface AssetResearchTask {
  task_id: string
  status: AssetResearchTaskStatus
  asset_type: AssetResearchAssetType
  canonical_id: string
  progress: number
  message?: string | null
  error_code?: string | null
  report_id?: string | null
  prediction_id?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface AssetResearchResult {
  task_id: string
  status: AssetResearchTaskStatus
  report_id?: string | null
  prediction_id?: string | null
  published_decision?: AssetResearchDecision | null
  report?: {
    meta?: Record<string, unknown>
    sections?: Array<{
      section_id: string
      title: string
      markdown: string
      evidence_ids?: string[]
    }>
    disclaimer?: string
  } | null
}

export interface AssetResearchReport {
  report_id: string
  task_id: string
  prediction_id?: string | null
  report: {
    meta?: Record<string, unknown>
    sections?: Array<{
      section_id: string
      title: string
      markdown: string
      evidence_ids?: string[]
    }>
    disclaimer?: string
    [key: string]: unknown
  }
  rendered_markdown: string
  content_hash: string
  created_at: string
}

export type AssetResearchExportFormat = 'MARKDOWN' | 'PDF'

export interface AssetResearchReportExport {
  export_id: string
  report_id: string
  format: AssetResearchExportFormat
  status: 'QUEUED' | 'SUCCEEDED' | 'FAILED'
  content_hash?: string | null
  error_code?: string | null
  download_url?: string | null
  created_at: string
  completed_at?: string | null
}

export type AssetResearchPublicationTargetType = 'KNOWLEDGE_BASE' | 'WORKSPACE'

export interface AssetResearchCreateReportPublication {
  target_type: AssetResearchPublicationTargetType
  target_ref: string
  title?: string
}

export interface AssetResearchReportPublication {
  publication_id: string
  report_id: string
  target_type: AssetResearchPublicationTargetType
  target_ref: string
  status: 'QUEUED' | 'SUCCEEDED' | 'FAILED'
  external_ref?: string | null
  content_hash?: string | null
  error_code?: string | null
  created_at: string
  completed_at?: string | null
}

export interface AssetResearchSignalHistoryItem {
  prediction_id: string
  owner_scope: 'USER' | 'PUBLIC_SHADOW'
  asset_type: AssetResearchAssetType
  canonical_id: string
  as_of_at: string
  horizon_code: string
  actionability: AssetResearchActionability
  quality_status: 'ELIGIBLE' | 'DEGRADED' | 'REJECTED'
  published_decision: AssetResearchDecision
}

export interface AssetResearchSignalHistory {
  items: AssetResearchSignalHistoryItem[]
  next_cursor?: string | null
}

export interface AssetResearchSignalEvidence {
  prediction_id: string
  canonical_id: string
  asset_type: AssetResearchAssetType
  source: Record<string, unknown>
  source_snapshot_hash?: string | null
  license_tags: string[]
  versions: Record<string, string | null | undefined>
  reason_codes: string[]
}

export interface AssetResearchSignalSummary {
  asset_type: AssetResearchAssetType
  canonical_id: string
  head_spec_hash?: string | null
  available_head_spec_hashes: string[]
  cohort_selection_required: boolean
  total_generated_count: number
  excluded_prediction_count: number
  generated_count: number
  scorable_count: number
  actioned_generated_count: number
  actioned_scorable_count: number
  actioned_success_count: number
  actioned_success_rate?: number | null
  coverage_rate?: number | null
  maturity_rate?: number | null
  brier_score?: number | null
  brier_skill_score?: number | null
  average_net_return?: number | null
  max_drawdown?: number | null
  calibration_bins: Array<{
    lower_bound: number
    upper_bound: number
    sample_count: number
    mean_confidence: number
    observed_frequency: number
  }>
  action_breakdown: Array<Record<string, unknown>>
}

export interface AssetResearchCreateTask {
  asset_type: AssetResearchAssetType
  canonical_id: string
  horizon_code?: string
  position_context?: 'FLAT' | 'LONG' | 'SHORT' | 'UNKNOWN'
  position_context_snapshot_id?: string | null
  request_options?: Record<string, unknown>
}

function idempotencyConfig(idempotencyKey?: string) {
  return idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : undefined
}

export const assetResearchApi = {
  getCapabilities() {
    return api.get<AssetResearchCapabilities>('/asset-research/capabilities')
  },
  searchInstruments(
    assetType: AssetResearchAssetType,
    query: string,
    limit = 20,
    identityLevel?: InstrumentIdentity['identity_level'],
  ) {
    return api.get<InstrumentSearchResponse>('/asset-research/instruments/search', {
      params: {
        asset_type: assetType,
        query,
        limit,
        ...(identityLevel ? { identity_level: identityLevel } : {}),
      },
    })
  },
  resolveInstrument(data: {
    asset_type: AssetResearchAssetType
    query: string
    venue?: string
    canonical_id?: string
    identity_level?: InstrumentIdentity['identity_level']
  }) {
    return api.post<InstrumentIdentity>('/asset-research/instruments/resolve', data)
  },
  createTask(data: AssetResearchCreateTask, idempotencyKey?: string) {
    return api.post<AssetResearchTask>('/asset-research/tasks', data, idempotencyConfig(idempotencyKey))
  },
  getTask(taskId: string) {
    return api.get<AssetResearchTask>(`/asset-research/tasks/${taskId}`)
  },
  getTaskResult(taskId: string) {
    return api.get<AssetResearchResult>(`/asset-research/tasks/${taskId}/result`)
  },
  cancelTask(taskId: string) {
    return api.post<AssetResearchTask>(`/asset-research/tasks/${taskId}/cancel`)
  },
  retryTask(taskId: string) {
    return api.post<AssetResearchTask>(`/asset-research/tasks/${taskId}/retry`)
  },
  getSignalHistory(assetType: AssetResearchAssetType, canonicalId: string, limit = 30) {
    return api.get<AssetResearchSignalHistory>('/asset-research/signals', {
      params: { asset_type: assetType, canonical_id: canonicalId, limit },
    })
  },
  getSignalEvidence(predictionId: string) {
    return api.get<AssetResearchSignalEvidence>(`/asset-research/signals/${predictionId}/evidence`)
  },
  getSignalSummary(
    assetType: AssetResearchAssetType,
    canonicalId: string,
    headSpecHash?: string,
  ) {
    return api.get<AssetResearchSignalSummary>('/asset-research/signals/summary', {
      params: {
        asset_type: assetType,
        canonical_id: canonicalId,
        ...(headSpecHash ? { head_spec_hash: headSpecHash } : {}),
      },
    })
  },
  getLatestReport(assetType: AssetResearchAssetType, canonicalId: string) {
    return api.get<AssetResearchReport | null>('/asset-research/reports/latest', {
      params: { asset_type: assetType, canonical_id: canonicalId },
    })
  },
  getReport(reportId: string) {
    return api.get<AssetResearchReport>(`/asset-research/reports/${reportId}`)
  },
  createReportExport(
    reportId: string,
    format: AssetResearchExportFormat,
    idempotencyKey?: string,
  ) {
    return api.post<AssetResearchReportExport>(
      `/asset-research/reports/${reportId}/exports`,
      { format },
      idempotencyConfig(idempotencyKey),
    )
  },
  createReportPublication(
    reportId: string,
    data: AssetResearchCreateReportPublication,
    idempotencyKey?: string,
  ) {
    return api.post<AssetResearchReportPublication>(
      `/asset-research/reports/${reportId}/publications`,
      data,
      idempotencyConfig(idempotencyKey),
    )
  },
  getReportPublication(publicationId: string) {
    return api.get<AssetResearchReportPublication>(`/asset-research/publications/${publicationId}`)
  },
  downloadReportExport(downloadUrl: string) {
    const relativeUrl = downloadUrl.replace(/^\/api\/v1(?=\/)/, '')
    return api.get<Blob>(relativeUrl, { responseType: 'blob' })
  },
}
