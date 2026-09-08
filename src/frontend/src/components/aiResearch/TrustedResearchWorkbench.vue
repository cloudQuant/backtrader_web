<template>
  <section class="trusted-workbench" aria-labelledby="trusted-workbench-title" data-test="trusted-research-workbench">
    <header class="trusted-workbench__header">
      <div>
        <span>{{ t('strategy.aiResearchTrusted.protocol') }}</span>
        <h2 id="trusted-workbench-title">{{ t('strategy.aiResearchTrusted.title') }}</h2>
        <p>{{ t('strategy.aiResearchTrusted.subtitle') }}</p>
      </div>
      <div class="trusted-workbench__header-actions">
        <button type="button" :disabled="!runtime.activeRunId.value || runtime.loading.value" @click="refresh">{{ t('strategy.aiResearchTrusted.refreshEvidence') }}</button>
        <button
          v-if="runtime.draft.value === null && runtime.preparedRun.value === null"
          type="button"
          class="trusted-workbench__primary"
          data-test="trusted-research-create-draft"
          :disabled="!hasCompletePreregistration || runtime.submitting.value"
          @click="createDraft"
        >{{ t('strategy.aiResearchTrusted.createDraft') }}</button>
        <button
          v-else-if="runtime.preparedRun.value === null"
          type="button"
          class="trusted-workbench__primary"
          data-test="trusted-research-confirm-precheck"
          :disabled="!hasCompletePreregistration || runtime.submitting.value"
          @click="confirmAndPrepare"
        >{{ t('strategy.aiResearchTrusted.confirmAndPrecheck') }}</button>
        <button
          v-else-if="needsPrecheckRetry"
          type="button"
          class="trusted-workbench__primary"
          data-test="trusted-research-retry-precheck"
          :disabled="runtime.submitting.value"
          @click="retryPrecheck"
        >
          {{ t('strategy.aiResearchTrusted.retryPrecheck') }}
        </button>
        <button
          v-else
          type="button"
          class="trusted-workbench__primary"
          data-test="trusted-research-start-run"
          :disabled="!canStartPreparedRun || runtime.submitting.value"
          @click="startPreparedRun"
        >{{ t('strategy.aiResearchTrusted.startResearch') }}</button>
      </div>
    </header>

    <RunHistoryPanel
      :tasks="runtime.taskHistory.value"
      :selected-task-id="runtime.activeTaskId.value"
      :next-cursor="runtime.taskHistoryNextCursor.value"
      :loading="runtime.taskHistoryLoading.value"
      @select="selectHistoryTask"
      @refresh="refreshHistory"
      @load-more="loadMoreHistory"
    />

    <form class="trusted-workbench__form" @submit.prevent="createDraft">
      <label>{{ t('strategy.aiResearchTrusted.question') }}<input v-model.trim="form.question" required maxlength="500" :placeholder="t('strategy.aiResearchTrusted.questionPlaceholder')"></label>
      <label>{{ t('strategy.aiResearchTrusted.economicMechanism') }}<input v-model.trim="form.economicMechanism" required maxlength="500" :placeholder="t('strategy.aiResearchTrusted.economicMechanismPlaceholder')"></label>
      <label>{{ t('strategy.aiResearchTrusted.symbol') }}<input v-model.trim="form.symbol" required maxlength="50" placeholder="RB0"></label>
      <label>{{ t('strategy.aiResearchTrusted.frequency') }}<input v-model.trim="form.frequency" required maxlength="32" placeholder="1d"></label>
      <label>{{ t('strategy.aiResearchTrusted.startDate') }}<input v-model="form.startDate" required type="date"></label>
      <label>{{ t('strategy.aiResearchTrusted.endDate') }}<input v-model="form.endDate" required type="date"></label>
      <label>{{ t('strategy.aiResearchTrusted.informationCutoff') }}<input v-model="form.informationCutoff" required type="datetime-local"></label>
      <label>{{ t('strategy.aiResearchTrusted.slippageBps') }}<input v-model.number="form.slippageBps" required min="0" step="0.1" type="number"></label>
      <label>{{ t('strategy.aiResearchTrusted.maxParticipationRate') }}<input v-model.number="form.maxParticipationRate" required min="0.0001" max="1" step="0.01" type="number"></label>
      <label>{{ t('strategy.aiResearchTrusted.maxTrials') }}<input v-model.number="form.maxTrials" required min="1" step="1" type="number"></label>
      <label>
        {{ t('strategy.aiResearchTrusted.objectReceiptId') }}
        <input
          v-model.trim="form.objectReceiptId"
          required
          maxlength="256"
          data-test="trusted-research-object-receipt-id"
          :placeholder="t('strategy.aiResearchTrusted.objectReceiptPlaceholder')"
        >
        <small>{{ t('strategy.aiResearchTrusted.objectReceiptHelp') }}</small>
      </label>
      <label>{{ t('strategy.aiResearchTrusted.profileId') }}<input v-model.trim="form.profileId" required maxlength="128" data-test="trusted-research-profile-id"></label>
      <label>{{ t('strategy.aiResearchTrusted.profileVersion') }}<input v-model.trim="form.profileVersion" required maxlength="128" data-test="trusted-research-profile-version"></label>
    </form>

    <section
      v-if="runtime.draft.value !== null"
      class="trusted-workbench__draft"
      data-test="trusted-research-draft"
      aria-live="polite"
    >
      <div>
        <strong>{{ runtime.preparedRun.value ? t('strategy.aiResearchTrusted.precheckReady') : t('strategy.aiResearchTrusted.draftReady') }}</strong>
        <p>{{ runtime.preparedRun.value ? t('strategy.aiResearchTrusted.precheckReview') : t('strategy.aiResearchTrusted.draftReview') }}</p>
        <code>{{ runtime.draft.value.contentHash }}</code>
        <details class="trusted-workbench__frozen-payload">
          <summary>{{ t('strategy.aiResearchTrusted.frozenPayload') }}</summary>
          <pre data-test="trusted-research-canonical-payload">{{ draftPayload }}</pre>
        </details>
      </div>
      <button type="button" data-test="trusted-research-discard-draft" @click="runtime.invalidateDraft">
        {{ t('strategy.aiResearchTrusted.discardDraft') }}
      </button>
    </section>

    <section
      v-if="runtime.preparedRun.value !== null"
      class="trusted-workbench__precheck"
      data-test="trusted-research-precheck"
      aria-live="polite"
    >
      <div>
        <strong>{{ t('strategy.aiResearchTrusted.precheckStatus', { status: runtime.preparedRun.value.precheck.status }) }}</strong>
        <p>{{ t('strategy.aiResearchTrusted.precheckTiming', { checkedAt: runtime.preparedRun.value.precheck.checked_at, expiresAt: runtime.preparedRun.value.precheck.expires_at }) }}</p>
        <code>{{ runtime.preparedRun.value.precheck.input_hash }}</code>
        <p v-if="runtime.preparedRun.value.precheck.reason_code" class="trusted-workbench__precheck-reason">
          {{ runtime.preparedRun.value.precheck.reason_code }}
        </p>
      </div>
      <span class="trusted-workbench__status" :data-status="runtime.preparedRun.value.precheck.status">
        {{ runtime.preparedRun.value.precheck.status }}
      </span>
    </section>

    <p v-if="runtime.errorCode.value" class="trusted-workbench__error" role="alert">{{ errorMessage }}</p>
    <p v-if="runtime.submitting.value" class="trusted-workbench__busy" aria-live="polite">{{ t('strategy.aiResearchTrusted.submitting') }}</p>

    <div class="trusted-workbench__grid">
      <HypothesisPanel :hypothesis="runtime.workbench.value?.hypothesis" />
      <DataPanel :dataset="runtime.workbench.value?.dataset" />
      <CandidatePanel
        :candidates="runtime.workbench.value?.candidates"
        :active-candidate-id="runtime.activeCandidateId.value"
        :freezing-candidate-id="runtime.freezingCandidateId.value"
        :requesting-holdout-candidate-id="runtime.requestingHoldoutCandidateId.value"
        :holdout-commands="runtime.workbench.value?.holdout_commands"
        :run-id="runtime.workbench.value?.run.id"
        :run-experiment-epoch-id="runtime.workbench.value?.run.experiment_epoch_id"
        :run-dataset-snapshot-id="runtime.workbench.value?.run.dataset_snapshot_id"
        :dataset-snapshot-id="runtime.workbench.value?.dataset?.id"
        :dataset-content-hash="runtime.workbench.value?.dataset?.content_hash"
        @freeze="freezeCandidate"
        @request-holdout="requestHoldout"
      />
      <LedgerPanel :ledger="runtime.workbench.value?.ledger" />
      <EvidencePanel
        :evidence-class="runtime.workbench.value?.evidence_class || 'PROTOCOL_V2_NOT_STARTED'"
        :gates="runtime.workbench.value?.gates"
        :governance-decisions="runtime.workbench.value?.governance_decisions"
        :model-invocations="runtime.workbench.value?.model_invocations"
        :evidence-packages="runtime.workbench.value?.evidence_packages"
        :holdout-commands="runtime.workbench.value?.holdout_commands"
        :evaluations="runtime.workbench.value?.evaluations"
        :promotion-policy-version="runtime.workbench.value?.run.promotion_policy_version"
      />
      <ApprovalPanel
        :run-id="queryValue(route.query.run_id)"
        :candidate-id="queryValue(route.query.candidate_id)"
        :candidates="runtime.workbench.value?.candidates"
        @select-candidate="setApprovalCandidate"
      />
      <DecisionPanel :decisions="runtime.workbench.value?.decisions" :can-cancel="canCancel" @cancel="cancel" />
      <TaskEventTimeline
        :task-id="runtime.activeTaskId.value"
        :events="runtime.taskEvents.value"
        :loading="runtime.eventPolling.value"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAiResearchV2 } from '@/composables/useAiResearchV2'
import type { AiResearchV2Task } from '@/types/aiResearchV2'
import ApprovalPanel from './ApprovalPanel.vue'
import DataPanel from './DataPanel.vue'
import CandidatePanel from './CandidatePanel.vue'
import DecisionPanel from './DecisionPanel.vue'
import EvidencePanel from './EvidencePanel.vue'
import HypothesisPanel from './HypothesisPanel.vue'
import LedgerPanel from './LedgerPanel.vue'
import RunHistoryPanel from './RunHistoryPanel.vue'
import TaskEventTimeline from './TaskEventTimeline.vue'

const runtime = useAiResearchV2()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const form = reactive({
  question: '',
  economicMechanism: '',
  symbol: '',
  frequency: '1d',
  startDate: '2022-01-01',
  endDate: '2025-12-31',
  informationCutoff: '2026-01-01T00:00',
  slippageBps: 1,
  maxParticipationRate: 0.1,
  maxTrials: 20,
  objectReceiptId: '',
  profileId: 'dev-single-process',
  profileVersion: 'v1',
})

const canCancel = computed(() => {
  const status = runtime.workbench.value?.task?.status
  return Boolean(status && !['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(status))
})

const hasCompletePreregistration = computed(() => Boolean(
  form.question
  && form.economicMechanism
  && form.symbol
  && form.frequency
  && Number.isFinite(Date.parse(`${form.startDate}T00:00:00Z`))
  && Number.isFinite(Date.parse(`${form.endDate}T00:00:00Z`))
  && Date.parse(`${form.startDate}T00:00:00Z`) < Date.parse(`${form.endDate}T00:00:00Z`)
  && form.informationCutoff
  && Number.isFinite(Date.parse(form.informationCutoff))
  && Date.parse(form.informationCutoff) >= Date.parse(`${form.endDate}T00:00:00Z`)
  && Number.isFinite(form.slippageBps)
  && form.slippageBps >= 0
  && Number.isFinite(form.maxParticipationRate)
  && form.maxParticipationRate > 0
  && form.maxParticipationRate <= 1
  && Number.isInteger(form.maxTrials)
  && form.maxTrials > 0
  && form.objectReceiptId
  && form.profileId
  && form.profileVersion,
))

const canStartPreparedRun = computed(() => {
  const prepared = runtime.preparedRun.value
  return Boolean(prepared && prepared.precheck.status === 'PASS' && !runtime.precheckExpired.value)
})

const needsPrecheckRetry = computed(() => {
  const prepared = runtime.preparedRun.value
  return Boolean(prepared && (prepared.precheck.status !== 'PASS' || runtime.precheckExpired.value))
})

const draftPayload = computed(() => {
  const payload = runtime.draft.value?.payload
  return payload ? JSON.stringify(payload, null, 2) : ''
})

const errorMessage = computed(() => {
  const code = runtime.errorCode.value
  if (code === 'BLOCKED_TOPOLOGY_CAPABILITY') {
    return t('strategy.aiResearchTrusted.blockedTopology')
  }
  if (code === 'RESEARCH_TASK_CONFIRMATION_STALE') {
    return t('strategy.aiResearchTrusted.staleConfirmation')
  }
  if (code?.startsWith('RESEARCH_TASK_PRECHECK_') || code?.startsWith('RESEARCH_DATA_PRECHECK_')) {
    return t('strategy.aiResearchTrusted.stalePrecheck', { code })
  }
  if (code?.startsWith('RESEARCH_CANDIDATE_') || code === 'RESEARCH_V2_CANDIDATE_SELECTION_INVALID') {
    return t('strategy.aiResearchTrusted.candidate.freezeFailed', { code })
  }
  if (code?.includes('HOLDOUT')) {
    return t('strategy.aiResearchTrusted.candidate.holdoutFailed', { code })
  }
  return t('strategy.aiResearchTrusted.requestFailed', { code })
})

async function createDraft(): Promise<void> {
  if (!hasCompletePreregistration.value || runtime.submitting.value) return
  const created = await runtime.createDraft(hypothesisPayload())
  if (created !== null) await clearRouteSelection()
}

async function confirmAndPrepare(): Promise<void> {
  if (!hasCompletePreregistration.value || runtime.submitting.value) return
  const informationCutoff = new Date(form.informationCutoff).toISOString()
  await runtime.confirmDraftAndPrepare({
    hypothesisPayload: hypothesisPayload(),
    dataset: {
      dataset_policy_version: 'policy-v1',
      partition_kind: 'DISCOVERY',
      instrument_manifest: {
        symbols: [form.symbol],
        asset_class: 'futures',
        identity_scheme: 'exchange_symbol',
      },
      split_manifest: splitManifest(),
      source_manifest: {
        provider: 'controlled-research-source',
        frequency: form.frequency,
        timezone: 'Asia/Shanghai',
        adjustment_rule: 'continuous-contract-unadjusted',
        event_time_basis: 'bar_close',
        ingested_at: informationCutoff,
        as_of_at: informationCutoff,
        vintage: 'controlled-research-source-v1',
      },
      execution_policy: {
        fill: 'next_bar_open',
        commission_bps: 2,
        slippage_bps: form.slippageBps,
        volume_limit: form.maxParticipationRate,
        suspension: 'BLOCKED',
        price_limit: 'BLOCKED',
        market_impact: 'UNKNOWN',
      },
      point_in_time_cutoff: informationCutoff,
      object_receipt_id: form.objectReceiptId,
      license_tags: ['controlled-research-license'],
    },
    searchBudget: { max_trials: form.maxTrials },
    profileId: form.profileId,
    profileVersion: form.profileVersion,
    promotionPolicyVersion: 'promotion-v1',
    idempotencyKey: newIdempotencyKey(),
  })
}

async function startPreparedRun(): Promise<void> {
  const started = await runtime.startPreparedRun()
  if (started !== null) await setRouteSelection(started.run.id, started.task?.id ?? null)
}

async function retryPrecheck(): Promise<void> {
  await runtime.retryPreparedPrecheck()
}

function hypothesisPayload(): Record<string, unknown> {
  return {
    research_question: form.question,
    economic_mechanism: form.economicMechanism,
    asset_scope: { symbols: [form.symbol] },
    frequency: form.frequency,
    time_window: { start: form.startDate, end: form.endDate },
    information_cutoff: new Date(form.informationCutoff).toISOString(),
    cost_model: { commission_bps: 2.0, slippage_bps: form.slippageBps },
    execution_model: {
      fill: 'next_bar_open',
      commission_bps: 2.0,
      slippage_bps: form.slippageBps,
      volume_limit: form.maxParticipationRate,
      suspension: 'BLOCKED',
      price_limit: 'BLOCKED',
      market_impact: 'UNKNOWN',
    },
    primary_metric: 'deflated_sharpe',
    secondary_metrics: ['max_drawdown', 'turnover'],
    capacity_assumptions: { max_participation_rate: form.maxParticipationRate },
    falsification_criteria: { max_drawdown: 0.2 },
    search_space: { lookback: [10, 20] },
    max_budget: { max_trials: form.maxTrials },
    dataset_policy_version: 'policy-v1',
  }
}

function splitManifest(): Record<string, unknown> {
  const start = new Date(`${form.startDate}T00:00:00Z`)
  const end = new Date(`${form.endDate}T00:00:00Z`)
  const midpoint = new Date(start.getTime() + Math.floor((end.getTime() - start.getTime()) / 2))
  const validationStart = new Date(midpoint.getTime() + 24 * 60 * 60 * 1000)
  const datePart = (value: Date): string => value.toISOString().slice(0, 10)
  return {
    start: form.startDate,
    end: form.endDate,
    walk_forward: true,
    purge_bars: 5,
    embargo_bars: 5,
    folds: [{
      train_start: form.startDate,
      train_end: datePart(midpoint),
      validation_start: datePart(validationStart),
      validation_end: form.endDate,
    }],
  }
}

async function refresh(): Promise<void> {
  if (runtime.activeRunId.value) {
    await runtime.load(
      runtime.activeRunId.value,
      queryValue(route.query.task_id),
      queryValue(route.query.candidate_id),
    )
  }
}

async function cancel(): Promise<void> {
  await runtime.cancelCurrent()
}

async function freezeCandidate(
  candidateId: string,
  expectedCandidateHash: string,
  onSettled: (succeeded: boolean) => void,
): Promise<void> {
  let succeeded = false
  try {
    succeeded = await runtime.freezeCandidate(candidateId, expectedCandidateHash) !== null
  } finally {
    onSettled(succeeded)
  }
}

async function requestHoldout(
  candidateId: string,
  expectedCandidateHash: string,
): Promise<void> {
  await runtime.requestHoldout(candidateId, expectedCandidateHash)
}

async function refreshHistory(): Promise<void> {
  await runtime.loadTaskHistory()
}

async function loadMoreHistory(): Promise<void> {
  await runtime.loadMoreTaskHistory()
}

async function selectHistoryTask(task: AiResearchV2Task): Promise<void> {
  await router.replace({
    query: {
      ...route.query,
      run_id: task.run_id,
      task_id: task.id,
      candidate_id: undefined,
    },
  })
}

async function setApprovalCandidate(candidateId: string | null): Promise<void> {
  await router.replace({
    query: {
      ...route.query,
      candidate_id: candidateId ?? undefined,
    },
  })
}

async function setRouteSelection(runId: string, taskId: string | null): Promise<void> {
  lastRouteSelection = routeSelectionKey(runId, taskId, null)
  await router.replace({
    query: {
      ...route.query,
      run_id: runId,
      task_id: taskId ?? undefined,
      candidate_id: undefined,
    },
  })
}

async function clearRouteSelection(): Promise<void> {
  lastRouteSelection = routeSelectionKey(null, null, null)
  await router.replace({
    query: {
      ...route.query,
      run_id: undefined,
      task_id: undefined,
      candidate_id: undefined,
    },
  })
}

function queryValue(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized || null
}

let lastRouteSelection = ''

async function restoreRouteSelection(): Promise<void> {
  const runId = queryValue(route.query.run_id)
  const taskId = queryValue(route.query.task_id)
  const candidateId = queryValue(route.query.candidate_id)
  const selection = routeSelectionKey(runId, taskId, candidateId)
  if (selection === lastRouteSelection) return
  lastRouteSelection = selection
  if (runId === null) {
    runtime.resetSelection()
    return
  }
  await runtime.load(runId, taskId, candidateId)
}

function routeSelectionKey(
  runId: string | null,
  taskId: string | null,
  candidateId: string | null,
): string {
  return `${runId ?? ''}\u0000${taskId ?? ''}\u0000${candidateId ?? ''}`
}

function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() || `trusted-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

onMounted(() => {
  runtime.startTaskHistoryPolling()
})

watch(
  () => [route.query.run_id, route.query.task_id, route.query.candidate_id],
  () => {
    void restoreRouteSelection()
  },
  { immediate: true },
)

watch(
  () => [
    form.question,
    form.economicMechanism,
    form.symbol,
    form.frequency,
    form.startDate,
    form.endDate,
    form.informationCutoff,
    form.slippageBps,
    form.maxParticipationRate,
    form.maxTrials,
    form.objectReceiptId,
    form.profileId,
    form.profileVersion,
  ],
  () => runtime.invalidateDraft(),
)
</script>

<style scoped>
.trusted-workbench { display: grid; gap: 16px; margin-bottom: 20px; padding: 18px; border: 1px solid var(--primary-light-7); border-radius: 12px; background: linear-gradient(145deg, var(--fill-color-lighter), var(--bg-color)); }.trusted-workbench__header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }.trusted-workbench__header span { color: var(--primary-color); font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }.trusted-workbench__header h2 { margin: 4px 0; font-size: 20px; }.trusted-workbench__header p { max-width: 720px; margin: 0; color: var(--text-color-secondary); line-height: 1.5; }.trusted-workbench__header-actions { display: flex; flex-wrap: wrap; gap: 8px; }.trusted-workbench button { min-height: 34px; padding: 7px 11px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-color); color: var(--text-color-primary); cursor: pointer; }.trusted-workbench button:disabled { cursor: not-allowed; opacity: .55; }.trusted-workbench__primary { border-color: var(--primary-color) !important; background: var(--primary-color) !important; color: #fff !important; }.trusted-workbench__form { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }.trusted-workbench__form label { display: grid; gap: 5px; color: var(--text-color-secondary); font-size: 12px; }.trusted-workbench__form input { min-width: 0; padding: 7px 8px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-color); color: var(--text-color-primary); }.trusted-workbench__form label:first-child { grid-column: span 2; }.trusted-workbench__error { margin: 0; padding: 9px; border: 1px solid var(--danger-border-color); border-radius: 6px; color: var(--danger-text-color); }.trusted-workbench__busy { margin: 0; color: var(--primary-color); }.trusted-workbench__draft, .trusted-workbench__precheck { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid var(--warning-border-color); border-radius: 6px; background: var(--warning-fill-color-light); }.trusted-workbench__precheck { border-color: var(--primary-light-5); background: var(--fill-color-light); }.trusted-workbench__draft p, .trusted-workbench__precheck p { margin: 4px 0; color: var(--text-color-secondary); }.trusted-workbench__draft code, .trusted-workbench__precheck code { display: block; max-width: 100%; overflow-wrap: anywhere; font-size: 12px; }.trusted-workbench__frozen-payload { margin-top: 8px; }.trusted-workbench__frozen-payload summary { cursor: pointer; color: var(--primary-color); }.trusted-workbench__frozen-payload pre { max-height: 260px; margin: 8px 0 0; overflow: auto; padding: 8px; border-radius: 4px; background: var(--fill-color); color: var(--text-color-primary); font-size: 12px; white-space: pre-wrap; }.trusted-workbench__precheck-reason { color: var(--danger-text-color) !important; }.trusted-workbench__status { padding: 3px 8px; border: 1px solid var(--border-color); border-radius: 999px; font-size: 12px; font-weight: 700; }.trusted-workbench__status[data-status='PASS'] { color: var(--success-text-color); }.trusted-workbench__status[data-status='FAIL'], .trusted-workbench__status[data-status='BLOCKED'] { color: var(--danger-text-color); }.trusted-workbench__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.trusted-workbench__grid > :last-child { grid-column: 1 / -1; } @media (max-width: 1100px) { .trusted-workbench__form { grid-template-columns: repeat(3, minmax(0, 1fr)); }.trusted-workbench__form label:first-child { grid-column: span 1; } } @media (max-width: 720px) { .trusted-workbench__header { display: grid; }.trusted-workbench__form, .trusted-workbench__grid { grid-template-columns: 1fr; }.trusted-workbench__grid > :last-child { grid-column: auto; }.trusted-workbench__draft, .trusted-workbench__precheck { display: grid; } }
</style>
