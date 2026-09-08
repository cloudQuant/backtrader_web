import { afterEach, describe, expect, it, vi } from 'vitest'

import { useAiResearchV2, type AiResearchV2Api } from '@/composables/useAiResearchV2'
import type {
  AiResearchV2Candidate,
  AiResearchV2DataPrecheck,
  AiResearchV2DataPrecheckRequest,
  AiResearchV2EvaluationSummary,
  AiResearchV2EvidencePackageSummary,
  AiResearchV2HoldoutCommand,
  AiResearchV2RunSubmission,
  AiResearchV2Task,
  AiResearchV2TaskEvent,
  AiResearchV2TaskEventPage,
  AiResearchV2Workbench,
} from '@/types/aiResearchV2'

function candidate(
  id = 'candidate-1',
  freezeStatus: AiResearchV2Candidate['freeze_status'] = 'MUTABLE',
): AiResearchV2Candidate {
  return {
    id,
    run_id: 'run-a',
    experiment_epoch_id: 'epoch-1',
    source_version_id: null,
    dataset_snapshot_id: 'dataset-1',
    code_artifact_id: 'code-1',
    dependency_artifact_id: 'dependencies-1',
    candidate_hash: 'a'.repeat(64),
    environment_hash: 'b'.repeat(64),
    cost_model_hash: 'c'.repeat(64),
    params: { lookback: 20 },
    freeze_status: freezeStatus,
    frozen_at: freezeStatus === 'FROZEN' ? '2026-09-07T00:00:00Z' : null,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

function workbench(runId: string): AiResearchV2Workbench {
  return {
    run: {
      id: runId,
      hypothesis_version_id: 'hypothesis',
      dataset_snapshot_id: 'dataset-1',
      experiment_epoch_id: 'epoch-1',
      protocol_version: 'v2',
      status: 'QUEUED',
      stage_cursor: 'CLARIFY',
      promotion_policy_version: 'promotion-v1',
      request_hash: 'a'.repeat(64),
      capability_profile_id: 'dev-single-process',
      capability_profile_version: 'v1',
      capability_evidence_hash: 'e'.repeat(64),
      trace_id: `trace-${runId}`,
      created_at: '2026-09-04T00:00:00Z',
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

function task(
  taskId: string,
  runId: string,
  status = 'RUNNING',
): AiResearchV2Task {
  return {
    id: taskId,
    run_id: runId,
    status,
    stage_cursor: 'CLARIFY',
    attempt_count: 1,
    created_at: '2026-09-05T00:00:00Z',
  }
}

function holdoutCommand(
  status: AiResearchV2HoldoutCommand['status'] = 'QUEUED',
  overrides: Partial<AiResearchV2HoldoutCommand> = {},
): AiResearchV2HoldoutCommand {
  return {
    id: 'holdout-command-1',
    run_id: 'run-a',
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
    capability_evidence_hash: 'e'.repeat(64),
    error_code: null,
    request_hash: 'f'.repeat(64),
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    ...overrides,
  }
}

function evaluationSummary(
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

function evidencePackage(
  overrides: Partial<AiResearchV2EvidencePackageSummary> = {},
): AiResearchV2EvidencePackageSummary {
  return {
    id: 'evidence-package-1',
    candidate_id: 'candidate-1',
    command_id: 'holdout-command-1',
    evaluation_id: 'evaluation-1',
    promotion_policy_version: 'promotion-v1',
    gate_input_evidence_hash: '1'.repeat(64),
    manifest_hash: '2'.repeat(64),
    approval_binding_hash: '3'.repeat(64),
    status: 'ACTIVE',
    created_at: '2026-09-08T00:00:03Z',
    ...overrides,
  }
}

function workbenchWithTask(
  runId: string,
  taskId = `task-${runId}`,
  status = 'RUNNING',
): AiResearchV2Workbench {
  return {
    ...workbench(runId),
    task: task(taskId, runId, status),
  }
}

function workbenchWithCandidate(
  freezeStatus: AiResearchV2Candidate['freeze_status'] = 'MUTABLE',
): AiResearchV2Workbench {
  return {
    ...workbenchWithTask('run-a', 'task-a', 'SUCCEEDED'),
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
    candidates: [candidate('candidate-1', freezeStatus)],
  }
}

type SafeTaskEvent = AiResearchV2TaskEvent

function apiWithWorkbench(
  getTrustedAIResearchWorkbench: AiResearchV2Api['getTrustedAIResearchWorkbench'],
): AiResearchV2Api {
  const unavailable = async (): Promise<never> => {
    throw new Error('not used by this test')
  }
  return {
    createTrustedAIResearchHypothesis: unavailable,
    confirmTrustedAIResearchHypothesis: unavailable,
    createTrustedAIResearchDataset: unavailable,
    createTrustedAIResearchEpoch: unavailable,
    createTrustedAIResearchDataPrecheck: unavailable as unknown as AiResearchV2Api['createTrustedAIResearchDataPrecheck'],
    submitTrustedAIResearchRun: unavailable as unknown as (
      data: Parameters<AiResearchV2Api['submitTrustedAIResearchRun']>[0],
      idempotencyKey: string,
      signal?: AbortSignal,
    ) => Promise<AiResearchV2RunSubmission>,
    getTrustedAIResearchWorkbench,
    listTrustedAIResearchTasks: unavailable as unknown as AiResearchV2Api['listTrustedAIResearchTasks'],
    getTrustedAIResearchTask: unavailable as unknown as AiResearchV2Api['getTrustedAIResearchTask'],
    listTrustedAIResearchTaskEvents: unavailable as unknown as AiResearchV2Api['listTrustedAIResearchTaskEvents'],
    cancelTrustedAIResearchTask: unavailable as unknown as (
      taskId: string,
      signal?: AbortSignal,
    ) => Promise<AiResearchV2Task>,
    freezeTrustedAIResearchCandidate: unavailable as unknown as AiResearchV2Api['freezeTrustedAIResearchCandidate'],
    requestTrustedAIResearchHoldout: unavailable as unknown as AiResearchV2Api['requestTrustedAIResearchHoldout'],
    getTrustedAIResearchHoldout: unavailable as unknown as AiResearchV2Api['getTrustedAIResearchHoldout'],
  }
}

function apiWithObservability(
  getTrustedAIResearchWorkbench: AiResearchV2Api['getTrustedAIResearchWorkbench'],
  options: Pick<
    AiResearchV2Api,
    'getTrustedAIResearchTask' | 'listTrustedAIResearchTaskEvents'
  >,
): AiResearchV2Api {
  return {
    ...apiWithWorkbench(getTrustedAIResearchWorkbench),
    getTrustedAIResearchTask: options.getTrustedAIResearchTask,
    listTrustedAIResearchTasks: async () => ({ items: [], next_cursor: null }),
    listTrustedAIResearchTaskEvents: options.listTrustedAIResearchTaskEvents,
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('useAiResearchV2', () => {
  it('keeps a newly created hypothesis as a draft until the user explicitly confirms it', async () => {
    const calls: string[] = []
    const api: AiResearchV2Api = {
      createTrustedAIResearchHypothesis: async () => {
        calls.push('draft')
        return {
          id: 'draft-1',
          content_hash: 'a'.repeat(64),
          canonical_payload: { research_question: 'canonical server payload' },
        }
      },
      confirmTrustedAIResearchHypothesis: async () => {
        calls.push('confirm')
        return { id: 'confirmed-1', content_hash: 'a'.repeat(64) }
      },
      createTrustedAIResearchDataset: async () => {
        calls.push('dataset')
        return { id: 'dataset-1' }
      },
      createTrustedAIResearchEpoch: async () => {
        calls.push('epoch')
        return { id: 'epoch-1' }
      },
      createTrustedAIResearchDataPrecheck: async () => {
        calls.push('precheck')
        return {
          id: 'precheck-1',
          hypothesis_version_id: 'confirmed-1',
          dataset_snapshot_id: 'dataset-1',
          experiment_epoch_id: 'epoch-1',
          profile_id: 'isolated-profile',
          profile_version: 'v1',
          promotion_policy_version: 'promotion-v1',
          status: 'PASS',
          input_hash: 'c'.repeat(64),
          evidence_hash: 'd'.repeat(64),
          checked_at: '2026-09-05T00:00:00Z',
          expires_at: '2099-09-05T00:15:00Z',
          details: {},
        }
      },
      submitTrustedAIResearchRun: async () => {
        calls.push('submit')
        return {
          run: workbench('run-1').run,
          task: {
            id: 'task-1',
            run_id: 'run-1',
            status: 'QUEUED',
            stage_cursor: 'CLARIFY',
            attempt_count: 0,
            created_at: '2026-09-05T00:00:00Z',
          },
        }
      },
      getTrustedAIResearchWorkbench: async () => {
        calls.push('workbench')
        return workbench('run-1')
      },
      listTrustedAIResearchTasks: async () => ({ items: [], next_cursor: null }),
      getTrustedAIResearchTask: async () => {
        throw new Error('not used by this test')
      },
      listTrustedAIResearchTaskEvents: async () => ({
        items: [],
        next_cursor: null,
        resume_cursor: null,
      }),
      cancelTrustedAIResearchTask: async () => {
        throw new Error('not used by this test')
      },
      freezeTrustedAIResearchCandidate: async () => {
        throw new Error('not used by this test')
      },
      requestTrustedAIResearchHoldout: async () => {
        throw new Error('not used by this test')
      },
      getTrustedAIResearchHoldout: async () => {
        throw new Error('not used by this test')
      },
    }
    const runtime = useAiResearchV2({ api })
    const input = {
      hypothesisPayload: { research_question: 'Does the signal persist?' },
      dataset: {
        dataset_policy_version: 'policy-v1',
        partition_kind: 'DISCOVERY' as const,
        instrument_manifest: { symbols: ['RB0'] },
        split_manifest: {},
        source_manifest: {},
        execution_policy: {},
        point_in_time_cutoff: '2026-09-05T00:00:00Z',
        object_receipt_id: 'fixture-receipt-discovery-v1',
        license_tags: ['test-license'],
      },
      searchBudget: { max_trials: 1 },
      profileId: 'isolated-profile',
      profileVersion: 'v1',
      promotionPolicyVersion: 'promotion-v1',
      idempotencyKey: 'operation-1',
    }

    await runtime.createDraft(input.hypothesisPayload)

    expect(calls).toEqual(['draft'])
    expect(runtime.draft.value?.id).toBe('draft-1')
    expect(runtime.draft.value?.payload).toEqual({ research_question: 'canonical server payload' })
    expect(runtime.activeRunId.value).toBeNull()

    await runtime.confirmDraftAndPrepare(input)

    expect(calls).toEqual(['draft', 'confirm', 'dataset', 'epoch', 'precheck'])
    expect(runtime.activeRunId.value).toBeNull()
    expect(runtime.preparedRun.value?.precheck.id).toBe('precheck-1')

    await runtime.startPreparedRun()

    expect(calls).toEqual(['draft', 'confirm', 'dataset', 'epoch', 'precheck', 'submit', 'workbench'])
    expect(runtime.workbench.value?.run.id).toBe('run-1')
    runtime.dispose()
  })

  it('discards a late response from a prior run after switching to a new run', async () => {
    const first = deferred<AiResearchV2Workbench>()
    const api = apiWithWorkbench(async (runId: string) =>
      runId === 'run-a' ? first.promise : workbench('run-b'),
    )
    const runtime = useAiResearchV2({ api })

    const loadingA = runtime.load('run-a')
    const loadingB = runtime.load('run-b')
    await loadingB
    first.resolve(workbench('run-a'))
    await loadingA

    expect(runtime.workbench.value?.run.id).toBe('run-b')
    expect(runtime.activeRunId.value).toBe('run-b')
    runtime.dispose()
  })

  it('loads owner-scoped task history through opaque cursor pages without duplicates', async () => {
    const listTasks = vi.fn(async (cursor?: string | null) => {
      if (cursor === null || cursor === undefined) {
        return {
          items: [task('task-a', 'run-a'), task('task-b', 'run-b')],
          next_cursor: 'opaque-history-cursor-1',
        }
      }
      return {
        items: [task('task-b', 'run-b', 'SUCCEEDED'), task('task-c', 'run-c')],
        next_cursor: null,
      }
    })
    const api = apiWithWorkbench(async (runId) => workbench(runId))
    api.listTrustedAIResearchTasks = listTasks
    const runtime = useAiResearchV2({ api })

    await runtime.loadTaskHistory()
    await runtime.loadMoreTaskHistory()

    expect(listTasks.mock.calls.map(([cursor]) => cursor)).toEqual([null, 'opaque-history-cursor-1'])
    expect(runtime.taskHistory.value.map((entry) => entry.id)).toEqual(['task-a', 'task-b', 'task-c'])
    expect(runtime.taskHistory.value.find((entry) => entry.id === 'task-b')?.status).toBe('SUCCEEDED')
    expect(runtime.taskHistoryNextCursor.value).toBeNull()
    runtime.dispose()
  })

  it('preserves cursor-paginated history when automatic first-page refresh would run', async () => {
    vi.useFakeTimers()
    const pageItems = (start: number) => Array.from(
      { length: 20 },
      (_, offset) => task(`task-${start + offset}`, `run-${start + offset}`),
    )
    const listTasks = vi.fn(async (cursor?: string | null) => {
      if (cursor === null || cursor === undefined) {
        return { items: pageItems(1), next_cursor: 'opaque-history-cursor-2' }
      }
      if (cursor === 'opaque-history-cursor-2') {
        return { items: pageItems(21), next_cursor: 'opaque-history-cursor-3' }
      }
      if (cursor === 'opaque-history-cursor-3') {
        return { items: pageItems(41), next_cursor: 'opaque-history-cursor-4' }
      }
      throw new Error(`unexpected cursor ${cursor}`)
    })
    const api = apiWithWorkbench(async (runId) => workbench(runId))
    api.listTrustedAIResearchTasks = listTasks
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    runtime.startTaskHistoryPolling()
    await vi.advanceTimersByTimeAsync(0)
    await runtime.loadMoreTaskHistory()
    await runtime.loadMoreTaskHistory()

    expect(runtime.taskHistory.value).toHaveLength(60)
    expect(runtime.taskHistory.value[59]?.id).toBe('task-60')
    expect(runtime.taskHistoryNextCursor.value).toBe('opaque-history-cursor-4')

    await vi.advanceTimersByTimeAsync(1)

    expect(listTasks.mock.calls.map(([cursor]) => cursor)).toEqual([
      null,
      'opaque-history-cursor-2',
      'opaque-history-cursor-3',
    ])
    expect(runtime.taskHistory.value).toHaveLength(60)
    expect(runtime.taskHistory.value[59]?.id).toBe('task-60')
    expect(runtime.taskHistoryNextCursor.value).toBe('opaque-history-cursor-4')

    await runtime.loadTaskHistory()

    expect(listTasks.mock.calls.map(([cursor]) => cursor)).toEqual([
      null,
      'opaque-history-cursor-2',
      'opaque-history-cursor-3',
      null,
    ])
    expect(runtime.taskHistory.value).toHaveLength(20)
    expect(runtime.taskHistoryNextCursor.value).toBe('opaque-history-cursor-2')
    runtime.dispose()
  })

  it('rejects a candidate selection that is not present in the selected workbench', async () => {
    const api = apiWithWorkbench(async () => ({
      ...workbenchWithTask('run-b', 'task-b'),
      candidates: [{ ...candidate('candidate-b'), run_id: 'run-b' }],
    }))
    const runtime = useAiResearchV2({ api })

    const selected = await runtime.load('run-b', 'task-b', 'candidate-a')

    expect(selected).toBeNull()
    expect(runtime.workbench.value).toBeNull()
    expect(runtime.activeCandidateId.value).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_V2_CANDIDATE_SELECTION_INVALID')
    runtime.dispose()
  })

  it('binds a candidate selection only after the selected workbench contains it', async () => {
    const api = apiWithWorkbench(async () => ({
      ...workbenchWithTask('run-b', 'task-b'),
      candidates: [{ ...candidate('candidate-b'), run_id: 'run-b' }],
    }))
    const runtime = useAiResearchV2({ api })

    const selected = await runtime.load('run-b', 'task-b', 'candidate-b')

    expect(selected?.run.id).toBe('run-b')
    expect(runtime.workbench.value?.run.id).toBe('run-b')
    expect(runtime.activeCandidateId.value).toBe('candidate-b')
    runtime.dispose()
  })

  it('keeps the current workbench visible and reports a stable error for a mismatched refresh', async () => {
    const current = workbenchWithCandidate()
    const getWorkbench = vi.fn()
      .mockResolvedValueOnce(current)
      .mockResolvedValueOnce(workbench('run-other'))
    const runtime = useAiResearchV2({ api: apiWithWorkbench(getWorkbench) })
    await runtime.load('run-a', 'task-a', 'candidate-1')
    const preserved = runtime.workbench.value

    const refreshed = await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(refreshed).toBeNull()
    expect(runtime.workbench.value).toBe(preserved)
    expect(runtime.activeRunId.value).toBe('run-a')
    expect(runtime.activeCandidateId.value).toBe('candidate-1')
    expect(runtime.errorCode.value).toBe('RESEARCH_V2_WORKBENCH_SELECTION_INVALID')
    runtime.dispose()
  })

  it('fails closed before freeze when the candidate identity is not fully bound to the workbench', async () => {
    const incomplete = workbenchWithCandidate()
    incomplete.dataset = { ...incomplete.dataset!, content_hash: 'NOT-A-SHA256' }
    const api = apiWithWorkbench(async () => incomplete)
    api.freezeTrustedAIResearchCandidate = vi.fn(async () => candidate('candidate-1', 'FROZEN'))
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.freezeCandidate('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(api.freezeTrustedAIResearchCandidate).not.toHaveBeenCalled()
    expect(runtime.errorCode.value).toBe('RESEARCH_CANDIDATE_FREEZE_IDENTITY_INCOMPLETE')
    runtime.dispose()
  })

  it('submits one freeze while a candidate freeze is already in flight and refreshes the selected workbench', async () => {
    const pendingFreeze = deferred<AiResearchV2Candidate>()
    let reads = 0
    const getWorkbench = vi.fn(async () => {
      reads += 1
      return workbenchWithCandidate(reads > 1 ? 'FROZEN' : 'MUTABLE')
    })
    const api = apiWithWorkbench(getWorkbench)
    api.freezeTrustedAIResearchCandidate = vi.fn(() => pendingFreeze.promise)
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const first = runtime.freezeCandidate('candidate-1', 'a'.repeat(64))
    const duplicate = runtime.freezeCandidate('candidate-1', 'a'.repeat(64))

    expect(api.freezeTrustedAIResearchCandidate).toHaveBeenCalledTimes(1)
    expect(runtime.freezingCandidateId.value).toBe('candidate-1')
    expect(await duplicate).toBeNull()

    pendingFreeze.resolve(candidate('candidate-1', 'FROZEN'))
    expect((await first)?.freeze_status).toBe('FROZEN')
    expect(getWorkbench).toHaveBeenCalledTimes(2)
    expect(runtime.workbench.value?.candidates[0]?.freeze_status).toBe('FROZEN')
    expect(runtime.freezingCandidateId.value).toBeNull()
    runtime.dispose()
  })

  it('keeps a stable server error code when candidate freeze is rejected', async () => {
    const api = apiWithWorkbench(async () => workbenchWithCandidate())
    api.freezeTrustedAIResearchCandidate = async () => {
      throw { response: { data: { detail: 'RESEARCH_CANDIDATE_HASH_MISMATCH' } } }
    }
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.freezeCandidate('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_CANDIDATE_HASH_MISMATCH')
    expect(runtime.workbench.value?.candidates[0]?.freeze_status).toBe('MUTABLE')
    runtime.dispose()
  })

  it('rejects a freeze response whose immutable binding differs from the confirmed candidate', async () => {
    const getWorkbench = vi.fn(async () => workbenchWithCandidate())
    const api = apiWithWorkbench(getWorkbench)
    api.freezeTrustedAIResearchCandidate = vi.fn(async () => ({
      ...candidate('candidate-1', 'FROZEN'),
      environment_hash: 'f'.repeat(64),
    }))
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.freezeCandidate('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_CANDIDATE_FREEZE_RESPONSE_INVALID')
    expect(getWorkbench).toHaveBeenCalledTimes(1)
    runtime.dispose()
  })

  it('keeps the confirmed workbench when the dataset hash drifts during the freeze refresh', async () => {
    const confirmedWorkbench = workbenchWithCandidate()
    const driftedWorkbench = workbenchWithCandidate('FROZEN')
    driftedWorkbench.dataset = {
      ...driftedWorkbench.dataset!,
      content_hash: 'e'.repeat(64),
    }
    const getWorkbench = vi.fn()
      .mockResolvedValueOnce(confirmedWorkbench)
      .mockResolvedValueOnce(driftedWorkbench)
    const api = apiWithWorkbench(getWorkbench)
    api.freezeTrustedAIResearchCandidate = vi.fn(async () => candidate('candidate-1', 'FROZEN'))
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.freezeCandidate('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_CANDIDATE_FREEZE_REFRESH_INVALID')
    expect(runtime.workbench.value?.dataset?.content_hash).toBe('d'.repeat(64))
    expect(runtime.workbench.value?.candidates[0]?.freeze_status).toBe('MUTABLE')
    runtime.dispose()
  })

  it('ignores a successful freeze response that settles after disposal even when transport ignores abort', async () => {
    const pendingFreeze = deferred<AiResearchV2Candidate>()
    const getWorkbench = vi.fn(async () => workbenchWithCandidate())
    const api = apiWithWorkbench(getWorkbench)
    api.freezeTrustedAIResearchCandidate = vi.fn(() => pendingFreeze.promise)
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const freezing = runtime.freezeCandidate('candidate-1', 'a'.repeat(64))
    runtime.dispose()
    pendingFreeze.resolve(candidate('candidate-1', 'FROZEN'))

    expect(await freezing).toBeNull()
    expect(getWorkbench).toHaveBeenCalledTimes(1)
    expect(runtime.freezingCandidateId.value).toBeNull()
  })

  it('wins over a same-run refresh that started before the freeze response arrived', async () => {
    const pendingFreeze = deferred<AiResearchV2Candidate>()
    let reads = 0
    const getWorkbench = vi.fn(async () => {
      reads += 1
      return workbenchWithCandidate(reads >= 3 ? 'FROZEN' : 'MUTABLE')
    })
    const api = apiWithWorkbench(getWorkbench)
    api.freezeTrustedAIResearchCandidate = () => pendingFreeze.promise
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const freezing = runtime.freezeCandidate('candidate-1', 'a'.repeat(64))
    await runtime.load('run-a', 'task-a', 'candidate-1')
    pendingFreeze.resolve(candidate('candidate-1', 'FROZEN'))

    expect((await freezing)?.freeze_status).toBe('FROZEN')
    expect(getWorkbench).toHaveBeenCalledTimes(3)
    expect(runtime.workbench.value?.candidates[0]?.freeze_status).toBe('FROZEN')
    runtime.dispose()
  })

  it('creates one logical holdout request for rapid duplicate actions', async () => {
    vi.useFakeTimers()
    const pendingRequest = deferred<AiResearchV2HoldoutCommand>()
    const api = apiWithWorkbench(async () => workbenchWithCandidate('FROZEN'))
    api.requestTrustedAIResearchHoldout = vi.fn(() => pendingRequest.promise)
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand())
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const first = runtime.requestHoldout('candidate-1', 'a'.repeat(64))
    const duplicate = runtime.requestHoldout('candidate-1', 'a'.repeat(64))

    expect(api.requestTrustedAIResearchHoldout).toHaveBeenCalledTimes(1)
    expect(api.requestTrustedAIResearchHoldout).toHaveBeenCalledWith(
      'candidate-1',
      'a'.repeat(64),
      expect.stringMatching(/\S+/),
      expect.anything(),
    )
    expect(await duplicate).toBeNull()

    pendingRequest.resolve(holdoutCommand())
    expect((await first)?.id).toBe('holdout-command-1')
    expect(runtime.requestingHoldoutCandidateId.value).toBeNull()
    expect(runtime.activeHoldoutCommand.value?.status).toBe('QUEUED')
    expect(runtime.holdoutPolling.value).toBe(true)
    runtime.dispose()
  })

  it('recovers a committed holdout command from the same-run workbench after a lost ACK', async () => {
    vi.useFakeTimers()
    const initial = workbenchWithCandidate('FROZEN')
    const recovered = { ...initial, holdout_commands: [holdoutCommand()] }
    const getWorkbench = vi.fn()
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(recovered)
    const api = apiWithWorkbench(getWorkbench)
    api.requestTrustedAIResearchHoldout = vi.fn(async () => {
      throw new Error('socket closed after commit')
    })
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand('RUNNING'))
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const command = await runtime.requestHoldout('candidate-1', 'a'.repeat(64))

    expect(command?.id).toBe('holdout-command-1')
    expect(getWorkbench).toHaveBeenCalledTimes(2)
    expect(runtime.activeHoldoutCommand.value?.id).toBe('holdout-command-1')
    expect(runtime.holdoutPolling.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1)
    expect(api.getTrustedAIResearchHoldout).toHaveBeenCalledWith(
      'holdout-command-1',
      expect.anything(),
    )
    runtime.dispose()
  })

  it('reuses the original idempotency key after a 5xx reconciles to no command', async () => {
    const initial = workbenchWithCandidate('FROZEN')
    const getWorkbench = vi.fn(async () => initial)
    const keys: string[] = []
    const api = apiWithWorkbench(getWorkbench)
    api.requestTrustedAIResearchHoldout = vi.fn(
      async (_candidateId, _expectedHash, idempotencyKey) => {
        keys.push(idempotencyKey)
        if (keys.length === 1) {
          throw {
            response: {
              status: 503,
              data: { detail: 'HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN' },
            },
          }
        }
        return holdoutCommand()
      },
    )
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand('RUNNING'))
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.requestHoldout('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(getWorkbench).toHaveBeenCalledTimes(2)
    expect(await runtime.requestHoldout('candidate-1', 'a'.repeat(64))).not.toBeNull()
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
    runtime.dispose()
  })

  it('drops the idempotency key after a deterministic 4xx rejection', async () => {
    const keys: string[] = []
    const api = apiWithWorkbench(async () => workbenchWithCandidate('FROZEN'))
    api.requestTrustedAIResearchHoldout = vi.fn(
      async (_candidateId, _expectedHash, idempotencyKey) => {
        keys.push(idempotencyKey)
        if (keys.length === 1) {
          throw {
            response: {
              status: 409,
              data: { detail: 'HOLDOUT_REQUEST_CONFLICT' },
            },
          }
        }
        return holdoutCommand()
      },
    )
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand('RUNNING'))
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.requestHoldout('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(await runtime.requestHoldout('candidate-1', 'a'.repeat(64))).not.toBeNull()
    expect(keys).toHaveLength(2)
    expect(keys[1]).not.toBe(keys[0])
    runtime.dispose()
  })

  it('aborts and ignores a late holdout response after switching runs', async () => {
    const pendingRequest = deferred<AiResearchV2HoldoutCommand>()
    let requestSignal: AbortSignal | undefined
    const api = apiWithWorkbench(async (runId) => (
      runId === 'run-a' ? workbenchWithCandidate('FROZEN') : workbench('run-b')
    ))
    api.requestTrustedAIResearchHoldout = vi.fn(
      async (_candidateId, _expectedHash, _idempotencyKey, signal) => {
        requestSignal = signal
        return pendingRequest.promise
      },
    )
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const requesting = runtime.requestHoldout('candidate-1', 'a'.repeat(64))
    await runtime.load('run-b')

    expect(requestSignal?.aborted).toBe(true)
    pendingRequest.resolve(holdoutCommand())
    expect(await requesting).toBeNull()
    expect(runtime.activeRunId.value).toBe('run-b')
    expect(runtime.workbench.value?.run.id).toBe('run-b')
    expect(runtime.activeHoldoutCommand.value).toBeNull()
    runtime.dispose()
  })

  it('aborts and ignores a late holdout response after switching candidates in the same run', async () => {
    const pendingRequest = deferred<AiResearchV2HoldoutCommand>()
    let requestSignal: AbortSignal | undefined
    const selectionWorkbench: AiResearchV2Workbench = {
      ...workbenchWithCandidate('FROZEN'),
      candidates: [
        candidate('candidate-1', 'FROZEN'),
        candidate('candidate-2', 'FROZEN'),
      ],
    }
    const api = apiWithWorkbench(async () => selectionWorkbench)
    api.requestTrustedAIResearchHoldout = vi.fn(
      async (_candidateId, _expectedHash, _idempotencyKey, signal) => {
        requestSignal = signal
        return pendingRequest.promise
      },
    )
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const requesting = runtime.requestHoldout('candidate-1', 'a'.repeat(64))
    await runtime.load('run-a', 'task-a', 'candidate-2')

    expect(requestSignal?.aborted).toBe(true)
    pendingRequest.resolve(holdoutCommand())
    expect(await requesting).toBeNull()
    expect(runtime.activeRunId.value).toBe('run-a')
    expect(runtime.activeCandidateId.value).toBe('candidate-2')
    expect(runtime.activeHoldoutCommand.value).toBeNull()
    runtime.dispose()
  })

  it('aborts and ignores an in-flight holdout request when disposed', async () => {
    const pendingRequest = deferred<AiResearchV2HoldoutCommand>()
    let requestSignal: AbortSignal | undefined
    const api = apiWithWorkbench(async () => workbenchWithCandidate('FROZEN'))
    api.requestTrustedAIResearchHoldout = vi.fn(
      async (_candidateId, _expectedHash, _idempotencyKey, signal) => {
        requestSignal = signal
        return pendingRequest.promise
      },
    )
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    const requesting = runtime.requestHoldout('candidate-1', 'a'.repeat(64))
    runtime.dispose()

    expect(requestSignal?.aborted).toBe(true)
    pendingRequest.resolve(holdoutCommand())
    expect(await requesting).toBeNull()
    expect(runtime.requestingHoldoutCandidateId.value).toBeNull()
    expect(runtime.activeHoldoutCommand.value).toBeNull()
    expect(runtime.holdoutPolling.value).toBe(false)
  })

  it('rejects a holdout response whose immutable browser binding is different', async () => {
    const api = apiWithWorkbench(async () => workbenchWithCandidate('FROZEN'))
    api.requestTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand('QUEUED', {
      run_id: 'run-foreign',
    }))
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand())
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.requestHoldout('candidate-1', 'a'.repeat(64))).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID')
    expect(runtime.activeHoldoutCommand.value).toBeNull()
    expect(api.getTrustedAIResearchHoldout).not.toHaveBeenCalled()
    runtime.dispose()
  })

  it('retains only the display-safe holdout projection from an API response', async () => {
    const unsafeResponse = {
      ...holdoutCommand(),
      evaluation_id: 'sealed-evaluation-must-never-reach-browser-state',
      authorization_token: 'must-never-reach-browser-state',
      token_hash: 'must-never-reach-browser-state',
      storage_uri: 'sealed://must-never-reach-browser-state',
      evaluator_credentials: { secret: 'must-never-reach-browser-state' },
    } as unknown as AiResearchV2HoldoutCommand
    const api = apiWithWorkbench(async () => workbenchWithCandidate('FROZEN'))
    api.requestTrustedAIResearchHoldout = vi.fn(async () => unsafeResponse)
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand())
    const runtime = useAiResearchV2({ api })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.requestHoldout('candidate-1', 'a'.repeat(64))).not.toBeNull()
    const stored = JSON.stringify(runtime.workbench.value?.holdout_commands)
    expect(stored).not.toContain('authorization_token')
    expect(stored).not.toContain('token_hash')
    expect(stored).not.toContain('storage_uri')
    expect(stored).not.toContain('evaluator_credentials')
    expect(stored).not.toContain('evaluation_id')
    expect(stored).not.toContain('must-never-reach-browser-state')
    runtime.dispose()
  })

  it('rebuilds holdout-dependent browser state without unknown evaluation or package fields', async () => {
    const safeEvaluation = evaluationSummary()
    const safePackage = evidencePackage()
    const unsafeWorkbench = {
      ...workbenchWithCandidate('FROZEN'),
      browser_state_canary: 'must-never-reach-browser-state',
      run: {
        ...workbenchWithCandidate('FROZEN').run,
        authorization_token: 'must-never-reach-browser-state',
      },
      candidates: [{
        ...candidate('candidate-1', 'FROZEN'),
        failure_reason: 'must-never-reach-browser-state',
      }],
      evaluations: [{
        ...safeEvaluation,
        metrics: {
          sharpe: 9.9,
          max_drawdown: -0.01,
        },
        gate_inputs: { raw_sealed: [1, 2, 3] },
        failure_reason: 'must-never-reach-browser-state',
        token: 'must-never-reach-browser-state',
        storage_uri: 'sealed://must-never-reach-browser-state',
      }],
      evidence_packages: [{
        ...safePackage,
        metrics: { sharpe: 9.9 },
        failure_reason: 'must-never-reach-browser-state',
        token_hash: 'must-never-reach-browser-state',
        storage_uri: 'sealed://must-never-reach-browser-state',
      }],
    } as unknown as AiResearchV2Workbench
    const api = apiWithWorkbench(async () => unsafeWorkbench)
    const runtime = useAiResearchV2({ api })

    expect(await runtime.load('run-a', 'task-a', 'candidate-1')).not.toBeNull()
    expect(runtime.workbench.value?.evaluations).toEqual([safeEvaluation])
    expect(runtime.workbench.value?.evidence_packages).toEqual([safePackage])
    const stored = JSON.stringify(runtime.workbench.value)
    for (const prohibited of [
      'browser_state_canary',
      'authorization_token',
      'metrics',
      'sharpe',
      'max_drawdown',
      'gate_inputs',
      'raw_sealed',
      'failure_reason',
      'token_hash',
      'storage_uri',
      'must-never-reach-browser-state',
    ]) expect(stored).not.toContain(prohibited)
    runtime.dispose()
  })

  it('fails closed when the workbench contains a legacy non-sealed holdout label', async () => {
    const unsafeWorkbench = {
      ...workbenchWithCandidate('FROZEN'),
      evaluations: [{
        ...evaluationSummary(),
        evaluation_type: 'HOLDOUT',
      }],
    } as unknown as AiResearchV2Workbench
    const runtime = useAiResearchV2({ api: apiWithWorkbench(async () => unsafeWorkbench) })

    expect(await runtime.load('run-a', 'task-a', 'candidate-1')).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID')
    expect(runtime.workbench.value).toBeNull()
    runtime.dispose()
  })

  it('polls the same holdout command through terminal success and refreshes its package', async () => {
    vi.useFakeTimers()
    const queued = holdoutCommand('QUEUED')
    const running = holdoutCommand('RUNNING', { updated_at: '2026-09-08T00:00:01Z' })
    const succeeded = holdoutCommand('SUCCEEDED', { updated_at: '2026-09-08T00:00:02Z' })
    const terminalWorkbench: AiResearchV2Workbench = {
      ...workbenchWithCandidate('FROZEN'),
      holdout_commands: [succeeded],
      evaluations: [evaluationSummary()],
      evidence_packages: [evidencePackage()],
    }
    const getWorkbench = vi.fn()
      .mockResolvedValueOnce(workbenchWithCandidate('FROZEN'))
      .mockResolvedValueOnce(terminalWorkbench)
    const api = apiWithWorkbench(getWorkbench)
    api.requestTrustedAIResearchHoldout = vi.fn(async () => queued)
    api.getTrustedAIResearchHoldout = vi.fn()
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(succeeded)
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    await runtime.requestHoldout('candidate-1', 'a'.repeat(64))
    await vi.advanceTimersByTimeAsync(1)
    expect(runtime.activeHoldoutCommand.value?.status).toBe('RUNNING')
    await vi.advanceTimersByTimeAsync(1)

    expect(api.getTrustedAIResearchHoldout).toHaveBeenCalledTimes(2)
    expect(api.getTrustedAIResearchHoldout).toHaveBeenNthCalledWith(
      1,
      'holdout-command-1',
      expect.anything(),
    )
    expect(api.getTrustedAIResearchHoldout).toHaveBeenNthCalledWith(
      2,
      'holdout-command-1',
      expect.anything(),
    )
    expect(getWorkbench).toHaveBeenCalledTimes(2)
    expect(runtime.activeHoldoutCommand.value?.status).toBe('SUCCEEDED')
    expect(runtime.workbench.value?.evidence_packages[0]?.id).toBe('evidence-package-1')
    expect(runtime.holdoutPolling.value).toBe(false)
    runtime.dispose()
  })

  it('restores polling for the latest non-terminal holdout command in a loaded workbench', async () => {
    vi.useFakeTimers()
    const staleTerminal = holdoutCommand('FAILED', {
      id: 'holdout-command-old',
      error_code: 'HOLDOUT_OLD_FAILURE',
      updated_at: '2026-09-09T00:00:00Z',
    })
    const queued = holdoutCommand('QUEUED', { updated_at: '2026-09-08T00:00:00Z' })
    const restoredWorkbench = {
      ...workbenchWithCandidate('FROZEN'),
      holdout_commands: [staleTerminal, queued],
    }
    const api = apiWithWorkbench(async () => restoredWorkbench)
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand('RUNNING'))
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    expect(runtime.activeHoldoutCommand.value?.id).toBe('holdout-command-1')
    expect(runtime.holdoutPolling.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1)

    expect(api.getTrustedAIResearchHoldout).toHaveBeenCalledWith(
      'holdout-command-1',
      expect.anything(),
    )
    expect(runtime.activeHoldoutCommand.value?.status).toBe('RUNNING')
    runtime.dispose()
  })

  it.each(['QUEUED', 'RUNNING'] as const)(
    'restores %s holdout polling when a same-run refresh fails',
    async (status) => {
      vi.useFakeTimers()
      const preserved = {
        ...workbenchWithCandidate('FROZEN'),
        holdout_commands: [holdoutCommand(status)],
      }
      const getWorkbench = vi.fn()
        .mockResolvedValueOnce(preserved)
        .mockRejectedValueOnce(new Error('refresh unavailable'))
      const api = apiWithWorkbench(getWorkbench)
      api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand(status))
      const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })
      await runtime.load('run-a', 'task-a', 'candidate-1')

      expect(await runtime.load('run-a', 'task-a', 'candidate-1')).toBeNull()
      expect(runtime.workbench.value).not.toBeNull()
      expect(runtime.activeCandidateId.value).toBe('candidate-1')
      expect(runtime.activeHoldoutCommand.value?.status).toBe(status)
      expect(runtime.holdoutPolling.value).toBe(true)
      await vi.advanceTimersByTimeAsync(1)
      expect(api.getTrustedAIResearchHoldout).toHaveBeenCalledWith(
        'holdout-command-1',
        expect.anything(),
      )
      runtime.dispose()
    },
  )

  it('restores holdout polling after an invalid same-run candidate switch', async () => {
    vi.useFakeTimers()
    const preserved = {
      ...workbenchWithCandidate('FROZEN'),
      holdout_commands: [holdoutCommand('RUNNING')],
    }
    const api = apiWithWorkbench(async () => preserved)
    api.getTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand('RUNNING'))
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    expect(await runtime.load('run-a', 'task-a', 'candidate-missing')).toBeNull()
    expect(runtime.errorCode.value).toBe('RESEARCH_V2_CANDIDATE_SELECTION_INVALID')
    expect(runtime.activeCandidateId.value).toBe('candidate-1')
    expect(runtime.activeHoldoutCommand.value?.status).toBe('RUNNING')
    expect(runtime.holdoutPolling.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1)
    expect(api.getTrustedAIResearchHoldout).toHaveBeenCalledWith(
      'holdout-command-1',
      expect.anything(),
    )
    runtime.dispose()
  })

  it('keeps the terminal holdout error code while refreshing the same workbench', async () => {
    vi.useFakeTimers()
    const failed = holdoutCommand('FAILED', {
      error_code: 'HOLDOUT_EVALUATOR_CAPABILITY_BLOCKED',
      updated_at: '2026-09-08T00:00:01Z',
    })
    const terminalWorkbench = {
      ...workbenchWithCandidate('FROZEN'),
      holdout_commands: [failed],
    }
    const getWorkbench = vi.fn()
      .mockResolvedValueOnce(workbenchWithCandidate('FROZEN'))
      .mockResolvedValueOnce(terminalWorkbench)
    const api = apiWithWorkbench(getWorkbench)
    api.requestTrustedAIResearchHoldout = vi.fn(async () => holdoutCommand())
    api.getTrustedAIResearchHoldout = vi.fn(async () => failed)
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })
    await runtime.load('run-a', 'task-a', 'candidate-1')

    await runtime.requestHoldout('candidate-1', 'a'.repeat(64))
    await vi.advanceTimersByTimeAsync(1)

    expect(runtime.errorCode.value).toBe('HOLDOUT_EVALUATOR_CAPABILITY_BLOCKED')
    expect(runtime.activeHoldoutCommand.value?.status).toBe('FAILED')
    expect(runtime.holdoutPolling.value).toBe(false)
    expect(getWorkbench).toHaveBeenCalledTimes(2)
    runtime.dispose()
  })

  it('keeps task-detail polling independent from an in-flight event stream', async () => {
    vi.useFakeTimers()
    const pendingEvents = deferred<AiResearchV2TaskEventPage>()
    let taskSignal: AbortSignal | undefined
    let eventSignal: AbortSignal | undefined
    const getTask = vi.fn(async (_taskId: string, signal?: AbortSignal) => {
      taskSignal = signal
      return task('task-a', 'run-a')
    })
    const getEvents = vi.fn(async (_taskId: string, _cursor?: string | null, _limit?: number, signal?: AbortSignal) => {
      eventSignal = signal
      return pendingEvents.promise
    })
    const api = apiWithObservability(
      async () => workbenchWithTask('run-a', 'task-a'),
      {
        getTrustedAIResearchTask: getTask,
        listTrustedAIResearchTaskEvents: getEvents,
      },
    )
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)
    await vi.advanceTimersByTimeAsync(1)

    expect(getEvents).toHaveBeenCalledTimes(1)
    expect(getTask).toHaveBeenCalledTimes(2)
    expect(taskSignal).toBeDefined()
    expect(eventSignal).toBeDefined()
    expect(taskSignal).not.toBe(eventSignal)

    runtime.dispose()
    pendingEvents.resolve({ items: [], next_cursor: null, resume_cursor: null })
    await vi.advanceTimersByTimeAsync(0)
  })

  it('polls one active task at a time and appends only redacted event metadata', async () => {
    vi.useFakeTimers()
    const taskSnapshot = deferred<AiResearchV2Task>()
    const eventPage = deferred<AiResearchV2TaskEventPage>()
    const getTask = vi.fn(async () => taskSnapshot.promise)
    const getEvents = vi.fn(async (_taskId: string, _cursor?: string | null) => eventPage.promise)
    const getWorkbench = vi.fn(async () => workbenchWithTask('run-a', 'task-a'))
    const api = apiWithObservability(getWorkbench, {
      getTrustedAIResearchTask: getTask,
      listTrustedAIResearchTaskEvents: getEvents,
    })
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)

    expect(getTask).toHaveBeenCalledTimes(1)
    expect(getEvents).toHaveBeenCalledTimes(1)
    expect(getWorkbench).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(10)
    expect(getTask).toHaveBeenCalledTimes(1)

    taskSnapshot.resolve(task('task-a', 'run-a'))
    eventPage.resolve({
      items: [{
        id: 'event-1',
        task_id: 'task-a',
        run_id: 'run-a',
        sequence_no: 1,
        event_type: 'STAGE_STARTED',
        stage: 'CLARIFY',
        status: 'RUNNING',
        error_code: null,
        stage_attempt_id: 'attempt-1',
        trace_id: 'trace-run-a',
        created_at: '2026-09-05T00:00:01Z',
      }],
      next_cursor: null,
      resume_cursor: 'opaque-resume-cursor-1',
    })
    await vi.advanceTimersByTimeAsync(0)

    const observableRuntime = runtime as typeof runtime & {
      taskEvents: { value: SafeTaskEvent[] }
      taskEventsCursor: { value: string | null }
      taskEventsResumeCursor: { value: string | null }
    }
    expect(observableRuntime.taskEvents.value).toEqual([
      expect.objectContaining({ id: 'event-1', event_type: 'STAGE_STARTED' }),
    ])
    expect(observableRuntime.taskEventsCursor.value).toBeNull()
    expect(observableRuntime.taskEventsResumeCursor.value).toBe('opaque-resume-cursor-1')
    await vi.advanceTimersByTimeAsync(1)
    expect(getEvents.mock.calls[1]?.[1]).toBe('opaque-resume-cursor-1')
    runtime.dispose()
  })

  it('aborts a stale poll and never lets its task or run response overwrite a switched run', async () => {
    vi.useFakeTimers()
    const staleTask = deferred<AiResearchV2Task>()
    const staleEvents = deferred<AiResearchV2TaskEventPage>()
    const staleWorkbench = deferred<AiResearchV2Workbench>()
    let runACalls = 0
    let staleSignal: AbortSignal | undefined
    const getWorkbench = vi.fn(async (runId: string, signal?: AbortSignal) => {
      if (runId === 'run-b') return workbenchWithTask('run-b', 'task-b')
      runACalls += 1
      if (runACalls === 1) return workbenchWithTask('run-a', 'task-a')
      staleSignal = signal
      return staleWorkbench.promise
    })
    const api = apiWithObservability(getWorkbench, {
      getTrustedAIResearchTask: async () => staleTask.promise,
      listTrustedAIResearchTaskEvents: async () => staleEvents.promise,
    })
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)
    await runtime.load('run-b')

    expect(staleSignal?.aborted).toBe(true)

    staleTask.resolve(task('task-a', 'run-a', 'SUCCEEDED'))
    staleEvents.resolve({ items: [], next_cursor: null, resume_cursor: null })
    staleWorkbench.resolve(workbenchWithTask('run-a', 'task-a', 'SUCCEEDED'))
    await vi.advanceTimersByTimeAsync(0)

    expect(runtime.activeRunId.value).toBe('run-b')
    expect(runtime.workbench.value?.run.id).toBe('run-b')
    expect(runtime.workbench.value?.task?.id).toBe('task-b')
    expect(runtime.taskEvents.value).toEqual([])
    runtime.dispose()
  })

  it('lets B polling start when aborted A task and event requests ignore abort and settle late', async () => {
    vi.useFakeTimers()
    const staleTask = deferred<AiResearchV2Task>()
    const staleEvents = deferred<AiResearchV2TaskEventPage>()
    const staleWorkbench = deferred<AiResearchV2Workbench>()
    const currentTask = deferred<AiResearchV2Task>()
    const currentEvents = deferred<AiResearchV2TaskEventPage>()
    const currentWorkbench = deferred<AiResearchV2Workbench>()
    let runAWorkbenchCalls = 0
    let runBWorkbenchCalls = 0
    const getWorkbench = vi.fn(async (runId: string) => {
      if (runId === 'run-a') {
        runAWorkbenchCalls += 1
        return runAWorkbenchCalls === 1
          ? workbenchWithTask('run-a', 'task-a')
          : staleWorkbench.promise
      }
      runBWorkbenchCalls += 1
      return runBWorkbenchCalls === 1
        ? workbenchWithTask('run-b', 'task-b')
        : currentWorkbench.promise
    })
    const getTask = vi.fn(async (taskId: string) => (
      taskId === 'task-a' ? staleTask.promise : currentTask.promise
    ))
    const getEvents = vi.fn(async (taskId: string) => (
      taskId === 'task-a' ? staleEvents.promise : currentEvents.promise
    ))
    const api = apiWithObservability(getWorkbench, {
      getTrustedAIResearchTask: getTask,
      listTrustedAIResearchTaskEvents: getEvents,
    })
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)
    await runtime.load('run-b')
    await vi.advanceTimersByTimeAsync(1)

    expect(getTask).toHaveBeenCalledWith('task-b', expect.anything())
    expect(getEvents).toHaveBeenCalledWith('task-b', null, 50, expect.anything())

    staleTask.resolve(task('task-a', 'run-a'))
    staleEvents.resolve({ items: [], next_cursor: null, resume_cursor: null })
    staleWorkbench.resolve(workbenchWithTask('run-a', 'task-a'))
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(10)

    expect(getTask.mock.calls.filter(([taskId]) => taskId === 'task-b')).toHaveLength(1)
    expect(getEvents.mock.calls.filter(([taskId]) => taskId === 'task-b')).toHaveLength(1)

    currentTask.resolve(task('task-b', 'run-b'))
    currentEvents.resolve({ items: [], next_cursor: null, resume_cursor: null })
    currentWorkbench.resolve(workbenchWithTask('run-b', 'task-b'))
    await vi.advanceTimersByTimeAsync(0)
    runtime.dispose()
  })

  it('aborts the old polling lifecycle before cancellation and starts a fresh owned poll', async () => {
    vi.useFakeTimers()
    const pendingTask = deferred<AiResearchV2Task>()
    const pendingEvents = deferred<AiResearchV2TaskEventPage>()
    let pollingSignal: AbortSignal | undefined
    const getTask = vi.fn(async (_taskId: string, signal?: AbortSignal) => {
      pollingSignal = signal
      return pendingTask.promise
    })
    const cancelTask = vi.fn(async () => task('task-a', 'run-a', 'RUNNING'))
    const api = apiWithObservability(
      async () => workbenchWithTask('run-a', 'task-a'),
      {
        getTrustedAIResearchTask: getTask,
        listTrustedAIResearchTaskEvents: async () => pendingEvents.promise,
      },
    )
    api.cancelTrustedAIResearchTask = cancelTask
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)
    await runtime.cancelCurrent()

    expect(pollingSignal?.aborted).toBe(true)
    expect(cancelTask).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(20)
    expect(getTask).toHaveBeenCalledTimes(2)

    pendingTask.resolve(task('task-a', 'run-a', 'RUNNING'))
    pendingEvents.resolve({ items: [], next_cursor: null, resume_cursor: null })
    await vi.advanceTimersByTimeAsync(0)
    runtime.dispose()
  })

  it('drops a cancellation response that is not bound to the selected task and run', async () => {
    const api = apiWithObservability(
      async () => workbenchWithTask('run-a', 'task-a'),
      {
        getTrustedAIResearchTask: async () => task('task-a', 'run-a'),
        listTrustedAIResearchTaskEvents: async () => ({
          items: [],
          next_cursor: null,
          resume_cursor: null,
        }),
      },
    )
    api.cancelTrustedAIResearchTask = async () => task('task-other', 'run-a', 'CANCELLED')
    const runtime = useAiResearchV2({ api })

    await runtime.load('run-a')
    const cancelled = await runtime.cancelCurrent()

    expect(cancelled).toBeNull()
    expect(runtime.workbench.value?.task?.id).toBe('task-a')
    runtime.dispose()
  })

  it('aborts an active task poll when the composable is disposed', async () => {
    vi.useFakeTimers()
    const pendingTask = deferred<AiResearchV2Task>()
    const pendingEvents = deferred<AiResearchV2TaskEventPage>()
    let pollingSignal: AbortSignal | undefined
    let eventSignal: AbortSignal | undefined
    const api = apiWithObservability(
      async () => workbenchWithTask('run-a', 'task-a'),
      {
        getTrustedAIResearchTask: async (_taskId, signal) => {
          pollingSignal = signal
          return pendingTask.promise
        },
        listTrustedAIResearchTaskEvents: async (_taskId, _cursor, _limit, signal) => {
          eventSignal = signal
          return pendingEvents.promise
        },
      },
    )
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)
    runtime.dispose()

    expect(pollingSignal?.aborted).toBe(true)
    expect(eventSignal?.aborted).toBe(true)
    pendingTask.resolve(task('task-a', 'run-a', 'RUNNING'))
    pendingEvents.resolve({ items: [], next_cursor: null, resume_cursor: null })
    await vi.advanceTimersByTimeAsync(0)
  })

  it('stops polling as soon as the server reports a terminal task state', async () => {
    vi.useFakeTimers()
    const getTask = vi.fn(async () => task('task-a', 'run-a', 'SUCCEEDED'))
    const getEvents = vi.fn(async () => ({ items: [], next_cursor: null, resume_cursor: null }))
    const getWorkbench = vi.fn(async () => workbenchWithTask('run-a', 'task-a'))
    const api = apiWithObservability(getWorkbench, {
      getTrustedAIResearchTask: getTask,
      listTrustedAIResearchTaskEvents: getEvents,
    })
    const runtime = useAiResearchV2({ api, pollIntervalMs: 1 })

    await runtime.load('run-a')
    await vi.advanceTimersByTimeAsync(1)
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(20)

    expect(getTask).toHaveBeenCalledTimes(1)
    runtime.dispose()
  })

  it('keeps the server error code from the standard API error envelope', async () => {
    const api = apiWithWorkbench(async () => {
      throw { response: { data: { message: 'AI_RESEARCH_PROTOCOL_V2_DISABLED' } } }
    })
    const runtime = useAiResearchV2({ api })

    await runtime.load('run-disabled')

    expect(runtime.errorCode.value).toBe('AI_RESEARCH_PROTOCOL_V2_DISABLED')
    runtime.dispose()
  })

  it('rechecks an existing launch binding instead of recreating a research family', async () => {
    const calls: AiResearchV2DataPrecheckRequest[] = []
    const api = apiWithWorkbench(async () => workbench('not-used'))
    api.createTrustedAIResearchDataPrecheck = async (data) => {
      calls.push(data)
      return passedPrecheck('precheck-retry')
    }
    const runtime = useAiResearchV2({ api })
    runtime.preparedRun.value = {
      hypothesisId: 'hypothesis-1',
      datasetId: 'dataset-1',
      epochId: 'epoch-1',
      profileId: 'isolated-profile',
      profileVersion: 'v1',
      promotionPolicyVersion: 'promotion-v1',
      requestJson: {
        hypothesis_content_hash: 'a'.repeat(64),
        dataset_snapshot_id: 'dataset-1',
        experiment_epoch_id: 'epoch-1',
      },
      idempotencyKey: 'operation-1',
      precheck: {
        ...passedPrecheck('precheck-failed'),
        status: 'BLOCKED',
        reason_code: 'BLOCKED_TOPOLOGY_CAPABILITY:sandbox_runner',
      },
    }

    const retried = await runtime.retryPreparedPrecheck()

    expect(calls).toEqual([
      {
        hypothesis_version_id: 'hypothesis-1',
        dataset_snapshot_id: 'dataset-1',
        experiment_epoch_id: 'epoch-1',
        profile_id: 'isolated-profile',
        profile_version: 'v1',
        promotion_policy_version: 'promotion-v1',
        request_json: {
          hypothesis_content_hash: 'a'.repeat(64),
          dataset_snapshot_id: 'dataset-1',
          experiment_epoch_id: 'epoch-1',
        },
      },
    ])
    expect(retried?.precheck.id).toBe('precheck-retry')
    expect(runtime.preparedRun.value?.precheck.status).toBe('PASS')
    runtime.dispose()
  })
})

function passedPrecheck(id: string): AiResearchV2DataPrecheck {
  return {
    id,
    hypothesis_version_id: 'hypothesis-1',
    dataset_snapshot_id: 'dataset-1',
    experiment_epoch_id: 'epoch-1',
    profile_id: 'isolated-profile',
    profile_version: 'v1',
    promotion_policy_version: 'promotion-v1',
    status: 'PASS',
    input_hash: 'c'.repeat(64),
    evidence_hash: 'd'.repeat(64),
    checked_at: '2026-09-05T00:00:00Z',
    expires_at: '2099-09-05T00:15:00Z',
    details: {},
  }
}
