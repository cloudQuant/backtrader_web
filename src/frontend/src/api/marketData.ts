import request from './index'
import type {
  AssetSpecResponse,
  DataPrecheckRequest,
  DataPrecheckResponse,
  ExecutionModelResponse,
  MarketDataCoverageMatrixResponse,
} from '@/types/trust'

export type MarketAssetType = 'stock' | 'futures' | 'bond' | 'fund' | 'option' | 'fx' | 'crypto'
/**
 * Keep this wire union aligned with the v2 public DTO. A family can declare a
 * bar cadence, reporting period, or point-in-time snapshot; executable state
 * remains server-owned by the reviewed family control plane.
 */
export type MarketDataQueryFrequency = '5min' | '30min' | '1h' | '1d' | '1w' | '1mo' | 'snapshot'
export type MarketDataQueryDataKind = (
  | 'bars'
  | 'quote_snapshot'
  | 'valuation_snapshot'
  | 'option_chain'
  | 'position_report'
  | 'reference_series'
  | 'inventory_report'
  | 'option_risk_surface'
)
export type MarketDataQueryMode = 'local_first' | 'local_only' | 'refresh'
export type MarketDataQueryConsistency = 'display' | 'strict'
export type MarketDataQueryPurpose = (
  | 'display'
  | 'research'
  | 'research_cache_fill'
  | 'backtest'
  | 'export'
)
export const MARKET_DATA_FAMILY_CONTRACT_VERSION = 'market-data-family-v1' as const
export type MarketDataFamilyContractVersion = typeof MARKET_DATA_FAMILY_CONTRACT_VERSION

/**
 * Server-owned effective rollout state for the normalized data platform.
 *
 * These fields intentionally describe enabled capabilities only; they never
 * expose source credentials, provider configuration, or raw deployment flags.
 */
export interface MarketDataCapabilitiesResponse {
  version: 'market-data-capabilities-v1'
  query_v2_enabled: boolean
  online_fetch_enabled: boolean
  research_cache_fill_enabled: boolean
  research_backtest_bridge_enabled: boolean
}

export function hasMarketDataCapabilities(value: unknown): value is MarketDataCapabilitiesResponse {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<MarketDataCapabilitiesResponse>
  return candidate.version === 'market-data-capabilities-v1'
    && typeof candidate.query_v2_enabled === 'boolean'
    && typeof candidate.online_fetch_enabled === 'boolean'
    && typeof candidate.research_cache_fill_enabled === 'boolean'
    && typeof candidate.research_backtest_bridge_enabled === 'boolean'
}

/**
 * Server-proven v2 request facts attached to a legacy lookup when, and only
 * when, the API can resolve an exact canonical instrument and active dataset.
 *
 * The frontend deliberately does not derive a canonical ID or dataset code
 * from a symbol.  This keeps the progressive rollout safe while the catalog
 * and master-data bootstrap are incomplete.
 */
/** Every executable v2 query carries both immutable server-issued family axes. */
export interface MarketDataFamilyBinding {
  family_id: string
  family_contract_version: MarketDataFamilyContractVersion
}

export interface MarketDataQueryContractRequestBase {
  identity: {
    canonical_id: string
  }
  dataset_code: string
  data_kind: MarketDataQueryDataKind
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
export type MarketDataQueryBundleFrequency = MarketDataQueryFrequency
export type MarketDataQueryBundleFrequencySemantics = 'calendar_grid' | 'snapshot' | 'reporting_period'
export type MarketDataQueryBundleCoverageModel = (
  | 'calendar_grid'
  | 'snapshot_freshness'
  | 'slice_completeness'
  | 'report_completeness'
)
export type MarketDataQueryBundleDataKind = MarketDataQueryDataKind

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
 * The bundle describes an observation shape only.  It is intentionally not a
 * permission to query facts: callers still need a server-issued, exact query
 * contract before a page can render a specialized or generic observation view.
 */
export type MarketDataFamilyObservationShape = 'single_record' | 'dimensioned_records'

export function marketDataFamilyObservationShape(
  family: Pick<MarketDataQueryBundleFamily, 'data_kind' | 'dimension_fields'>,
): MarketDataFamilyObservationShape {
  if (
    family.dimension_fields.length > 0
    || family.data_kind === 'option_chain'
    || family.data_kind === 'position_report'
    || family.data_kind === 'inventory_report'
    || family.data_kind === 'option_risk_surface'
  ) {
    return 'dimensioned_records'
  }
  return 'single_record'
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
  data_kind: MarketDataQueryDataKind
  frequency: MarketDataQueryFrequency
  source_policy_id: string
  /** Immutable echo of the required public query family binding. */
  family_id: string
  family_contract_version: MarketDataFamilyContractVersion
  knowledge_cutoff: string
  identity_knowledge_cutoff: string
  observations: MarketDataQueryObservation[]
  next_cursor: string | null
  coverage: MarketDataQueryCoverage
  fetches: MarketDataQueryFetch[]
  warnings: MarketDataQueryWarning[]
  refresh_status: 'fresh_complete' | 'fresh_incomplete' | 'fresh_unknown_calendar' | null
  historical_status: 'unknown_calendar' | 'HISTORICAL_COVERAGE_UNAVAILABLE' | null
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
  /**
   * The legacy bridge currently exposes daily/weekly/monthly labels, while a
   * v2 family may declare an intraday cadence or a snapshot.  Keep the wire
   * type representable so a reviewed server-side bridge can introduce those
   * families without the browser rejecting its own signed contract first.
   */
  period: 'daily' | 'weekly' | 'monthly' | MarketDataQueryFrequency
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
  /**
   * Legacy lookup compatibility proof for an attached v2 contract.  A client
   * may use that contract only when these server-issued values exactly match
   * both the current symbol and the contract identity.
   */
  query_contract_symbol?: string | null
  query_contract_canonical_id?: string | null
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

const MARKET_DATA_QUERY_DATA_KINDS: readonly MarketDataQueryDataKind[] = [
  'bars',
  'quote_snapshot',
  'valuation_snapshot',
  'option_chain',
  'position_report',
  'reference_series',
  'inventory_report',
  'option_risk_surface',
]
const MARKET_DATA_QUERY_FREQUENCIES: readonly MarketDataQueryFrequency[] = [
  '5min',
  '30min',
  '1h',
  '1d',
  '1w',
  '1mo',
  'snapshot',
]
const MARKET_DATA_QUERY_BUNDLE_DATA_KINDS: readonly MarketDataQueryBundleDataKind[] = (
  MARKET_DATA_QUERY_DATA_KINDS
)
const MARKET_DATA_QUERY_BUNDLE_FREQUENCIES: readonly MarketDataQueryBundleFrequency[] = (
  MARKET_DATA_QUERY_FREQUENCIES
)
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

function hasRequiredMarketDataFamilyBinding(value: Record<string, unknown>): boolean {
  return nonEmptyText(value.family_id)
    && value.family_contract_version === MARKET_DATA_FAMILY_CONTRACT_VERSION
}

function hasCoherentMarketDataQueryBundleFamilyShape(family: Record<string, unknown>): boolean {
  const dataKind = family.data_kind as MarketDataQueryBundleDataKind
  const frequencySemantics = family.frequency_semantics as MarketDataQueryBundleFrequencySemantics
  const frequencies = family.frequencies as MarketDataQueryBundleFrequency[]
  const coverageModel = family.coverage_model as MarketDataQueryBundleCoverageModel
  const dimensionFields = family.dimension_fields as string[]
  const hasOnlySnapshotFrequency = frequencies.length === 1 && frequencies[0] === 'snapshot'
  const hasNoSnapshotFrequency = !frequencies.includes('snapshot')

  // A bundle is an authenticated control-plane document.  Validate each
  // product shape as a matrix rather than accepting a broadly plausible
  // cadence.  In particular, a chain/report must not become executable when
  // a malformed response labels it as a single-record calendar series.
  if (dataKind === 'bars' || dataKind === 'reference_series') {
    return frequencySemantics === 'calendar_grid'
      && coverageModel === 'calendar_grid'
      && hasNoSnapshotFrequency
      && dimensionFields.length === 0
  }
  if (dataKind === 'quote_snapshot' || dataKind === 'valuation_snapshot') {
    return frequencySemantics === 'snapshot'
      && coverageModel === 'snapshot_freshness'
      && hasOnlySnapshotFrequency
      && dimensionFields.length === 0
  }
  if (dataKind === 'option_chain' || dataKind === 'option_risk_surface') {
    return frequencySemantics === 'snapshot'
      && coverageModel === 'slice_completeness'
      && hasOnlySnapshotFrequency
      && dimensionFields.length > 0
  }
  if (dataKind === 'position_report' || dataKind === 'inventory_report') {
    return frequencySemantics === 'reporting_period'
      && coverageModel === 'report_completeness'
      && hasNoSnapshotFrequency
      && dimensionFields.length > 0
  }
  return false
}

/**
 * Return whether a family can be selected by the current market-data page.
 *
 * The public wire DTO intentionally describes several non-executable
 * multi-record product classes so the page can render their explicit NO-GO
 * state.  It must not, however, treat a malformed or prematurely promoted
 * ``ready`` status as permission to issue a chain/surface/report query.  The
 * page currently has reviewed renderers only for single-record bars,
 * reference series, and quote snapshots.  Keep this allowlist beside the
 * wire-shape validator so an unsupported data kind cannot become selectable
 * merely by carrying a source-policy ID.
 */
export function isMarketDataQueryBundleFamilyExecutable(
  value: unknown,
): value is MarketDataQueryBundleFamily {
  if (!value || typeof value !== 'object') return false
  const family = value as Record<string, unknown>
  if (
    family.status !== 'ready'
    || !nonEmptyText(family.source_policy_id)
    || family.reason_code !== null
    || !hasCoherentMarketDataQueryBundleFamilyShape(family)
  ) {
    return false
  }
  return (
    family.data_kind === 'bars'
    || family.data_kind === 'reference_series'
    || family.data_kind === 'quote_snapshot'
  )
}

function hasCoherentMarketDataQueryContractShape(request: Record<string, unknown>): boolean {
  const dataKind = request.data_kind as MarketDataQueryDataKind
  const frequency = request.frequency as MarketDataQueryFrequency
  if (dataKind === 'bars' || dataKind === 'reference_series') return frequency !== 'snapshot'
  if (dataKind === 'quote_snapshot' || dataKind === 'valuation_snapshot') return frequency === 'snapshot'
  if (dataKind === 'option_chain' || dataKind === 'option_risk_surface') return frequency === 'snapshot'
  if (dataKind === 'position_report' || dataKind === 'inventory_report') return frequency !== 'snapshot'
  return false
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
    if (
      new Set(fieldNames).size !== fieldNames.length
      || !hasCoherentMarketDataQueryBundleFamilyShape(family)
    ) {
      return false
    }
    if (family.status === 'ready') return isMarketDataQueryBundleFamilyExecutable(family)
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
      && MARKET_DATA_QUERY_DATA_KINDS.includes(request.data_kind as MarketDataQueryDataKind)
      && MARKET_DATA_QUERY_FREQUENCIES.includes(request.frequency as MarketDataQueryFrequency)
      && hasDistinctTextArray(request.required_fields, 1)
      && nonEmptyText(request.source_policy_id)
      && hasRequiredMarketDataFamilyBinding(request)
      && hasCoherentMarketDataQueryContractShape(request)
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
    // Preserve an explicit `null` from the server contract. For a reviewed
    // undeclared axis (such as an FX pair's currency/unit), `undefined` would
    // disappear during JSON serialization and turn an exact signed request
    // into an omitted/generic semantic axis at the API boundary.
    adjustment: request.adjustment,
    price_basis: request.price_basis,
    currency: request.currency,
    unit: request.unit,
    source_policy_id: request.source_policy_id,
    mode: options.mode || request.mode,
    start: options.start,
    end: options.end,
    consistency: options.consistency,
    purpose: options.purpose,
    knowledge_cutoff: options.knowledge_cutoff,
    page_size: options.page_size,
  }
  return {
    ...requestBase,
    family_id: request.family_id,
    family_contract_version: request.family_contract_version,
  }
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
  getCapabilities() {
    return request.get<unknown>('/data/market-data/capabilities', {
      suppressErrorMessage: true,
      skipRetry: true,
      validateStatus: (status) => status >= 200 && status < 300,
    })
  },
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
