export interface AiResearchV2Hypothesis {
  id: string
  hypothesis_id: string
  workspace_id?: string | null
  version_no: number
  parent_version_id?: string | null
  status: 'DRAFT' | 'CONFIRMED' | 'SUPERSEDED'
  canonical_payload: Record<string, unknown>
  content_hash: string
  confirmed_at?: string | null
  created_at: string
}

export interface AiResearchV2Dataset {
  id: string
  dataset_policy_version: string
  partition_kind: 'DISCOVERY' | 'ITERATION_VALIDATION'
  instrument_manifest: Record<string, unknown>
  split_manifest: Record<string, unknown>
  source_manifest: Record<string, unknown>
  execution_policy: Record<string, unknown>
  point_in_time_cutoff: string
  content_hash: string
}

export interface AiResearchV2Epoch {
  id: string
  hypothesis_version_id: string
  family_hash: string
  search_budget: Record<string, unknown>
  dataset_policy_version: string
  holdout_budget: number
  status: 'OPEN' | 'SELECTED' | 'DISCLOSED' | 'CLOSED'
  selected_candidate_id?: string | null
  opened_at: string
}

export interface AiResearchV2Run {
  id: string
  hypothesis_version_id: string
  dataset_snapshot_id?: string | null
  data_precheck_id?: string | null
  experiment_epoch_id?: string | null
  protocol_version: string
  status: string
  stage_cursor: string
  promotion_policy_version: string
  request_hash: string
  capability_profile_id: string
  capability_profile_version: string
  capability_evidence_hash: string
  trace_id: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface AiResearchV2Task {
  id: string
  run_id: string
  status: string
  stage_cursor: string
  error_code?: string | null
  trace_id?: string | null
  cancel_requested_at?: string | null
  attempt_count: number
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

/**
 * Cursor pagination owned by the service. Cursors are opaque browser values:
 * callers may return them to the matching endpoint but must not parse them.
 */
export interface AiResearchV2CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

/**
 * Redacted task-progress metadata. Raw request content, provider prompts,
 * leases, credentials, and executor payloads are deliberately not represented.
 */
export interface AiResearchV2TaskEvent {
  id: string
  task_id: string
  run_id: string
  sequence_no: number
  event_type: string
  stage?: string | null
  status?: string | null
  error_code?: string | null
  stage_attempt_id?: string | null
  trace_id?: string | null
  created_at: string
}

export type AiResearchV2TaskPage = AiResearchV2CursorPage<AiResearchV2Task>

/** Event reads additionally supply an opaque position for their next live read. */
export interface AiResearchV2TaskEventPage extends AiResearchV2CursorPage<AiResearchV2TaskEvent> {
  resume_cursor: string | null
}

export interface AiResearchV2RunSubmission {
  run: AiResearchV2Run
  task: AiResearchV2Task
}

/** Server-evaluated, expiry-bound evidence required before a run can start. */
export interface AiResearchV2DataPrecheck {
  id: string
  hypothesis_version_id: string
  dataset_snapshot_id: string
  experiment_epoch_id: string
  profile_id: string
  profile_version: string
  promotion_policy_version: string
  input_hash: string
  evidence_hash: string
  status: 'PASS' | 'FAIL' | 'BLOCKED'
  reason_code?: string | null
  details: Record<string, unknown>
  checked_at: string
  expires_at: string
}

/** Server-redacted model lineage suitable for the evidence workbench. */
export interface AiResearchV2ModelInvocationSummary {
  id: string
  provider: string
  requested_model: string
  resolved_model: string
  prompt_template_version: string
  token_usage: Record<string, unknown>
  cost: Record<string, unknown>
  error_code?: string | null
  created_at: string
}

/** Identity of a server-built evidence package; its manifest remains controlled. */
export interface AiResearchV2EvidencePackageSummary {
  id: string
  candidate_id: string
  command_id: string | null
  evaluation_id: string | null
  promotion_policy_version: string
  gate_input_evidence_hash: string
  manifest_hash: string
  approval_binding_hash: string
  status: 'ACTIVE' | 'WITHDRAWN'
  created_at: string
}

/**
 * Display-safe identity of one generated candidate.
 *
 * Code, dependency contents, storage references, and sealed evaluation data
 * deliberately stay outside this browser contract.
 */
export interface AiResearchV2Candidate {
  id: string
  run_id: string
  experiment_epoch_id: string
  source_version_id: string | null
  dataset_snapshot_id: string
  code_artifact_id: string
  dependency_artifact_id: string
  candidate_hash: string
  environment_hash: string
  cost_model_hash: string
  params: Record<string, unknown>
  freeze_status: 'MUTABLE' | 'FROZEN'
  frozen_at: string | null
}

export interface AiResearchV2CandidateFreezeRequest {
  expected_candidate_hash: string
}

/**
 * Display-safe lifecycle projection for one server-authorized holdout command.
 *
 * Lease tokens, authorization material, controlled storage references, sealed
 * measurements, and evaluator credentials are intentionally absent.
 */
export interface AiResearchV2HoldoutCommand {
  id: string
  run_id: string
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'TIMED_OUT' | 'RECONCILING'
  stage: 'REQUEST_HOLDOUT' | 'HOLDOUT_PENDING'
  candidate_id: string
  candidate_hash: string
  experiment_epoch_id: string
  dataset_snapshot_id: string
  policy_version: string
  evaluator_identity: string
  capability_profile_id: string
  capability_profile_version: string
  capability_evidence_hash: string
  error_code?: string | null
  request_hash: string
  created_at: string
  updated_at: string
}

/** Metric-free evaluation identity. Sealed measurements and gate inputs never enter browser state. */
export interface AiResearchV2EvaluationSummary {
  id: string
  experiment_epoch_id: string
  candidate_id: string
  dataset_snapshot_id: string
  evaluation_type: 'SEALED_HOLDOUT' | 'ITERATION_VALIDATION'
  evaluator_identity: string
  evaluator_version: string
  policy_version: string
  status: 'PENDING' | 'RUNNING' | 'PASSED' | 'REJECTED' | 'FAILED' | 'EXPIRED'
  completed_at: string | null
}

export interface AiResearchV2CandidateFreezeIdentity {
  runId: string | null | undefined
  runExperimentEpochId: string | null | undefined
  runDatasetSnapshotId: string | null | undefined
  datasetSnapshotId: string | null | undefined
  datasetContentHash: string | null | undefined
}

const SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/

export type AiResearchApprovalMode = 'single_actor' | 'multi_actor'
export type AiResearchApprovalDecision = 'APPROVED' | 'REJECTED' | 'REQUESTED_CHANGES'
export type AiResearchApprovalRequestStatus = 'PENDING' | 'DECIDED' | 'EXPIRED' | 'REVOKED'
export const AI_RESEARCH_APPROVAL_BLOCKED = 'RESEARCH_APPROVAL_BLOCKED' as const
export type AiResearchApprovalRequestBlockedReason =
  | 'OWNER_REQUIRED'
  | 'EVIDENCE_AMBIGUOUS'
  | 'EVIDENCE_NOT_CURRENT'
  | 'APPROVAL_EVIDENCE_DENIED'
  | typeof AI_RESEARCH_APPROVAL_BLOCKED
export type AiResearchApprovalDecisionBlockedReason =
  | 'AUTHORITY_REQUIRED'
  | 'REQUEST_REQUIRED'
  | 'COOLDOWN_ACTIVE'
  | 'EVIDENCE_NOT_CURRENT'
  | typeof AI_RESEARCH_APPROVAL_BLOCKED

const APPROVAL_REQUEST_BLOCKED_REASONS = new Set<string>([
  'OWNER_REQUIRED',
  'EVIDENCE_AMBIGUOUS',
  'EVIDENCE_NOT_CURRENT',
  'APPROVAL_EVIDENCE_DENIED',
])
const APPROVAL_DECISION_BLOCKED_REASONS = new Set<string>([
  'AUTHORITY_REQUIRED',
  'REQUEST_REQUIRED',
  'COOLDOWN_ACTIVE',
  'EVIDENCE_NOT_CURRENT',
])

export interface AiResearchApprovalRequestCreate {
  gate_input_evidence_hash: string
  evidence_package_hash: string
}

export interface AiResearchApprovalDecisionCreate extends AiResearchApprovalRequestCreate {
  approval_request_id: string
  decision: AiResearchApprovalDecision
  reason: string
  challenge_responses: Record<string, string>
  residual_risk_acknowledgement: string | null
}

export interface AiResearchApprovalRequestReceipt {
  id: string
  run_id: string
  candidate_id: string
  evidence_package_id: string
  policy_version: string
  policy_material_hash: string
  approval_mode: AiResearchApprovalMode
  gate_input_evidence_hash: string
  evidence_package_hash: string
  request_material_hash: string
  status: AiResearchApprovalRequestStatus
  requested_at: string
  eligible_at: string
  expires_at: string
  decided_at: string | null
}

export interface AiResearchApprovalDecisionReceipt {
  id: string
  run_id: string
  candidate_id: string
  approval_request_id: string
  decision: AiResearchApprovalDecision
  policy_version: string
  policy_material_hash: string
  approval_mode: AiResearchApprovalMode
  gate_input_evidence_hash: string
  evidence_package_hash: string
  decision_material_hash: string
  decision_intent_hash: string
  risk_acknowledgement: boolean
  challenge_keys: string[]
  reason: string
  decided_at: string
  expires_at: string
}

export interface AiResearchApprovalEvidencePackage {
  id: string
  candidate_id: string
  status: 'ACTIVE'
  promotion_policy_version: string
  command_id: string
  evaluation_id: string
  gate_input_evidence_hash: string
  manifest_hash: string
  approval_binding_hash: string
}

export interface AiResearchApprovalGate {
  gate_code: string
  status: 'PASS'
  reason_code: string
  input_evidence_hash: string
  executor_version: string
  evaluated_at: string
}

export interface AiResearchApprovalMachineEvidence {
  package: AiResearchApprovalEvidencePackage
  gates: AiResearchApprovalGate[]
}

export interface AiResearchApprovalContext {
  run_id: string
  candidate_id: string
  candidate_hash: string
  policy_version: string
  policy_material_hash: string
  approval_mode: AiResearchApprovalMode
  can_request: boolean
  request_blocked_reason: AiResearchApprovalRequestBlockedReason | null
  can_decide: boolean
  can_approve: boolean
  decision_blocked_reason: AiResearchApprovalDecisionBlockedReason | null
  cooldown_seconds: number
  required_challenge_keys: string[]
  risk_acknowledgement_required: boolean
  current_request: AiResearchApprovalRequestReceipt | null
  latest_decision: AiResearchApprovalDecisionReceipt | null
  machine_evidence_summary: AiResearchApprovalMachineEvidence | null
}

export const AI_RESEARCH_APPROVAL_GATE_CODES = [
  'CANDIDATE_FROZEN',
  'SEALED_HOLDOUT',
  'EVIDENCE_BINDING',
  'DEFLATED_SHARPE',
  'MAX_DRAWDOWN',
  'ROBUSTNESS',
  'COST',
  'SLIPPAGE',
  'TURNOVER',
  'CAPACITY',
  'EXTREME_PATH',
  'EXECUTION_SEMANTICS',
  'SECURITY_SCAN',
] as const

/** Convert an untrusted request receipt into browser-owned state. */
export function projectAiResearchApprovalRequest(
  value: unknown,
): AiResearchApprovalRequestReceipt | null {
  const item = approvalRecord(value)
  if (item === null) return null
  const status = item.status
  const mode = approvalMode(item.approval_mode)
  if (
    !approvalStrings(item, [
      'id',
      'run_id',
      'candidate_id',
      'evidence_package_id',
      'policy_version',
    ])
    || mode === null
    || !approvalHash(item.policy_material_hash)
    || !approvalHash(item.gate_input_evidence_hash)
    || !approvalHash(item.evidence_package_hash)
    || !approvalHash(item.request_material_hash)
    || !['PENDING', 'DECIDED', 'EXPIRED', 'REVOKED'].includes(String(status))
    || !approvalDate(item.requested_at)
    || !approvalDate(item.eligible_at)
    || !approvalDate(item.expires_at)
    || !approvalOptionalDate(item.decided_at)
    || (status === 'PENDING' && item.decided_at !== null)
    || (status !== 'PENDING' && item.decided_at === null)
  ) return null
  return {
    id: item.id as string,
    run_id: item.run_id as string,
    candidate_id: item.candidate_id as string,
    evidence_package_id: item.evidence_package_id as string,
    policy_version: item.policy_version as string,
    policy_material_hash: item.policy_material_hash as string,
    approval_mode: mode,
    gate_input_evidence_hash: item.gate_input_evidence_hash as string,
    evidence_package_hash: item.evidence_package_hash as string,
    request_material_hash: item.request_material_hash as string,
    status: status as AiResearchApprovalRequestStatus,
    requested_at: item.requested_at as string,
    eligible_at: item.eligible_at as string,
    expires_at: item.expires_at as string,
    decided_at: item.decided_at as string | null,
  }
}

/** Convert an untrusted decision receipt into browser-owned state. */
export function projectAiResearchApprovalDecision(
  value: unknown,
): AiResearchApprovalDecisionReceipt | null {
  const item = approvalRecord(value)
  if (item === null) return null
  const mode = approvalMode(item.approval_mode)
  const decision = item.decision
  const challengeKeys = approvalStringList(item.challenge_keys)
  const reason = approvalHumanText(item.reason)
  if (
    !approvalStrings(item, [
      'id',
      'run_id',
      'candidate_id',
      'approval_request_id',
      'policy_version',
    ])
    || reason === null
    || mode === null
    || !['APPROVED', 'REJECTED', 'REQUESTED_CHANGES'].includes(String(decision))
    || !approvalHash(item.policy_material_hash)
    || !approvalHash(item.gate_input_evidence_hash)
    || !approvalHash(item.evidence_package_hash)
    || !approvalHash(item.decision_material_hash)
    || !approvalHash(item.decision_intent_hash)
    || typeof item.risk_acknowledgement !== 'boolean'
    || challengeKeys === null
    || !approvalDate(item.decided_at)
    || !approvalDate(item.expires_at)
  ) return null
  return {
    id: item.id as string,
    run_id: item.run_id as string,
    candidate_id: item.candidate_id as string,
    approval_request_id: item.approval_request_id as string,
    decision: decision as AiResearchApprovalDecision,
    policy_version: item.policy_version as string,
    policy_material_hash: item.policy_material_hash as string,
    approval_mode: mode,
    gate_input_evidence_hash: item.gate_input_evidence_hash as string,
    evidence_package_hash: item.evidence_package_hash as string,
    decision_material_hash: item.decision_material_hash as string,
    decision_intent_hash: item.decision_intent_hash as string,
    risk_acknowledgement: item.risk_acknowledgement,
    challenge_keys: challengeKeys,
    reason,
    decided_at: item.decided_at as string,
    expires_at: item.expires_at as string,
  }
}

/** Convert an untrusted approval response into browser-owned state. */
export function projectAiResearchApprovalContext(value: unknown): AiResearchApprovalContext | null {
  const item = approvalRecord(value)
  if (item === null) return null
  const mode = approvalMode(item.approval_mode)
  const challengeKeys = approvalStringList(item.required_challenge_keys)
  const requestBlockedReason = approvalBlockedReason<AiResearchApprovalRequestBlockedReason>(
    item.request_blocked_reason,
    APPROVAL_REQUEST_BLOCKED_REASONS,
  )
  const decisionBlockedReason = approvalBlockedReason<AiResearchApprovalDecisionBlockedReason>(
    item.decision_blocked_reason,
    APPROVAL_DECISION_BLOCKED_REASONS,
  )
  const currentRequest = item.current_request === null
    ? null
    : projectAiResearchApprovalRequest(item.current_request)
  const latestDecision = item.latest_decision === null
    ? null
    : projectAiResearchApprovalDecision(item.latest_decision)
  const machineEvidence = item.machine_evidence_summary === null
    ? null
    : projectApprovalMachineEvidence(item.machine_evidence_summary)
  if (
    !approvalStrings(item, ['run_id', 'candidate_id', 'policy_version'])
    || !approvalHash(item.candidate_hash)
    || !approvalHash(item.policy_material_hash)
    || mode === null
    || typeof item.can_request !== 'boolean'
    || requestBlockedReason === undefined
    || typeof item.can_decide !== 'boolean'
    || typeof item.can_approve !== 'boolean'
    || decisionBlockedReason === undefined
    || !Number.isInteger(item.cooldown_seconds)
    || (item.cooldown_seconds as number) < 0
    || challengeKeys === null
    || typeof item.risk_acknowledgement_required !== 'boolean'
    || (item.current_request !== null && currentRequest === null)
    || (item.latest_decision !== null && latestDecision === null)
    || (item.machine_evidence_summary !== null && machineEvidence === null)
  ) return null
  const context = {
    run_id: item.run_id as string,
    candidate_id: item.candidate_id as string,
    candidate_hash: item.candidate_hash as string,
    policy_version: item.policy_version as string,
    policy_material_hash: item.policy_material_hash as string,
    approval_mode: mode,
    can_request: item.can_request,
    request_blocked_reason: requestBlockedReason,
    can_decide: item.can_decide,
    can_approve: item.can_approve,
    decision_blocked_reason: decisionBlockedReason,
    cooldown_seconds: item.cooldown_seconds as number,
    required_challenge_keys: challengeKeys,
    risk_acknowledgement_required: item.risk_acknowledgement_required,
    current_request: currentRequest,
    latest_decision: latestDecision,
    machine_evidence_summary: machineEvidence,
  } satisfies AiResearchApprovalContext
  if (
    (context.can_request && context.request_blocked_reason !== null)
    || (!context.can_request && context.request_blocked_reason === null)
    || (context.can_decide && context.decision_blocked_reason !== null)
    || (!context.can_decide && context.decision_blocked_reason === null)
    || (context.can_approve && !context.can_decide)
    || (context.can_request && machineEvidence === null)
    || (context.can_decide && (currentRequest === null || machineEvidence === null))
    || (currentRequest !== null && !approvalRequestMatchesContext(currentRequest, context))
    || (latestDecision !== null && !approvalDecisionMatchesContext(latestDecision, context))
    || (machineEvidence !== null
      && !approvalEvidenceMatchesContext(machineEvidence, context, currentRequest))
  ) return null
  return context
}

function projectApprovalMachineEvidence(value: unknown): AiResearchApprovalMachineEvidence | null {
  const item = approvalRecord(value)
  if (item === null || !Array.isArray(item.gates)) return null
  const evidencePackage = projectApprovalEvidencePackage(item.package)
  const gates = item.gates.map(projectApprovalGate)
  if (
    evidencePackage === null
    || gates.some((gate) => gate === null)
    || gates.length !== AI_RESEARCH_APPROVAL_GATE_CODES.length
    || gates.some((gate, index) => gate?.gate_code !== AI_RESEARCH_APPROVAL_GATE_CODES[index])
    || gates.some(
      (gate, index) => gate?.reason_code !== `HOLDOUT_${AI_RESEARCH_APPROVAL_GATE_CODES[index]}_PASSED`,
    )
  ) return null
  return {
    package: evidencePackage,
    gates: gates as AiResearchApprovalGate[],
  }
}

function projectApprovalEvidencePackage(value: unknown): AiResearchApprovalEvidencePackage | null {
  const item = approvalRecord(value)
  if (
    item === null
    || !approvalStrings(item, [
      'id',
      'candidate_id',
      'promotion_policy_version',
      'command_id',
      'evaluation_id',
    ])
    || item.status !== 'ACTIVE'
    || !approvalHash(item.gate_input_evidence_hash)
    || !approvalHash(item.manifest_hash)
    || !approvalHash(item.approval_binding_hash)
  ) return null
  return {
    id: item.id as string,
    candidate_id: item.candidate_id as string,
    status: 'ACTIVE',
    promotion_policy_version: item.promotion_policy_version as string,
    command_id: item.command_id as string,
    evaluation_id: item.evaluation_id as string,
    gate_input_evidence_hash: item.gate_input_evidence_hash as string,
    manifest_hash: item.manifest_hash as string,
    approval_binding_hash: item.approval_binding_hash as string,
  }
}

function projectApprovalGate(value: unknown): AiResearchApprovalGate | null {
  const item = approvalRecord(value)
  if (
    item === null
    || !approvalStrings(item, ['gate_code', 'reason_code', 'executor_version'])
    || item.status !== 'PASS'
    || !approvalHash(item.input_evidence_hash)
    || !approvalDate(item.evaluated_at)
  ) return null
  return {
    gate_code: item.gate_code as string,
    status: 'PASS',
    reason_code: item.reason_code as string,
    input_evidence_hash: item.input_evidence_hash as string,
    executor_version: item.executor_version as string,
    evaluated_at: item.evaluated_at as string,
  }
}

function approvalRequestMatchesContext(
  request: AiResearchApprovalRequestReceipt,
  context: AiResearchApprovalContext,
): boolean {
  return request.status === 'PENDING'
    && request.run_id === context.run_id
    && request.candidate_id === context.candidate_id
    && request.policy_version === context.policy_version
    && request.policy_material_hash === context.policy_material_hash
    && request.approval_mode === context.approval_mode
}

function approvalDecisionMatchesContext(
  decision: AiResearchApprovalDecisionReceipt,
  context: AiResearchApprovalContext,
): boolean {
  return decision.run_id === context.run_id
    && decision.candidate_id === context.candidate_id
}

function approvalEvidenceMatchesContext(
  evidence: AiResearchApprovalMachineEvidence,
  context: AiResearchApprovalContext,
  request: AiResearchApprovalRequestReceipt | null,
): boolean {
  return evidence.package.candidate_id === context.candidate_id
    && evidence.gates.every(
      (gate) => gate.input_evidence_hash === evidence.package.gate_input_evidence_hash,
    )
    && (request === null || (
      evidence.package.id === request.evidence_package_id
      && evidence.package.gate_input_evidence_hash === request.gate_input_evidence_hash
      && evidence.package.manifest_hash === request.evidence_package_hash
    ))
}

function approvalRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function approvalStrings(item: Record<string, unknown>, keys: readonly string[]): boolean {
  return keys.every(
    (key) => typeof item[key] === 'string'
      && stripAiResearchApprovalText(item[key] as string).length > 0,
  )
}

function approvalBlockedReason<T extends string>(
  value: unknown,
  allowed: ReadonlySet<string>,
): T | typeof AI_RESEARCH_APPROVAL_BLOCKED | null | undefined {
  if (value === null) return null
  if (typeof value !== 'string' || stripAiResearchApprovalText(value).length === 0) return undefined
  return allowed.has(value) ? value as T : AI_RESEARCH_APPROVAL_BLOCKED
}

function approvalStringList(value: unknown): string[] | null {
  if (
    !Array.isArray(value)
    || value.some(
      (item) => typeof item !== 'string' || stripAiResearchApprovalText(item).length === 0,
    )
    || new Set(value).size !== value.length
  ) return null
  return [...value] as string[]
}

/** Match Python `str.strip()` exactly for browser/server approval canonicalization. */
export function stripAiResearchApprovalText(value: string): string {
  let start = 0
  let end = value.length
  while (start < end && isPythonStripCodeUnit(value.charCodeAt(start))) start += 1
  while (end > start && isPythonStripCodeUnit(value.charCodeAt(end - 1))) end -= 1
  return value.slice(start, end)
}

function isPythonStripCodeUnit(codeUnit: number): boolean {
  return (codeUnit >= 0x0009 && codeUnit <= 0x000d)
    || (codeUnit >= 0x001c && codeUnit <= 0x0020)
    || codeUnit === 0x0085
    || codeUnit === 0x00a0
    || codeUnit === 0x1680
    || (codeUnit >= 0x2000 && codeUnit <= 0x200a)
    || codeUnit === 0x2028
    || codeUnit === 0x2029
    || codeUnit === 0x202f
    || codeUnit === 0x205f
    || codeUnit === 0x3000
}

function approvalHumanText(value: unknown): string | null {
  if (typeof value !== 'string' || stripAiResearchApprovalText(value).length === 0) return null
  return approvalHumanTextIsUnsafe(value) ? '[REDACTED]' : value
}

function approvalHumanTextIsUnsafe(value: string): boolean {
  return /(?:^|[^a-z0-9+.-])[a-z][a-z0-9+.-]*:(?=\S)/iu.test(value)
    || /(?:^|[^a-z0-9])\/(?:[^/\s]+\/)*[^/\s]+/iu.test(value)
    || /(?:^|[^a-z0-9])[a-z]:[\\/][^\s]+/iu.test(value)
    || /(?:^|[^a-z0-9])(?:\\\\|\/\/)[^\\/\s]+[\\/][^\s]+/iu.test(value)
    || /(?:^|[\s('"{}\x5b])[^\s:/@]+:[^\s/@]+@[^\s/]+/u.test(value)
    || /(?:^|[^a-z0-9])(?:sealed|raw)[\s_-]+(?:metrics?|measurements?|values?|results?|manifests?|holdout|payloads?|data|evidence|outputs?|inputs?|must[\s_-]*not[\s_-]*escape)(?:$|[^a-z0-9])/iu
      .test(value)
}

function approvalMode(value: unknown): AiResearchApprovalMode | null {
  return value === 'single_actor' || value === 'multi_actor' ? value : null
}

function approvalHash(value: unknown): boolean {
  return typeof value === 'string' && SHA256_HEX_PATTERN.test(value)
}

function approvalDate(value: unknown): boolean {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

function approvalOptionalDate(value: unknown): boolean {
  return value === null || approvalDate(value)
}

/**
 * A freeze is offered only when every browser-visible identity binding agrees.
 * The server remains authoritative and rechecks the expected candidate hash.
 */
export function isAiResearchV2CandidateFreezeIdentityComplete(
  candidate: AiResearchV2Candidate,
  identity: AiResearchV2CandidateFreezeIdentity,
): boolean {
  return Boolean(
    candidate.id
    && candidate.run_id
    && candidate.experiment_epoch_id
    && candidate.dataset_snapshot_id
    && candidate.code_artifact_id
    && candidate.dependency_artifact_id
    && candidate.run_id === identity.runId
    && candidate.experiment_epoch_id === identity.runExperimentEpochId
    && candidate.dataset_snapshot_id === identity.runDatasetSnapshotId
    && candidate.dataset_snapshot_id === identity.datasetSnapshotId
    && SHA256_HEX_PATTERN.test(candidate.candidate_hash)
    && SHA256_HEX_PATTERN.test(candidate.environment_hash)
    && SHA256_HEX_PATTERN.test(candidate.cost_model_hash)
    && SHA256_HEX_PATTERN.test(identity.datasetContentHash ?? '')
  )
}

/** A server-recorded limitation; it never changes the referenced hard-gate result. */
export interface AiResearchV2GovernanceDecisionSummary {
  id: string
  target_requirement_or_gate: string
  original_status: 'FAIL' | 'BLOCKED' | 'NOT_RUN'
  reason: string
  risk: string
  compensating_controls: string[]
  effective_at: string
  expires_at: string
  revoked_at?: string | null
}

export interface AiResearchV2Workbench {
  run: AiResearchV2Run
  task?: AiResearchV2Task | null
  hypothesis?: Record<string, unknown> | null
  dataset?: AiResearchV2Dataset | null
  candidates: AiResearchV2Candidate[]
  holdout_commands: AiResearchV2HoldoutCommand[]
  ledger: Array<Record<string, unknown>>
  model_invocations: AiResearchV2ModelInvocationSummary[]
  evaluations: AiResearchV2EvaluationSummary[]
  gates: Array<Record<string, unknown>>
  decisions: Array<Record<string, unknown>>
  governance_decisions: AiResearchV2GovernanceDecisionSummary[]
  evidence_packages: AiResearchV2EvidencePackageSummary[]
  evidence_class: string
}

export interface AiResearchV2DatasetCreateRequest {
  dataset_policy_version: string
  partition_kind: 'DISCOVERY' | 'ITERATION_VALIDATION'
  instrument_manifest: Record<string, unknown>
  split_manifest: Record<string, unknown>
  source_manifest: Record<string, unknown>
  execution_policy: Record<string, unknown>
  point_in_time_cutoff: string
  /** Opaque server-issued receipt for a controlled dataset object; never a URI. */
  object_receipt_id: string
  license_tags: string[]
}

export interface AiResearchV2EpochCreateRequest {
  hypothesis_version_id: string
  search_budget: Record<string, unknown>
  dataset_policy_version: string
}

export interface AiResearchV2RunSubmitRequest {
  hypothesis_version_id: string
  dataset_snapshot_id: string
  experiment_epoch_id: string
  profile_id: string
  profile_version: string
  promotion_policy_version: string
  request_json: Record<string, unknown>
  precheck_id: string
  workspace_id?: string | null
}

export interface AiResearchV2DataPrecheckRequest {
  hypothesis_version_id: string
  dataset_snapshot_id: string
  experiment_epoch_id: string
  profile_id: string
  profile_version: string
  promotion_policy_version: string
  request_json: Record<string, unknown>
  workspace_id?: string | null
  ttl_seconds?: number
}
