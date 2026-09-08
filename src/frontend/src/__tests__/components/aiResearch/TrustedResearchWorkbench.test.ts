import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { strategyApi } from '@/api/strategy'
import { approvalContextFor } from '@/__tests__/fixtures/aiResearchApproval'
import TrustedResearchWorkbench from '@/components/aiResearch/TrustedResearchWorkbench.vue'
import { projectAiResearchApprovalContext } from '@/types/aiResearchV2'
import type {
  AiResearchV2Candidate,
  AiResearchV2HoldoutCommand,
  AiResearchV2Workbench,
} from '@/types/aiResearchV2'

function candidate(
  freezeStatus: AiResearchV2Candidate['freeze_status'] = 'MUTABLE',
): AiResearchV2Candidate {
  return {
    id: 'candidate-1',
    run_id: 'run-b',
    experiment_epoch_id: 'epoch-1',
    source_version_id: null,
    dataset_snapshot_id: 'dataset-1',
    code_artifact_id: 'code-1',
    dependency_artifact_id: 'dependencies-1',
    candidate_hash: 'a'.repeat(64),
    environment_hash: 'b'.repeat(64),
    cost_model_hash: 'c'.repeat(64),
    params: { lookback: 20, threshold: 1.5 },
    freeze_status: freezeStatus,
    frozen_at: freezeStatus === 'FROZEN' ? '2026-09-07T00:00:00Z' : null,
  }
}

function workbench(runId: string, taskId: string): AiResearchV2Workbench {
  return {
    run: {
      id: runId,
      hypothesis_version_id: 'hypothesis-1',
      dataset_snapshot_id: 'dataset-1',
      experiment_epoch_id: 'epoch-1',
      protocol_version: 'v2',
      status: 'QUEUED',
      stage_cursor: 'CLARIFY',
      promotion_policy_version: 'promotion-v1',
      request_hash: 'a'.repeat(64),
      capability_profile_id: 'dev-single-process',
      capability_profile_version: 'v1',
      capability_evidence_hash: 'b'.repeat(64),
      trace_id: 'trace-run-b',
      created_at: '2026-09-05T00:00:00Z',
    },
    task: {
      id: taskId,
      run_id: runId,
      status: 'SUCCEEDED',
      stage_cursor: 'GENERATE',
      error_code: null,
      trace_id: 'trace-run-b',
      attempt_count: 1,
      created_at: '2026-09-05T00:00:00Z',
      completed_at: '2026-09-05T00:01:00Z',
    },
    candidates: [],
    holdout_commands: [],
    ledger: [],
    model_invocations: [],
    evaluations: [],
    gates: [],
    decisions: [],
    governance_decisions: [],
    evidence_packages: [],
    evidence_class: 'PROTOCOL_V2_PENDING',
  }
}

function holdoutCommand(
  status: AiResearchV2HoldoutCommand['status'] = 'QUEUED',
  overrides: Partial<AiResearchV2HoldoutCommand> = {},
): AiResearchV2HoldoutCommand {
  return {
    id: 'holdout-command-1',
    run_id: 'run-b',
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
    capability_profile_id: 'dev-single-process',
    capability_profile_version: 'v1',
    capability_evidence_hash: 'b'.repeat(64),
    error_code: null,
    request_hash: 'f'.repeat(64),
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    ...overrides,
  }
}

function candidateWorkbench(
  freezeStatus: AiResearchV2Candidate['freeze_status'] = 'MUTABLE',
): AiResearchV2Workbench {
  return {
    ...workbench('run-b', 'task-b'),
    dataset: {
      id: 'dataset-1',
      dataset_policy_version: 'policy-v1',
      partition_kind: 'DISCOVERY',
      instrument_manifest: {},
      split_manifest: {},
      source_manifest: {},
      execution_policy: {},
      point_in_time_cutoff: '2026-09-01T00:00:00Z',
      content_hash: 'd'.repeat(64),
    },
    candidates: [candidate(freezeStatus)],
  }
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

beforeEach(() => {
  vi.spyOn(strategyApi, 'getTrustedAIResearchApprovalContext').mockImplementation(
    async (runId, candidateId) => {
      const projected = projectAiResearchApprovalContext(approvalContextFor(runId, candidateId))
      if (projected === null) throw new Error('bad approval fixture')
      return projected
    },
  )
  vi.spyOn(strategyApi, 'listTrustedAIResearchTasks').mockResolvedValue({
    items: [],
    next_cursor: null,
  })
  vi.spyOn(strategyApi, 'listTrustedAIResearchTaskEvents').mockResolvedValue({
    items: [],
    next_cursor: null,
    resume_cursor: null,
  })
})

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
}

function mountWorkbench(router = createTestRouter()) {
  return mount(TrustedResearchWorkbench, {
    global: { plugins: [router] },
  })
}

describe('TrustedResearchWorkbench', () => {
  it('starts with an explicit draft action instead of an implicit confirmation action', () => {
    const wrapper = mountWorkbench()

    const createDraft = wrapper.get('[data-test="trusted-research-create-draft"]')
    expect(createDraft).toBeTruthy()
    expect(createDraft.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="trusted-research-confirm-start"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('requires a registered server-side data receipt before a draft can be created', async () => {
    const wrapper = mountWorkbench()
    const fields = wrapper.findAll('.trusted-workbench__form input')

    await fields[0].setValue('Does a stable signal persist?')
    await fields[1].setValue('The economic mechanism is documented.')
    await fields[2].setValue('RB0')

    const createDraft = wrapper.get('[data-test="trusted-research-create-draft"]')
    expect(createDraft.attributes('disabled')).toBeDefined()

    const objectReceipt = wrapper.get('[data-test="trusted-research-object-receipt-id"]')
    await objectReceipt.setValue('fixture-receipt-discovery-v1')
    expect(createDraft.attributes('disabled')).toBeUndefined()

    expect(wrapper.html()).not.toContain('controlled://')

    await wrapper.get('[data-test="trusted-research-profile-id"]').setValue('')
    expect(createDraft.attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="trusted-research-profile-id"]').setValue('isolated-profile')
    await wrapper.get('[data-test="trusted-research-profile-version"]').setValue('')
    expect(createDraft.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('restores a route-selected run from owner task history and renders its safe timeline area', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b')
    await router.isReady()
    vi.mocked(strategyApi.listTrustedAIResearchTasks).mockResolvedValue({
      items: [{
        id: 'task-b',
        run_id: 'run-b',
        status: 'SUCCEEDED',
        stage_cursor: 'GENERATE',
        error_code: null,
        trace_id: 'trace-run-b',
        attempt_count: 1,
        created_at: '2026-09-05T00:00:00Z',
        completed_at: '2026-09-05T00:01:00Z',
      }],
      next_cursor: null,
    })
    const getWorkbench = vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench')
      .mockResolvedValue(workbench('run-b', 'task-b'))

    const wrapper = mountWorkbench(router)
    await flushPromises()

    expect(getWorkbench).toHaveBeenCalledWith('run-b', expect.anything())
    expect(wrapper.get('[data-test="trusted-research-history"]').text()).toContain('task-b')
    expect(wrapper.get('[data-test="trusted-research-events"]').text()).toContain('任务事件时间线')
    wrapper.unmount()
  })

  it('clears a stale candidate query when history selection switches to another run', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-a&task_id=task-a&candidate_id=candidate-a')
    await router.isReady()
    vi.mocked(strategyApi.listTrustedAIResearchTasks).mockResolvedValue({
      items: [{
        id: 'task-b',
        run_id: 'run-b',
        status: 'SUCCEEDED',
        stage_cursor: 'GENERATE',
        error_code: null,
        trace_id: 'trace-run-b',
        attempt_count: 1,
        created_at: '2026-09-05T00:00:00Z',
        completed_at: '2026-09-05T00:01:00Z',
      }],
      next_cursor: null,
    })
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockImplementation(async (runId) => ({
      ...workbench(runId, `task-${runId.slice(-1)}`),
      candidates: [{
        ...candidate(),
        id: `candidate-${runId.slice(-1)}`,
        run_id: runId,
      }],
    }))

    const wrapper = mountWorkbench(router)
    await flushPromises()
    await wrapper.get('button[aria-label*="task-b"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.run_id).toBe('run-b')
    expect(router.currentRoute.value.query.task_id).toBe('task-b')
    expect(router.currentRoute.value.query.candidate_id).toBeUndefined()
    wrapper.unmount()
  })

  it('renders candidate bindings without exposing sealed evaluation content', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    const candidateWithControlledFields = {
      ...candidate(),
      sealed_metrics: { sharpe: 99 },
      storage_reference: 'controlled://sealed-evaluation',
    }
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue({
      ...candidateWorkbench(),
      candidates: [candidateWithControlledFields],
    })

    const wrapper = mountWorkbench(router)
    await flushPromises()

    const panel = wrapper.get('[data-test="trusted-research-candidates"]')
    expect(panel.text()).toContain('a'.repeat(64))
    expect(panel.text()).toContain('d'.repeat(64))
    expect(panel.text()).toContain('b'.repeat(64))
    expect(panel.text()).toContain('c'.repeat(64))
    expect(panel.text()).toContain('"lookback": 20')
    expect(panel.html()).not.toContain('sealed_metrics')
    expect(panel.html()).not.toContain('controlled://sealed-evaluation')
    wrapper.unmount()
  })

  it('binds explicit freeze confirmation to the displayed candidate hash', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    const mutableWorkbench = candidateWorkbench()
    const frozenWorkbench = candidateWorkbench('FROZEN')
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench')
      .mockResolvedValueOnce(mutableWorkbench)
      .mockResolvedValueOnce(frozenWorkbench)
    const freeze = vi.spyOn(strategyApi, 'freezeTrustedAIResearchCandidate')
      .mockResolvedValue(candidate('FROZEN'))

    const wrapper = mountWorkbench(router)
    await flushPromises()
    await wrapper.get('[data-test="trusted-research-candidate-freeze-candidate-1"]').trigger('click')

    const dialog = wrapper.get('[data-test="trusted-research-freeze-dialog"]')
    expect(dialog.attributes('role')).toBe('dialog')
    expect(dialog.attributes('aria-describedby')).toBe('trusted-research-freeze-warning')
    expect(dialog.text()).toContain('a'.repeat(64))
    expect(dialog.text()).toContain('冻结不等于独立评估、人工审批或上线授权')

    await dialog.get('[data-test="trusted-research-freeze-confirm"]').trigger('click')
    await flushPromises()

    expect(freeze).toHaveBeenCalledWith(
      'candidate-1',
      { expected_candidate_hash: 'a'.repeat(64) },
      expect.anything(),
    )
    expect(strategyApi.getTrustedAIResearchWorkbench).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-test="trusted-research-candidates"]').text()).toContain('已冻结')
    expect(wrapper.find('[data-test="trusted-research-freeze-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers independent holdout only for a completely bound frozen candidate', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench')
      .mockResolvedValue(candidateWorkbench('FROZEN'))

    const wrapper = mountWorkbench(router)
    await flushPromises()

    const action = wrapper.get('[data-test="trusted-research-candidate-holdout-candidate-1"]')
    expect(action.attributes('disabled')).toBeUndefined()
    expect(action.attributes('aria-describedby')).toContain(
      'trusted-research-candidate-holdout-warning-candidate-1',
    )
    expect(wrapper.get('[data-test="trusted-research-candidate-holdout-warning-candidate-1"]')
      .text()).toContain('冻结不等于独立留出评估')
    wrapper.unmount()
  })

  it('does not expose a holdout action for a mutable or incompletely bound candidate', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    const incompleteFrozen = candidateWorkbench('FROZEN')
    incompleteFrozen.dataset = { ...incompleteFrozen.dataset!, content_hash: 'not-a-sha256' }
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench')
      .mockResolvedValueOnce(candidateWorkbench('MUTABLE'))
      .mockResolvedValueOnce(incompleteFrozen)

    const wrapper = mountWorkbench(router)
    await flushPromises()
    expect(wrapper.find('[data-test="trusted-research-candidate-holdout-candidate-1"]').exists())
      .toBe(false)

    await wrapper.get('.trusted-workbench__header-actions button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="trusted-research-candidate-holdout-candidate-1"]').exists())
      .toBe(false)
    wrapper.unmount()
  })

  it.each([
    ['RUNNING', '运行中'],
    ['SUCCEEDED', '已完成'],
  ] as const)(
    'blocks another holdout request when the epoch already has a %s command',
    async (status, translatedStatus) => {
      const router = createTestRouter()
      await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
      await router.isReady()
      vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue({
        ...candidateWorkbench('FROZEN'),
        holdout_commands: [holdoutCommand(status)],
      })

      const wrapper = mountWorkbench(router)
      await flushPromises()

      expect(wrapper.find('[data-test="trusted-research-candidate-holdout-candidate-1"]').exists())
        .toBe(false)
      const state = wrapper.get(
        '[data-test="trusted-research-candidate-holdout-status-candidate-1"]',
      )
      expect(state.attributes('aria-live')).toBe('polite')
      expect(state.text()).toContain(translatedStatus)
      expect(state.text()).not.toContain(`：${status}`)
      wrapper.unmount()
    },
  )

  it('requests holdout with candidate identity only and renders the queued lifecycle', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench')
      .mockResolvedValue(candidateWorkbench('FROZEN'))
    const requestHoldout = vi.spyOn(strategyApi, 'requestTrustedAIResearchHoldout')
      .mockResolvedValue(holdoutCommand())
    vi.spyOn(strategyApi, 'getTrustedAIResearchHoldout').mockResolvedValue(holdoutCommand())

    const wrapper = mountWorkbench(router)
    await flushPromises()
    await wrapper.get('[data-test="trusted-research-candidate-holdout-candidate-1"]')
      .trigger('click')
    await flushPromises()

    expect(requestHoldout).toHaveBeenCalledWith(
      'candidate-1',
      'a'.repeat(64),
      expect.stringMatching(/\S+/),
      expect.anything(),
    )
    const state = wrapper.get('[data-test="trusted-holdout-state"]')
    expect(state.attributes('aria-live')).toBe('polite')
    expect(state.attributes('data-status')).toBe('QUEUED')
    expect(state.text()).toContain('已排队')
    expect(wrapper.html()).not.toContain('sealed://')
    expect(wrapper.html()).not.toContain('token_hash')
    wrapper.unmount()
  })

  it('resumes the latest non-terminal holdout after page restoration', async () => {
    vi.useFakeTimers()
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue({
      ...candidateWorkbench('FROZEN'),
      holdout_commands: [holdoutCommand('QUEUED')],
    })
    const getHoldout = vi.spyOn(strategyApi, 'getTrustedAIResearchHoldout')
      .mockResolvedValue(holdoutCommand('RUNNING'))

    const wrapper = mountWorkbench(router)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect(getHoldout).toHaveBeenCalledWith('holdout-command-1', expect.anything())
    expect(wrapper.get('[data-test="trusted-holdout-state"]').attributes('data-status'))
      .toBe('RUNNING')
    wrapper.unmount()
  })

  it('fails closed in the UI when a candidate freeze identity is incomplete', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    const incomplete = candidateWorkbench()
    incomplete.candidates = [{ ...candidate(), environment_hash: 'not-a-sha256' }]
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue(incomplete)

    const wrapper = mountWorkbench(router)
    await flushPromises()

    const freeze = wrapper.get('[data-test="trusted-research-candidate-freeze-candidate-1"]')
    expect(freeze.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="trusted-research-candidate-incomplete-candidate-1"]').text())
      .toContain('身份绑定不完整')
    await freeze.trigger('click')
    expect(wrapper.find('[data-test="trusted-research-freeze-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('moves focus into the confirmation dialog and restores it when review is cancelled', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue(candidateWorkbench())
    const host = document.createElement('div')
    document.body.append(host)
    const wrapper = mount(TrustedResearchWorkbench, {
      attachTo: host,
      global: { plugins: [router] },
    })
    await flushPromises()

    const opener = wrapper.get('[data-test="trusted-research-candidate-freeze-candidate-1"]')
    ;(opener.element as HTMLElement).focus()
    await opener.trigger('click')
    await flushPromises()

    const dialog = wrapper.get('[data-test="trusted-research-freeze-dialog"]')
    expect(document.activeElement).toBe(dialog.element)
    await dialog.get('[data-test="trusted-research-freeze-cancel"]').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(opener.element)

    wrapper.unmount()
    host.remove()
  })

  it('cycles Tab and Shift+Tab focus within the freeze confirmation dialog', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue(candidateWorkbench())
    const host = document.createElement('div')
    document.body.append(host)
    const wrapper = mount(TrustedResearchWorkbench, {
      attachTo: host,
      global: { plugins: [router] },
    })
    await flushPromises()

    await wrapper.get('[data-test="trusted-research-candidate-freeze-candidate-1"]').trigger('click')
    await flushPromises()
    const dialog = wrapper.get('[data-test="trusted-research-freeze-dialog"]')
    const cancel = dialog.get('[data-test="trusted-research-freeze-cancel"]')
    const confirm = dialog.get('[data-test="trusted-research-freeze-confirm"]')

    await dialog.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(cancel.element)

    ;(confirm.element as HTMLElement).focus()
    await confirm.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(cancel.element)

    ;(cancel.element as HTMLElement).focus()
    await cancel.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirm.element)

    wrapper.unmount()
    host.remove()
  })

  it('restores focus to the re-enabled freeze trigger after submission fails', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue(candidateWorkbench())
    vi.spyOn(strategyApi, 'freezeTrustedAIResearchCandidate').mockRejectedValue({
      response: { data: { detail: 'RESEARCH_CANDIDATE_FREEZE_CONFLICT' } },
    })
    const host = document.createElement('div')
    document.body.append(host)
    const wrapper = mount(TrustedResearchWorkbench, {
      attachTo: host,
      global: { plugins: [router] },
    })
    await flushPromises()

    const opener = wrapper.get('[data-test="trusted-research-candidate-freeze-candidate-1"]')
    ;(opener.element as HTMLElement).focus()
    await opener.trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="trusted-research-freeze-confirm"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('RESEARCH_CANDIDATE_FREEZE_CONFLICT')
    expect(opener.attributes('disabled')).toBeUndefined()
    expect(document.activeElement).toBe(opener.element)

    wrapper.unmount()
    host.remove()
  })

  it('loads a reviewer approval context even when the owner-scoped workbench is forbidden', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&candidate_id=candidate-1')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockRejectedValue({
      response: { status: 403, data: { detail: { code: 'RESEARCH_RUN_FORBIDDEN' } } },
    })

    const wrapper = mountWorkbench(router)
    await flushPromises()

    expect(strategyApi.getTrustedAIResearchApprovalContext).toHaveBeenCalledWith(
      'run-b',
      'candidate-1',
      expect.anything(),
    )
    expect(wrapper.findAll('[data-test="trusted-approval-gate"]')).toHaveLength(13)
    wrapper.unmount()
  })

  it('writes candidate selection to the route before loading its approval context', async () => {
    const router = createTestRouter()
    await router.push('/?run_id=run-b&task_id=task-b')
    await router.isReady()
    vi.spyOn(strategyApi, 'getTrustedAIResearchWorkbench').mockResolvedValue(candidateWorkbench())
    const wrapper = mountWorkbench(router)
    await flushPromises()

    await wrapper.get('[data-test="trusted-approval-candidate"]').setValue('candidate-1')
    await flushPromises()

    expect(router.currentRoute.value.query.candidate_id).toBe('candidate-1')
    expect(strategyApi.getTrustedAIResearchApprovalContext).toHaveBeenCalledWith(
      'run-b',
      'candidate-1',
      expect.anything(),
    )
    wrapper.unmount()
  })
})
