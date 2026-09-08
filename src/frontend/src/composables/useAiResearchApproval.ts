import { getCurrentScope, onScopeDispose, ref } from 'vue'

import { strategyApi } from '@/api/strategy'
import { normalizeAiResearchApprovalPublicErrorCode } from '@/contracts/aiResearchApprovalErrors'
import { stripAiResearchApprovalText } from '@/types/aiResearchV2'
import type {
  AiResearchApprovalContext,
  AiResearchApprovalDecision,
  AiResearchApprovalDecisionCreate,
  AiResearchApprovalDecisionReceipt,
  AiResearchApprovalRequestCreate,
  AiResearchApprovalRequestReceipt,
} from '@/types/aiResearchV2'

export interface AiResearchApprovalApi {
  getTrustedAIResearchApprovalContext(
    runId: string,
    candidateId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchApprovalContext>
  requestTrustedAIResearchApproval(
    runId: string,
    candidateId: string,
    data: AiResearchApprovalRequestCreate,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchApprovalRequestReceipt>
  decideTrustedAIResearchApproval(
    runId: string,
    candidateId: string,
    data: AiResearchApprovalDecisionCreate,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchApprovalDecisionReceipt>
}

export interface AiResearchApprovalDecisionInput {
  decision: AiResearchApprovalDecision
  reason: string
  challengeResponses: Record<string, string>
  residualRiskAcknowledgement: string | null
}

export interface AiResearchApprovalDecisionIntentHashInput {
  approvalRequestId: string
  decision: AiResearchApprovalDecision
  reason: string
  gateInputEvidenceHash: string
  evidencePackageHash: string
  challengeKeys: string[]
  challengeResponses: Record<string, string>
  residualRiskAcknowledgement: string | null
}

export interface UseAiResearchApprovalOptions {
  api?: AiResearchApprovalApi
  keyFactory?: () => string
}

interface ApprovalIntent<T> {
  scope: string
  signature: string
  key: string
  payload: T
}

interface RequestApprovalIntent extends ApprovalIntent<AiResearchApprovalRequestCreate> {
  evidencePackageId: string
  policyVersion: string
  policyMaterialHash: string
  approvalMode: AiResearchApprovalContext['approval_mode']
}

interface DecisionApprovalIntent extends ApprovalIntent<AiResearchApprovalDecisionCreate> {
  policyVersion: string
  policyMaterialHash: string
  approvalMode: AiResearchApprovalContext['approval_mode']
  requestMaterialHash: string
  challengeKeys: string[]
  decisionIntentHash: string
}

const SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/
const GENERIC_APPROVAL_ERROR_CODE = 'RESEARCH_APPROVAL_OPERATION_FAILED'

/**
 * Owns the browser side of the server-authorized human approval protocol.
 *
 * Authorization is never inferred here. The runtime only enables an action
 * when the closed approval context says it is allowed, and every mutation is
 * rebuilt from the server-bound request and evidence identities.
 */
export function useAiResearchApproval(options: UseAiResearchApprovalOptions = {}) {
  const api = options.api ?? strategyApi
  const keyFactory = options.keyFactory ?? newApprovalIdempotencyKey
  const context = ref<AiResearchApprovalContext | null>(null)
  const activeRunId = ref<string | null>(null)
  const activeCandidateId = ref<string | null>(null)
  const loading = ref(false)
  const requesting = ref(false)
  const deciding = ref(false)
  const errorCode = ref<string | null>(null)
  const recoveredAction = ref<'request' | 'decision' | null>(null)

  let generation = 0
  let scopeRevision = 0
  let contextController: AbortController | null = null
  let requestController: AbortController | null = null
  let decisionController: AbortController | null = null
  let requestIntent: RequestApprovalIntent | null = null
  let decisionIntent: DecisionApprovalIntent | null = null

  async function select(
    runId: string | null,
    candidateId: string | null,
  ): Promise<AiResearchApprovalContext | null> {
    const nextScope = approvalScope(runId, candidateId)
    const currentScope = approvalScope(activeRunId.value, activeCandidateId.value)
    generation += 1
    abortRequests()
    activeRunId.value = nonEmpty(runId) ? runId : null
    activeCandidateId.value = nonEmpty(candidateId) ? candidateId : null
    context.value = null
    loading.value = false
    requesting.value = false
    deciding.value = false
    errorCode.value = null
    recoveredAction.value = null
    if (nextScope !== currentScope) {
      scopeRevision += 1
      requestIntent = null
      decisionIntent = null
    }
    if (activeRunId.value === null || activeCandidateId.value === null) return null
    return loadSelection(generation)
  }

  async function refresh(): Promise<AiResearchApprovalContext | null> {
    if (activeRunId.value === null || activeCandidateId.value === null) {
      errorCode.value = 'RESEARCH_APPROVAL_SELECTION_REQUIRED'
      return null
    }
    generation += 1
    contextController?.abort()
    requestController?.abort()
    decisionController?.abort()
    contextController = null
    requestController = null
    decisionController = null
    requesting.value = false
    deciding.value = false
    return loadSelection(generation)
  }

  async function loadSelection(requestGeneration: number): Promise<AiResearchApprovalContext | null> {
    const runId = activeRunId.value
    const candidateId = activeCandidateId.value
    if (runId === null || candidateId === null) return null
    contextController = makeAbortController()
    loading.value = true
    errorCode.value = null
    try {
      const received = await api.getTrustedAIResearchApprovalContext(
        runId,
        candidateId,
        contextController?.signal,
      )
      if (!isCurrent(runId, candidateId, requestGeneration)) return null
      if (received.run_id !== runId || received.candidate_id !== candidateId) {
        context.value = null
        errorCode.value = 'RESEARCH_APPROVAL_CONTEXT_BINDING_INVALID'
        return null
      }
      context.value = received
      reconcileIntents(received)
      return received
    } catch (caught) {
      if (isCurrent(runId, candidateId, requestGeneration)) {
        context.value = null
        errorCode.value = approvalApiErrorCode(caught)
      }
      return null
    } finally {
      if (isCurrent(runId, candidateId, requestGeneration)) loading.value = false
    }
  }

  async function requestApproval(): Promise<AiResearchApprovalRequestReceipt | null> {
    const selected = selectedContext()
    if (selected === null) return null
    if (!selected.can_request) {
      errorCode.value = selected.request_blocked_reason || 'RESEARCH_APPROVAL_REQUEST_NOT_ALLOWED'
      return null
    }
    if (selected.current_request !== null) {
      errorCode.value = 'RESEARCH_APPROVAL_REQUEST_ALREADY_PENDING'
      return null
    }
    const evidence = selected.machine_evidence_summary
    if (
      evidence === null
      || evidence.package.status !== 'ACTIVE'
      || evidence.package.candidate_id !== selected.candidate_id
      || !nonEmpty(evidence.package.command_id)
      || !nonEmpty(evidence.package.evaluation_id)
      || !SHA256_HEX_PATTERN.test(evidence.package.gate_input_evidence_hash)
      || !SHA256_HEX_PATTERN.test(evidence.package.manifest_hash)
    ) {
      errorCode.value = 'RESEARCH_APPROVAL_EVIDENCE_INCOMPLETE'
      return null
    }
    if (requesting.value) return null
    const payload: AiResearchApprovalRequestCreate = {
      gate_input_evidence_hash: evidence.package.gate_input_evidence_hash,
      evidence_package_hash: evidence.package.manifest_hash,
    }
    const scope = approvalScope(selected.run_id, selected.candidate_id)
    const signature = approvalSignature({
      payload,
      evidence_package_id: evidence.package.id,
      policy_version: selected.policy_version,
      policy_material_hash: selected.policy_material_hash,
      approval_mode: selected.approval_mode,
    })
    const nextIntent = matchingIntent(requestIntent, scope, signature)
      ?? {
        scope,
        signature,
        key: keyFactory(),
        payload,
        evidencePackageId: evidence.package.id,
        policyVersion: selected.policy_version,
        policyMaterialHash: selected.policy_material_hash,
        approvalMode: selected.approval_mode,
      }
    requestIntent = nextIntent
    const intent = nextIntent
    const requestGeneration = generation
    const requestScopeRevision = scopeRevision
    const mutationController = makeAbortController()
    requestController = mutationController
    requesting.value = true
    errorCode.value = null
    recoveredAction.value = null
    try {
      const receipt = await api.requestTrustedAIResearchApproval(
        selected.run_id,
        selected.candidate_id,
        intent.payload,
        intent.key,
        mutationController?.signal,
      )
      if (!isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) return null
      if (!approvalRequestMatchesIntent(receipt, intent)) {
        const recovered = await reconcileUnknownContext(
          selected.run_id,
          selected.candidate_id,
          requestGeneration,
        )
        const recoveredRequest = recovered?.current_request
        if (recoveredRequest && approvalRequestMatchesIntent(recoveredRequest, intent)) {
          requestIntent = null
          recoveredAction.value = 'request'
          errorCode.value = null
          return recoveredRequest
        }
        if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) {
          errorCode.value = 'RESEARCH_APPROVAL_RESPONSE_MISMATCH'
        }
        return null
      }
      requestIntent = null
      requesting.value = false
      await refresh()
      return isScopeCurrent(
        selected.run_id,
        selected.candidate_id,
        requestScopeRevision,
      ) ? receipt : null
    } catch (caught) {
      if (!isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) return null
      const error = approvalApiErrorCode(caught)
      if (isDeterministicClientError(caught)) {
        requestIntent = null
      } else {
        const received = await reconcileUnknownContext(
          selected.run_id,
          selected.candidate_id,
          requestGeneration,
        )
        const recoveredRequest = received?.current_request
        if (recoveredRequest && approvalRequestMatchesIntent(recoveredRequest, intent)) {
          requestIntent = null
          recoveredAction.value = 'request'
          errorCode.value = null
          return recoveredRequest
        }
      }
      if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) {
        errorCode.value = error
      }
      return null
    } finally {
      if (requestController === mutationController) requestController = null
      if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) {
        requesting.value = false
      }
    }
  }

  async function submitDecision(
    input: AiResearchApprovalDecisionInput,
  ): Promise<AiResearchApprovalDecisionReceipt | null> {
    const selected = selectedContext()
    if (selected === null) return null
    if (!selected.can_decide) {
      errorCode.value = selected.decision_blocked_reason || 'RESEARCH_APPROVAL_DECISION_NOT_ALLOWED'
      return null
    }
    if (input.decision === 'APPROVED' && !selected.can_approve) {
      errorCode.value = 'RESEARCH_APPROVAL_APPROVE_NOT_ALLOWED'
      return null
    }
    const reason = stripAiResearchApprovalText(input.reason)
    if (reason.length === 0) {
      errorCode.value = 'RESEARCH_APPROVAL_REASON_REQUIRED'
      return null
    }
    const currentRequest = selected.current_request
    const evidence = selected.machine_evidence_summary
    if (currentRequest === null || evidence === null) {
      errorCode.value = 'RESEARCH_APPROVAL_EVIDENCE_INCOMPLETE'
      return null
    }
    const isApproval = input.decision === 'APPROVED'
    const challengeResponses = isApproval
      ? requiredChallengeResponses(selected.required_challenge_keys, input.challengeResponses)
      : {}
    if (challengeResponses === null) {
      errorCode.value = 'RESEARCH_APPROVAL_CHALLENGES_REQUIRED'
      return null
    }
    const riskAcknowledgement = isApproval
      ? stripAiResearchApprovalText(input.residualRiskAcknowledgement || '') || null
      : null
    if (isApproval && selected.risk_acknowledgement_required && riskAcknowledgement === null) {
      errorCode.value = 'RESEARCH_APPROVAL_RISK_ACKNOWLEDGEMENT_REQUIRED'
      return null
    }
    if (deciding.value) return null
    const payload: AiResearchApprovalDecisionCreate = {
      approval_request_id: currentRequest.id,
      decision: input.decision,
      reason,
      gate_input_evidence_hash: currentRequest.gate_input_evidence_hash,
      evidence_package_hash: currentRequest.evidence_package_hash,
      challenge_responses: challengeResponses,
      residual_risk_acknowledgement: riskAcknowledgement,
    }
    const scope = approvalScope(selected.run_id, selected.candidate_id)
    const signature = approvalSignature({
      payload,
      request_material_hash: currentRequest.request_material_hash,
      policy_version: currentRequest.policy_version,
      policy_material_hash: currentRequest.policy_material_hash,
      approval_mode: currentRequest.approval_mode,
      required_challenge_keys: selected.required_challenge_keys,
    })
    const requestGeneration = generation
    const requestScopeRevision = scopeRevision
    deciding.value = true
    errorCode.value = null
    recoveredAction.value = null
    let nextIntent = matchingIntent(decisionIntent, scope, signature)
    if (nextIntent === null) {
      let decisionIntentHash: string
      try {
        decisionIntentHash = await aiResearchApprovalDecisionIntentHash({
          approvalRequestId: payload.approval_request_id,
          decision: payload.decision,
          reason: payload.reason,
          gateInputEvidenceHash: payload.gate_input_evidence_hash,
          evidencePackageHash: payload.evidence_package_hash,
          challengeKeys: selected.required_challenge_keys,
          challengeResponses: payload.challenge_responses,
          residualRiskAcknowledgement: payload.residual_risk_acknowledgement,
        })
      } catch {
        if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) {
          errorCode.value = GENERIC_APPROVAL_ERROR_CODE
          deciding.value = false
        }
        return null
      }
      if (!isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) return null
      nextIntent = {
        scope,
        signature,
        key: keyFactory(),
        payload,
        policyVersion: currentRequest.policy_version,
        policyMaterialHash: currentRequest.policy_material_hash,
        approvalMode: currentRequest.approval_mode,
        requestMaterialHash: currentRequest.request_material_hash,
        challengeKeys: [...selected.required_challenge_keys],
        decisionIntentHash,
      }
    }
    decisionIntent = nextIntent
    const intent = nextIntent
    const mutationController = makeAbortController()
    decisionController = mutationController
    try {
      const receipt = await api.decideTrustedAIResearchApproval(
        selected.run_id,
        selected.candidate_id,
        intent.payload,
        intent.key,
        mutationController?.signal,
      )
      if (!isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) return null
      if (!approvalDecisionMatchesIntent(receipt, intent)) {
        const recovered = await reconcileUnknownContext(
          selected.run_id,
          selected.candidate_id,
          requestGeneration,
        )
        const recoveredDecision = recovered?.latest_decision
        if (recoveredDecision && approvalDecisionMatchesIntent(recoveredDecision, intent)) {
          decisionIntent = null
          recoveredAction.value = 'decision'
          errorCode.value = null
          return recoveredDecision
        }
        if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) {
          errorCode.value = 'RESEARCH_APPROVAL_RESPONSE_MISMATCH'
        }
        return null
      }
      decisionIntent = null
      deciding.value = false
      await refresh()
      return isScopeCurrent(
        selected.run_id,
        selected.candidate_id,
        requestScopeRevision,
      ) ? receipt : null
    } catch (caught) {
      if (!isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) return null
      const error = approvalApiErrorCode(caught)
      if (isDeterministicClientError(caught)) {
        decisionIntent = null
      } else {
        const received = await reconcileUnknownContext(
          selected.run_id,
          selected.candidate_id,
          requestGeneration,
        )
        const recoveredDecision = received?.latest_decision
        if (recoveredDecision && approvalDecisionMatchesIntent(recoveredDecision, intent)) {
          decisionIntent = null
          recoveredAction.value = 'decision'
          errorCode.value = null
          return recoveredDecision
        }
      }
      if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) {
        errorCode.value = error
      }
      return null
    } finally {
      if (decisionController === mutationController) decisionController = null
      if (isCurrent(selected.run_id, selected.candidate_id, requestGeneration)) deciding.value = false
    }
  }

  function selectedContext(): AiResearchApprovalContext | null {
    const selected = context.value
    if (
      selected === null
      || selected.run_id !== activeRunId.value
      || selected.candidate_id !== activeCandidateId.value
    ) {
      errorCode.value = 'RESEARCH_APPROVAL_SELECTION_REQUIRED'
      return null
    }
    return selected
  }

  function isCurrent(runId: string, candidateId: string, requestGeneration: number): boolean {
    return generation === requestGeneration
      && activeRunId.value === runId
      && activeCandidateId.value === candidateId
  }

  function isScopeCurrent(
    runId: string,
    candidateId: string,
    requestScopeRevision: number,
  ): boolean {
    return scopeRevision === requestScopeRevision
      && activeRunId.value === runId
      && activeCandidateId.value === candidateId
  }

  function reconcileIntents(received: AiResearchApprovalContext): void {
    const scope = approvalScope(received.run_id, received.candidate_id)
    if (requestIntent?.scope !== scope) requestIntent = null
    if (decisionIntent?.scope !== scope) decisionIntent = null
    if (
      requestIntent !== null
      && received.current_request !== null
      && approvalRequestMatchesIntent(received.current_request, requestIntent)
    ) {
      requestIntent = null
      recoveredAction.value = 'request'
    }
    if (
      decisionIntent !== null
      && received.latest_decision !== null
      && approvalDecisionMatchesIntent(received.latest_decision, decisionIntent)
    ) {
      decisionIntent = null
      recoveredAction.value = 'decision'
    }
  }

  async function reconcileUnknownContext(
    runId: string,
    candidateId: string,
    requestGeneration: number,
  ): Promise<AiResearchApprovalContext | null> {
    if (!isCurrent(runId, candidateId, requestGeneration)) return null
    contextController?.abort()
    contextController = makeAbortController()
    loading.value = true
    try {
      const received = await api.getTrustedAIResearchApprovalContext(
        runId,
        candidateId,
        contextController?.signal,
      )
      if (
        !isCurrent(runId, candidateId, requestGeneration)
        || received.run_id !== runId
        || received.candidate_id !== candidateId
      ) return null
      context.value = received
      return received
    } catch {
      return null
    } finally {
      if (isCurrent(runId, candidateId, requestGeneration)) loading.value = false
    }
  }

  function clearError(): void {
    errorCode.value = null
    recoveredAction.value = null
  }

  function dispose(): void {
    generation += 1
    abortRequests()
    activeRunId.value = null
    activeCandidateId.value = null
    context.value = null
    loading.value = false
    requesting.value = false
    deciding.value = false
    errorCode.value = null
    requestIntent = null
    decisionIntent = null
  }

  function abortRequests(): void {
    contextController?.abort()
    requestController?.abort()
    decisionController?.abort()
    contextController = null
    requestController = null
    decisionController = null
  }

  if (getCurrentScope()) onScopeDispose(dispose)

  return {
    context,
    activeRunId,
    activeCandidateId,
    loading,
    requesting,
    deciding,
    errorCode,
    recoveredAction,
    select,
    refresh,
    requestApproval,
    submitDecision,
    clearError,
    dispose,
  }
}

function approvalScope(runId: string | null, candidateId: string | null): string {
  return runId === null || candidateId === null ? '' : `${runId}\u0000${candidateId}`
}

function approvalSignature(value: unknown): string {
  return JSON.stringify(canonicalJson(value))
}

function canonicalJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalJson)
  if (value === null || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entry]) => [key, canonicalJson(entry)]),
  )
}

function matchingIntent<T extends { scope: string; signature: string }>(
  intent: T | null,
  scope: string,
  signature: string,
): T | null {
  return intent?.scope === scope && intent.signature === signature ? intent : null
}

function approvalRequestMatchesIntent(
  request: AiResearchApprovalRequestReceipt,
  intent: RequestApprovalIntent,
): boolean {
  return approvalScope(request.run_id, request.candidate_id) === intent.scope
    && request.evidence_package_id === intent.evidencePackageId
    && request.policy_version === intent.policyVersion
    && request.policy_material_hash === intent.policyMaterialHash
    && request.approval_mode === intent.approvalMode
    && request.gate_input_evidence_hash === intent.payload.gate_input_evidence_hash
    && request.evidence_package_hash === intent.payload.evidence_package_hash
}

function approvalDecisionMatchesIntent(
  decision: AiResearchApprovalDecisionReceipt,
  intent: DecisionApprovalIntent,
): boolean {
  const expectedChallengeKeys = Object.keys(intent.payload.challenge_responses).sort()
  const receivedChallengeKeys = [...decision.challenge_keys].sort()
  return approvalScope(decision.run_id, decision.candidate_id) === intent.scope
    && decision.approval_request_id === intent.payload.approval_request_id
    && decision.decision === intent.payload.decision
    && decision.decision_intent_hash === intent.decisionIntentHash
    && decision.policy_version === intent.policyVersion
    && decision.policy_material_hash === intent.policyMaterialHash
    && decision.approval_mode === intent.approvalMode
    && decision.gate_input_evidence_hash === intent.payload.gate_input_evidence_hash
    && decision.evidence_package_hash === intent.payload.evidence_package_hash
    && decision.risk_acknowledgement
      === (intent.payload.residual_risk_acknowledgement !== null)
    && approvalSignature(receivedChallengeKeys) === approvalSignature(expectedChallengeKeys)
}

/** Compute the public browser-verifiable decision receipt defined by the backend contract. */
export async function aiResearchApprovalDecisionIntentHash(
  input: AiResearchApprovalDecisionIntentHashInput,
): Promise<string> {
  const reason = stripAiResearchApprovalText(input.reason)
  const riskAcknowledgement = stripAiResearchApprovalText(
    input.residualRiskAcknowledgement || '',
  )
  const challengeKeys = [...input.challengeKeys]
  const responseKeys = Object.keys(input.challengeResponses)
  const allowedKeys = new Set(challengeKeys)
  if (
    !stripAiResearchApprovalText(input.approvalRequestId)
    || !['APPROVED', 'REJECTED', 'REQUESTED_CHANGES'].includes(input.decision)
    || !reason
    || !SHA256_HEX_PATTERN.test(input.gateInputEvidenceHash)
    || !SHA256_HEX_PATTERN.test(input.evidencePackageHash)
    || challengeKeys.some((key) => !stripAiResearchApprovalText(key))
    || allowedKeys.size !== challengeKeys.length
    || responseKeys.some((key) => !allowedKeys.has(key))
    || responseKeys.some((key) => typeof input.challengeResponses[key] !== 'string')
  ) throw new Error('RESEARCH_APPROVAL_DECISION_INTENT_INVALID')

  const challengeRecords: Array<{ key: string; answer_hash: string }> = []
  for (const key of challengeKeys) {
    const answer = stripAiResearchApprovalText(input.challengeResponses[key] || '')
    if (answer) {
      challengeRecords.push({ key, answer_hash: await approvalContentHash(answer) })
    }
  }
  const [reasonHash, challengeHash, riskAcknowledgementHash] = await Promise.all([
    approvalContentHash(reason),
    approvalContentHash(challengeRecords),
    approvalContentHash(riskAcknowledgement),
  ])
  return approvalContentHash({
    schema_version: 'ai-research-human-decision-intent/v1',
    approval_request_id: input.approvalRequestId,
    decision: input.decision,
    reason_hash: reasonHash,
    gate_input_evidence_hash: input.gateInputEvidenceHash,
    evidence_package_hash: input.evidencePackageHash,
    challenge_hash: challengeHash,
    risk_acknowledgement_hash: riskAcknowledgementHash,
  })
}

async function approvalContentHash(value: unknown): Promise<string> {
  const subtle = globalThis.crypto?.subtle
  if (!subtle) throw new Error('RESEARCH_APPROVAL_CRYPTO_UNAVAILABLE')
  const payload = JSON.stringify(canonicalJson(value))
  if (payload === undefined) throw new Error('RESEARCH_APPROVAL_CANONICAL_VALUE_INVALID')
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(payload))
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

function requiredChallengeResponses(
  requiredKeys: string[],
  received: Record<string, string>,
): Record<string, string> | null {
  const response: Record<string, string> = {}
  for (const key of requiredKeys) {
    const answer = stripAiResearchApprovalText(received[key] || '')
    if (!answer) return null
    response[key] = answer
  }
  return response
}

function approvalApiErrorCode(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as {
      response?: {
        data?: {
          details?: unknown
          detail?: unknown
          message?: unknown
          error?: unknown
        }
      }
    }).response
    const currentCode = approvalEnvelopeCode(response?.data?.details)
    const legacyCode = approvalEnvelopeCode(response?.data?.detail)
    if (currentCode !== undefined && legacyCode !== undefined) {
      const current = normalizeAiResearchApprovalPublicErrorCode(currentCode)
      const legacy = normalizeAiResearchApprovalPublicErrorCode(legacyCode)
      return current !== null && current === legacy ? current : GENERIC_APPROVAL_ERROR_CODE
    }
    const normalized = normalizeAiResearchApprovalPublicErrorCode(currentCode ?? legacyCode)
    if (normalized !== null) return normalized
  }
  return GENERIC_APPROVAL_ERROR_CODE
}

function approvalEnvelopeCode(value: unknown): unknown | undefined {
  return value && typeof value === 'object' && 'code' in value
    ? (value as { code?: unknown }).code
    : undefined
}

function isDeterministicClientError(error: unknown): boolean {
  if (!error || typeof error !== 'object' || !('response' in error)) return false
  const status = (error as { response?: { status?: unknown } }).response?.status
  return typeof status === 'number' && status >= 400 && status < 500
}

function newApprovalIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.()
    || `approval-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function makeAbortController(): AbortController | null {
  return typeof AbortController === 'undefined' ? null : new AbortController()
}

function nonEmpty(value: string | null): value is string {
  return typeof value === 'string' && stripAiResearchApprovalText(value).length > 0
}
