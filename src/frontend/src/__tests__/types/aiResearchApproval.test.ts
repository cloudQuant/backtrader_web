import { describe, expect, it } from 'vitest'

import {
  projectAiResearchApprovalContext,
  projectAiResearchApprovalDecision,
  projectAiResearchApprovalRequest,
} from '@/types/aiResearchV2'

const GATE_CODES = [
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

function approvalRequest() {
  return {
    id: 'request-1',
    run_id: 'run-1',
    candidate_id: 'candidate-1',
    evidence_package_id: 'package-1',
    policy_version: 'approval-multi-v2',
    policy_material_hash: 'a'.repeat(64),
    approval_mode: 'multi_actor',
    gate_input_evidence_hash: 'b'.repeat(64),
    evidence_package_hash: 'c'.repeat(64),
    request_material_hash: 'e'.repeat(64),
    status: 'PENDING',
    requested_at: '2026-09-08T00:00:00Z',
    eligible_at: '2026-09-08T00:00:00Z',
    expires_at: '2026-09-09T00:00:00Z',
    decided_at: null,
  }
}

function approvalDecision() {
  return {
    id: 'decision-1',
    run_id: 'run-1',
    candidate_id: 'candidate-1',
    approval_request_id: 'request-1',
    decision: 'APPROVED',
    policy_version: 'approval-multi-v2',
    policy_material_hash: 'a'.repeat(64),
    approval_mode: 'multi_actor',
    gate_input_evidence_hash: 'b'.repeat(64),
    evidence_package_hash: 'c'.repeat(64),
    decision_material_hash: 'f'.repeat(64),
    decision_intent_hash: '9'.repeat(64),
    risk_acknowledgement: false,
    challenge_keys: [],
    reason: 'Independent review completed.',
    decided_at: '2026-09-08T00:01:00Z',
    expires_at: '2026-09-09T00:00:00Z',
  }
}

function approvalContext() {
  return {
    run_id: 'run-1',
    candidate_id: 'candidate-1',
    candidate_hash: 'd'.repeat(64),
    policy_version: 'approval-multi-v2',
    policy_material_hash: 'a'.repeat(64),
    approval_mode: 'multi_actor',
    can_request: false,
    request_blocked_reason: 'OWNER_REQUIRED' as string | null,
    can_decide: true,
    can_approve: true,
    decision_blocked_reason: null as string | null,
    cooldown_seconds: 0,
    required_challenge_keys: [] as string[],
    risk_acknowledgement_required: false,
    current_request: approvalRequest() as ReturnType<typeof approvalRequest> | null,
    latest_decision: null,
    machine_evidence_summary: {
      package: {
        id: 'package-1',
        candidate_id: 'candidate-1',
        status: 'ACTIVE',
        promotion_policy_version: 'promotion-v1',
        command_id: 'command-1',
        evaluation_id: 'evaluation-1',
        gate_input_evidence_hash: 'b'.repeat(64),
        manifest_hash: 'c'.repeat(64),
        approval_binding_hash: 'e'.repeat(64),
        manifest: { sealed_metric: 99 },
        storage_uri: 'sealed://must-never-enter-browser-state',
      },
      gates: GATE_CODES.map((gateCode) => ({
        gate_code: gateCode as string,
        status: 'PASS',
        reason_code: `HOLDOUT_${gateCode}_PASSED`,
        input_evidence_hash: 'b'.repeat(64),
        executor_version: 'holdout-v2',
        evaluated_at: '2026-09-08T00:00:30Z',
        metrics: { sharpe: 99 },
        gate_inputs: { raw: 'must-never-enter-browser-state' },
      })),
      grant_id: 'must-never-enter-browser-state',
      domain_permissions: ['admin'],
    } as {
      package: Record<string, unknown>
      gates: Array<Record<string, unknown>>
      grant_id?: string
      domain_permissions?: string[]
    } | null,
    actor_id: 'must-never-enter-browser-state',
    now: '2099-01-01T00:00:00Z',
  }
}

describe('AI research approval browser contract', () => {
  it('projects a complete review context into an allowlisted closed shape', () => {
    const projected = projectAiResearchApprovalContext(approvalContext())

    expect(projected?.machine_evidence_summary?.gates).toHaveLength(13)
    expect(projected?.machine_evidence_summary?.package.evaluation_id).toBe('evaluation-1')
    expect(projected?.current_request?.id).toBe('request-1')
    const stored = JSON.stringify(projected)
    for (const prohibited of [
      '"manifest":',
      'metrics',
      'gate_inputs',
      'sealed_metric',
      'storage_uri',
      'grant_id',
      'domain_permissions',
      'actor_id',
      'must-never-enter-browser-state',
      '"now"',
    ]) expect(stored).not.toContain(prohibited)
  })

  it('requires server can_approve while keeping negative-decision authority distinct', () => {
    const fenced = approvalContext()
    fenced.can_approve = false

    expect(projectAiResearchApprovalContext(fenced)).toMatchObject({
      can_decide: true,
      can_approve: false,
    })

    const missing = approvalContext()
    delete (missing as Partial<ReturnType<typeof approvalContext>>).can_approve
    expect(projectAiResearchApprovalContext(missing)).toBeNull()

    const inconsistent = approvalContext()
    inconsistent.can_decide = false
    inconsistent.can_approve = true
    inconsistent.decision_blocked_reason = 'AUTHORITY_REQUIRED'
    expect(projectAiResearchApprovalContext(inconsistent)).toBeNull()
  })

  it.each([
    ['only twelve gates', (value: ReturnType<typeof approvalContext>) => {
      value.machine_evidence_summary?.gates.pop()
    }],
    ['a duplicate gate', (value: ReturnType<typeof approvalContext>) => {
      if (value.machine_evidence_summary) {
        value.machine_evidence_summary.gates[12].gate_code = 'CANDIDATE_FROZEN'
      }
    }],
    ['a non-stable gate reason', (value: ReturnType<typeof approvalContext>) => {
      if (value.machine_evidence_summary) {
        value.machine_evidence_summary.gates[0].reason_code = 'raw metric was 99.2'
      }
    }],
    ['a mismatched package', (value: ReturnType<typeof approvalContext>) => {
      if (value.machine_evidence_summary) {
        value.machine_evidence_summary.package.candidate_id = 'candidate-other'
      }
    }],
    ['a non-hex policy hash', (value: ReturnType<typeof approvalContext>) => {
      value.policy_material_hash = 'not-a-hash'
    }],
  ])('fails closed for %s', (_label, mutate) => {
    const value = approvalContext()
    mutate(value)

    expect(projectAiResearchApprovalContext(value)).toBeNull()
  })

  it('fails closed when a requestable owner context omits current machine evidence', () => {
    const value = approvalContext()
    value.can_request = true
    value.request_blocked_reason = null
    value.can_decide = false
    value.can_approve = false
    value.decision_blocked_reason = 'AUTHORITY_REQUIRED'
    value.current_request = null
    value.machine_evidence_summary = null

    const projected = projectAiResearchApprovalContext(value)

    expect(projected).toBeNull()
  })

  it('accepts a requestable owner context with the server-selected active evidence', () => {
    const value = approvalContext()
    value.can_request = true
    value.request_blocked_reason = null
    value.can_decide = false
    value.can_approve = false
    value.decision_blocked_reason = 'AUTHORITY_REQUIRED'
    value.current_request = null

    const projected = projectAiResearchApprovalContext(value)

    expect(projected?.can_request).toBe(true)
    expect(projected?.machine_evidence_summary?.package.id).toBe('package-1')
  })

  it('keeps the server deny fence separate from decision authority', () => {
    const value = approvalContext()
    value.current_request = null
    value.can_request = false
    value.request_blocked_reason = 'APPROVAL_EVIDENCE_DENIED'
    value.can_decide = false
    value.can_approve = false
    value.decision_blocked_reason = 'REQUEST_REQUIRED'

    const projected = projectAiResearchApprovalContext(value)

    expect(projected?.can_request).toBe(false)
    expect(projected?.request_blocked_reason).toBe('APPROVAL_EVIDENCE_DENIED')
    expect(projected?.can_decide).toBe(false)
  })

  it('maps unknown blocker text to one safe public code', () => {
    const value = approvalContext()
    value.can_request = false
    value.request_blocked_reason = 'file:///srv/research/private-manifest.json'
    value.can_decide = false
    value.can_approve = false
    value.decision_blocked_reason = '/Users/operator/.secrets/approval-token'

    const projected = projectAiResearchApprovalContext(value)

    expect(projected?.request_blocked_reason).toBe('RESEARCH_APPROVAL_BLOCKED')
    expect(projected?.decision_blocked_reason).toBe('RESEARCH_APPROVAL_BLOCKED')
    expect(JSON.stringify(projected)).not.toContain('/srv/research')
    expect(JSON.stringify(projected)).not.toContain('/Users/operator')
  })

  it('projects request and decision receipts without authority internals', () => {
    const request = projectAiResearchApprovalRequest({
      ...approvalRequest(),
      requested_by: 'must-never-enter-browser-state',
    })
    const decision = projectAiResearchApprovalDecision({
      ...approvalDecision(),
      actor_id: 'must-never-enter-browser-state',
      grant_hash: 'must-never-enter-browser-state',
    })

    expect(request?.id).toBe('request-1')
    expect(request?.request_material_hash).toBe('e'.repeat(64))
    expect(decision?.decision).toBe('APPROVED')
    expect(decision?.decision_material_hash).toBe('f'.repeat(64))
    expect(decision?.decision_intent_hash).toBe('9'.repeat(64))
    expect(JSON.stringify({ request, decision })).not.toContain('must-never-enter-browser-state')
  })

  it('rejects missing or malformed approval material hashes', () => {
    expect(projectAiResearchApprovalRequest({
      ...approvalRequest(),
      request_material_hash: 'NOT-A-SHA256',
    })).toBeNull()
    expect(projectAiResearchApprovalDecision({
      ...approvalDecision(),
      decision_intent_hash: 'A'.repeat(64),
    })).toBeNull()
  })

  it.each([
    ['arbitrary URI scheme', 'review ftp://internal.example/raw-result'],
    ['POSIX absolute path', 'review /srv/research/private.sqlite before approval'],
    ['Windows absolute path', String.raw`review C:\Users\operator\approval.txt`],
    ['UNC absolute path', String.raw`review \\fileserver\sealed\result.json`],
    ['credential URI', 'postgresql://reviewer:secret@db.internal/research'],
    ['userinfo without a URI scheme', 'review reviewer:secret@db.internal/research'],
    ['RFC data scheme', 'data:text/plain,private'],
    ['single-slash file scheme', 'file:/srv/research/private.sqlite'],
    ['punctuation-adjacent POSIX path', 'review,/srv/research/private.sqlite'],
    ['punctuation-adjacent Windows path', String.raw`review=C:\Users\operator\approval.txt`],
    ['Chinese-adjacent RFC data scheme', '请查data:text/plain,private'],
    ['Chinese-adjacent POSIX path', '请查/srv/research/private.sqlite'],
    ['Chinese-adjacent Windows path', String.raw`请查C:\Users\operator\approval.txt`],
    ['Chinese-adjacent UNC path', String.raw`请查\\fileserver\sealed\result.json`],
    ['sealed payload marker', 'SEALED_METRICS_MUST_NOT_ESCAPE'],
    ['raw payload marker', 'raw-holdout payload must not escape'],
  ])('redacts unsafe decision reason text containing %s', (_label, unsafeReason) => {
    const projected = projectAiResearchApprovalDecision({
      ...approvalDecision(),
      reason: unsafeReason,
    })

    expect(projected?.reason).toBe('[REDACTED]')
    expect(JSON.stringify(projected)).not.toContain(unsafeReason)
  })

  it.each([
    '已独立复核全部十三项门禁。',
    '说明：已独立复核，风险可接受。',
    '说明: 已独立复核，风险可接受。',
    '盘符 C: 仅为文字说明，不是绝对路径。',
    '请查 research/private.sqlite 和 reports\\approval.txt 相对路径。',
  ])('preserves bounded human review prose without unsafe text markers: %s', (reason) => {
    const projected = projectAiResearchApprovalDecision({
      ...approvalDecision(),
      reason,
    })

    expect(projected?.reason).toBe(reason)
  })
})
