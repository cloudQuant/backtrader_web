import { AI_RESEARCH_APPROVAL_GATE_CODES } from '@/types/aiResearchV2'

export const APPROVAL_HASHES = {
  gate: 'a'.repeat(64),
  package: 'b'.repeat(64),
  policy: 'c'.repeat(64),
  candidate: 'd'.repeat(64),
  binding: 'e'.repeat(64),
  requestMaterial: '6'.repeat(64),
  decisionMaterial: '7'.repeat(64),
  decisionIntent: '71a6201ce64d921bf408593c58bcc47e12a7a55762cfeae11d1233d3a44a8b05',
} as const

export const APPROVAL_POLICY_VERSION = 'approval-multi-v2'
export const PROMOTION_POLICY_VERSION = 'promotion-v1'

export function approvalRequestFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 'approval-request-1',
    run_id: 'run-1',
    candidate_id: 'candidate-1',
    evidence_package_id: 'package-1',
    policy_version: APPROVAL_POLICY_VERSION,
    policy_material_hash: APPROVAL_HASHES.policy,
    approval_mode: 'multi_actor',
    gate_input_evidence_hash: APPROVAL_HASHES.gate,
    evidence_package_hash: APPROVAL_HASHES.package,
    request_material_hash: APPROVAL_HASHES.requestMaterial,
    status: 'PENDING',
    requested_at: '2026-09-08T00:00:00Z',
    eligible_at: '2026-09-08T00:00:00Z',
    expires_at: '2026-09-08T01:00:00Z',
    decided_at: null,
    actor_id: 'must-not-cross-browser-boundary',
    ...overrides,
  }
}

export function approvalDecisionFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 'approval-decision-1',
    run_id: 'run-1',
    candidate_id: 'candidate-1',
    approval_request_id: 'approval-request-1',
    decision: 'APPROVED',
    policy_version: APPROVAL_POLICY_VERSION,
    policy_material_hash: APPROVAL_HASHES.policy,
    approval_mode: 'multi_actor',
    gate_input_evidence_hash: APPROVAL_HASHES.gate,
    evidence_package_hash: APPROVAL_HASHES.package,
    decision_material_hash: APPROVAL_HASHES.decisionMaterial,
    decision_intent_hash: APPROVAL_HASHES.decisionIntent,
    risk_acknowledgement: false,
    challenge_keys: [],
    reason: 'Reviewed all thirteen server-bound gates.',
    decided_at: '2026-09-08T00:10:00Z',
    expires_at: '2026-09-08T01:00:00Z',
    grant_id: 'must-not-cross-browser-boundary',
    ...overrides,
  }
}

export function approvalContextFixture(overrides: Record<string, unknown> = {}) {
  const canDecide = 'can_decide' in overrides ? overrides.can_decide : true
  const canApprove = 'can_approve' in overrides ? overrides.can_approve : canDecide
  return {
    run_id: 'run-1',
    candidate_id: 'candidate-1',
    candidate_hash: APPROVAL_HASHES.candidate,
    policy_version: APPROVAL_POLICY_VERSION,
    policy_material_hash: APPROVAL_HASHES.policy,
    approval_mode: 'multi_actor',
    can_request: false,
    request_blocked_reason: 'OWNER_REQUIRED',
    can_decide: canDecide,
    can_approve: canApprove,
    decision_blocked_reason: null,
    cooldown_seconds: 0,
    required_challenge_keys: [],
    risk_acknowledgement_required: false,
    current_request: approvalRequestFixture(),
    latest_decision: null,
    machine_evidence_summary: {
      package: {
        id: 'package-1',
        candidate_id: 'candidate-1',
        status: 'ACTIVE',
        promotion_policy_version: PROMOTION_POLICY_VERSION,
        command_id: 'holdout-command-1',
        evaluation_id: 'holdout-evaluation-1',
        gate_input_evidence_hash: APPROVAL_HASHES.gate,
        manifest_hash: APPROVAL_HASHES.package,
        approval_binding_hash: APPROVAL_HASHES.binding,
        manifest: { sealed_metric: 99 },
        storage_uri: 's3://must-not-cross-browser-boundary',
      },
      gates: AI_RESEARCH_APPROVAL_GATE_CODES.map((gateCode) => ({
        gate_code: gateCode,
        status: 'PASS',
        reason_code: `HOLDOUT_${gateCode}_PASSED`,
        input_evidence_hash: APPROVAL_HASHES.gate,
        executor_version: 'gate-engine-v1',
        evaluated_at: '2026-09-08T00:05:00Z',
        metrics: { secret: 42 },
        gate_inputs: { secret: true },
      })),
      grant: { id: 'must-not-cross-browser-boundary' },
    },
    actor_id: 'must-not-cross-browser-boundary',
    domain_permissions: ['must-not-cross-browser-boundary'],
    now: '2999-01-01T00:00:00Z',
    ...overrides,
  }
}

export function approvalContextFor(
  runId: string,
  candidateId: string,
  overrides: Record<string, unknown> = {},
) {
  const value = approvalContextFixture()
  value.run_id = runId
  value.candidate_id = candidateId
  value.current_request = {
    ...value.current_request,
    run_id: runId,
    candidate_id: candidateId,
  }
  value.machine_evidence_summary = {
    ...value.machine_evidence_summary,
    package: {
      ...value.machine_evidence_summary.package,
      candidate_id: candidateId,
    },
  }
  return { ...value, ...overrides }
}
