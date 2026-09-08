import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { strategyApi } from '@/api/strategy'
import ApprovalPanel from '@/components/aiResearch/ApprovalPanel.vue'
import {
  approvalContextFor,
  approvalContextFixture,
  approvalDecisionFixture,
  approvalRequestFixture,
} from '@/__tests__/fixtures/aiResearchApproval'
import {
  projectAiResearchApprovalContext,
  projectAiResearchApprovalDecision,
  projectAiResearchApprovalRequest,
} from '@/types/aiResearchV2'
import type { AiResearchV2Candidate } from '@/types/aiResearchV2'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function context(overrides: Record<string, unknown> = {}) {
  const projected = projectAiResearchApprovalContext(approvalContextFixture(overrides))
  if (projected === null) throw new Error('bad approval fixture')
  return projected
}

function candidate(): AiResearchV2Candidate {
  return {
    id: 'candidate-1',
    run_id: 'run-1',
    experiment_epoch_id: 'epoch-1',
    source_version_id: null,
    dataset_snapshot_id: 'dataset-1',
    code_artifact_id: 'code-1',
    dependency_artifact_id: 'dependency-1',
    candidate_hash: 'd'.repeat(64),
    environment_hash: 'e'.repeat(64),
    cost_model_hash: 'f'.repeat(64),
    params: {},
    freeze_status: 'FROZEN',
    frozen_at: '2026-09-08T00:00:00Z',
  }
}

beforeEach(() => {
  vi.spyOn(strategyApi, 'getTrustedAIResearchApprovalContext').mockResolvedValue(context())
  vi.spyOn(strategyApi, 'requestTrustedAIResearchApproval').mockResolvedValue(
    projectAiResearchApprovalRequest(approvalRequestFixture())!,
  )
  vi.spyOn(strategyApi, 'decideTrustedAIResearchApproval').mockResolvedValue(
    projectAiResearchApprovalDecision(approvalDecisionFixture())!,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ApprovalPanel', () => {
  it('renders the closed ACTIVE package and all thirteen safe gates for a reviewer', async () => {
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    const gates = wrapper.findAll('[data-test="trusted-approval-gate"]')
    expect(gates).toHaveLength(13)
    expect(gates[0].text()).toContain('CANDIDATE_FROZEN')
    expect(gates[0].text()).toContain('HOLDOUT_CANDIDATE_FROZEN_PASSED')
    expect(gates[12].text()).toContain('SECURITY_SCAN')
    expect(wrapper.get('[data-test="trusted-approval-package"]').text()).toContain('package-1')
    expect(wrapper.get('[data-test="trusted-approval-live"]').attributes('aria-live')).toBe('polite')

    const html = wrapper.html()
    for (const canary of [
      'sealed_metric',
      'storage_uri',
      'gate_inputs',
      'secret: 42',
      'must-not-cross-browser-boundary',
    ]) expect(html).not.toContain(canary)
    wrapper.unmount()
  })

  it('lets an owner request approval only when the server context allows it', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    const request = wrapper.get('[data-test="trusted-approval-request"]')
    expect(request.attributes('disabled')).toBeUndefined()
    await request.trigger('click')
    await flushPromises()

    expect(strategyApi.requestTrustedAIResearchApproval).toHaveBeenCalledWith(
      'run-1',
      'candidate-1',
      {
        gate_input_evidence_hash: 'a'.repeat(64),
        evidence_package_hash: 'b'.repeat(64),
      },
      expect.any(String),
      expect.anything(),
    )
    wrapper.unmount()
  })

  it('keeps request disabled when the server reports missing or ambiguous active evidence', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      can_request: false,
      request_blocked_reason: 'EVIDENCE_AMBIGUOUS',
      can_decide: false,
      decision_blocked_reason: 'REQUEST_REQUIRED',
      current_request: null,
      machine_evidence_summary: null,
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="trusted-approval-request"]').attributes('disabled'))
      .toBeDefined()
    expect(wrapper.get('[data-test="trusted-approval-request-blocked"]').text())
      .toContain('EVIDENCE_AMBIGUOUS')
    wrapper.unmount()
  })

  it('never renders unknown blocker URI or filesystem text', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      can_request: false,
      request_blocked_reason: 's3://private-bucket/raw-holdout',
      can_decide: false,
      decision_blocked_reason: '/srv/research/internal.sqlite',
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="trusted-approval-request-blocked"]').text())
      .toContain('RESEARCH_APPROVAL_BLOCKED')
    expect(wrapper.get('[data-test="trusted-approval-blocked"]').text())
      .toContain('RESEARCH_APPROVAL_BLOCKED')
    expect(wrapper.html()).not.toContain('s3://private-bucket')
    expect(wrapper.html()).not.toContain('/srv/research')
    wrapper.unmount()
  })

  it.each([
    ['credential URI', String.raw`file://reviewer:secret@internal/C:\sealed\raw-result.json`],
    ['RFC data scheme', 'data:text/plain,private'],
    ['single-slash file scheme', 'file:/srv/research/private.sqlite'],
    ['punctuation-adjacent POSIX path', 'review,/srv/research/private.sqlite'],
    ['punctuation-adjacent Windows path', String.raw`review=C:\Users\operator\approval.txt`],
    ['Chinese-adjacent RFC data scheme', '请查data:text/plain,private'],
    ['Chinese-adjacent POSIX path', '请查/srv/research/private.sqlite'],
    ['Chinese-adjacent Windows path', String.raw`请查C:\Users\operator\approval.txt`],
    ['Chinese-adjacent UNC path', String.raw`请查\\fileserver\sealed\result.json`],
  ])('never renders an unsafe %s latest-decision reason', async (_label, unsafeReason) => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      can_decide: false,
      decision_blocked_reason: 'REQUEST_REQUIRED',
      current_request: null,
      latest_decision: approvalDecisionFixture({
        decision: 'REJECTED',
        reason: unsafeReason,
      }),
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="trusted-approval-latest-decision"]').text())
      .toContain('[REDACTED]')
    expect(wrapper.html()).not.toContain(unsafeReason)
    expect(wrapper.html()).not.toContain('reviewer:secret')
    wrapper.unmount()
  })

  it('requires reason, all challenges, and residual-risk acknowledgement in single actor mode', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      approval_mode: 'single_actor',
      cooldown_seconds: 90,
      required_challenge_keys: ['candidate_hash', 'gate_hash'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({ approval_mode: 'single_actor' }),
    }))
    vi.mocked(strategyApi.decideTrustedAIResearchApproval).mockResolvedValue(
      projectAiResearchApprovalDecision(approvalDecisionFixture({
        approval_mode: 'single_actor',
        risk_acknowledgement: true,
        challenge_keys: ['candidate_hash', 'gate_hash'],
        decision_intent_hash:
          'f5b6d67e2a4ac6442f0c0ff3e1b2eed58298ad8111c8d8ad37cc8dabb48337f6',
      }))!,
    )
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="trusted-approval-cooldown"]').text()).toContain('90')
    const submit = wrapper.get('[data-test="trusted-approval-submit"]')
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="trusted-approval-reason"]').setValue(
      'I reviewed every gate and the residual risk.',
    )
    const challenges = wrapper.findAll('[data-test="trusted-approval-challenge"]')
    expect(challenges).toHaveLength(2)
    await challenges[0].setValue('candidate dddddddd')
    await challenges[1].setValue('gate aaaaaaaa')
    await wrapper.get('[data-test="trusted-approval-risk"]').setValue(
      'I accept the documented residual risk and cooldown constraint.',
    )
    expect(submit.attributes('disabled')).toBeUndefined()

    await submit.trigger('click')
    await vi.waitFor(() => {
      expect(strategyApi.decideTrustedAIResearchApproval).toHaveBeenCalledWith(
        'run-1',
        'candidate-1',
        expect.objectContaining({
          approval_request_id: 'approval-request-1',
          challenge_responses: {
            candidate_hash: 'candidate dddddddd',
            gate_hash: 'gate aaaaaaaa',
          },
          residual_risk_acknowledgement:
            'I accept the documented residual risk and cooldown constraint.',
        }),
        expect.any(String),
        expect.anything(),
      )
    })
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps submit disabled when Python-only whitespace is used for required approval text', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      approval_mode: 'single_actor',
      required_challenge_keys: ['candidate_hash'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({ approval_mode: 'single_actor' }),
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()
    const submit = wrapper.get('[data-test="trusted-approval-submit"]')
    const reason = wrapper.get('[data-test="trusted-approval-reason"]')
    const challenge = wrapper.get('[data-test="trusted-approval-challenge"]')
    const risk = wrapper.get('[data-test="trusted-approval-risk"]')

    await reason.setValue('\u0085')
    await challenge.setValue('verified')
    await risk.setValue('accepted')
    expect(submit.attributes('disabled')).toBeDefined()

    await reason.setValue('reviewed')
    await challenge.setValue('\u0085')
    expect(submit.attributes('disabled')).toBeDefined()

    await challenge.setValue('verified')
    await risk.setValue('\u0085')
    expect(submit.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('does not infer multi-actor self-approval when the server blocks the decision', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()
    await wrapper.get('[data-test="trusted-approval-reason"]').setValue('I am the owner.')

    expect(wrapper.get('[data-test="trusted-approval-submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="trusted-approval-blocked"]').text())
      .toContain('AUTHORITY_REQUIRED')
    expect(strategyApi.decideTrustedAIResearchApproval).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps rejection available with a reason even when approval challenges are incomplete', async () => {
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
      approval_mode: 'single_actor',
      required_challenge_keys: ['candidate_hash'],
      risk_acknowledgement_required: true,
      current_request: approvalRequestFixture({ approval_mode: 'single_actor' }),
    }))
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    await wrapper.get('[data-test="trusted-approval-decision"]').setValue('REJECTED')
    await wrapper.get('[data-test="trusted-approval-reason"]').setValue('Evidence is insufficient.')

    expect(wrapper.get('[data-test="trusted-approval-submit"]').attributes('disabled'))
      .toBeUndefined()
    wrapper.unmount()
  })

  it.each(['REJECTED', 'REQUESTED_CHANGES'] as const)(
    'blocks approval behind the server deny fence while preserving %s',
    async (negativeDecision) => {
      vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockResolvedValue(context({
        can_request: false,
        request_blocked_reason: 'APPROVAL_EVIDENCE_DENIED',
        can_decide: true,
        can_approve: false,
        decision_blocked_reason: null,
      }))
      const wrapper = mount(ApprovalPanel, {
        props: { runId: 'run-1', candidateId: 'candidate-1' },
      })
      await flushPromises()
      const submit = wrapper.get('[data-test="trusted-approval-submit"]')

      await wrapper.get('[data-test="trusted-approval-reason"]').setValue('Evidence is denied.')
      expect(submit.attributes('disabled')).toBeDefined()

      await wrapper.get('[data-test="trusted-approval-decision"]').setValue(negativeDecision)
      expect(submit.attributes('disabled')).toBeUndefined()
      await submit.trigger('click')

      await vi.waitFor(() => {
        expect(strategyApi.decideTrustedAIResearchApproval).toHaveBeenCalledWith(
          'run-1',
          'candidate-1',
          expect.objectContaining({
            decision: negativeDecision,
            reason: 'Evidence is denied.',
          }),
          expect.any(String),
          expect.anything(),
        )
      })
      wrapper.unmount()
    },
  )

  it('supports candidate selection without loading an owner-only workbench', async () => {
    const wrapper = mount(ApprovalPanel, {
      props: {
        runId: 'run-1',
        candidateId: null,
        candidates: [candidate()],
      },
    })
    await wrapper.get('[data-test="trusted-approval-candidate"]').setValue('candidate-1')

    expect(wrapper.emitted('selectCandidate')).toEqual([['candidate-1']])
    expect(strategyApi.getTrustedAIResearchApprovalContext).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not publish an old-scope success after switching during post-commit refresh', async () => {
    const oldRefresh = deferred<ReturnType<typeof context>>()
    const ownerContext = context({
      can_request: true,
      request_blocked_reason: null,
      can_decide: false,
      decision_blocked_reason: 'AUTHORITY_REQUIRED',
      current_request: null,
    })
    const nextContext = projectAiResearchApprovalContext(
      approvalContextFor('run-2', 'candidate-2'),
    )!
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockReset()
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext)
      .mockResolvedValueOnce(ownerContext)
      .mockReturnValueOnce(oldRefresh.promise)
      .mockResolvedValueOnce(nextContext)
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()

    await wrapper.get('[data-test="trusted-approval-request"]').trigger('click')
    await vi.waitFor(() => {
      expect(strategyApi.getTrustedAIResearchApprovalContext).toHaveBeenCalledTimes(2)
    })
    await wrapper.setProps({ runId: 'run-2', candidateId: 'candidate-2' })
    await flushPromises()
    oldRefresh.resolve(context())
    await flushPromises()

    expect(wrapper.get('[data-test="trusted-approval-live"]').text()).toBe('')
    expect(wrapper.get('[data-test="trusted-approval-current-request"]').text())
      .toContain('approval-request-1')
    wrapper.unmount()
  })

  it('does not publish an old-scope decision after switching during post-commit refresh', async () => {
    const oldRefresh = deferred<ReturnType<typeof context>>()
    const nextContext = projectAiResearchApprovalContext(
      approvalContextFor('run-2', 'candidate-2'),
    )!
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext).mockReset()
    vi.mocked(strategyApi.getTrustedAIResearchApprovalContext)
      .mockResolvedValueOnce(context())
      .mockReturnValueOnce(oldRefresh.promise)
      .mockResolvedValueOnce(nextContext)
    const wrapper = mount(ApprovalPanel, {
      props: { runId: 'run-1', candidateId: 'candidate-1' },
    })
    await flushPromises()
    await wrapper.get('[data-test="trusted-approval-reason"]').setValue(
      'Reviewed all thirteen server-bound gates.',
    )

    await wrapper.get('[data-test="trusted-approval-submit"]').trigger('click')
    await vi.waitFor(() => {
      expect(strategyApi.getTrustedAIResearchApprovalContext).toHaveBeenCalledTimes(2)
    })
    await wrapper.setProps({ runId: 'run-2', candidateId: 'candidate-2' })
    await flushPromises()
    oldRefresh.resolve(context())
    await flushPromises()

    expect(wrapper.get('[data-test="trusted-approval-live"]').text()).toBe('')
    expect(wrapper.get('[data-test="trusted-approval-current-request"]').text())
      .toContain('approval-request-1')
    wrapper.unmount()
  })
})
