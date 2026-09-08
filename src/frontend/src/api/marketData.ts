import request from './index'
import type {
  AssetSpecResponse,
  DataPrecheckRequest,
  DataPrecheckResponse,
  ExecutionModelResponse,
  MarketDataCoverageMatrixResponse,
} from '@/types/trust'

export type MarketAssetType = 'stock' | 'futures' | 'bond' | 'fund' | 'option' | 'fx' | 'crypto'
export type MarketDataQueryFrequency = '5min' | '30min' | '1h' | '1d' | '1w' | '1mo'
export type MarketDataQueryMode = 'local_first' | 'local_only' | 'refresh'
export type MarketDataQueryConsistency = 'display' | 'strict'
export type MarketDataQueryPurpose = 'display' | 'research' | 'backtest' | 'export'
export const MARKET_DATA_FAMILY_CONTRACT_VERSION = 'market-data-family-v1' as const
export type MarketDataFamilyContractVersion = typeof MARKET_DATA_FAMILY_CONTRACT_VERSION

/**
 * Server-proven v2 request facts attached to a legacy lookup when, and only
 * when, the API can resolve an exact canonical instrument and active dataset.
 *
 * The frontend deliberately does not derive a canonical ID or dataset code
 * from a symbol.  This keeps the progressive rollout safe while the catalog
 * and master-data bootstrap are incomplete.
 */
/** A query is either unbound or carries both immutable family binding axes. */
export type MarketDataFamilyBinding = (
  | {
    family_id: string
    family_contract_version: MarketDataFamilyContractVersion
  }
  | {
    family_id?: undefined
    family_contract_version?: undefined
  }
)

export interface MarketDataQueryContractRequestBase {
  identity: {
    canonical_id: string
  }
  dataset_code: string
  data_kind: 'bars' | 'quote_snapshot' | 'option_chain' | 'position_report' | 'reference_series'
  frequency: MarketDataQueryFrequency
  required_fields: string[]
  adjustment?: string | null
  price_basis?: string | null
  currency?: string | null
  unit?: string | null
  source_policy_id: string
  mode: 'local_first'
}

export type MarketDataQueryContractRequest = MarketDataQueryContractRequestBase & MarketDataFamilyBinding

export interface MarketDataQueryContract {
  version: 'market-data-v2'
  request: MarketDataQueryContractRequest
}

export type MarketDataQueryBundleFamilyStatus = 'ready' | 'unconfigured' | 'not_applicable'
export type MarketDataQueryBundleFrequency = MarketDataQueryFrequency | 'snapshot'
export type MarketDataQueryBundleFrequencySemantics = 'calendar_grid' | 'snapshot' | 'reporting_period'
export type MarketDataQueryBundleCoverageModel = (
  | 'calendar_grid'
  | 'snapshot_freshness'
  | 'slice_completeness'
  | 'report_completeness'
)
export type MarketDataQueryBundleDataKind = (
  | 'bars'
  | 'quote_snapshot'
  | 'option_chain'
  | 'position_report'
  | 'reference_series'
  | 'inventory_report'
  | 'option_risk_surface'
)

/**
 * A read-only, server-owned declaration of one market-page data family.
 *
 * This is deliberately not executable query input. The data platform still
 * issues a symbol-specific v2 query contract before a client can read bars.
 * Keeping the static bundle separate means an unconfigured family cannot be
 * reconstructed from a legacy page payload.
 */
export interface MarketDataQueryBundleFamily {
  family_id: string
  family_contract_version: MarketDataFamilyContractVersion
  asset_type: MarketAssetType
  status: MarketDataQueryBundleFamilyStatus
  dataset_code: string
  data_kind: MarketDataQueryBundleDataKind
  frequency_semantics: MarketDataQueryBundleFrequencySemantics
  frequencies: MarketDataQueryBundleFrequency[]
  field_profile_id: string
  required_fields: string[]
  optional_fields: string[]
  dimension_fields: string[]
  coverage_model: MarketDataQueryBundleCoverageModel
  source_policy_id: string | null
  reason_code: string | null
}

/**
 * Static control-plane response for all data families displayed by one asset
 * tab.  It has no symbol, date range, provider call, or database side effect.
 */
export interface MarketDataQueryBundle {
  version: 'market-data-family-bundle-v1'
  requested_asset_type: MarketAssetType
  families: MarketDataQueryBundleFamily[]
}

export type MarketDataQueryRequest = Omit<MarketDataQueryContractRequestBase, 'mode'> & MarketDataFamilyBinding & {
  start: string
  end: string
  mode: MarketDataQueryMode
  consistency?: MarketDataQueryConsistency
  purpose?: MarketDataQueryPurpose
  knowledge_cutoff?: string
  page_size?: number
  cursor?: string
}

export interface MarketDataQueryOptions {
  signal?: AbortSignal
  suppressErrorMessage?: boolean
}

export interface MarketDataQueryObservation {
  revision_id: string
  source_snapshot_id: string
  event_at: string
  available_at: string
  committed_at: string
  revision_number: number
  quality: string
  fields: Record<string, unknown>
}

export interface MarketDataQueryCoverageGap {
  position: string
  event_at: string[]
  fetch_start: string
  fetch_end: string
}

export interface MarketDataQueryCoverage {
  status: string
  expected_event_count: number
  accepted_event_count: number
  missing_event_count: number
  coverage_ratio: number | null
  gaps: MarketDataQueryCoverageGap[]
  rejection_counts: Record<string, number>
  calendar_reason: string | null
}

export interface MarketDataQueryFetch {
  route_id: string
  provider_id: string
  source_snapshot_id: string
  observation_revision_ids: string[]
  passing_observation_count: number
  failed_observation_count: number
}

export interface MarketDataQueryWarning {
  code: string
  route_id?: string | null
  provider_id?: string | null
}

export interface MarketDataQueryResponse {
  query_id: string
  canonical_id: string
  dataset_code: string
  asset_type: MarketAssetType
  instrument_metadata_version: string
  data_kind: string
  frequency: string
  source_policy_id: string
  /** Echoes the request binding when a family-controlled query was issued. */
  family_id?: string
  family_contract_version?: MarketDataFamilyContractVersion
  knowledge_cutoff: string
  identity_knowledge_cutoff: string
  observations: MarketDataQueryObservation[]
  next_cursor: string | null
  coverage: MarketDataQueryCoverage
  fetches: MarketDataQueryFetch[]
  warnings: MarketDataQueryWarning[]
  refresh_status: 'fresh_complete' | 'fresh_incomplete' | 'fresh_unknown_calendar' | null
}

export interface MarketInstrumentLookupParams {
  asset_type: MarketAssetType
  symbol: string
  start_date?: string
  end_date?: string
  period?: string
  market?: string
  refresh_online?: boolean
}

export interface MarketInstrumentOption {
  asset_type: MarketAssetType
  symbol: string
  name: string
  market?: string | null
  source_table?: string | null
  latest_date?: string | null
  has_snapshot: boolean
  has_history: boolean
  history_rows: number
}

export interface MarketInstrumentOptionsParams {
  asset_type: MarketAssetType
  search?: string
  limit?: number
}

export interface MarketDataQueryContractParams {
  asset_type: MarketAssetType
  symbol: string
  period: 'daily' | 'weekly' | 'monthly'
  family_id?: string
}

export interface MarketDataQueryBundleParams {
  asset_type: MarketAssetType
  family_id?: string
}

export interface MarketInstrumentOptionsResponse {
  asset_type: MarketAssetType
  items: MarketInstrumentOption[]
  total: number
}

export interface MarketSnapshot {
  symbol?: string
  name?: string
  price?: number | null
  change?: number | null
  change_pct?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  previous_close?: number | null
  settle?: number | null
  previous_settle?: number | null
  bid?: number | null
  ask?: number | null
  volume?: number | null
  turnover?: number | null
  turnover_rate?: number | null
  open_interest?: number | null
  strike?: number | null
  days_to_expiry?: number | null
  market_cap?: number | null
  float_market_cap?: number | null
  pe?: number | null
  pb?: number | null
  update_time?: string | null
  data_source_table?: string | null
  history_currency?: string | null
  [key: string]: unknown
}

export interface MarketHistoryRow {
  date: string
  name?: string | null
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  price?: number | null
  volume?: number | null
  turnover?: number | null
  change?: number | null
  change_pct?: number | null
  turnover_rate?: number | null
  open_interest?: number | null
  settle?: number | null
  strike?: number | null
  days_to_expiry?: number | null
  [key: string]: unknown
}

export interface MarketInstrumentIndicators {
  latest_close?: number | null
  return_pct?: number | null
  highest_close?: number | null
  lowest_close?: number | null
  avg_volume?: number | null
  observation_count?: number
}

export interface MarketInstrumentLookupResponse {
  asset_type: MarketAssetType
  symbol: string
  name: string
  market?: string | null
  provider?: string | null
  /**
   * Present only after the backend has proven an exact v2 identity and
   * dataset binding. Its absence is a normal rollout state and callers must
   * continue through the legacy local lookup path.
   */
  query_contract?: MarketDataQueryContract | null
  snapshot: MarketSnapshot
  history: {
    period: string
    rows: MarketHistoryRow[]
    total: number
  }
  indicators: MarketInstrumentIndicators
  warnings: string[]
}

export interface MarketDataCoverageQuery {
  asset_type?: MarketAssetType | string | null
  symbol?: string | null
  timeframe?: string | null
  provider?: string | null
  refresh_if_empty?: boolean
  limit?: number
}

export interface MarketDataCoverageRefreshQuery {
  asset_type?: MarketAssetType | string | null
  symbol?: string | null
  timeframe?: string | null
  limit?: number
}

function nonEmptyText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

const MARKET_ASSET_TYPES: readonly MarketAssetType[] = [
  'stock',
  'futures',
  'bond',
  'fund',
  'option',
  'fx',
  'crypto',
]

function isMarketAssetType(value: unknown): value is MarketAssetType {
  return typeof value === 'string' && MARKET_ASSET_TYPES.includes(value as MarketAssetType)
}

const MARKET_DATA_QUERY_BUNDLE_DATA_KINDS: readonly MarketDataQueryBundleDataKind[] = [
  'bars',
  'quote_snapshot',
  'option_chain',
  'position_report',
  'reference_series',
  'inventory_report',
  'option_risk_surface',
]
const MARKET_DATA_QUERY_BUNDLE_FREQUENCIES: readonly MarketDataQueryBundleFrequency[] = [
  '5min',
  '30min',
  '1h',
  '1d',
  '1w',
  '1mo',
  'snapshot',
]
const MARKET_DATA_QUERY_BUNDLE_FREQUENCY_SEMANTICS: readonly MarketDataQueryBundleFrequencySemantics[] = [
  'calendar_grid',
  'snapshot',
  'reporting_period',
]
const MARKET_DATA_QUERY_BUNDLE_COVERAGE_MODELS: readonly MarketDataQueryBundleCoverageModel[] = [
  'calendar_grid',
  'snapshot_freshness',
  'slice_completeness',
  'report_completeness',
]

function hasDistinctTextArray(value: unknown, minLength = 0): value is string[] {
  return Array.isArray(value)
    && value.length >= minLength
    && value.every(nonEmptyText)
    && new Set(value).size === value.length
}

function hasPairedMarketDataFamilyBinding(value: Record<string, unknown>): boolean {
  const hasFamilyId = value.family_id !== undefined
  const hasFamilyVersion = value.family_contract_version !== undefined
  if (hasFamilyId !== hasFamilyVersion) return false
  if (!hasFamilyId) return true
  return nonEmptyText(value.family_id)
    && value.family_contract_version === MARKET_DATA_FAMILY_CONTRACT_VERSION
}

/**
 * Return whether a static family-control bundle is safe to use as an
 * authoritative page capability declaration.
 *
 * A malformed 2xx payload must not activate the compatibility route: callers
 * treat it as a v2 failure.  Ready entries require their descriptive
 * read-only contract, while unavailable entries may only expose a stable
 * reason code.
 */
export function hasMarketDataQueryBundle(value: unknown): value is MarketDataQueryBundle {
  if (!value || typeof value !== 'object') return false
  const bundle = value as Record<string, unknown>
  if (
    bundle.version !== 'market-data-family-bundle-v1'
    || !isMarketAssetType(bundle.requested_asset_type)
    || !Array.isArray(bundle.families)
  ) {
    return false
  }

  const requestedAssetType = bundle.requested_asset_type
  const familyIds = new Set<string>()
  return bundle.families.length > 0 && bundle.families.every((entry) => {
    if (!entry || typeof entry !== 'object') return false
    const family = entry as Record<string, unknown>
    if (!nonEmptyText(family.family_id) || familyIds.has(family.family_id)) return false
    familyIds.add(family.family_id)
    if (family.family_contract_version !== MARKET_DATA_FAMILY_CONTRACT_VERSION) return false
    if (!isMarketAssetType(family.asset_type) || !family.family_id.startsWith(`${family.asset_type}.`)) {
      return false
    }
    if (
      family.status !== 'ready'
      && family.status !== 'unconfigured'
      && family.status !== 'not_applicable'
    ) {
      return false
    }
    // The optional server-side family filter can explicitly return a family
    // from another asset as not_applicable. The page requests the full bundle
    // and performs the stricter same-asset check before consuming it.
    if (family.asset_type !== requestedAssetType && family.status !== 'not_applicable') return false
    if (
      !nonEmptyText(family.dataset_code)
      || !MARKET_DATA_QUERY_BUNDLE_DATA_KINDS.includes(family.data_kind as MarketDataQueryBundleDataKind)
      || !MARKET_DATA_QUERY_BUNDLE_FREQUENCY_SEMANTICS.includes(
        family.frequency_semantics as MarketDataQueryBundleFrequencySemantics,
      )
      || !hasDistinctTextArray(family.frequencies, 1)
      || !family.frequencies.every((frequency) => (
        MARKET_DATA_QUERY_BUNDLE_FREQUENCIES.includes(frequency as MarketDataQueryBundleFrequency)
      ))
      || !nonEmptyText(family.field_profile_id)
      || !hasDistinctTextArray(family.required_fields, 1)
      || !hasDistinctTextArray(family.optional_fields)
      || !hasDistinctTextArray(family.dimension_fields)
      || !MARKET_DATA_QUERY_BUNDLE_COVERAGE_MODELS.includes(
        family.coverage_model as MarketDataQueryBundleCoverageModel,
      )
    ) {
      return false
    }
    const fieldNames = [
      ...family.required_fields,
      ...family.optional_fields,
      ...family.dimension_fields,
    ]
    if (new Set(fieldNames).size !== fieldNames.length) return false
    if (family.status === 'ready') {
      return nonEmptyText(family.source_policy_id) && family.reason_code === null
    }
    return family.source_policy_id === null && nonEmptyText(family.reason_code)
  })
}

/** Return whether a server payload is a complete, safe v2 query contract. */
export function hasMarketDataQueryContract(value: unknown): value is MarketDataQueryContract {
  if (!value || typeof value !== 'object') return false
  const contract = value as Record<string, unknown>
  if (contract.version !== 'market-data-v2' || !contract.request || typeof contract.request !== 'object') {
    return false
  }
  const request = contract.request as Record<string, unknown>
  const identity = request.identity
  const canonicalId = identity && typeof identity === 'object'
    ? (identity as Record<string, unknown>).canonical_id
    : undefined
  return Boolean(
    nonEmptyText(canonicalId)
      && nonEmptyText(request.dataset_code)
      && nonEmptyText(request.data_kind)
      && nonEmptyText(request.frequency)
      && Array.isArray(request.required_fields)
      && request.required_fields.length > 0
      && request.required_fields.every(nonEmptyText)
      && nonEmptyText(request.source_policy_id)
      && hasPairedMarketDataFamilyBinding(request)
      && request.mode === 'local_first',
  )
}

/**
 * Materialize one v2 request from a server-issued contract.
 *
 * The caller can only supply transport/window settings and the explicitly
 * supported rollout mode. Identity, dataset, fields, and semantic axes are
 * copied from the server contract rather than inferred from UI text.
 */
export function createMarketDataQueryFromContract(
  contract: MarketDataQueryContract,
  options: {
    start: string
    end: string
    mode?: MarketDataQueryMode
    consistency?: MarketDataQueryConsistency
    purpose?: MarketDataQueryPurpose
    knowledge_cutoff?: string
    page_size?: number
  },
): MarketDataQueryRequest {
  if (!hasMarketDataQueryContract(contract)) {
    throw new Error('MARKET_DATA_QUERY_CONTRACT_INVALID')
  }
  const request = contract.request
  const requestBase = {
    identity: { canonical_id: request.identity.canonical_id },
    dataset_code: request.dataset_code,
    data_kind: request.data_kind,
    frequency: request.frequency,
    required_fields: [...request.required_fields],
    adjustment: request.adjustment ?? undefined,
    price_basis: request.price_basis ?? undefined,
    currency: request.currency ?? undefined,
    unit: request.unit ?? undefined,
    source_policy_id: request.source_policy_id,
    mode: options.mode || request.mode,
    start: options.start,
    end: options.end,
    consistency: options.consistency,
    purpose: options.purpose,
    knowledge_cutoff: options.knowledge_cutoff,
    page_size: options.page_size,
  }
  if (request.family_id && request.family_contract_version) {
    return {
      ...requestBase,
      family_id: request.family_id,
      family_contract_version: request.family_contract_version,
    }
  }
  return requestBase
}

function marketDataQueryErrorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return undefined
  const response = (error as { response?: { data?: unknown } }).response
  const data = response?.data
  if (!data || typeof data !== 'object') return undefined
  const record = data as Record<string, unknown>
  const detail = record.detail as Record<string, unknown> | undefined
  const details = record.details as Record<string, unknown> | undefined
  for (const candidate of [record.code, detail?.code, details?.code]) {
    if (typeof candidate === 'string' && candidate.trim()) return candidate
  }
  return undefined
}

/**
 * Identify only an unavailable v2 control-plane endpoint during progressive
 * rollout. Callers may use this before they have a valid family bundle or
 * symbol-specific contract. Once either one has been issued, a v2 execution
 * failure is authoritative and must remain visible: falling through to the
 * legacy endpoint could bypass the receipt-backed persistence protocol.
 */
export function isMarketDataQueryV2FallbackError(error: unknown): boolean {
  const response = error && typeof error === 'object'
    ? (error as { response?: { status?: unknown } }).response
    : undefined
  const status = typeof response?.status === 'number' ? response.status : undefined
  const code = marketDataQueryErrorCode(error)
  if (code) {
    return code === 'MARKET_DATA_QUERY_V2_DISABLED'
      || code === 'MARKET_DATA_QUERY_CONTRACT_UNAVAILABLE'
      || code === 'MARKET_DATA_QUERY_BUNDLE_UNAVAILABLE'
  }
  // Generic route absence is a deployment state.  Do not treat a generic
  // 5xx, transport failure, or a typed business rejection as compatibility.
  return status === 404 || status === 405 || status === 501
}

export const marketDataApi = {
  listInstrumentOptions(params: MarketInstrumentOptionsParams) {
    return request.get<MarketInstrumentOptionsResponse>('/data/market-instruments/options', {
      params,
    })
  },
  lookupInstrument(params: MarketInstrumentLookupParams) {
    return request.get<MarketInstrumentLookupResponse>('/data/market-instruments/lookup', {
      params,
    })
  },
  getQueryContract(params: MarketDataQueryContractParams) {
    // The caller classifies an expected unavailable contract from the rejected
    // response.  All other non-2xx responses remain failures, so a transient
    // server problem cannot silently activate the legacy online path.
    return request.get<unknown>('/data/market-instruments/query-contract', {
      params,
      suppressErrorMessage: true,
      skipRetry: true,
      validateStatus: (status) => status >= 200 && status < 300,
    })
  },
  getQueryBundle(params: MarketDataQueryBundleParams) {
    // This endpoint is a static, read-only control-plane declaration. The
    // caller validates the response before letting it suppress legacy data.
    return request.get<unknown>('/data/market-instruments/query-bundle', {
      params,
      suppressErrorMessage: true,
      skipRetry: true,
      validateStatus: (status) => status >= 200 && status < 300,
    })
  },
  queryLocalFirst(data: MarketDataQueryRequest, options?: MarketDataQueryOptions) {
    if (options?.signal || options?.suppressErrorMessage) {
      return request.post<MarketDataQueryResponse, MarketDataQueryRequest>('/data/queries', data, options)
    }
    return request.post<MarketDataQueryResponse, MarketDataQueryRequest>('/data/queries', data)
  },
  getAssetSpec(symbol: string, params?: { asset_type?: MarketAssetType | string | null }) {
    return request.get<AssetSpecResponse>(`/data/trust/asset-specs/${encodeURIComponent(symbol)}`, {
      params,
    })
  },
  getExecutionModel(symbol: string, params?: { asset_type?: MarketAssetType | string | null }) {
    return request.get<ExecutionModelResponse>(
      `/data/trust/asset-specs/${encodeURIComponent(symbol)}/execution-model`,
      { params },
    )
  },
  listCoverage(params: MarketDataCoverageQuery = {}) {
    return request.get<MarketDataCoverageMatrixResponse>('/data/trust/coverage', {
      params,
    })
  },
  refreshLocalCoverage(params: MarketDataCoverageRefreshQuery = {}) {
    return request.post<MarketDataCoverageMatrixResponse>('/data/trust/coverage/refresh-local', undefined, {
      params,
    })
  },
  refreshWarehouseCoverage(params: MarketDataCoverageRefreshQuery = {}) {
    return request.post<MarketDataCoverageMatrixResponse>(
      '/data/trust/coverage/refresh-warehouse',
      undefined,
      { params },
    )
  },
  runPrecheck(data: DataPrecheckRequest, options?: { signal?: AbortSignal }) {
    if (options?.signal) {
      return request.post<DataPrecheckResponse, DataPrecheckRequest>('/data/trust/precheck', data, options)
    }
    return request.post<DataPrecheckResponse, DataPrecheckRequest>('/data/trust/precheck', data)
  },
}
