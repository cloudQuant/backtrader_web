import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EvidencePanel from '@/components/aiResearch/EvidencePanel.vue'
import type {
  AiResearchV2EvaluationSummary,
  AiResearchV2EvidencePackageSummary,
  AiResearchV2HoldoutCommand,
} from '@/types/aiResearchV2'

function holdoutCommand(
  status: AiResearchV2HoldoutCommand['status'],
  overrides: Partial<AiResearchV2HoldoutCommand> = {},
): AiResearchV2HoldoutCommand {
  return {
    id: 'holdout-command-1',
    run_id: 'run-1',
    status,
    stage: status === 'QUEUED' || status === 'RECONCILING'
      ? 'REQUEST_HOLDOUT'
      : 'HOLDOUT_PENDING',
    candidate_id: 'candidate-1',
    candidate_hash: 'a'.repeat(64),
    experiment_epoch_id: 'epoch-1',
    dataset_snapshot_id: 'dataset-1',
    policy_version: 'promotion-v1',
    evaluator_identity: 'independent-evaluator',
    capability_profile_id: 'isolated-profile',
    capability_profile_version: 'v1',
    capability_evidence_hash: 'b'.repeat(64),
    error_code: null,
    request_hash: 'c'.repeat(64),
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    ...overrides,
  }
}

function evaluation(
  status: AiResearchV2EvaluationSummary['status'] = 'PASSED',
  overrides: Partial<AiResearchV2EvaluationSummary> = {},
): AiResearchV2EvaluationSummary {
  return {
    id: 'evaluation-1',
    experiment_epoch_id: 'epoch-1',
    candidate_id: 'candidate-1',
    dataset_snapshot_id: 'dataset-1',
    evaluation_type: 'SEALED_HOLDOUT',
    evaluator_identity: 'independent-evaluator',
    evaluator_version: 'v1',
    policy_version: 'promotion-v1',
    status,
    completed_at: '2026-09-08T00:00:02Z',
    ...overrides,
  }
}

describe('EvidencePanel', () => {
  it('shows safe model and evidence-package summaries without rendering controlled artifacts', () => {
    const wrapper = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_READY',
        gates: [],
        modelInvocations: [
          {
            id: 'invocation-1',
            provider: 'trusted-provider',
            requested_model: 'research-model',
            resolved_model: 'research-model-2026-09',
            prompt_template_version: 'prompt-v2',
            token_usage: { total_tokens: 42 },
            cost: { currency: 'USD', amount: 0.001 },
            error_code: null,
            created_at: '2026-09-05T00:00:00Z',
          },
        ],
        evidencePackages: [
          {
            id: 'package-1',
            candidate_id: 'candidate-1',
            command_id: null,
            evaluation_id: null,
            promotion_policy_version: 'promotion-v1',
            gate_input_evidence_hash: 'a'.repeat(64),
            manifest_hash: 'b'.repeat(64),
            approval_binding_hash: 'c'.repeat(64),
            status: 'ACTIVE',
            created_at: '2026-09-05T00:00:00Z',
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('模型调用谱系')
    expect(wrapper.text()).toContain('trusted-provider / research-model-2026-09')
    expect(wrapper.text()).toContain('prompt-v2')
    expect(wrapper.text()).toContain('证据包')
    expect(wrapper.text()).toContain('promotion-v1')
    expect(wrapper.text()).toContain('b'.repeat(64))
    expect(wrapper.text()).not.toContain('controlled://research-input/discovery.parquet')
    expect(wrapper.text()).not.toContain('raw-secret-manifest-content')
  })

  it('shows governance deviations as active limitations without calling them a pass', () => {
    const wrapper = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_PENDING',
        gates: [],
        governanceDecisions: [
          {
            id: 'governance-1',
            target_requirement_or_gate: 'NFR-PERF-001',
            original_status: 'BLOCKED',
            reason: 'A raw operator note that must not be rendered.',
            risk: 'A raw risk note that must not be rendered.',
            compensating_controls: ['A raw control that must not be rendered.'],
            effective_at: '2026-09-05T00:00:00Z',
            expires_at: '2026-09-12T00:00:00Z',
            revoked_at: null,
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('治理偏差')
    expect(wrapper.text()).toContain('NFR-PERF-001')
    expect(wrapper.text()).toContain('BLOCKED')
    expect(wrapper.text()).toContain('不会改变原硬门状态')
    expect(wrapper.text()).not.toContain('A raw operator note that must not be rendered.')
    expect(wrapper.text()).not.toContain('A raw risk note that must not be rendered.')
    expect(wrapper.text()).not.toContain('A raw control that must not be rendered.')
  })

  it('never renders evaluation or package canaries with ordinary metric names', () => {
    const wrapper = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_EVALUATION_RECORDED',
        evaluations: [{
          ...evaluation(),
          metrics: { sharpe: 9.9, max_drawdown: -0.01 },
          gate_inputs: { raw_sealed: [1, 2, 3] },
          failure_reason: 'must-never-render',
          token: 'must-never-render',
          storage_uri: 'sealed://must-never-render',
        } as unknown as AiResearchV2EvaluationSummary],
        evidencePackages: [{
          id: 'package-canary',
          candidate_id: 'candidate-1',
          command_id: null,
          evaluation_id: null,
          promotion_policy_version: 'promotion-v1',
          gate_input_evidence_hash: 'a'.repeat(64),
          manifest_hash: 'b'.repeat(64),
          approval_binding_hash: 'c'.repeat(64),
          status: 'ACTIVE',
          created_at: '2026-09-08T00:00:03Z',
          metrics: { sharpe: 9.9, max_drawdown: -0.01 },
          failure_reason: 'must-never-render',
          token_hash: 'must-never-render',
          storage_uri: 'sealed://must-never-render',
        } as unknown as AiResearchV2EvidencePackageSummary],
      },
    })

    for (const prohibited of [
      'sharpe',
      'max_drawdown',
      'gate_inputs',
      'raw_sealed',
      'failure_reason',
      'must-never-render',
      'sealed://',
    ]) expect(wrapper.html()).not.toContain(prohibited)
  })

  it.each([
    ['QUEUED', '已排队'],
    ['RUNNING', '正在运行'],
    ['RECONCILING', '正在核对'],
    ['FAILED', '执行失败'],
    ['CANCELLED', '已取消'],
    ['TIMED_OUT', '已超时'],
  ] as const)('renders holdout lifecycle %s separately from missing evidence', (status, label) => {
    const command = {
      ...holdoutCommand(status, {
        error_code: status === 'FAILED' ? 'HOLDOUT_EVALUATOR_UNAVAILABLE' : null,
      }),
      authorization_token: 'must-never-render',
      storage_uri: 'sealed://must-never-render',
    }
    const wrapper = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_PENDING',
        holdoutCommands: [command],
      },
    })

    const state = wrapper.get('[data-test="trusted-holdout-state"]')
    expect(state.attributes('data-status')).toBe(status)
    expect(state.attributes('aria-live')).toBe('polite')
    expect(state.text()).toContain(label)
    if (status === 'FAILED') expect(state.text()).toContain('HOLDOUT_EVALUATOR_UNAVAILABLE')
    expect(wrapper.html()).not.toContain('must-never-render')
  })

  it('distinguishes a rejected holdout from a successful command without a package', () => {
    const rejected = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_GATE_DECISIONS_RECORDED',
        holdoutCommands: [holdoutCommand('SUCCEEDED')],
        evaluations: [{
          ...evaluation('REJECTED'),
          metrics: { sealed_secret: 'must-never-render' },
        }],
      },
    })
    const succeededWithoutPackage = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_EVALUATION_RECORDED',
        holdoutCommands: [holdoutCommand('SUCCEEDED')],
        evaluations: [evaluation()],
      },
    })

    expect(rejected.get('[data-test="trusted-holdout-state"]').attributes('data-status'))
      .toBe('REJECTED')
    expect(rejected.text()).toContain('硬门拒绝')
    expect(rejected.html()).not.toContain('must-never-render')
    expect(succeededWithoutPackage.get('[data-test="trusted-holdout-state"]')
      .attributes('data-status')).toBe('SUCCEEDED_NO_PACKAGE')
    expect(succeededWithoutPackage.text()).toContain('证据包尚未生成')
    expect(succeededWithoutPackage.text()).not.toContain('尚无服务端构建的证据包')
  })

  it.each([
    ['withdrawn package', { status: 'WITHDRAWN' }, {}],
    ['stale policy', { promotion_policy_version: 'promotion-v0' }, {}],
    ['different command', { command_id: 'holdout-command-other' }, {}],
    ['different evaluation', { evaluation_id: 'evaluation-other' }, {}],
    ['different evaluation dataset', {}, { dataset_snapshot_id: 'dataset-other' }],
    ['different evaluator', {}, { evaluator_identity: 'explorer-self-evaluator' }],
    ['legacy non-sealed evaluation type', {}, { evaluation_type: 'HOLDOUT' }],
  ] as const)(
    'does not call holdout evidence complete for a %s',
    (_label, packageOverrides, evaluationOverrides) => {
      const packageWithCanaries = {
        id: 'package-1',
        candidate_id: 'candidate-1',
        command_id: 'holdout-command-1',
        evaluation_id: 'evaluation-1',
        promotion_policy_version: 'promotion-v1',
        gate_input_evidence_hash: 'a'.repeat(64),
        manifest_hash: 'b'.repeat(64),
        approval_binding_hash: 'c'.repeat(64),
        status: 'ACTIVE',
        created_at: '2026-09-08T00:00:03Z',
        metrics: { sharpe: 99, max_drawdown: -0.01 },
        failure_reason: 'must-never-render',
        token: 'must-never-render',
        storage_uri: 'sealed://must-never-render',
        ...packageOverrides,
      } as unknown as AiResearchV2EvidencePackageSummary
      const wrapper = mount(EvidencePanel, {
        props: {
          evidenceClass: 'PROTOCOL_V2_EVALUATION_RECORDED',
          promotionPolicyVersion: 'promotion-v1',
          holdoutCommands: [holdoutCommand('SUCCEEDED')],
          evaluations: [{
            ...evaluation(),
            ...evaluationOverrides,
            metrics: { sharpe: 99, max_drawdown: -0.01 },
            gate_inputs: { raw_sealed: [1, 2, 3] },
            failure_reason: 'must-never-render',
          } as unknown as AiResearchV2EvaluationSummary],
          evidencePackages: [packageWithCanaries],
        },
      })

      const state = wrapper.get('[data-test="trusted-holdout-state"]')
      expect(state.attributes('data-status')).toBe('SUCCEEDED_NO_PACKAGE')
      expect(state.text()).toContain('证据包尚未生成')
      expect(wrapper.html()).not.toContain('sharpe')
      expect(wrapper.html()).not.toContain('max_drawdown')
      expect(wrapper.html()).not.toContain('failure_reason')
      expect(wrapper.html()).not.toContain('must-never-render')
      expect(wrapper.html()).not.toContain('sealed://')
    },
  )

  it('marks evidence complete only for an active current-policy package exactly bound to command and evaluation', () => {
    const wrapper = mount(EvidencePanel, {
      props: {
        evidenceClass: 'PROTOCOL_V2_READY',
        promotionPolicyVersion: 'promotion-v1',
        holdoutCommands: [holdoutCommand('SUCCEEDED')],
        evaluations: [evaluation()],
        evidencePackages: [{
          id: 'package-1',
          candidate_id: 'candidate-1',
          command_id: 'holdout-command-1',
          evaluation_id: 'evaluation-1',
          promotion_policy_version: 'promotion-v1',
          gate_input_evidence_hash: 'a'.repeat(64),
          manifest_hash: 'b'.repeat(64),
          approval_binding_hash: 'c'.repeat(64),
          status: 'ACTIVE',
          created_at: '2026-09-08T00:00:03Z',
        }],
      },
    })

    expect(wrapper.get('[data-test="trusted-holdout-state"]').attributes('data-status'))
      .toBe('SUCCEEDED')
  })
})
