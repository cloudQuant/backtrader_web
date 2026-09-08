import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/api/index'
import { strategyApi } from '@/api/strategy'
import {
  APPROVAL_HASHES,
  approvalContextFixture,
  approvalDecisionFixture,
  approvalRequestFixture,
} from '@/__tests__/fixtures/aiResearchApproval'
import type {
  AiResearchApprovalDecisionCreate,
  AiResearchApprovalRequestCreate,
} from '@/types/aiResearchV2'

vi.mock('@/api/index', () => ({
  default: { post: vi.fn(), get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

describe('strategyApi trusted approval boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('projects the reviewer context and strips all authority and sealed payload canaries', async () => {
    const signal = new AbortController().signal
    vi.mocked(api.get).mockResolvedValue(approvalContextFixture())

    const context = await strategyApi.getTrustedAIResearchApprovalContext(
      'run-1',
      'candidate-1',
      signal,
    )

    expect(api.get).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/runs/run-1/candidates/candidate-1/approval-context',
      { signal, suppressErrorToast: true },
    )
    expect(context.machine_evidence_summary?.gates).toHaveLength(13)
    const stored = JSON.stringify(context)
    for (const canary of [
      'sealed_metric',
      'storage_uri',
      'metrics',
      'gate_inputs',
      'grant',
      'actor_id',
      'domain_permissions',
      '2999-01-01',
    ]) expect(stored).not.toContain(canary)
  })

  it('creates a request with only package hashes and an idempotency key', async () => {
    const signal = new AbortController().signal
    vi.mocked(api.post).mockResolvedValue(approvalRequestFixture())

    const unsafeBody = {
      gate_input_evidence_hash: APPROVAL_HASHES.gate,
      evidence_package_hash: APPROVAL_HASHES.package,
      actor_id: 'forged-actor',
      approval_mode: 'single_actor',
      now: '2999-01-01T00:00:00Z',
    } as AiResearchApprovalRequestCreate
    const receipt = await strategyApi.requestTrustedAIResearchApproval(
      'run-1',
      'candidate-1',
      unsafeBody,
      'approval-request-key-1',
      signal,
    )

    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/runs/run-1/candidates/candidate-1/approval-requests',
      {
        gate_input_evidence_hash: APPROVAL_HASHES.gate,
        evidence_package_hash: APPROVAL_HASHES.package,
      },
      {
        headers: { 'Idempotency-Key': 'approval-request-key-1' },
        signal,
        suppressErrorToast: true,
      },
    )
    expect(receipt.id).toBe('approval-request-1')
    expect(receipt.request_material_hash).toBe(APPROVAL_HASHES.requestMaterial)
    expect(receipt).not.toHaveProperty('actor_id')
  })

  it('submits a decision without client-declared actor, policy, mode, permissions, or time', async () => {
    const signal = new AbortController().signal
    vi.mocked(api.post).mockResolvedValue(approvalDecisionFixture())
    const body = {
      approval_request_id: 'approval-request-1',
      decision: 'APPROVED' as const,
      reason: 'Reviewed all thirteen server-bound gates.',
      gate_input_evidence_hash: APPROVAL_HASHES.gate,
      evidence_package_hash: APPROVAL_HASHES.package,
      challenge_responses: {},
      residual_risk_acknowledgement: null,
      actor_id: 'forged-actor',
      policy: { mode: 'single_actor' },
      permissions: ['admin'],
      now: '2999-01-01T00:00:00Z',
    } as AiResearchApprovalDecisionCreate

    const receipt = await strategyApi.decideTrustedAIResearchApproval(
      'run-1',
      'candidate-1',
      body,
      'approval-decision-key-1',
      signal,
    )

    expect(api.post).toHaveBeenCalledWith(
      '/strategy/ai-research/v2/runs/run-1/candidates/candidate-1/approval-decisions',
      expect.objectContaining({
        approval_request_id: 'approval-request-1',
        decision: 'APPROVED',
      }),
      {
        headers: { 'Idempotency-Key': 'approval-decision-key-1' },
        signal,
        suppressErrorToast: true,
      },
    )
    const sent = vi.mocked(api.post).mock.calls[0]?.[1] as Record<string, unknown>
    for (const forbidden of ['actor_id', 'policy', 'approval_mode', 'permissions', 'now']) {
      expect(sent).not.toHaveProperty(forbidden)
    }
    expect(receipt).not.toHaveProperty('grant_id')
    expect(receipt.decision_material_hash).toBe(APPROVAL_HASHES.decisionMaterial)
    expect(receipt.decision_intent_hash).toBe(APPROVAL_HASHES.decisionIntent)
  })

  it.each([
    ['credential URI', 'ssh://reviewer:secret@internal/srv/sealed-results.json'],
    ['RFC data scheme', 'data:text/plain,private'],
    ['single-slash file scheme', 'file:/srv/research/private.sqlite'],
    ['punctuation-adjacent POSIX path', 'review,/srv/research/private.sqlite'],
    ['punctuation-adjacent Windows path', String.raw`review=C:\Users\operator\approval.txt`],
    ['Chinese-adjacent RFC data scheme', '请查data:text/plain,private'],
    ['Chinese-adjacent POSIX path', '请查/srv/research/private.sqlite'],
    ['Chinese-adjacent Windows path', String.raw`请查C:\Users\operator\approval.txt`],
    ['Chinese-adjacent UNC path', String.raw`请查\\fileserver\sealed\result.json`],
  ])('redacts an unsafe %s reason from the decision API response', async (_label, unsafeReason) => {
    vi.mocked(api.post).mockResolvedValue(approvalDecisionFixture({ reason: unsafeReason }))

    const receipt = await strategyApi.decideTrustedAIResearchApproval(
      'run-1',
      'candidate-1',
      {
        approval_request_id: 'approval-request-1',
        decision: 'REJECTED',
        reason: 'Evidence is insufficient.',
        gate_input_evidence_hash: APPROVAL_HASHES.gate,
        evidence_package_hash: APPROVAL_HASHES.package,
        challenge_responses: {},
        residual_risk_acknowledgement: null,
      },
      'approval-decision-key-unsafe-response',
    )

    expect(receipt.reason).toBe('[REDACTED]')
    expect(JSON.stringify(receipt)).not.toContain(unsafeReason)
  })

  it('fails closed when the server response is not the closed approval contract', async () => {
    vi.mocked(api.get).mockResolvedValue(approvalContextFixture({
      machine_evidence_summary: { gates: [] },
    }))
    vi.mocked(api.post).mockResolvedValueOnce(approvalRequestFixture({
      gate_input_evidence_hash: 'not-a-hash',
    }))

    await expect(
      strategyApi.getTrustedAIResearchApprovalContext('run-1', 'candidate-1'),
    ).rejects.toThrow('RESEARCH_APPROVAL_CONTEXT_INVALID')
    await expect(strategyApi.requestTrustedAIResearchApproval(
      'run-1',
      'candidate-1',
      {
        gate_input_evidence_hash: APPROVAL_HASHES.gate,
        evidence_package_hash: APPROVAL_HASHES.package,
      },
      'approval-request-key-2',
    )).rejects.toThrow('RESEARCH_APPROVAL_REQUEST_INVALID')
  })
})
