import { describe, expect, it, vi } from 'vitest'

import { useAiResearchApproval } from '@/composables/useAiResearchApproval'
import {
  APPROVAL_HASHES,
  APPROVAL_POLICY_VERSION,
  PROMOTION_POLICY_VERSION,
  approvalContextFor,
  approvalContextFixture,
  approvalDecisionFixture,
  approvalRequestFixture,
} from '@/__tests__/fixtures/aiResearchApproval'
import { projectAiResearchApprovalContext } from '@/types/aiResearchV2'
import type {
  AiResearchApprovalContext,
  AiResearchApprovalDecisionCreate,
  AiResearchApprovalRequestCreate,
} from '@/types/aiResearchV2'

const APPROVAL_PUBLIC_ERROR_CODES = [
  'APPROVAL_CAPABILITY_PROFILE_INVALID',
  'APPROVAL_CHALLENGE_INCOMPLETE',
  'APPROVAL_CHALLENGE_INVALID',
  'APPROVAL_COOLDOWN_ACTIVE',
  'APPROVAL_DECISION_COMMIT_OUTCOME_UNKNOWN',
  'APPROVAL_DECISION_INVALID',
  'APPROVAL_EVIDENCE_DENIED',
  'APPROVAL_EVIDENCE_PACKAGE_CORRUPT',
  'APPROVAL_EVIDENCE_PACKAGE_NOT_FOUND',
  'APPROVAL_EVIDENCE_PACKAGE_STALE',
  'APPROVAL_EVIDENCE_PACKAGE_UNVERIFIABLE',
  'APPROVAL_EVIDENCE_PACKAGE_VERSION_UNSUPPORTED',
  'APPROVAL_EVIDENCE_PACKAGE_WITHDRAWN',
  'APPROVAL_GRANT_ALREADY_ACTIVE',
  'APPROVAL_GRANT_ALREADY_REVOKED',
  'APPROVAL_GRANT_AMBIGUOUS',
  'APPROVAL_GRANT_AUDIT_INVALID',
  'APPROVAL_GRANT_COMMAND_INVALID',
  'APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN',
  'APPROVAL_GRANT_IDEMPOTENCY_CONFLICT',
  'APPROVAL_GRANT_MANAGER_REQUIRED',
  'APPROVAL_GRANT_NOT_FOUND',
  'APPROVAL_GRANT_REQUIRED',
  'APPROVAL_GRANT_REVOCATION_REASON_REQUIRED',
  'APPROVAL_GRANT_SCOPE_MISMATCH',
  'APPROVAL_GRANT_SCOPE_NOT_FOUND',
  'APPROVAL_GRANT_STALE',
  'APPROVAL_GRANT_SUBJECT_INVALID',
  'APPROVAL_GRANT_TTL_INVALID',
  'APPROVAL_HARD_GATES_NOT_PASS',
  'APPROVAL_IDEMPOTENCY_CONFLICT',
  'APPROVAL_IDEMPOTENCY_KEY_REQUIRED',
  'APPROVAL_IDEMPOTENCY_OR_EVIDENCE_INVALID',
  'APPROVAL_POLICY_MATERIAL_MISMATCH',
  'APPROVAL_POLICY_SCOPE_MISMATCH',
  'APPROVAL_POLICY_UNSUPPORTED',
  'APPROVAL_REASON_REQUIRED',
  'APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN',
  'APPROVAL_REQUEST_EVIDENCE_MISMATCH',
  'APPROVAL_REQUEST_EXPIRED',
  'APPROVAL_REQUEST_IDEMPOTENCY_CONFLICT',
  'APPROVAL_REQUEST_NOT_FOUND',
  'APPROVAL_REQUEST_NOT_PENDING',
  'APPROVAL_REQUEST_REQUIRED',
  'APPROVAL_RISK_ACKNOWLEDGEMENT_INVALID',
  'APPROVAL_RISK_ACKNOWLEDGEMENT_REQUIRED',
  'APPROVAL_SCOPE_NOT_FOUND',
  'APPROVAL_SEPARATION_REQUIRED',
] as const

const APPROVAL_INTERNAL_ERROR_CODES = [
  'APPROVAL_DATABASE_CLOCK_INVALID',
  'APPROVAL_DECISION_EVIDENCE_MISMATCH',
  'APPROVAL_DECISION_INTENT_INVALID',
  'APPROVAL_DENIAL_FENCE_CONFLICT',
  'APPROVAL_MACHINE_EVIDENCE_INCOMPLETE',
  'APPROVAL_POLICY_CATALOG_INVALID',
  'APPROVAL_REQUEST_TRANSITION_INVALID',
] as const

function context(overrides: Record<string, unknown> = {}): AiResearchApprovalContext {
  const projected = projectAiResearchApprovalContext(approvalContextFixture(overrides))
  if (projected === null) throw new Error('bad approval fixture')
  return projected
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function apiMock() {
  return {
    getTrustedAIResearchApprovalContext: vi.fn(),
    requestTrustedAIResearchApproval: vi.fn(),
    decideTrustedAIResearchApproval: vi.fn(),
  }
}

function contextWithUnrelatedRequest(): AiResearchApprovalContext {
  const raw = approvalContextFixture()
  const gateHash = 'f'.repeat(64)
  const packageHash = '1'.repeat(64)
  raw.current_request = approvalRequestFixture({
    id: 'approval-request-unrelated',
    evidence_package_id: 'package-unrelated',
    gate_input_evidence_hash: gateHash,
    evidence_package_hash: packageHash,
  })
  raw.machine_evidence_summary.package = {
    ...raw.machine_evidence_summary.package,
    id: 'package-unrelated',
    gate_input_evidence_hash: gateHash,
    manifest_hash: packageHash,
  }
  raw.machine_evidence_summary.gates = raw.machine_evidence_summary.gates.map((gate) => ({
    ...gate,
    input_evidence_hash: gateHash,
  }))
  const projected = projectAiResearchApprovalContext(raw)
  if (projected === null) throw new Error('bad unrelated request fixture')
  return projected
}

describe('useAiResearchApproval', () => {
  it('keeps approval authority policy separate from the promotion evidence policy', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(ownerContext)
      .mockResolvedValueOnce(context())
    api.requestTrustedAIResearchApproval.mockResolvedValueOnce(approvalRequestFixture())
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    expect(ownerContext.policy_version).toBe(APPROVAL_POLICY_VERSION)
    expect(ownerContext.machine_evidence_summary?.package.promotion_policy_version)
      .toBe(PROMOTION_POLICY_VERSION)
    expect(APPROVAL_POLICY_VERSION).not.toBe(PROMOTION_POLICY_VERSION)
    await expect(runtime.requestApproval()).resolves.toMatchObject({
      policy_version: APPROVAL_POLICY_VERSION,
    })
    expect(api.requestTrustedAIResearchApproval).toHaveBeenCalledTimes(1)
  })

  it('isolates late context responses when run and candidate selection changes', async () => {
    const api = apiMock()
    const first = deferred<AiResearchApprovalContext>()
    const second = deferred<AiResearchApprovalContext>()
    api.getTrustedAIResearchApprovalContext
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const runtime = useAiResearchApproval({ api })

    const firstLoad = runtime.select('run-a', 'candidate-a')
    const firstSignal = api.getTrustedAIResearchApprovalContext.mock.calls[0]?.[2]
    const secondLoad = runtime.select('run-1', 'candidate-1')
    second.resolve(context())
    await secondLoad
    first.resolve(context())
    await firstLoad

    expect(firstSignal?.aborted).toBe(true)
    expect(runtime.activeRunId.value).toBe('run-1')
    expect(runtime.activeCandidateId.value).toBe('candidate-1')
    expect(runtime.context.value?.candidate_id).toBe('candidate-1')
    expect(runtime.loading.value).toBe(false)
  })

  it('reuses the exact request idempotency key after an ambiguous 5xx ACK loss', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(ownerContext)
    api.requestTrustedAIResearchApproval
      .mockRejectedValueOnce({
        response: {
          status: 503,
          data: { detail: { code: 'APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN' } },
        },
      })
      .mockResolvedValueOnce(approvalRequestFixture())
    const keyFactory = vi.fn()
      .mockReturnValueOnce('request-key-1')
      .mockReturnValueOnce('request-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')

    await expect(runtime.requestApproval()).resolves.toBeNull()
    expect(runtime.errorCode.value).toBe('APPROVAL_REQUEST_COMMIT_OUTCOME_UNKNOWN')
    expect(api.getTrustedAIResearchApprovalContext).toHaveBeenCalledTimes(2)
    await expect(runtime.requestApproval()).resolves.toMatchObject({ id: 'approval-request-1' })
    expect(runtime.requesting.value).toBe(false)

    const calls = api.requestTrustedAIResearchApproval.mock.calls
    expect(calls[0]?.[3]).toBe('request-key-1')
    expect(calls[1]?.[3]).toBe('request-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
    const body = calls[0]?.[2] as AiResearchApprovalRequestCreate
    expect(body).toEqual({
      gate_input_evidence_hash: APPROVAL_HASHES.gate,
      evidence_package_hash: APPROVAL_HASHES.package,
    })
    for (const forbidden of ['actor_id', 'policy', 'mode', 'permissions', 'now']) {
      expect(body).not.toHaveProperty(forbidden)
    }
  })

  it('aborts and settles an in-flight request on refresh while preserving its exact key', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    const pendingMutation = deferred<ReturnType<typeof approvalRequestFixture>>()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(ownerContext)
    api.requestTrustedAIResearchApproval
      .mockReturnValueOnce(pendingMutation.promise)
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn().mockReturnValueOnce('request-key-1').mockReturnValueOnce('request-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')

    const request = runtime.requestApproval()
    await vi.waitFor(() => expect(api.requestTrustedAIResearchApproval).toHaveBeenCalledTimes(1))
    const signal = api.requestTrustedAIResearchApproval.mock.calls[0]?.[4]
    const refresh = runtime.refresh()

    expect(signal?.aborted).toBe(true)
    expect(runtime.requesting.value).toBe(false)
    expect(runtime.loading.value).toBe(true)
    await refresh
    pendingMutation.reject(new DOMException('aborted', 'AbortError'))
    await request
    await runtime.requestApproval()

    expect(api.requestTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('request-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
  })

  it('aborts and settles an in-flight decision on refresh while preserving its exact key', async () => {
    const api = apiMock()
    const reviewerContext = context()
    const pendingMutation = deferred<ReturnType<typeof approvalDecisionFixture>>()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(reviewerContext)
    api.decideTrustedAIResearchApproval
      .mockReturnValueOnce(pendingMutation.promise)
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn().mockReturnValueOnce('decision-key-1').mockReturnValueOnce('decision-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')
    const input = {
      decision: 'APPROVED' as const,
      reason: 'Reviewed all thirteen server-bound gates.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    }

    const decision = runtime.submitDecision(input)
    await vi.waitFor(() => expect(api.decideTrustedAIResearchApproval).toHaveBeenCalledTimes(1))
    const signal = api.decideTrustedAIResearchApproval.mock.calls[0]?.[4]
    const refresh = runtime.refresh()

    expect(signal?.aborted).toBe(true)
    expect(runtime.deciding.value).toBe(false)
    expect(runtime.loading.value).toBe(true)
    await refresh
    pendingMutation.reject(new DOMException('aborted', 'AbortError'))
    await decision
    await runtime.submitDecision(input)

    expect(api.decideTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('decision-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
  })

  it('fails closed and preserves the key when a 2xx request receipt mismatches the intent', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(ownerContext)
    api.requestTrustedAIResearchApproval
      .mockResolvedValueOnce(approvalRequestFixture({ evidence_package_hash: 'f'.repeat(64) }))
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn().mockReturnValueOnce('request-key-1').mockReturnValueOnce('request-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')

    await expect(runtime.requestApproval()).resolves.toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_RESPONSE_MISMATCH')
    expect(api.getTrustedAIResearchApprovalContext).toHaveBeenCalledTimes(2)
    await runtime.requestApproval()

    expect(api.requestTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('request-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
  })

  it('fails closed and preserves the key when a 2xx decision receipt mismatches the intent', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context())
    api.decideTrustedAIResearchApproval
      .mockResolvedValueOnce(approvalDecisionFixture({
        decision_intent_hash: '8'.repeat(64),
      }))
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn().mockReturnValueOnce('decision-key-1').mockReturnValueOnce('decision-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')
    const input = {
      decision: 'APPROVED' as const,
      reason: 'Reviewed all thirteen server-bound gates.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    }

    await expect(runtime.submitDecision(input)).resolves.toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_RESPONSE_MISMATCH')
    expect(api.getTrustedAIResearchApprovalContext).toHaveBeenCalledTimes(2)
    await runtime.submitDecision(input)

    expect(api.decideTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('decision-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
  })

  it('accepts an exact decision intent when the safe server reason is redacted', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      required_challenge_keys: ['review_note'],
    }))
    api.decideTrustedAIResearchApproval.mockResolvedValue(approvalDecisionFixture({
      decision: 'REJECTED',
      reason: '[REDACTED]',
      decision_intent_hash: '9a7625abb246b19eb95c3cf90f468184eb0b0d1041ab2e0840028a7d791fa6c2',
    }))
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    const receipt = await runtime.submitDecision({
      decision: 'REJECTED',
      reason: ' see s3://private-bucket/raw and SEALED_METRICS_MUST_NOT_ESCAPE ',
      challengeResponses: { review_note: 'ignored for a negative decision' },
      residualRiskAcknowledgement: 'ignored for a negative decision',
    })

    expect(receipt?.id).toBe('approval-decision-1')
    expect(receipt?.reason).toBe('[REDACTED]')
    expect(runtime.errorCode.value).toBeNull()
  })

  it.each([
    ['challenge answer', '90efc2ac8fa7ccd56ba5afe1f1efe9a9fdc9860784c965850bd008cf701b4b6a'],
    ['risk acknowledgement', '67eb270986cd83517a9de3f3fcc7be132befb95e6f186a2540971e8afe0652cd'],
  ])('rejects a receipt with the same public shape but a different %s', async (_label, driftHash) => {
    const api = apiMock()
    const requestId = '33333333-3333-3333-3333-333333333333'
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      approval_mode: 'single_actor',
      required_challenge_keys: ['execution_risk', 'model_risk'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({
        id: requestId,
        approval_mode: 'single_actor',
      }),
    }))
    api.decideTrustedAIResearchApproval.mockResolvedValue(approvalDecisionFixture({
      approval_request_id: requestId,
      approval_mode: 'single_actor',
      reason: '已复核模型与执行风险',
      challenge_keys: ['execution_risk', 'model_risk'],
      risk_acknowledgement: true,
      decision_intent_hash: driftHash,
    }))
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    const receipt = await runtime.submitDecision({
      decision: 'APPROVED',
      reason: '  已复核模型与执行风险  ',
      challengeResponses: {
        model_risk: '  模型风险已核验  ',
        execution_risk: ' 执行风险已核验 ',
      },
      residualRiskAcknowledgement: '  我接受剩余风险  ',
    })

    expect(receipt).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_RESPONSE_MISMATCH')
  })

  it('never exposes arbitrary server detail, message, error, or Error.message text', async () => {
    const unsafeErrors = [
      { response: { status: 500, data: { detail: 'file:///private/sealed-manifest.json' } } },
      { response: { status: 500, data: { message: '/srv/research/internal.sqlite' } } },
      { response: { status: 500, data: { error: 's3://private-bucket/raw-holdout' } } },
      new Error('/Users/operator/.secrets/approval-token'),
      { response: { status: 500, data: { detail: { code: 'APPROVAL_INTERNAL_SECRET_PATH' } } } },
    ]

    for (const unsafeError of unsafeErrors) {
      const api = apiMock()
      api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce(unsafeError)
      const runtime = useAiResearchApproval({ api })

      await runtime.select('run-1', 'candidate-1')

      expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_OPERATION_FAILED')
    }

    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce({
      response: { status: 409, data: { detail: { code: 'APPROVAL_REQUEST_EXPIRED' } } },
    })
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')
    expect(runtime.errorCode.value).toBe('APPROVAL_REQUEST_EXPIRED')
  })

  it.each(APPROVAL_PUBLIC_ERROR_CODES)(
    'accepts the exact public approval error catalog code %s',
    async (code) => {
      const api = apiMock()
      api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce({
        response: { status: 409, data: { details: { code } } },
      })
      const runtime = useAiResearchApproval({ api })

      await runtime.select('run-1', 'candidate-1')

      expect(runtime.errorCode.value).toBe(code)
    },
  )

  it.each(APPROVAL_INTERNAL_ERROR_CODES)(
    'rejects internal approval error code %s',
    async (code) => {
      const api = apiMock()
      api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce({
        response: { status: 409, data: { details: { code } } },
      })
      const runtime = useAiResearchApproval({ api })

      await runtime.select('run-1', 'candidate-1')

      expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_OPERATION_FAILED')
    },
  )

  it.each([
    'APPROVAL_PRIVATE_INTERNAL',
    'APPROVAL_DECISION_INVALID:private',
    'APPROVAL_CHALLENGE_INVALID:model_risk',
  ])('rejects unknown or unauthorized dynamic approval error code %s', async (code) => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce({
      response: { status: 409, data: { details: { code } } },
    })
    const runtime = useAiResearchApproval({ api })

    await runtime.select('run-1', 'candidate-1')

    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_OPERATION_FAILED')
  })

  it('normalizes only the challenge-incomplete suffix without echoing its keys', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce({
      response: {
        status: 422,
        data: { details: { code: 'APPROVAL_CHALLENGE_INCOMPLETE:model_risk,secret' } },
      },
    })
    const runtime = useAiResearchApproval({ api })

    await runtime.select('run-1', 'candidate-1')

    expect(runtime.errorCode.value).toBe('APPROVAL_CHALLENGE_INCOMPLETE')
    expect(runtime.errorCode.value).not.toContain('model_risk')
    expect(runtime.errorCode.value).not.toContain('secret')
  })

  it('fails closed when current and legacy error envelopes disagree', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          details: { code: 'APPROVAL_REQUEST_EXPIRED' },
          detail: { code: 'APPROVAL_REASON_REQUIRED' },
        },
      },
    })
    const runtime = useAiResearchApproval({ api })

    await runtime.select('run-1', 'candidate-1')

    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_OPERATION_FAILED')
  })

  it('recovers an applied approval request through exact context readback after ACK loss', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(ownerContext)
      .mockResolvedValueOnce(context())
    api.requestTrustedAIResearchApproval.mockRejectedValueOnce(
      new TypeError('connection closed after commit'),
    )
    const runtime = useAiResearchApproval({ api, keyFactory: () => 'request-key-1' })
    await runtime.select('run-1', 'candidate-1')

    const recovered = await runtime.requestApproval()

    expect(recovered?.id).toBe('approval-request-1')
    expect(runtime.context.value?.current_request?.id).toBe('approval-request-1')
    expect(runtime.errorCode.value).toBeNull()
    expect(api.requestTrustedAIResearchApproval).toHaveBeenCalledTimes(1)
  })

  it('discards a request intent after any deterministic 4xx response', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    }))
    api.requestTrustedAIResearchApproval
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn()
      .mockReturnValueOnce('request-key-1')
      .mockReturnValueOnce('request-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')

    await runtime.requestApproval()
    await runtime.requestApproval()

    expect(api.requestTrustedAIResearchApproval.mock.calls[0]?.[3]).toBe('request-key-1')
    expect(api.requestTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('request-key-2')
  })

  it('does not clear an uncertain request key when reconciliation sees an unrelated request', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(ownerContext)
      .mockResolvedValueOnce(contextWithUnrelatedRequest())
      .mockResolvedValueOnce(ownerContext)
    api.requestTrustedAIResearchApproval
      .mockRejectedValueOnce(new TypeError('ACK lost'))
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn()
      .mockReturnValueOnce('request-key-1')
      .mockReturnValueOnce('request-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')

    await runtime.requestApproval()
    await runtime.refresh()
    await runtime.requestApproval()

    expect(api.requestTrustedAIResearchApproval.mock.calls[0]?.[3]).toBe('request-key-1')
    expect(api.requestTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('request-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
  })

  it('uses a new request key when the server-selected package identity drifts', async () => {
    const api = apiMock()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    const driftedContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
      machine_evidence_summary: {
        ...ownerContext.machine_evidence_summary!,
        package: {
          ...ownerContext.machine_evidence_summary!.package,
          id: 'package-2',
        },
      },
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(ownerContext)
      .mockResolvedValueOnce(driftedContext)
    api.requestTrustedAIResearchApproval
      .mockRejectedValueOnce(new TypeError('ACK lost'))
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn()
      .mockReturnValueOnce('request-key-1')
      .mockReturnValueOnce('request-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')

    await runtime.requestApproval()
    await runtime.requestApproval()

    expect(api.requestTrustedAIResearchApproval.mock.calls[0]?.[3]).toBe('request-key-1')
    expect(api.requestTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('request-key-2')
    expect(keyFactory).toHaveBeenCalledTimes(2)
  })

  it('builds a decision only from the current server request and reuses its key after ACK loss', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context())
    api.decideTrustedAIResearchApproval
      .mockRejectedValueOnce(new TypeError('network disconnected after commit'))
      .mockResolvedValueOnce(approvalDecisionFixture())
    const keyFactory = vi.fn().mockReturnValue('decision-key-1')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')
    const input = {
      decision: 'APPROVED' as const,
      reason: 'Reviewed all thirteen server-bound gates.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    }

    await expect(runtime.submitDecision(input)).resolves.toBeNull()
    await expect(runtime.submitDecision(input)).resolves.toMatchObject({ id: 'approval-decision-1' })
    expect(runtime.deciding.value).toBe(false)

    const calls = api.decideTrustedAIResearchApproval.mock.calls
    expect(calls[0]?.[3]).toBe('decision-key-1')
    expect(calls[1]?.[3]).toBe('decision-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
    const body = calls[0]?.[2] as AiResearchApprovalDecisionCreate
    expect(body).toEqual({
      approval_request_id: 'approval-request-1',
      decision: 'APPROVED',
      reason: input.reason,
      gate_input_evidence_hash: APPROVAL_HASHES.gate,
      evidence_package_hash: APPROVAL_HASHES.package,
      challenge_responses: {},
      residual_risk_acknowledgement: null,
    })
  })

  it('recovers an applied exact decision from latest-decision context after ACK loss', async () => {
    const api = apiMock()
    const decidedContext = context({
      can_decide: false,
      decision_blocked_reason: 'REQUEST_REQUIRED',
      current_request: null,
      latest_decision: approvalDecisionFixture(),
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(context())
      .mockResolvedValueOnce(decidedContext)
    api.decideTrustedAIResearchApproval.mockRejectedValueOnce(new TypeError('ACK lost'))
    const runtime = useAiResearchApproval({ api, keyFactory: () => 'decision-key-1' })
    await runtime.select('run-1', 'candidate-1')

    const recovered = await runtime.submitDecision({
      decision: 'APPROVED',
      reason: 'Reviewed all thirteen server-bound gates.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    })

    expect(recovered?.id).toBe('approval-decision-1')
    expect(runtime.context.value?.latest_decision?.id).toBe('approval-decision-1')
    expect(runtime.errorCode.value).toBeNull()
    expect(api.decideTrustedAIResearchApproval).toHaveBeenCalledTimes(1)
  })

  it('keeps an uncertain decision key when latest decision has unrelated semantics', async () => {
    const api = apiMock()
    const reviewerContext = context()
    const unrelated = context({
      latest_decision: approvalDecisionFixture({
        id: 'approval-decision-unrelated',
        approval_request_id: 'approval-request-unrelated',
        decision: 'REJECTED',
        reason: 'An unrelated reviewer decision.',
      }),
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(reviewerContext)
      .mockResolvedValueOnce(unrelated)
      .mockResolvedValueOnce(reviewerContext)
    api.decideTrustedAIResearchApproval
      .mockRejectedValueOnce(new TypeError('ACK lost'))
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn()
      .mockReturnValueOnce('decision-key-1')
      .mockReturnValueOnce('decision-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')
    const input = {
      decision: 'APPROVED' as const,
      reason: 'Reviewed all thirteen server-bound gates.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    }

    await runtime.submitDecision(input)
    await runtime.refresh()
    await runtime.submitDecision(input)

    expect(api.decideTrustedAIResearchApproval.mock.calls[0]?.[3]).toBe('decision-key-1')
    expect(api.decideTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('decision-key-1')
    expect(keyFactory).toHaveBeenCalledTimes(1)
  })

  it('uses a new decision key when the exact server request material drifts', async () => {
    const api = apiMock()
    const driftedContext = context({
      current_request: approvalRequestFixture({
        request_material_hash: '5'.repeat(64),
      }),
    })
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(context())
      .mockResolvedValueOnce(driftedContext)
    api.decideTrustedAIResearchApproval
      .mockRejectedValueOnce(new TypeError('ACK lost'))
      .mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'CONFLICT' } } } })
    const keyFactory = vi.fn()
      .mockReturnValueOnce('decision-key-1')
      .mockReturnValueOnce('decision-key-2')
    const runtime = useAiResearchApproval({ api, keyFactory })
    await runtime.select('run-1', 'candidate-1')
    const input = {
      decision: 'APPROVED' as const,
      reason: 'Reviewed all thirteen server-bound gates.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    }

    await runtime.submitDecision(input)
    await runtime.submitDecision(input)

    expect(api.decideTrustedAIResearchApproval.mock.calls[0]?.[3]).toBe('decision-key-1')
    expect(api.decideTrustedAIResearchApproval.mock.calls[1]?.[3]).toBe('decision-key-2')
    expect(keyFactory).toHaveBeenCalledTimes(2)
  })

  it('allows a negative decision with a reason without approval-only challenges or risk text', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      approval_mode: 'single_actor',
      required_challenge_keys: ['candidate_hash', 'gate_hash'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({ approval_mode: 'single_actor' }),
    }))
    api.decideTrustedAIResearchApproval.mockResolvedValue(approvalDecisionFixture({
      decision: 'REJECTED',
      approval_mode: 'single_actor',
    }))
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    await runtime.submitDecision({
      decision: 'REJECTED',
      reason: 'The evidence is insufficient.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    })

    expect(api.decideTrustedAIResearchApproval).toHaveBeenCalledWith(
      'run-1',
      'candidate-1',
      expect.objectContaining({
        decision: 'REJECTED',
        reason: 'The evidence is insufficient.',
        challenge_responses: {},
        residual_risk_acknowledgement: null,
      }),
      expect.any(String),
      expect.anything(),
    )
  })

  it('enforces server can_approve only for approval while retaining negative-decision authority', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      can_request: false,
      request_blocked_reason: 'APPROVAL_EVIDENCE_DENIED',
      can_decide: true,
      can_approve: false,
      decision_blocked_reason: null,
    }))
    api.decideTrustedAIResearchApproval.mockRejectedValue({
      response: { status: 409, data: { detail: { code: 'APPROVAL_IDEMPOTENCY_CONFLICT' } } },
    })
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    await runtime.submitDecision({
      decision: 'APPROVED',
      reason: 'Reviewed.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    })
    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_APPROVE_NOT_ALLOWED')
    expect(api.decideTrustedAIResearchApproval).not.toHaveBeenCalled()

    await runtime.submitDecision({
      decision: 'REJECTED',
      reason: 'Evidence is denied.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    })
    expect(api.decideTrustedAIResearchApproval).toHaveBeenCalledTimes(1)

    await runtime.submitDecision({
      decision: 'REQUESTED_CHANGES',
      reason: 'Evidence package must be replaced.',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    })
    expect(api.decideTrustedAIResearchApproval).toHaveBeenCalledTimes(2)
    expect(api.decideTrustedAIResearchApproval.mock.calls[1]?.[2]).toMatchObject({
      decision: 'REQUESTED_CHANGES',
      reason: 'Evidence package must be replaced.',
    })
  })

  it('ignores a late ambiguous-ACK reconciliation after the selected scope changes', async () => {
    const api = apiMock()
    const oldOwner = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    const reconcile = deferred<AiResearchApprovalContext>()
    const nextContext = projectAiResearchApprovalContext(
      approvalContextFor('run-2', 'candidate-2'),
    )!
    api.getTrustedAIResearchApprovalContext
      .mockResolvedValueOnce(oldOwner)
      .mockReturnValueOnce(reconcile.promise)
      .mockResolvedValueOnce(nextContext)
    api.requestTrustedAIResearchApproval.mockRejectedValueOnce(new TypeError('ACK lost'))
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    const request = runtime.requestApproval()
    await vi.waitFor(() => {
      expect(api.getTrustedAIResearchApprovalContext).toHaveBeenCalledTimes(2)
    })
    const reconcileSignal = api.getTrustedAIResearchApprovalContext.mock.calls[1]?.[2]
    await runtime.select('run-2', 'candidate-2')
    reconcile.resolve(context())
    await request

    expect(reconcileSignal?.aborted).toBe(true)
    expect(runtime.activeRunId.value).toBe('run-2')
    expect(runtime.context.value?.candidate_id).toBe('candidate-2')
  })

  it('fails closed on missing permission, reason, challenges, risk acknowledgement, or evidence', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      can_decide: false,
      decision_blocked_reason: 'COOLDOWN_ACTIVE',
    }))
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')
    await runtime.submitDecision({
      decision: 'APPROVED',
      reason: 'reviewed',
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    })
    expect(runtime.errorCode.value).toBe('COOLDOWN_ACTIVE')
    expect(api.decideTrustedAIResearchApproval).not.toHaveBeenCalled()

    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      approval_mode: 'single_actor',
      required_challenge_keys: ['candidate_hash', 'gate_hash'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({ approval_mode: 'single_actor' }),
    }))
    await runtime.select('run-1', 'candidate-1')
    await runtime.submitDecision({
      decision: 'APPROVED',
      reason: ' ',
      challengeResponses: { candidate_hash: 'ok' },
      residualRiskAcknowledgement: null,
    })
    expect(runtime.errorCode.value).toBe('RESEARCH_APPROVAL_REASON_REQUIRED')
    expect(api.decideTrustedAIResearchApproval).not.toHaveBeenCalled()
  })

  it.each([
    {
      label: 'reason',
      input: {
        reason: '\u0085',
        challengeResponses: { candidate_hash: 'verified' },
        residualRiskAcknowledgement: 'accepted',
      },
      errorCode: 'RESEARCH_APPROVAL_REASON_REQUIRED',
    },
    {
      label: 'challenge response',
      input: {
        reason: 'reviewed',
        challengeResponses: { candidate_hash: '\u0085' },
        residualRiskAcknowledgement: 'accepted',
      },
      errorCode: 'RESEARCH_APPROVAL_CHALLENGES_REQUIRED',
    },
    {
      label: 'risk acknowledgement',
      input: {
        reason: 'reviewed',
        challengeResponses: { candidate_hash: 'verified' },
        residualRiskAcknowledgement: '\u0085',
      },
      errorCode: 'RESEARCH_APPROVAL_RISK_ACKNOWLEDGEMENT_REQUIRED',
    },
  ])('uses Python strip semantics for approval $label validation', async ({ input, errorCode }) => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      approval_mode: 'single_actor',
      required_challenge_keys: ['candidate_hash'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({ approval_mode: 'single_actor' }),
    }))
    api.decideTrustedAIResearchApproval.mockResolvedValue(approvalDecisionFixture())
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    await runtime.submitDecision({ decision: 'APPROVED', ...input })

    expect(runtime.errorCode.value).toBe(errorCode)
    expect(api.decideTrustedAIResearchApproval).not.toHaveBeenCalled()
  })

  it('honors the independent request deny fence without consulting decision authority', async () => {
    const api = apiMock()
    api.getTrustedAIResearchApprovalContext.mockResolvedValue(context({
      can_request: false,
      request_blocked_reason: 'APPROVAL_EVIDENCE_DENIED',
      can_decide: false,
      decision_blocked_reason: 'REQUEST_REQUIRED',
      current_request: null,
    }))
    const runtime = useAiResearchApproval({ api })
    await runtime.select('run-1', 'candidate-1')

    await runtime.requestApproval()

    expect(runtime.errorCode.value).toBe('APPROVAL_EVIDENCE_DENIED')
    expect(api.requestTrustedAIResearchApproval).not.toHaveBeenCalled()
  })

  it('aborts in-flight work and clears selection on dispose', async () => {
    const api = apiMock()
    const pending = deferred<AiResearchApprovalContext>()
    api.getTrustedAIResearchApprovalContext.mockReturnValue(pending.promise)
    const runtime = useAiResearchApproval({ api })
    void runtime.select('run-1', 'candidate-1')
    const signal = api.getTrustedAIResearchApprovalContext.mock.calls[0]?.[2]

    runtime.dispose()

    expect(signal?.aborted).toBe(true)
    expect(runtime.activeRunId.value).toBeNull()
    expect(runtime.activeCandidateId.value).toBeNull()
    expect(runtime.context.value).toBeNull()
  })
})
