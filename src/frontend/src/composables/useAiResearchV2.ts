import { getCurrentScope, onScopeDispose, ref } from 'vue'

import { strategyApi } from '@/api/strategy'
import { isAiResearchV2CandidateFreezeIdentityComplete } from '@/types/aiResearchV2'
import type {
  AiResearchV2Candidate,
  AiResearchV2CandidateFreezeRequest,
  AiResearchV2DataPrecheck,
  AiResearchV2DataPrecheckRequest,
  AiResearchV2DatasetCreateRequest,
  AiResearchV2EvaluationSummary,
  AiResearchV2EvidencePackageSummary,
  AiResearchV2HoldoutCommand,
  AiResearchV2RunSubmission,
  AiResearchV2RunSubmitRequest,
  AiResearchV2Task,
  AiResearchV2TaskEvent,
  AiResearchV2TaskEventPage,
  AiResearchV2TaskPage,
  AiResearchV2Workbench,
} from '@/types/aiResearchV2'

export interface AiResearchV2Api {
  createTrustedAIResearchHypothesis(
    payload: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<{ id: string; content_hash: string; canonical_payload: Record<string, unknown> }>
  confirmTrustedAIResearchHypothesis(
    hypothesisId: string,
    requestHash: string,
    signal?: AbortSignal,
  ): Promise<{ id: string; content_hash: string }>
  createTrustedAIResearchDataset(
    data: AiResearchV2DatasetCreateRequest,
    signal?: AbortSignal,
  ): Promise<{ id: string }>
  createTrustedAIResearchEpoch(
    data: {
      hypothesis_version_id: string
      search_budget: Record<string, unknown>
      dataset_policy_version: string
    },
    signal?: AbortSignal,
  ): Promise<{ id: string }>
  createTrustedAIResearchDataPrecheck(
    data: AiResearchV2DataPrecheckRequest,
    signal?: AbortSignal,
  ): Promise<AiResearchV2DataPrecheck>
  submitTrustedAIResearchRun(
    data: AiResearchV2RunSubmitRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2RunSubmission>
  getTrustedAIResearchWorkbench(runId: string, signal?: AbortSignal): Promise<AiResearchV2Workbench>
  listTrustedAIResearchTasks(
    cursor?: string | null,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<AiResearchV2TaskPage>
  getTrustedAIResearchTask(taskId: string, signal?: AbortSignal): Promise<AiResearchV2Task>
  listTrustedAIResearchTaskEvents(
    taskId: string,
    cursor?: string | null,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<AiResearchV2TaskEventPage>
  cancelTrustedAIResearchTask(taskId: string, signal?: AbortSignal): Promise<AiResearchV2Task>
  freezeTrustedAIResearchCandidate(
    candidateId: string,
    data: AiResearchV2CandidateFreezeRequest,
    signal?: AbortSignal,
  ): Promise<AiResearchV2Candidate>
  requestTrustedAIResearchHoldout(
    candidateId: string,
    expectedHash: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2HoldoutCommand>
  getTrustedAIResearchHoldout(
    commandId: string,
    signal?: AbortSignal,
  ): Promise<AiResearchV2HoldoutCommand>
}

export interface TrustedResearchStartInput {
  hypothesisPayload: Record<string, unknown>
  dataset: AiResearchV2DatasetCreateRequest
  searchBudget: Record<string, unknown>
  profileId: string
  profileVersion: string
  promotionPolicyVersion: string
  idempotencyKey: string
}

export interface AiResearchV2Draft {
  id: string
  contentHash: string
  payload: Record<string, unknown>
}

export interface AiResearchV2PreparedRun {
  hypothesisId: string
  datasetId: string
  epochId: string
  profileId: string
  profileVersion: string
  promotionPolicyVersion: string
  requestJson: Record<string, unknown>
  idempotencyKey: string
  precheck: AiResearchV2DataPrecheck
}

export interface UseAiResearchV2Options {
  api?: AiResearchV2Api
  /** Testable local cadence; production callers should normally use the default. */
  pollIntervalMs?: number
}

const DEFAULT_TASK_POLL_INTERVAL_MS = 2_000
const TASK_HISTORY_PAGE_SIZE = 20
const TASK_EVENT_PAGE_SIZE = 50
const TERMINAL_TASK_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'])
const NON_TERMINAL_HOLDOUT_STATUSES = new Set(['QUEUED', 'RUNNING', 'RECONCILING'])
const TERMINAL_HOLDOUT_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'])
type WorkbenchValidator = (workbench: AiResearchV2Workbench) => string | null

interface HoldoutRequestIntent {
  runId: string
  candidateId: string
  candidateHash: string
  experimentEpochId: string
  idempotencyKey: string
}

/**
 * Keeps the evidence workbench attached to exactly one v2 run.
 *
 * Abort signals reduce wasted browser work, while a monotonically increasing
 * generation prevents a late HTTP response from ever overwriting a newer run.
 */
export function useAiResearchV2(options: UseAiResearchV2Options = {}) {
  const api = options.api ?? strategyApi
  const workbench = ref<AiResearchV2Workbench | null>(null)
  const activeRunId = ref<string | null>(null)
  const activeTaskId = ref<string | null>(null)
  const activeCandidateId = ref<string | null>(null)
  const draft = ref<AiResearchV2Draft | null>(null)
  const preparedRun = ref<AiResearchV2PreparedRun | null>(null)
  const precheckExpired = ref(false)
  const loading = ref(false)
  const submitting = ref(false)
  const errorCode = ref<string | null>(null)
  const taskEvents = ref<AiResearchV2TaskEvent[]>([])
  const taskEventsCursor = ref<string | null>(null)
  const taskEventsResumeCursor = ref<string | null>(null)
  const taskHistory = ref<AiResearchV2Task[]>([])
  const taskHistoryNextCursor = ref<string | null>(null)
  const taskHistoryLoading = ref(false)
  const polling = ref(false)
  const eventPolling = ref(false)
  const freezingCandidateId = ref<string | null>(null)
  const requestingHoldoutCandidateId = ref<string | null>(null)
  const activeHoldoutCommand = ref<AiResearchV2HoldoutCommand | null>(null)
  const holdoutPolling = ref(false)

  let generation = 0
  let controller: AbortController | null = null
  let precheckExpiryTimer: ReturnType<typeof setTimeout> | null = null
  let taskPollingGeneration = 0
  let taskPollingController: AbortController | null = null
  let taskPollingTimer: ReturnType<typeof setTimeout> | null = null
  let taskPollingInFlightOwner: symbol | null = null
  let taskPollingTaskId: string | null = null
  let eventPollingGeneration = 0
  let eventPollingController: AbortController | null = null
  let eventPollingTimer: ReturnType<typeof setTimeout> | null = null
  let eventPollingInFlightOwner: symbol | null = null
  let eventPollingTaskId: string | null = null
  let taskHistoryPollingGeneration = 0
  let taskHistoryRequestGeneration = 0
  let taskHistoryController: AbortController | null = null
  let taskHistoryTimer: ReturnType<typeof setTimeout> | null = null
  let taskHistoryInFlight = false
  let taskHistoryPollingActive = false
  let taskHistoryAutoRefreshPaused = false
  let candidateFreezeGeneration = 0
  let candidateFreezeController: AbortController | null = null
  let holdoutGeneration = 0
  let holdoutController: AbortController | null = null
  let holdoutTimer: ReturnType<typeof setTimeout> | null = null
  let holdoutInFlightOwner: symbol | null = null
  let holdoutRequestIntent: HoldoutRequestIntent | null = null
  const pollIntervalMs = normalizedPollInterval(options.pollIntervalMs)

  function beginRequest(): { generation: number; signal?: AbortSignal } {
    stopTaskPolling()
    stopEventPolling()
    stopHoldoutLifecycle(true)
    generation += 1
    controller?.abort()
    controller = typeof AbortController === 'undefined' ? null : new AbortController()
    return { generation, signal: controller?.signal }
  }

  function isCurrent(runId: string | null, requestGeneration: number): boolean {
    return activeRunId.value === runId && generation === requestGeneration
  }

  async function load(
    runId: string,
    expectedTaskId?: string | null,
    expectedCandidateId?: string | null,
    validateWorkbench?: WorkbenchValidator,
  ): Promise<AiResearchV2Workbench | null> {
    if (holdoutRequestIntent !== null && holdoutRequestIntent.runId !== runId) {
      holdoutRequestIntent = null
    }
    const preservedWorkbench = workbench.value?.run.id === runId ? workbench.value : null
    const preservedTaskId = preservedWorkbench === null ? null : activeTaskId.value
    const preservedCandidateId = preservedWorkbench === null ? null : activeCandidateId.value
    const request = beginRequest()
    activeRunId.value = runId
    if (preservedWorkbench === null) {
      activeTaskId.value = null
      activeCandidateId.value = null
      workbench.value = null
      clearTaskObservability()
    }
    loading.value = true
    errorCode.value = null
    let accepted = false
    try {
      const received = await api.getTrustedAIResearchWorkbench(runId, request.signal)
      if (!isCurrent(runId, request.generation)) return null
      const next = safeWorkbenchHoldoutProjection(received)
      if (next === null) {
        errorCode.value = 'RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID'
        return null
      }
      if (!isWorkbenchForSelection(next, runId, expectedTaskId)) {
        errorCode.value = 'RESEARCH_V2_WORKBENCH_SELECTION_INVALID'
        return null
      }
      const candidateId = expectedCandidateId ?? null
      if (candidateId !== null && !workbenchHasCandidate(next, candidateId)) {
        errorCode.value = 'RESEARCH_V2_CANDIDATE_SELECTION_INVALID'
        return null
      }
      const validationError = validateWorkbench?.(next) ?? null
      if (validationError !== null) {
        errorCode.value = validationError
        return null
      }
      workbench.value = next
      activeTaskId.value = next.task?.id ?? null
      activeCandidateId.value = candidateId
      if (
        holdoutRequestIntent !== null
        && (
          holdoutRequestIntent.runId !== runId
          || (candidateId !== null && holdoutRequestIntent.candidateId !== candidateId)
        )
      ) holdoutRequestIntent = null
      accepted = true
      startTaskPolling(runId, next.task)
      startEventPolling(runId, next.task)
      restoreHoldoutLifecycle(next)
      return next
    } catch (caught) {
      if (isCurrent(runId, request.generation)) {
        errorCode.value = apiErrorCode(caught)
      }
      return null
    } finally {
      if (isCurrent(runId, request.generation)) {
        loading.value = false
        if (!accepted && preservedWorkbench !== null && workbench.value === preservedWorkbench) {
          activeTaskId.value = preservedTaskId
          activeCandidateId.value = preservedCandidateId
          startTaskPolling(runId, preservedWorkbench.task)
          startEventPolling(runId, preservedWorkbench.task, true)
          restoreHoldoutLifecycle(preservedWorkbench)
        }
      }
    }
  }

  async function createDraft(payload: Record<string, unknown>): Promise<AiResearchV2Draft | null> {
    const request = beginRequest()
    activeRunId.value = null
    activeTaskId.value = null
    activeCandidateId.value = null
    workbench.value = null
    clearTaskObservability()
    clearPreparedRun()
    draft.value = null
    submitting.value = true
    errorCode.value = null
    try {
      const created = await api.createTrustedAIResearchHypothesis(payload, request.signal)
      if (generation !== request.generation) return null
      const next = {
        id: created.id,
        contentHash: created.content_hash,
        payload: structuredClone(created.canonical_payload),
      }
      draft.value = next
      return next
    } catch (caught) {
      if (generation === request.generation) {
        errorCode.value = apiErrorCode(caught)
      }
      return null
    } finally {
      if (generation === request.generation) {
        submitting.value = false
      }
    }
  }

  async function confirmDraftAndPrepare(
    input: TrustedResearchStartInput,
  ): Promise<AiResearchV2PreparedRun | null> {
    const pendingDraft = draft.value
    if (pendingDraft === null) {
      errorCode.value = 'RESEARCH_HYPOTHESIS_DRAFT_REQUIRED'
      return null
    }
    const request = beginRequest()
    submitting.value = true
    errorCode.value = null
    try {
      const hypothesis = await api.confirmTrustedAIResearchHypothesis(
        pendingDraft.id,
        pendingDraft.contentHash,
        request.signal,
      )
      if (generation !== request.generation) return null
      const dataset = await api.createTrustedAIResearchDataset(input.dataset, request.signal)
      if (generation !== request.generation) return null
      const epoch = await api.createTrustedAIResearchEpoch(
        {
          hypothesis_version_id: hypothesis.id,
          search_budget: input.searchBudget,
          dataset_policy_version: input.dataset.dataset_policy_version,
        },
        request.signal,
      )
      if (generation !== request.generation) return null
      const requestJson = {
        hypothesis_content_hash: hypothesis.content_hash,
        dataset_snapshot_id: dataset.id,
        experiment_epoch_id: epoch.id,
      }
      const precheck = await api.createTrustedAIResearchDataPrecheck(
        {
          hypothesis_version_id: hypothesis.id,
          dataset_snapshot_id: dataset.id,
          experiment_epoch_id: epoch.id,
          profile_id: input.profileId,
          profile_version: input.profileVersion,
          promotion_policy_version: input.promotionPolicyVersion,
          request_json: requestJson,
        },
        request.signal,
      )
      if (generation !== request.generation) return null
      const next: AiResearchV2PreparedRun = {
        hypothesisId: hypothesis.id,
        datasetId: dataset.id,
        epochId: epoch.id,
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        promotionPolicyVersion: input.promotionPolicyVersion,
        requestJson,
        idempotencyKey: input.idempotencyKey,
        precheck,
      }
      preparedRun.value = next
      schedulePrecheckExpiry(next)
      if (precheck.status !== 'PASS') errorCode.value = precheck.reason_code || 'RESEARCH_TASK_PRECHECK_NOT_PASSED'
      return next
    } catch (caught) {
      if (generation === request.generation) {
        errorCode.value = apiErrorCode(caught)
      }
      return null
    } finally {
      if (generation === request.generation) {
        submitting.value = false
      }
    }
  }

  async function startPreparedRun(): Promise<AiResearchV2Workbench | null> {
    const prepared = preparedRun.value
    if (prepared === null) {
      errorCode.value = 'RESEARCH_TASK_PRECHECK_REQUIRED'
      return null
    }
    if (prepared.precheck.status !== 'PASS') {
      errorCode.value = prepared.precheck.reason_code || 'RESEARCH_TASK_PRECHECK_NOT_PASSED'
      return null
    }
    if (isPreparedPrecheckExpired()) {
      errorCode.value = 'RESEARCH_TASK_PRECHECK_EXPIRED'
      return null
    }
    const request = beginRequest()
    submitting.value = true
    errorCode.value = null
    try {
      const submission = await api.submitTrustedAIResearchRun(
        {
          hypothesis_version_id: prepared.hypothesisId,
          dataset_snapshot_id: prepared.datasetId,
          experiment_epoch_id: prepared.epochId,
          profile_id: prepared.profileId,
          profile_version: prepared.profileVersion,
          promotion_policy_version: prepared.promotionPolicyVersion,
          request_json: prepared.requestJson,
          precheck_id: prepared.precheck.id,
        },
        prepared.idempotencyKey,
        request.signal,
      )
      if (generation !== request.generation) return null
      activeRunId.value = submission.run.id
      activeCandidateId.value = null
      const received = await api.getTrustedAIResearchWorkbench(submission.run.id, request.signal)
      if (!isCurrent(submission.run.id, request.generation)) return null
      const next = safeWorkbenchHoldoutProjection(received)
      if (next === null) {
        errorCode.value = 'RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID'
        return null
      }
      const taskSnapshot = next.task ?? submission.task
      const nextWorkbench = { ...next, task: taskSnapshot }
      if (!isWorkbenchForSelection(nextWorkbench, submission.run.id, taskSnapshot.id)) return null
      workbench.value = nextWorkbench
      activeTaskId.value = taskSnapshot.id
      clearTaskObservability()
      draft.value = null
      clearPreparedRun()
      startTaskPolling(submission.run.id, taskSnapshot)
      startEventPolling(submission.run.id, taskSnapshot)
      restoreHoldoutLifecycle(nextWorkbench)
      return nextWorkbench
    } catch (caught) {
      if (generation === request.generation) {
        errorCode.value = apiErrorCode(caught)
      }
      return null
    } finally {
      if (generation === request.generation) {
        submitting.value = false
      }
    }
  }

  async function retryPreparedPrecheck(): Promise<AiResearchV2PreparedRun | null> {
    const prepared = preparedRun.value
    if (prepared === null) {
      errorCode.value = 'RESEARCH_TASK_PRECHECK_REQUIRED'
      return null
    }
    const request = beginRequest()
    submitting.value = true
    errorCode.value = null
    try {
      const precheck = await api.createTrustedAIResearchDataPrecheck(
        {
          hypothesis_version_id: prepared.hypothesisId,
          dataset_snapshot_id: prepared.datasetId,
          experiment_epoch_id: prepared.epochId,
          profile_id: prepared.profileId,
          profile_version: prepared.profileVersion,
          promotion_policy_version: prepared.promotionPolicyVersion,
          request_json: prepared.requestJson,
        },
        request.signal,
      )
      if (generation !== request.generation) return null
      const next = { ...prepared, precheck }
      preparedRun.value = next
      schedulePrecheckExpiry(next)
      if (precheck.status !== 'PASS') errorCode.value = precheck.reason_code || 'RESEARCH_TASK_PRECHECK_NOT_PASSED'
      return next
    } catch (caught) {
      if (generation === request.generation) errorCode.value = apiErrorCode(caught)
      return null
    } finally {
      if (generation === request.generation) submitting.value = false
    }
  }

  async function confirmDraftAndStart(
    input: TrustedResearchStartInput,
  ): Promise<AiResearchV2Workbench | null> {
    const prepared = await confirmDraftAndPrepare(input)
    return prepared === null ? null : startPreparedRun()
  }

  function invalidateDraft(): void {
    if (draft.value !== null || preparedRun.value !== null) {
      generation += 1
      controller?.abort()
      controller = null
    }
    draft.value = null
    clearPreparedRun()
  }

  function clearPreparedRun(): void {
    if (precheckExpiryTimer !== null) clearTimeout(precheckExpiryTimer)
    precheckExpiryTimer = null
    preparedRun.value = null
    precheckExpired.value = false
  }

  function schedulePrecheckExpiry(prepared: AiResearchV2PreparedRun): void {
    if (precheckExpiryTimer !== null) clearTimeout(precheckExpiryTimer)
    precheckExpired.value = false
    const expiresAt = Date.parse(prepared.precheck.expires_at)
    if (!Number.isFinite(expiresAt)) {
      precheckExpired.value = true
      return
    }
    const delay = Math.max(0, expiresAt - Date.now())
    precheckExpiryTimer = setTimeout(() => {
      if (preparedRun.value?.precheck.id === prepared.precheck.id) precheckExpired.value = true
    }, Math.min(delay, 2_147_483_647))
  }

  function isPreparedPrecheckExpired(): boolean {
    const prepared = preparedRun.value
    if (prepared === null) return true
    const expiresAt = Date.parse(prepared.precheck.expires_at)
    return precheckExpired.value || !Number.isFinite(expiresAt) || expiresAt <= Date.now()
  }

  async function cancelCurrent(): Promise<AiResearchV2Task | null> {
    const taskId = workbench.value?.task?.id
    const runId = activeRunId.value
    if (!taskId || !runId) return null
    const request = beginRequest()
    activeRunId.value = runId
    loading.value = true
    try {
      const task = await api.cancelTrustedAIResearchTask(taskId, request.signal)
      if (!isCurrent(runId, request.generation)) return null
      if (task.id !== taskId || task.run_id !== runId) return null
      const currentWorkbench = workbench.value
      if (currentWorkbench === null) return null
      workbench.value = { ...currentWorkbench, task }
      activeTaskId.value = task.id
      startTaskPolling(runId, task)
      startEventPolling(runId, task, true)
      return task
    } catch (caught) {
      if (isCurrent(runId, request.generation)) errorCode.value = apiErrorCode(caught)
      return null
    } finally {
      if (isCurrent(runId, request.generation)) loading.value = false
    }
  }

  async function freezeCandidate(
    candidateId: string,
    expectedCandidateHash: string,
  ): Promise<AiResearchV2Candidate | null> {
    if (freezingCandidateId.value !== null) return null
    const selectedWorkbench = workbench.value
    const runId = activeRunId.value
    const candidate = selectedWorkbench?.candidates.find((item) => item.id === candidateId)
    if (selectedWorkbench === null || runId === null || candidate === undefined) {
      errorCode.value = 'RESEARCH_V2_CANDIDATE_SELECTION_INVALID'
      return null
    }
    if (
      candidate.candidate_hash !== expectedCandidateHash
      || !/^[0-9a-f]{64}$/.test(expectedCandidateHash)
    ) {
      errorCode.value = 'RESEARCH_CANDIDATE_HASH_MISMATCH'
      return null
    }
    if (
      selectedWorkbench.run.id !== runId
      || !isAiResearchV2CandidateFreezeIdentityComplete(
        candidate,
        candidateFreezeIdentity(selectedWorkbench),
      )
    ) {
      errorCode.value = 'RESEARCH_CANDIDATE_FREEZE_IDENTITY_INCOMPLETE'
      return null
    }
    if (candidate.freeze_status === 'FROZEN') return candidate

    const operation = ++candidateFreezeGeneration
    const requestController = typeof AbortController === 'undefined' ? null : new AbortController()
    candidateFreezeController = requestController
    freezingCandidateId.value = candidateId
    errorCode.value = null
    try {
      const frozen = await api.freezeTrustedAIResearchCandidate(
        candidateId,
        { expected_candidate_hash: expectedCandidateHash },
        requestController?.signal,
      )
      if (
        candidateFreezeGeneration !== operation
        || requestController?.signal.aborted
      ) return null
      if (
        frozen.id !== candidateId
        || frozen.run_id !== runId
        || frozen.candidate_hash !== expectedCandidateHash
        || frozen.freeze_status !== 'FROZEN'
        || !isAiResearchV2CandidateFreezeIdentityComplete(
          frozen,
          candidateFreezeIdentity(selectedWorkbench),
        )
        || !candidateFreezeBindingsMatch(candidate, frozen)
      ) {
        if (candidateFreezeGeneration === operation) {
          errorCode.value = 'RESEARCH_CANDIDATE_FREEZE_RESPONSE_INVALID'
        }
        return null
      }
      if (activeRunId.value !== runId) return frozen

      const selectedTaskId = activeTaskId.value
      const selectedCandidateId = activeCandidateId.value
      const refreshed = await load(
        runId,
        selectedTaskId,
        selectedCandidateId,
        (nextWorkbench) => {
          const refreshedCandidate = nextWorkbench.candidates.find(
            (item) => item.id === candidateId,
          )
          if (
            nextWorkbench.dataset?.id !== selectedWorkbench.dataset?.id
            || nextWorkbench.dataset?.content_hash !== selectedWorkbench.dataset?.content_hash
            || refreshedCandidate?.candidate_hash !== expectedCandidateHash
            || refreshedCandidate.freeze_status !== 'FROZEN'
            || !isAiResearchV2CandidateFreezeIdentityComplete(
              refreshedCandidate,
              candidateFreezeIdentity(nextWorkbench),
            )
            || !candidateFreezeBindingsMatch(candidate, refreshedCandidate)
          ) return 'RESEARCH_CANDIDATE_FREEZE_REFRESH_INVALID'
          return null
        },
      )
      if (
        candidateFreezeGeneration !== operation
        || requestController?.signal.aborted
      ) return null
      if (refreshed === null) return activeRunId.value === runId ? null : frozen
      return frozen
    } catch (caught) {
      if (
        candidateFreezeGeneration === operation
        && activeRunId.value === runId
        && !requestController?.signal.aborted
      ) {
        errorCode.value = apiErrorCode(caught)
      }
      return null
    } finally {
      if (candidateFreezeController === requestController) candidateFreezeController = null
      if (candidateFreezeGeneration === operation) freezingCandidateId.value = null
    }
  }

  async function requestHoldout(
    candidateId: string,
    expectedCandidateHash: string,
  ): Promise<AiResearchV2HoldoutCommand | null> {
    if (requestingHoldoutCandidateId.value !== null) return null
    const selectedWorkbench = workbench.value
    const runId = activeRunId.value
    const candidate = selectedWorkbench?.candidates.find((item) => item.id === candidateId)
    if (selectedWorkbench === null || runId === null || candidate === undefined) {
      errorCode.value = 'RESEARCH_V2_CANDIDATE_SELECTION_INVALID'
      return null
    }
    if (
      candidate.freeze_status !== 'FROZEN'
      || candidate.candidate_hash !== expectedCandidateHash
      || !SHA256_HEX_PATTERN.test(expectedCandidateHash)
      || selectedWorkbench.run.id !== runId
      || !isAiResearchV2CandidateFreezeIdentityComplete(
        candidate,
        candidateFreezeIdentity(selectedWorkbench),
      )
    ) {
      errorCode.value = 'RESEARCH_HOLDOUT_CANDIDATE_BINDING_INVALID'
      return null
    }
    if (selectedWorkbench.holdout_commands.some((command) => (
      command.candidate_id === candidate.id
      || command.experiment_epoch_id === candidate.experiment_epoch_id
    ))) {
      clearHoldoutRequestIntent(runId, candidateId, expectedCandidateHash)
      errorCode.value = 'RESEARCH_HOLDOUT_ALREADY_REQUESTED'
      return null
    }

    stopHoldoutLifecycle(true)
    const operation = ++holdoutGeneration
    const requestController = typeof AbortController === 'undefined' ? null : new AbortController()
    holdoutController = requestController
    requestingHoldoutCandidateId.value = candidateId
    errorCode.value = null
    const requestIntent = matchingHoldoutRequestIntent(
      holdoutRequestIntent,
      runId,
      candidate,
      expectedCandidateHash,
    ) ?? {
      runId,
      candidateId,
      candidateHash: expectedCandidateHash,
      experimentEpochId: candidate.experiment_epoch_id,
      idempotencyKey: newHoldoutIdempotencyKey(),
    }
    holdoutRequestIntent = requestIntent
    try {
      const received = await api.requestTrustedAIResearchHoldout(
        candidateId,
        expectedCandidateHash,
        requestIntent.idempotencyKey,
        requestController?.signal,
      )
      if (!isCurrentHoldoutOperation(operation, runId) || requestController?.signal.aborted) {
        return null
      }
      const command = safeHoldoutCommand(received)
      if (command === null || !holdoutCommandMatches(command, selectedWorkbench, candidate)) {
        return await reconcileAmbiguousHoldoutRequest(
          operation,
          runId,
          candidate,
          requestController,
          'RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID',
        )
      }
      if (holdoutRequestIntent === requestIntent) holdoutRequestIntent = null
      applyHoldoutCommand(command)
      if (isNonTerminalHoldoutStatus(command.status)) {
        holdoutPolling.value = true
        scheduleHoldoutPoll(operation, runId, command.id)
      } else {
        applyTerminalHoldoutError(command)
        await refreshWorkbenchForTerminalHoldout(operation, runId, command)
      }
      return command
    } catch (caught) {
      if (isCurrentHoldoutOperation(operation, runId) && !requestController?.signal.aborted) {
        if (isDeterministicClientError(caught)) {
          if (holdoutRequestIntent === requestIntent) holdoutRequestIntent = null
          errorCode.value = apiErrorCode(caught)
        } else {
          return await reconcileAmbiguousHoldoutRequest(
            operation,
            runId,
            candidate,
            requestController,
            apiErrorCode(caught),
          )
        }
      }
      return null
    } finally {
      if (holdoutGeneration === operation) {
        requestingHoldoutCandidateId.value = null
        if (!holdoutPolling.value && holdoutController === requestController) {
          holdoutController = null
        }
      }
    }
  }

  async function reconcileAmbiguousHoldoutRequest(
    operation: number,
    runId: string,
    requestedCandidate: AiResearchV2Candidate,
    requestController: AbortController | null,
    unresolvedErrorCode: string,
  ): Promise<AiResearchV2HoldoutCommand | null> {
    try {
      const received = await api.getTrustedAIResearchWorkbench(runId, requestController?.signal)
      if (!isCurrentHoldoutOperation(operation, runId) || requestController?.signal.aborted) {
        return null
      }
      const nextWorkbench = safeWorkbenchHoldoutProjection(received)
      const candidate = nextWorkbench?.candidates.find(
        (item) => item.id === requestedCandidate.id,
      )
      if (
        nextWorkbench === null
        || nextWorkbench.run.id !== runId
        || candidate === undefined
        || !candidateFreezeBindingsMatch(requestedCandidate, candidate)
      ) {
        errorCode.value = unresolvedErrorCode
        return null
      }
      workbench.value = nextWorkbench
      activeTaskId.value = nextWorkbench.task?.id ?? null
      const command = latestHoldoutCommand(nextWorkbench.holdout_commands.filter((item) => (
        item.candidate_id === candidate.id
        && item.experiment_epoch_id === candidate.experiment_epoch_id
        && holdoutCommandMatches(item, nextWorkbench, candidate)
      )))
      if (command === null) {
        errorCode.value = unresolvedErrorCode
        return null
      }
      holdoutRequestIntent = null
      activeHoldoutCommand.value = command
      errorCode.value = null
      if (isNonTerminalHoldoutStatus(command.status)) {
        holdoutPolling.value = true
        scheduleHoldoutPoll(operation, runId, command.id)
      } else {
        holdoutPolling.value = false
        applyTerminalHoldoutError(command)
      }
      return command
    } catch {
      if (isCurrentHoldoutOperation(operation, runId) && !requestController?.signal.aborted) {
        errorCode.value = unresolvedErrorCode
      }
      return null
    }
  }

  function clearHoldoutRequestIntent(
    runId: string,
    candidateId: string,
    candidateHash: string,
  ): void {
    if (
      holdoutRequestIntent?.runId === runId
      && holdoutRequestIntent.candidateId === candidateId
      && holdoutRequestIntent.candidateHash === candidateHash
    ) holdoutRequestIntent = null
  }

  function restoreHoldoutLifecycle(nextWorkbench: AiResearchV2Workbench): void {
    stopHoldoutLifecycle(true)
    const latestNonTerminal = latestHoldoutCommand(
      nextWorkbench.holdout_commands.filter((command) => (
        isNonTerminalHoldoutStatus(command.status)
      )),
    )
    const latest = latestNonTerminal ?? latestHoldoutCommand(nextWorkbench.holdout_commands)
    if (latest === null) return
    if (
      holdoutRequestIntent?.runId === latest.run_id
      && holdoutRequestIntent.candidateId === latest.candidate_id
      && holdoutRequestIntent.candidateHash === latest.candidate_hash
      && holdoutRequestIntent.experimentEpochId === latest.experiment_epoch_id
    ) holdoutRequestIntent = null
    activeHoldoutCommand.value = latest
    if (!isNonTerminalHoldoutStatus(latest.status)) {
      applyTerminalHoldoutError(latest)
      return
    }
    const operation = ++holdoutGeneration
    holdoutController = typeof AbortController === 'undefined' ? null : new AbortController()
    holdoutPolling.value = true
    scheduleHoldoutPoll(operation, nextWorkbench.run.id, latest.id)
  }

  function stopHoldoutLifecycle(clearCommand: boolean): void {
    holdoutGeneration += 1
    if (holdoutTimer !== null) clearTimeout(holdoutTimer)
    holdoutTimer = null
    holdoutController?.abort()
    holdoutController = null
    holdoutInFlightOwner = null
    requestingHoldoutCandidateId.value = null
    holdoutPolling.value = false
    if (clearCommand) activeHoldoutCommand.value = null
  }

  function isCurrentHoldoutOperation(operation: number, runId: string): boolean {
    return holdoutGeneration === operation && activeRunId.value === runId
  }

  function scheduleHoldoutPoll(operation: number, runId: string, commandId: string): void {
    if (!isCurrentHoldoutPoll(operation, runId, commandId)) return
    if (holdoutTimer !== null) clearTimeout(holdoutTimer)
    holdoutTimer = setTimeout(() => {
      holdoutTimer = null
      void pollHoldout(operation, runId, commandId)
    }, pollIntervalMs)
  }

  function isCurrentHoldoutPoll(operation: number, runId: string, commandId: string): boolean {
    return isCurrentHoldoutOperation(operation, runId)
      && activeHoldoutCommand.value?.id === commandId
      && holdoutPolling.value
  }

  async function pollHoldout(operation: number, runId: string, commandId: string): Promise<void> {
    if (!isCurrentHoldoutPoll(operation, runId, commandId)) return
    if (holdoutInFlightOwner !== null) {
      scheduleHoldoutPoll(operation, runId, commandId)
      return
    }
    const requestOwner = Symbol('ai-research-holdout-poll')
    holdoutInFlightOwner = requestOwner
    const requestController = holdoutController
    let continuePolling = true
    try {
      const received = await api.getTrustedAIResearchHoldout(commandId, requestController?.signal)
      if (!isCurrentHoldoutPoll(operation, runId, commandId)) return
      const nextWorkbench = workbench.value
      const candidate = nextWorkbench?.candidates.find(
        (item) => item.id === activeHoldoutCommand.value?.candidate_id,
      )
      const command = safeHoldoutCommand(received)
      if (
        nextWorkbench === null
        || candidate === undefined
        || command === null
        || command.id !== commandId
        || !holdoutCommandMatches(command, nextWorkbench, candidate)
      ) {
        errorCode.value = 'RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID'
        continuePolling = false
        return
      }
      applyHoldoutCommand(command)
      continuePolling = isNonTerminalHoldoutStatus(command.status)
      if (!continuePolling) {
        holdoutPolling.value = false
        applyTerminalHoldoutError(command)
        await refreshWorkbenchForTerminalHoldout(operation, runId, command)
      }
    } catch (caught) {
      if (isCurrentHoldoutOperation(operation, runId) && !requestController?.signal.aborted) {
        errorCode.value = apiErrorCode(caught)
      }
    } finally {
      if (holdoutInFlightOwner === requestOwner) holdoutInFlightOwner = null
      if (isCurrentHoldoutOperation(operation, runId)) {
        if (continuePolling && activeHoldoutCommand.value?.id === commandId) {
          scheduleHoldoutPoll(operation, runId, commandId)
        } else {
          holdoutPolling.value = false
          if (holdoutController === requestController) holdoutController = null
        }
      }
    }
  }

  async function refreshWorkbenchForTerminalHoldout(
    operation: number,
    runId: string,
    terminalCommand: AiResearchV2HoldoutCommand,
  ): Promise<void> {
    const failureCode = terminalHoldoutErrorCode(terminalCommand)
    try {
      const received = await api.getTrustedAIResearchWorkbench(runId, holdoutController?.signal)
      if (!isCurrentHoldoutOperation(operation, runId)) return
      const nextWorkbench = safeWorkbenchHoldoutProjection(received)
      const candidate = nextWorkbench?.candidates.find(
        (item) => item.id === terminalCommand.candidate_id,
      )
      const refreshedCommand = nextWorkbench?.holdout_commands.find(
        (command) => command.id === terminalCommand.id,
      )
      if (
        nextWorkbench === null
        || candidate === undefined
        || refreshedCommand === undefined
        || refreshedCommand.status !== terminalCommand.status
        || !isTerminalHoldoutStatus(refreshedCommand.status)
        || !holdoutCommandMatches(refreshedCommand, nextWorkbench, candidate)
      ) {
        if (failureCode === null) {
          errorCode.value = 'RESEARCH_HOLDOUT_TERMINAL_REFRESH_INVALID'
        }
        return
      }
      workbench.value = nextWorkbench
      activeTaskId.value = nextWorkbench.task?.id ?? null
      activeHoldoutCommand.value = refreshedCommand
    } catch (caught) {
      if (isCurrentHoldoutOperation(operation, runId) && failureCode === null) {
        errorCode.value = apiErrorCode(caught)
      }
    }
  }

  function applyHoldoutCommand(command: AiResearchV2HoldoutCommand): void {
    activeHoldoutCommand.value = command
    const selectedWorkbench = workbench.value
    if (selectedWorkbench === null || selectedWorkbench.run.id !== command.run_id) return
    const commands = [...selectedWorkbench.holdout_commands]
    const existingIndex = commands.findIndex((item) => item.id === command.id)
    if (existingIndex === -1) commands.push(command)
    else commands[existingIndex] = command
    workbench.value = { ...selectedWorkbench, holdout_commands: commands }
  }

  function applyTerminalHoldoutError(command: AiResearchV2HoldoutCommand): void {
    const code = terminalHoldoutErrorCode(command)
    if (code !== null) errorCode.value = code
  }

  function clearTaskObservability(): void {
    taskEvents.value = []
    taskEventsCursor.value = null
    taskEventsResumeCursor.value = null
  }

  /**
   * The task list is an owner-scoped, cursor-paginated projection. It has a
   * separate request lifecycle from the selected task and its event stream.
   */
  function startTaskHistoryPolling(): void {
    stopTaskHistoryPolling()
    const session = ++taskHistoryPollingGeneration
    taskHistoryPollingActive = true
    taskHistoryAutoRefreshPaused = false
    void pollTaskHistory(session)
  }

  function stopTaskHistoryPolling(): void {
    taskHistoryPollingActive = false
    taskHistoryPollingGeneration += 1
    taskHistoryRequestGeneration += 1
    if (taskHistoryTimer !== null) clearTimeout(taskHistoryTimer)
    taskHistoryTimer = null
    taskHistoryController?.abort()
    taskHistoryController = null
    taskHistoryInFlight = false
    taskHistoryLoading.value = false
  }

  function scheduleTaskHistoryPoll(session: number): void {
    if (
      !taskHistoryPollingActive
      || taskHistoryAutoRefreshPaused
      || taskHistoryPollingGeneration !== session
    ) return
    if (taskHistoryTimer !== null) clearTimeout(taskHistoryTimer)
    taskHistoryTimer = setTimeout(() => {
      taskHistoryTimer = null
      void pollTaskHistory(session)
    }, pollIntervalMs)
  }

  async function pollTaskHistory(session: number): Promise<void> {
    if (
      !taskHistoryPollingActive
      || taskHistoryAutoRefreshPaused
      || taskHistoryPollingGeneration !== session
    ) return
    await fetchTaskHistory(true, session)
    if (taskHistoryPollingGeneration === session) scheduleTaskHistoryPoll(session)
  }

  async function loadTaskHistory(): Promise<AiResearchV2TaskPage | null> {
    taskHistoryAutoRefreshPaused = false
    if (taskHistoryTimer !== null) clearTimeout(taskHistoryTimer)
    taskHistoryTimer = null
    const page = await fetchTaskHistory(true)
    if (page !== null && taskHistoryPollingActive) {
      scheduleTaskHistoryPoll(taskHistoryPollingGeneration)
    }
    return page
  }

  async function loadMoreTaskHistory(): Promise<AiResearchV2TaskPage | null> {
    if (taskHistoryNextCursor.value === null) return null
    const page = await fetchTaskHistory(false)
    if (page !== null) {
      // A first-page refresh has no safe cursor for the already loaded tail.
      // Preserve the user's paginated snapshot until they explicitly refresh it.
      taskHistoryAutoRefreshPaused = true
      if (taskHistoryTimer !== null) clearTimeout(taskHistoryTimer)
      taskHistoryTimer = null
    }
    return page
  }

  async function fetchTaskHistory(
    reset: boolean,
    pollingSession?: number,
  ): Promise<AiResearchV2TaskPage | null> {
    if (taskHistoryInFlight) return null
    const cursor = reset ? null : taskHistoryNextCursor.value
    if (!reset && cursor === null) return null
    const requestGeneration = ++taskHistoryRequestGeneration
    const requestController = typeof AbortController === 'undefined' ? null : new AbortController()
    taskHistoryController = requestController
    taskHistoryInFlight = true
    taskHistoryLoading.value = true
    try {
      const page = await api.listTrustedAIResearchTasks(
        cursor,
        TASK_HISTORY_PAGE_SIZE,
        requestController?.signal,
      )
      if (
        requestGeneration !== taskHistoryRequestGeneration
        || (pollingSession !== undefined && taskHistoryPollingGeneration !== pollingSession)
      ) {
        return null
      }
      taskHistory.value = mergeTaskHistory(taskHistory.value, page.items, reset)
      taskHistoryNextCursor.value = page.next_cursor
      return page
    } catch (caught) {
      if (
        requestGeneration === taskHistoryRequestGeneration
        && (pollingSession === undefined || taskHistoryPollingGeneration === pollingSession)
        && !requestController?.signal.aborted
      ) {
        errorCode.value = apiErrorCode(caught)
      }
      return null
    } finally {
      if (taskHistoryController === requestController) taskHistoryController = null
      if (requestGeneration === taskHistoryRequestGeneration) {
        taskHistoryInFlight = false
        taskHistoryLoading.value = false
      }
    }
  }

  /**
   * Task snapshots and event pages deliberately use different abort domains:
   * an event page can be slow without delaying the task FSM refresh.
   */
  function startTaskPolling(runId: string, taskSnapshot?: AiResearchV2Task | null): void {
    stopTaskPolling()
    if (
      taskSnapshot === null
      || taskSnapshot === undefined
      || taskSnapshot.run_id !== runId
      || isTerminalTaskStatus(taskSnapshot.status)
    ) {
      return
    }
    activeTaskId.value = taskSnapshot.id
    taskPollingTaskId = taskSnapshot.id
    const session = ++taskPollingGeneration
    polling.value = true
    scheduleTaskPoll(session, runId, taskSnapshot.id)
  }

  function stopTaskPolling(): void {
    taskPollingGeneration += 1
    if (taskPollingTimer !== null) clearTimeout(taskPollingTimer)
    taskPollingTimer = null
    taskPollingController?.abort()
    taskPollingController = null
    taskPollingInFlightOwner = null
    taskPollingTaskId = null
    polling.value = false
  }

  function scheduleTaskPoll(session: number, runId: string, taskId: string): void {
    if (!isCurrentTaskPollingSession(session, runId, taskId)) return
    if (taskPollingTimer !== null) clearTimeout(taskPollingTimer)
    taskPollingTimer = setTimeout(() => {
      taskPollingTimer = null
      void pollTask(session, runId, taskId)
    }, pollIntervalMs)
  }

  function isCurrentTaskPollingSession(session: number, runId: string, taskId: string): boolean {
    return taskPollingGeneration === session
      && taskPollingTaskId === taskId
      && activeRunId.value === runId
      && activeTaskId.value === taskId
  }

  async function pollTask(session: number, runId: string, taskId: string): Promise<void> {
    if (!isCurrentTaskPollingSession(session, runId, taskId)) return
    if (taskPollingInFlightOwner !== null) {
      scheduleTaskPoll(session, runId, taskId)
      return
    }

    const requestOwner = Symbol('ai-research-task-poll')
    taskPollingInFlightOwner = requestOwner
    const requestController = typeof AbortController === 'undefined' ? null : new AbortController()
    taskPollingController = requestController
    let continuePolling = true
    try {
      const [nextTask, receivedWorkbench] = await Promise.all([
        api.getTrustedAIResearchTask(taskId, requestController?.signal),
        api.getTrustedAIResearchWorkbench(runId, requestController?.signal),
      ])
      if (!isCurrentTaskPollingSession(session, runId, taskId)) return
      const nextWorkbench = safeWorkbenchHoldoutProjection(receivedWorkbench)
      if (
        nextWorkbench === null
        || nextTask.id !== taskId
        || nextTask.run_id !== runId
        || nextWorkbench.run.id !== runId
      ) {
        if (nextWorkbench === null) {
          errorCode.value = 'RESEARCH_HOLDOUT_COMMAND_BINDING_INVALID'
        }
        return
      }

      workbench.value = { ...nextWorkbench, task: nextTask }
      activeTaskId.value = taskId
      continuePolling = !isTerminalTaskStatus(nextTask.status)
    } catch (caught) {
      if (isCurrentTaskPollingSession(session, runId, taskId) && !requestController?.signal.aborted) {
        errorCode.value = apiErrorCode(caught)
      }
    } finally {
      if (taskPollingController === requestController) taskPollingController = null
      if (taskPollingInFlightOwner === requestOwner) taskPollingInFlightOwner = null
      if (isCurrentTaskPollingSession(session, runId, taskId)) {
        if (!continuePolling) {
          stopTaskPolling()
        } else {
          scheduleTaskPoll(session, runId, taskId)
        }
      }
    }
  }

  function startEventPolling(
    runId: string,
    taskSnapshot?: AiResearchV2Task | null,
    preserveEvents = false,
  ): void {
    stopEventPolling()
    if (
      taskSnapshot === null
      || taskSnapshot === undefined
      || taskSnapshot.run_id !== runId
    ) {
      return
    }
    if (!preserveEvents) clearTaskObservability()
    activeTaskId.value = taskSnapshot.id
    eventPollingTaskId = taskSnapshot.id
    const session = ++eventPollingGeneration
    eventPolling.value = true
    scheduleEventPoll(session, runId, taskSnapshot.id)
  }

  function stopEventPolling(): void {
    eventPollingGeneration += 1
    if (eventPollingTimer !== null) clearTimeout(eventPollingTimer)
    eventPollingTimer = null
    eventPollingController?.abort()
    eventPollingController = null
    eventPollingInFlightOwner = null
    eventPollingTaskId = null
    eventPolling.value = false
  }

  function scheduleEventPoll(
    session: number,
    runId: string,
    taskId: string,
    delay = pollIntervalMs,
  ): void {
    if (!isCurrentEventPollingSession(session, runId, taskId)) return
    if (eventPollingTimer !== null) clearTimeout(eventPollingTimer)
    eventPollingTimer = setTimeout(() => {
      eventPollingTimer = null
      void pollTaskEvents(session, runId, taskId)
    }, delay)
  }

  function isCurrentEventPollingSession(session: number, runId: string, taskId: string): boolean {
    return eventPollingGeneration === session
      && eventPollingTaskId === taskId
      && activeRunId.value === runId
      && activeTaskId.value === taskId
  }

  async function pollTaskEvents(session: number, runId: string, taskId: string): Promise<void> {
    if (!isCurrentEventPollingSession(session, runId, taskId)) return
    if (eventPollingInFlightOwner !== null) {
      scheduleEventPoll(session, runId, taskId)
      return
    }

    const requestOwner = Symbol('ai-research-event-poll')
    eventPollingInFlightOwner = requestOwner
    const requestController = typeof AbortController === 'undefined' ? null : new AbortController()
    eventPollingController = requestController
    let continuePolling = true
    let hasBacklog = false
    try {
      const page = await api.listTrustedAIResearchTaskEvents(
        taskId,
        taskEventsCursor.value ?? taskEventsResumeCursor.value,
        TASK_EVENT_PAGE_SIZE,
        requestController?.signal,
      )
      if (!isCurrentEventPollingSession(session, runId, taskId)) return
      appendTaskEvents(page, runId, taskId)
      hasBacklog = taskEventsCursor.value !== null
      const selectedTask = workbench.value?.task
      continuePolling = hasBacklog || Boolean(
        selectedTask
        && selectedTask.id === taskId
        && selectedTask.run_id === runId
        && !isTerminalTaskStatus(selectedTask.status),
      )
    } catch (caught) {
      if (isCurrentEventPollingSession(session, runId, taskId) && !requestController?.signal.aborted) {
        errorCode.value = apiErrorCode(caught)
      }
    } finally {
      if (eventPollingController === requestController) eventPollingController = null
      if (eventPollingInFlightOwner === requestOwner) eventPollingInFlightOwner = null
      if (isCurrentEventPollingSession(session, runId, taskId)) {
        if (!continuePolling) {
          stopEventPolling()
        } else {
          scheduleEventPoll(session, runId, taskId, hasBacklog ? 0 : pollIntervalMs)
        }
      }
    }
  }

  function appendTaskEvents(page: AiResearchV2TaskEventPage, runId: string, taskId: string): void {
    const seenEventIds = new Set(taskEvents.value.map((event) => event.id))
    const newEvents = page.items.filter((event) => (
      event.task_id === taskId
      && event.run_id === runId
      && !seenEventIds.has(event.id)
    ))
    if (newEvents.length > 0) taskEvents.value = [...taskEvents.value, ...newEvents]
    taskEventsCursor.value = page.next_cursor
    taskEventsResumeCursor.value = page.resume_cursor
  }

  async function selectTask(taskSnapshot: AiResearchV2Task): Promise<AiResearchV2Workbench | null> {
    return load(taskSnapshot.run_id, taskSnapshot.id)
  }

  function resetSelection(): void {
    stopTaskPolling()
    stopEventPolling()
    stopHoldoutLifecycle(true)
    generation += 1
    controller?.abort()
    controller = null
    activeRunId.value = null
    activeTaskId.value = null
    activeCandidateId.value = null
    workbench.value = null
    clearTaskObservability()
    errorCode.value = null
    loading.value = false
    holdoutRequestIntent = null
  }

  function dispose(): void {
    stopTaskPolling()
    stopEventPolling()
    stopTaskHistoryPolling()
    stopHoldoutLifecycle(true)
    generation += 1
    controller?.abort()
    controller = null
    candidateFreezeGeneration += 1
    candidateFreezeController?.abort()
    candidateFreezeController = null
    freezingCandidateId.value = null
    draft.value = null
    clearPreparedRun()
    loading.value = false
    submitting.value = false
    holdoutRequestIntent = null
  }

  if (getCurrentScope()) onScopeDispose(dispose)

  return {
    workbench,
    activeRunId,
    activeTaskId,
    activeCandidateId,
    draft,
    preparedRun,
    precheckExpired,
    loading,
    submitting,
    errorCode,
    taskEvents,
    taskEventsCursor,
    taskEventsResumeCursor,
    taskHistory,
    taskHistoryNextCursor,
    taskHistoryLoading,
    polling,
    eventPolling,
    freezingCandidateId,
    requestingHoldoutCandidateId,
    activeHoldoutCommand,
    holdoutPolling,
    load,
    selectTask,
    resetSelection,
    startTaskHistoryPolling,
    loadTaskHistory,
    loadMoreTaskHistory,
    createDraft,
    confirmDraftAndPrepare,
    confirmDraftAndStart,
    retryPreparedPrecheck,
    startPreparedRun,
    invalidateDraft,
    cancelCurrent,
    freezeCandidate,
    requestHoldout,
    dispose,
  }
}

const SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/

function safeWorkbenchHoldoutProjection(
  workbench: AiResearchV2Workbench,
): AiResearchV2Workbench | null {
  if (
    !Array.isArray(workbench.candidates)
    || !Array.isArray(workbench.holdout_commands)
    || !Array.isArray(workbench.evaluations)
    || !Array.isArray(workbench.evidence_packages)
  ) return null
  const commands: AiResearchV2HoldoutCommand[] = []
  for (const received of workbench.holdout_commands) {
    const command = safeHoldoutCommand(received)
    const candidate = command === null
      ? undefined
      : workbench.candidates.find((item) => item.id === command.candidate_id)
    if (
      command === null
      || candidate === undefined
      || !holdoutCommandMatches(command, workbench, candidate)
    ) return null
    commands.push(command)
  }
  const evaluations: AiResearchV2EvaluationSummary[] = []
  for (const received of workbench.evaluations) {
    const evaluation = safeEvaluationSummary(received)
    if (evaluation === null) return null
    evaluations.push(evaluation)
  }
  const evidencePackages: AiResearchV2EvidencePackageSummary[] = []
  for (const received of workbench.evidence_packages) {
    const evidencePackage = safeEvidencePackageSummary(received)
    if (evidencePackage === null) return null
    evidencePackages.push(evidencePackage)
  }
  return {
    run: safeRunProjection(workbench.run),
    task: workbench.task === null || workbench.task === undefined
      ? workbench.task
      : safeTaskProjection(workbench.task),
    hypothesis: workbench.hypothesis,
    dataset: workbench.dataset === null || workbench.dataset === undefined
      ? workbench.dataset
      : safeDatasetProjection(workbench.dataset),
    candidates: workbench.candidates.map(safeCandidateProjection),
    holdout_commands: commands,
    ledger: workbench.ledger,
    model_invocations: workbench.model_invocations,
    evaluations,
    gates: workbench.gates,
    decisions: workbench.decisions,
    governance_decisions: workbench.governance_decisions,
    evidence_packages: evidencePackages,
    evidence_class: workbench.evidence_class,
  }
}

function safeRunProjection(run: AiResearchV2Workbench['run']): AiResearchV2Workbench['run'] {
  return {
    id: run.id,
    hypothesis_version_id: run.hypothesis_version_id,
    dataset_snapshot_id: run.dataset_snapshot_id,
    data_precheck_id: run.data_precheck_id,
    experiment_epoch_id: run.experiment_epoch_id,
    protocol_version: run.protocol_version,
    status: run.status,
    stage_cursor: run.stage_cursor,
    promotion_policy_version: run.promotion_policy_version,
    request_hash: run.request_hash,
    capability_profile_id: run.capability_profile_id,
    capability_profile_version: run.capability_profile_version,
    capability_evidence_hash: run.capability_evidence_hash,
    trace_id: run.trace_id,
    created_at: run.created_at,
    started_at: run.started_at,
    completed_at: run.completed_at,
  }
}

function safeTaskProjection(task: AiResearchV2Task): AiResearchV2Task {
  return {
    id: task.id,
    run_id: task.run_id,
    status: task.status,
    stage_cursor: task.stage_cursor,
    error_code: task.error_code,
    trace_id: task.trace_id,
    cancel_requested_at: task.cancel_requested_at,
    attempt_count: task.attempt_count,
    created_at: task.created_at,
    started_at: task.started_at,
    completed_at: task.completed_at,
  }
}

function safeDatasetProjection(
  dataset: NonNullable<AiResearchV2Workbench['dataset']>,
): NonNullable<AiResearchV2Workbench['dataset']> {
  return {
    id: dataset.id,
    dataset_policy_version: dataset.dataset_policy_version,
    partition_kind: dataset.partition_kind,
    instrument_manifest: dataset.instrument_manifest,
    split_manifest: dataset.split_manifest,
    source_manifest: dataset.source_manifest,
    execution_policy: dataset.execution_policy,
    point_in_time_cutoff: dataset.point_in_time_cutoff,
    content_hash: dataset.content_hash,
  }
}

function safeCandidateProjection(candidate: AiResearchV2Candidate): AiResearchV2Candidate {
  return {
    id: candidate.id,
    run_id: candidate.run_id,
    experiment_epoch_id: candidate.experiment_epoch_id,
    source_version_id: candidate.source_version_id,
    dataset_snapshot_id: candidate.dataset_snapshot_id,
    code_artifact_id: candidate.code_artifact_id,
    dependency_artifact_id: candidate.dependency_artifact_id,
    candidate_hash: candidate.candidate_hash,
    environment_hash: candidate.environment_hash,
    cost_model_hash: candidate.cost_model_hash,
    params: candidate.params,
    freeze_status: candidate.freeze_status,
    frozen_at: candidate.frozen_at,
  }
}

function safeEvaluationSummary(
  received: AiResearchV2EvaluationSummary,
): AiResearchV2EvaluationSummary | null {
  const value = received as unknown as Record<string, unknown>
  const requiredStrings = [
    'id',
    'experiment_epoch_id',
    'candidate_id',
    'dataset_snapshot_id',
    'evaluation_type',
    'evaluator_identity',
    'evaluator_version',
    'policy_version',
  ] as const
  const statuses = new Set(['PENDING', 'RUNNING', 'PASSED', 'REJECTED', 'FAILED', 'EXPIRED'])
  const evaluationTypes = new Set(['SEALED_HOLDOUT', 'ITERATION_VALIDATION'])
  if (
    requiredStrings.some((key) => typeof value[key] !== 'string' || value[key].length === 0)
    || !evaluationTypes.has(value.evaluation_type as string)
    || typeof value.status !== 'string'
    || !statuses.has(value.status)
    || (value.completed_at !== null && value.completed_at !== undefined
      && (typeof value.completed_at !== 'string' || value.completed_at.length === 0))
  ) return null
  return {
    id: value.id as string,
    experiment_epoch_id: value.experiment_epoch_id as string,
    candidate_id: value.candidate_id as string,
    dataset_snapshot_id: value.dataset_snapshot_id as string,
    evaluation_type: value.evaluation_type as AiResearchV2EvaluationSummary['evaluation_type'],
    evaluator_identity: value.evaluator_identity as string,
    evaluator_version: value.evaluator_version as string,
    policy_version: value.policy_version as string,
    status: value.status as AiResearchV2EvaluationSummary['status'],
    completed_at: value.completed_at as string | null | undefined ?? null,
  }
}

function safeEvidencePackageSummary(
  received: AiResearchV2EvidencePackageSummary,
): AiResearchV2EvidencePackageSummary | null {
  const value = received as unknown as Record<string, unknown>
  const requiredStrings = [
    'id',
    'candidate_id',
    'promotion_policy_version',
    'created_at',
  ] as const
  if (
    requiredStrings.some((key) => typeof value[key] !== 'string' || value[key].length === 0)
    || (value.status !== 'ACTIVE' && value.status !== 'WITHDRAWN')
    || typeof value.gate_input_evidence_hash !== 'string'
    || !SHA256_HEX_PATTERN.test(value.gate_input_evidence_hash)
    || typeof value.manifest_hash !== 'string'
    || !SHA256_HEX_PATTERN.test(value.manifest_hash)
    || typeof value.approval_binding_hash !== 'string'
    || !SHA256_HEX_PATTERN.test(value.approval_binding_hash)
    || !isOptionalIdentifier(value.command_id)
    || !isOptionalIdentifier(value.evaluation_id)
  ) return null
  return {
    id: value.id as string,
    candidate_id: value.candidate_id as string,
    command_id: value.command_id as string | null | undefined ?? null,
    evaluation_id: value.evaluation_id as string | null | undefined ?? null,
    promotion_policy_version: value.promotion_policy_version as string,
    gate_input_evidence_hash: value.gate_input_evidence_hash,
    manifest_hash: value.manifest_hash,
    approval_binding_hash: value.approval_binding_hash,
    status: value.status,
    created_at: value.created_at as string,
  }
}

function isOptionalIdentifier(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === 'string' && value.length > 0)
}

function safeHoldoutCommand(received: AiResearchV2HoldoutCommand): AiResearchV2HoldoutCommand | null {
  const value = received as unknown as Record<string, unknown>
  const status = value.status
  const stage = value.stage
  if (
    typeof status !== 'string'
    || (!isNonTerminalHoldoutStatus(status) && !isTerminalHoldoutStatus(status))
    || (stage !== 'REQUEST_HOLDOUT' && stage !== 'HOLDOUT_PENDING')
  ) return null
  const requiredStrings = [
    'id',
    'run_id',
    'candidate_id',
    'experiment_epoch_id',
    'dataset_snapshot_id',
    'policy_version',
    'evaluator_identity',
    'capability_profile_id',
    'capability_profile_version',
    'created_at',
    'updated_at',
  ] as const
  if (requiredStrings.some((key) => typeof value[key] !== 'string' || value[key].length === 0)) {
    return null
  }
  if (
    typeof value.candidate_hash !== 'string'
    || !SHA256_HEX_PATTERN.test(value.candidate_hash)
    || typeof value.capability_evidence_hash !== 'string'
    || !SHA256_HEX_PATTERN.test(value.capability_evidence_hash)
    || typeof value.request_hash !== 'string'
    || !SHA256_HEX_PATTERN.test(value.request_hash)
    || (value.error_code !== null && value.error_code !== undefined
      && (typeof value.error_code !== 'string' || value.error_code.length === 0))
  ) return null

  return {
    id: value.id as string,
    run_id: value.run_id as string,
    status: status as AiResearchV2HoldoutCommand['status'],
    stage,
    candidate_id: value.candidate_id as string,
    candidate_hash: value.candidate_hash,
    experiment_epoch_id: value.experiment_epoch_id as string,
    dataset_snapshot_id: value.dataset_snapshot_id as string,
    policy_version: value.policy_version as string,
    evaluator_identity: value.evaluator_identity as string,
    capability_profile_id: value.capability_profile_id as string,
    capability_profile_version: value.capability_profile_version as string,
    capability_evidence_hash: value.capability_evidence_hash,
    error_code: value.error_code as string | null | undefined,
    request_hash: value.request_hash,
    created_at: value.created_at as string,
    updated_at: value.updated_at as string,
  }
}

function holdoutCommandMatches(
  command: AiResearchV2HoldoutCommand,
  workbench: AiResearchV2Workbench,
  candidate: AiResearchV2Candidate,
): boolean {
  return command.run_id === workbench.run.id
    && command.candidate_id === candidate.id
    && command.candidate_hash === candidate.candidate_hash
    && command.experiment_epoch_id === candidate.experiment_epoch_id
    && command.dataset_snapshot_id === candidate.dataset_snapshot_id
    && command.policy_version === workbench.run.promotion_policy_version
    && command.capability_profile_id === workbench.run.capability_profile_id
    && command.capability_profile_version === workbench.run.capability_profile_version
    && command.capability_evidence_hash === workbench.run.capability_evidence_hash
}

function latestHoldoutCommand(
  commands: AiResearchV2HoldoutCommand[],
): AiResearchV2HoldoutCommand | null {
  return commands.reduce<AiResearchV2HoldoutCommand | null>((latest, command) => {
    if (latest === null) return command
    const latestTimestamp = Date.parse(latest.updated_at)
    const commandTimestamp = Date.parse(command.updated_at)
    if (Number.isFinite(commandTimestamp) && commandTimestamp > latestTimestamp) return command
    if (commandTimestamp === latestTimestamp && command.id > latest.id) return command
    return latest
  }, null)
}

function isNonTerminalHoldoutStatus(status: string): boolean {
  return NON_TERMINAL_HOLDOUT_STATUSES.has(status)
}

function isTerminalHoldoutStatus(status: string): boolean {
  return TERMINAL_HOLDOUT_STATUSES.has(status)
}

function terminalHoldoutErrorCode(command: AiResearchV2HoldoutCommand): string | null {
  if (command.status === 'SUCCEEDED') return null
  if (!isTerminalHoldoutStatus(command.status)) return null
  return command.error_code || `RESEARCH_HOLDOUT_${command.status}`
}

function newHoldoutIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.()
    || `holdout-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function matchingHoldoutRequestIntent(
  intent: HoldoutRequestIntent | null,
  runId: string,
  candidate: AiResearchV2Candidate,
  candidateHash: string,
): HoldoutRequestIntent | null {
  if (
    intent?.runId !== runId
    || intent.candidateId !== candidate.id
    || intent.candidateHash !== candidateHash
    || intent.experimentEpochId !== candidate.experiment_epoch_id
  ) return null
  return intent
}

function normalizedPollInterval(value: number | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : DEFAULT_TASK_POLL_INTERVAL_MS
}

function isTerminalTaskStatus(status: string): boolean {
  return TERMINAL_TASK_STATUSES.has(status)
}

function isWorkbenchForSelection(
  workbench: AiResearchV2Workbench,
  runId: string,
  expectedTaskId?: string | null,
): boolean {
  if (workbench.run.id !== runId) return false
  const task = workbench.task
  if (task === null || task === undefined) return !expectedTaskId
  return task.run_id === runId && (!expectedTaskId || task.id === expectedTaskId)
}

function workbenchHasCandidate(workbench: AiResearchV2Workbench, candidateId: string): boolean {
  return workbench.candidates.some(
    (candidate) => candidate.id === candidateId && candidate.run_id === workbench.run.id,
  )
}

function candidateFreezeIdentity(workbench: AiResearchV2Workbench) {
  return {
    runId: workbench.run.id,
    runExperimentEpochId: workbench.run.experiment_epoch_id,
    runDatasetSnapshotId: workbench.run.dataset_snapshot_id,
    datasetSnapshotId: workbench.dataset?.id,
    datasetContentHash: workbench.dataset?.content_hash,
  }
}

function candidateFreezeBindingsMatch(
  expected: AiResearchV2Candidate,
  actual: AiResearchV2Candidate,
): boolean {
  return expected.id === actual.id
    && expected.run_id === actual.run_id
    && expected.experiment_epoch_id === actual.experiment_epoch_id
    && expected.source_version_id === actual.source_version_id
    && expected.dataset_snapshot_id === actual.dataset_snapshot_id
    && expected.code_artifact_id === actual.code_artifact_id
    && expected.dependency_artifact_id === actual.dependency_artifact_id
    && expected.candidate_hash === actual.candidate_hash
    && expected.environment_hash === actual.environment_hash
    && expected.cost_model_hash === actual.cost_model_hash
    && JSON.stringify(canonicalJson(expected.params)) === JSON.stringify(canonicalJson(actual.params))
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

function mergeTaskHistory(
  existing: AiResearchV2Task[],
  incoming: AiResearchV2Task[],
  reset: boolean,
): AiResearchV2Task[] {
  const merged = reset ? [] : [...existing]
  const positions = new Map(merged.map((task, index) => [task.id, index]))
  for (const task of incoming) {
    const existingIndex = positions.get(task.id)
    if (existingIndex === undefined) {
      positions.set(task.id, merged.length)
      merged.push(task)
    } else {
      merged[existingIndex] = task
    }
  }
  return merged
}

function apiErrorCode(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const payload = (error as {
      response?: { data?: { detail?: unknown; message?: unknown; error?: unknown } }
    }).response?.data
    if (typeof payload?.detail === 'string') return payload.detail
    if (typeof payload?.message === 'string') return payload.message
    if (typeof payload?.error === 'string') return payload.error
  }
  return error instanceof Error && error.message ? error.message : 'RESEARCH_V2_REQUEST_FAILED'
}

function isDeterministicClientError(error: unknown): boolean {
  if (!error || typeof error !== 'object' || !('response' in error)) return false
  const status = (error as { response?: { status?: unknown } }).response?.status
  return typeof status === 'number' && status >= 400 && status < 500
}
